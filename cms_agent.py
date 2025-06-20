"""cms_agent.py
Policy & Rulemaking Watcher Agent powered by OpenAI Assistant API.

Responsibilities
---------------
1. Poll CMS / Federal Register RSS feeds for high-impact rulemakings (IPPS, OPPS, PFS, MA/Part D etc.).
2. Detect new or updated documents, compute semantic diff against prior version, and extract key numeric impacts (e.g., RVU %, wage index shifts).
3. Summarize changes and automatically tag internal owners before routing the summary downstream (e.g., Slack, email).

Quick-start
-----------
1. Set environment variable `OPENAI_API_KEY`.
2. Optional: set `WATCH_PATH` (default: ./watch_state) to store previous fetch history.
3. Run: `python cms_agent.py run` to fetch updates once, or `python cms_agent.py daemon --interval 3600`.

Note: The script uses the new OpenAI Assistant (agents) framework. We register an Assistant, expose local tools (functions) it can invoke, then let the Assistant decide how to orchestrate them.  
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import feedparser
import openai
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

# --------------- CONFIG ---------------

# Key CMS/Federal Register RSS feeds to monitor
RSS_FEEDS: Dict[str, str] = {
    "ipps": "https://www.federalregister.gov/reader-aids/office-of-the-federal-register-announcements.rss",
    "opps": "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=Outpatient+Prospective+Payment+System&conditions%5Bagencies%5D%5B%5D=centers-for-medicare-and-medicaid-services",
    "pfs": "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=Physician+Fee+Schedule&conditions%5Bagencies%5D%5B%5D=centers-for-medicare-and-medicaid-services",
    "ma_pd": "https://www.federalregister.gov/documents/search.rss?conditions%5Bterm%5D=Medicare+Advantage+and+Part+D&conditions%5Bagencies%5D%5B%5D=centers-for-medicare-and-medicaid-services",
}

# Simple owner routing based on keyword mapping (can externalize to YAML)
OWNER_MAP: Dict[str, str] = {
    "hospital": "inpatient_team@company.com",
    "wage index": "finance@company.com",
    "rvu": "physician_revenue@company.com",
    "quality": "quality_measures@company.com",
    "star ratings": "ma_star_team@company.com",
}

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o")
WATCH_PATH = Path(os.getenv("WATCH_PATH", "watch_state"))
WATCH_PATH.mkdir(exist_ok=True, parents=True)

console = Console()

load_dotenv()  # load variables from .env if present

# Healthcare-related agencies from Federal Register API schemas
HEALTHCARE_AGENCIES = [
    "centers-for-medicare-medicaid-services",  # CMS - primary target
    "centers-for-disease-control-and-prevention",  # CDC
    "food-and-drug-administration",  # FDA
    "health-and-human-services-department",  # HHS
    "national-institutes-of-health",  # NIH
    "agency-for-healthcare-research-and-quality",  # AHRQ
    "health-resources-and-services-administration",  # HRSA
    "indian-health-service",  # IHS
    "substance-abuse-and-mental-health-services-administration",  # SAMHSA
    "medicare-payment-advisory-commission",  # MedPAC
    "reagan-udall-foundation-for-the-food-and-drug-administration",  # Reagan-Udall Foundation
]

# Configuration
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"

# --------------- Helper functions ---------------

def slugify(text: str) -> str:
    return (
        "".join(c.lower() if c.isalnum() else "-" for c in text)  # noqa: E501
        .strip("-")
        .replace("--", "-")
    )


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_html(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


# --------------- State persistence ---------------

def load_entry_state(feed_key: str, entry_id: str) -> Tuple[str, str]:
    """Return (hash, text) previous content or ("", "") if none."""
    f = WATCH_PATH / f"{feed_key}_{slugify(entry_id)}.json"
    if f.exists():
        data = json.loads(f.read_text())
        return data.get("hash", ""), data.get("text", "")
    return "", ""


def save_entry_state(feed_key: str, entry_id: str, content_hash: str, text: str):
    f = WATCH_PATH / f"{feed_key}_{slugify(entry_id)}.json"
    f.write_text(json.dumps({"hash": content_hash, "text": text}))


# --------------- Diff & summarization ---------------

def diff_text(old: str, new: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", n=3, fromfile="old", tofile="new"
    )
    return "\n".join(diff)


def summarize_with_openai(text: str, max_tokens: int = 300) -> str:
    prompt = (
        "You are a healthcare policy analyst. Summarize the following CMS rule change diff in concise bullet "
        "points, highlighting numeric impacts (e.g., RVU %, wage index shifts), timelines, and any new compliance "
        "guardrails. Use layperson language where possible.\n\n" + text
    )
    resp = openai.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


# --------------- Owner routing ---------------

def detect_owners(summary: str) -> List[str]:
    owners = set()
    lowered = summary.lower()
    for keyword, owner in OWNER_MAP.items():
        if keyword in lowered:
            owners.add(owner)
    return sorted(owners)


# --------------- Feed processing ---------------

def process_feed(feed_key: str, feed_url: str) -> List[Dict]:
    """Return list of update dicts for new/changed entries."""
    updates: List[Dict] = []
    parsed = feedparser.parse(feed_url)
    for entry in parsed.entries:
        entry_id = entry.get("id") or entry.get("link")
        published = dtparser.parse(entry.get("published", datetime.utcnow().isoformat()))
        

            
        link = entry.get("link")

        try:
            html = fetch_html(link)
            text = extract_plain_text(html)
        except Exception as exc:
            console.print(f"[red]Failed to fetch {link}: {exc}")
            continue

        new_hash = hash_text(text)
        old_hash, old_text = load_entry_state(feed_key, entry_id)
        if new_hash == old_hash:
            # no change
            continue

        diff = diff_text(old_text, text) if old_text else text[:4000]  # if first time, just snapshot
        summary = summarize_with_openai(diff)
        owners = detect_owners(summary)

        update = {
            "feed": feed_key,
            "title": entry.get("title", ""),
            "link": link,
            "published": published.isoformat(),
            "summary": summary,
            "owners": owners,
        }
        updates.append(update)

        # persist new state
        save_entry_state(feed_key, entry_id, new_hash, text)

    return updates


# --------------- OpenAI Assistant setup ---------------

def ensure_assistant() -> str:
    """Create the Assistant once and cache its id on disk."""
    cache_file = WATCH_PATH / "assistant_id.txt"
    if cache_file.exists():
        return cache_file.read_text().strip()

    client = openai
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_rule_updates",
                "description": "Fetch latest CMS rulemaking updates and diff summaries.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    ]

    assistant = client.beta.assistants.create(
        name="CMS Policy & Rulemaking Watcher",
        instructions=(
            "You are an expert healthcare compliance agent."
            " Call `list_rule_updates` to obtain recent CMS rulemaking changes, then craft actionable digests for compliance leads."
        ),
        model=MODEL_NAME,
        tools=tools,
    )
    cache_file.write_text(assistant.id)
    return assistant.id


# --------------- Tool handler ---------------

def list_rule_updates() -> List[Dict]:
    all_updates: List[Dict] = []
    for key, url in RSS_FEEDS.items():
        console.print(f"[cyan]Processing feed {key}...")
        updates = process_feed(key, url)
        all_updates.extend(updates)
    return all_updates


# --------------- CLI ---------------

def run_once():
    updates = list_rule_updates()
    if not updates:
        console.print("[green]No new updates.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Feed")
    table.add_column("Title")
    table.add_column("Owners")
    table.add_column("Summary", overflow="fold")

    for upd in updates:
        table.add_row(upd["feed"], upd["title"], ", ".join(upd["owners"]), upd["summary"][:120] + "…")

    console.print(table)


def daemon(interval: int):
    while True:
        console.rule(f"Polling at {datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
        try:
            run_once()
        except Exception as exc:
            console.print(f"[red]Error during run: {exc}")
        time.sleep(interval)


def fetch_federal_register_documents():
    """Fetch recent documents from Federal Register API for healthcare agencies."""
    try:
        params = {
            "conditions[term]": "medicare medicaid healthcare health insurance medical hospital physician",
            "order": "newest",
            "per_page": 50,
            "page": 1
        }
        
        # Add multiple healthcare agency filters
        for i, agency in enumerate(HEALTHCARE_AGENCIES):
            params[f"conditions[agencies][{i}]"] = agency
        
        response = requests.get(
            FEDERAL_REGISTER_API,
            params=params,
            headers={"User-Agent": "CMS-Agent/1.0"},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        documents = []
        
        for doc in data.get("results", []):
            documents.append({
                "id": doc.get("document_number"),
                "title": doc.get("title"),
                "summary": doc.get("abstract", ""),
                "url": doc.get("html_url"),
                "published": doc.get("publication_date"),
                "agencies": doc.get("agency_names", []),
                "type": doc.get("type")
            })
        
        return documents
        
    except Exception as e:
        print(f"Error fetching Federal Register documents: {e}")
        return []


if __name__ == "__main__":
    print("🏥 CMS Rulemaking Watcher Agent")
    print("=" * 50)
    
    # Fetch documents from Federal Register API
    print("📡 Fetching healthcare documents from Federal Register API...")
    documents = fetch_federal_register_documents()
    
    if not documents:
        print("❌ No documents found or API error")
        exit(1)
    
    print(f"📄 Found {len(documents)} healthcare documents")
    
    # Process each document
    for doc in documents:
        print(f"\n🔍 Processing: {doc['title'][:80]}...")
        
        # Check if document is relevant to our rule types
        title_lower = doc['title'].lower()
        summary_lower = doc['summary'].lower()
        
        relevant_keywords = [
            'ipps', 'inpatient prospective payment',
            'opps', 'outpatient prospective payment', 
            'physician fee schedule', 'pfs',
            'medicare advantage', 'part d'
        ]
        
        is_relevant = any(keyword in title_lower or keyword in summary_lower 
                         for keyword in relevant_keywords)
        
        if is_relevant:
            # Determine owner based on content
            owner = determine_owner(doc['title'], doc['summary'])
            
            # Check for changes (simplified for demo)
            doc_id = doc['id']
            current_content = f"{doc['title']}\n{doc['summary']}"
            
            if doc_id in document_cache:
                previous_content = document_cache[doc_id]
                if current_content != previous_content:
                    print(f"📝 Document updated: {doc['title'][:60]}...")
                    print(f"👤 Owner: {owner}")
                    
                    # Generate summary using OpenAI
                    summary = generate_summary(previous_content, current_content)
                    print(f"📋 Summary: {summary}")
                    
                    # Update cache
                    document_cache[doc_id] = current_content
                else:
                    print(f"✅ No changes detected")
            else:
                print(f"🆕 New document: {doc['title'][:60]}...")
                print(f"👤 Owner: {owner}")
                document_cache[doc_id] = current_content
        else:
            print(f"⏭️  Skipping non-relevant document")
    
    print(f"\n✅ Processed {len(documents)} documents")
    print("🔄 Run this script periodically to monitor for changes") 