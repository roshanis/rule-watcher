import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import difflib
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from rich.console import Console
from rich.table import Table


# -----------------------------
# Configuration
# -----------------------------

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

# Healthcare-related topics from Federal Register API schemas
HEALTHCARE_TOPICS = [
    "medicare", "medicaid", "health-care", "medical-devices", "hospitals", 
    "health-insurance", "health-maintenance-organizations-hmo", "health-professions",
    "health-records", "health-statistics", "heart-diseases", "hospice-care",
    "medical-dental-schools", "medical-assistance-program", "medical-research",
    "mental-health-programs", "nursing-homes", "prescription-drugs", "public-health",
    "health-facilities", "emergency-medical-services", "communicable-diseases",
    "immunization", "dental-health", "maternal-child-health", "drug-abuse",
    "drug-testing", "drug-traffic-control", "drugs", "biologics", "blood-diseases",
    "cancer", "genetic-diseases", "hiv-aids", "kidney-diseases", "lung-diseases",
    "tuberculosis", "venereal-diseases", "over-counter-drugs", "peer-review-organizations-pro"
]

# Healthcare-related suggested searches from Federal Register API schemas  
HEALTHCARE_SUGGESTED_SEARCHES = [
    "accountable-care-organizations", "clinical-laboratory-improvement-program",
    "continuation-of-health-benefits-cobra-", "electronic-health-information-technology",
    "health-and-human-services-grants-funding", "health-care-reform",
    "meaningful-use-of-electronic-health-records", "medical-devices",
    "medical-privacy-hipaa-", "medicare-medicaid-and-schip-payments"
]

# Feeds that frequently publish Medicare payment rules / notices.
# Users can extend or override with a local feeds.json file.
# RSS feeds disabled – focusing on Federal Register API instead.
DEFAULT_FEED_URLS: List[str] = []

# Keywords to watch and the internal owner to tag.
OWNER_KEYWORDS = {
    "IPPS": "Hospital Inpatient Payment Team",
    "Inpatient Prospective Payment": "Hospital Inpatient Payment Team",
    "OPPS": "Hospital Outpatient Payment Team",
    "Outpatient Prospective Payment": "Hospital Outpatient Payment Team",
    "Physician Fee Schedule": "Physician Payment Team",
    "PFS": "Physician Payment Team",
    "Medicare Advantage": "MA/Part D Team",
    "Part D": "MA/Part D Team",
}

# Directory where previous article snapshots are stored.
STATE_DIR = Path(".policy_watcher_state")
STATE_DIR.mkdir(exist_ok=True)

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("policy_watcher")
console = Console()

API_BASE = "https://www.federalregister.gov/api/v1/documents.json"
SEARCH_QUERY = "medicare medicaid healthcare health insurance medical hospital physician"
CMS_AGENCY_ID = 54  # Centers for Medicare & Medicaid Services

SUGGESTED_SEARCHES_URL = "https://www.federalregister.gov/api/v1/suggested_searches"
SUGGESTED_KEYWORDS = HEALTHCARE_SUGGESTED_SEARCHES


# -----------------------------
# Utility functions
# -----------------------------

def clean_html(html: str) -> str:
    """Return plain-text from HTML."""
    if html is None:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception as e:
        logger.warning(f"Error parsing HTML: {e}")
        return str(html) if html else ""


def extract_numbers(text: str) -> List[str]:
    """Extract numbers, percents, and monetary values from text."""
    pattern = re.compile(r"[+-]?\d+(?:\.\d+)?%?\$?")
    return pattern.findall(text)


def summarize_changes(old: str, new: str) -> Tuple[str, List[str]]:
    """Create a unified diff between old and new text and highlight numeric deltas."""
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", n=2, fromfile="previous", tofile="current"
    )
    diff_text = "\n".join(diff)

    # Identify numeric changes.
    old_nums = set(extract_numbers(old))
    new_nums = set(extract_numbers(new))
    added = new_nums - old_nums
    removed = old_nums - new_nums
    numeric_summary = []
    if added:
        numeric_summary.append(f"Added numbers: {', '.join(sorted(added))}")
    if removed:
        numeric_summary.append(f"Removed numbers: {', '.join(sorted(removed))}")
    return diff_text, numeric_summary


def detect_owner(title: str) -> str:
    for keyword, owner in OWNER_KEYWORDS.items():
        if keyword.lower() in title.lower():
            return owner
    return "(unassigned)"


def save_snapshot(item_id: str, content: str):
    """Save content snapshot atomically."""
    if not item_id:
        logger.warning("Empty item_id provided to save_snapshot")
        return
    
    try:
        path = STATE_DIR / f"{item_id}.txt"
        temp_path = path.with_suffix('.tmp')
        
        # Write to temporary file first, then rename (atomic operation)
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(path)
    except Exception as e:
        logger.error(f"Error saving snapshot for {item_id}: {e}")


def load_snapshot(item_id: str) -> str:
    """Load content snapshot with error handling."""
    if not item_id:
        return ""
    
    try:
        path = STATE_DIR / f"{item_id}.txt"
        if path.exists():
            return path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"Error loading snapshot for {item_id}: {e}")
    
    return ""


# -----------------------------
# Fetching
# -----------------------------

def fetch_feed(url: str):
    """Parse an RSS feed; gracefully handle errors."""
    try:
        parsed = feedparser.parse(url)
        if parsed.bozo:
            logger.warning("Feed parse issue for %s: %s", url, parsed.bozo_exception)
        return parsed.entries
    except Exception as exc:
        logger.error("Failed fetching %s: %s", url, exc)
        return []


def fetch_all_entries(feed_urls: List[str]):
    for feed_url in feed_urls:
        logger.info("Fetching feed: %s", feed_url)
        for entry in fetch_feed(feed_url):
            yield entry


def fetch_fr_search_entries(query: str = SEARCH_QUERY, agencies: List[str] = None, per_page: int = 20):
    """Yield document dicts from Federal Register API matching query/agencies."""
    if agencies is None:
        agencies = HEALTHCARE_AGENCIES
    
    params = {
        "conditions[term]": query,
        "order": "newest",
        "per_page": per_page,
        "page": 1,
    }
    
    # Add multiple agency filters
    for i, agency in enumerate(agencies):
        params[f"conditions[agencies][{i}]"] = agency
    
    try:
        resp = requests.get(API_BASE, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        for doc in resp.json().get("results", []):
            yield {
                "id": doc.get("document_number"),
                "title": doc.get("title"),
                "published": doc.get("publication_date"),
                "link": doc.get("html_url"),
                "summary": doc.get("abstract", ""),
            }
    except Exception as exc:
        logger.error("Federal Register API error: %s", exc)


def fetch_fr_topic_entries(topics: List[str] = None, per_page: int = 20):
    """Yield document dicts from Federal Register API matching healthcare topics."""
    if topics is None:
        topics = HEALTHCARE_TOPICS[:10]  # Use first 10 topics to avoid too many params
    
    params = {
        "order": "newest",
        "per_page": per_page,
        "page": 1,
    }
    
    # Add multiple topic filters
    for i, topic in enumerate(topics):
        params[f"conditions[topics][{i}]"] = topic
    
    try:
        resp = requests.get(API_BASE, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        for doc in resp.json().get("results", []):
            yield {
                "id": doc.get("document_number"),
                "title": doc.get("title"),
                "published": doc.get("publication_date"),
                "link": doc.get("html_url"),
                "summary": doc.get("abstract", ""),
            }
    except Exception as exc:
        logger.error("Federal Register API topic search error: %s", exc)


def build_fr_params(search_conditions: Dict) -> Dict:
    """Convert a suggested_searches search_conditions dict into FR API params."""
    params = {
        "order": "newest", 
        "per_page": 20, 
        "page": 1
    }
    for key, value in search_conditions.items():
        if key == "term":
            params["conditions[term]"] = value
        elif key == "agency_ids":
            # list of ints
            params.update({f"conditions[agency_ids][{i}]": aid for i, aid in enumerate(value)})
        elif key == "near":
            # {'within': '25'} -> conditions[near][within]=25
            for near_key, near_val in value.items():
                params[f"conditions[near][{near_key}]"] = near_val
        else:
            # generic catch-all
            params[f"conditions[{key}]"] = value
    return params


def fetch_fr_suggested_entries(keywords=None):
    """Yield FR documents for suggested searches whose title matches given keywords."""
    if keywords is None:
        keywords = HEALTHCARE_SUGGESTED_SEARCHES
    
    try:
        js = requests.get(SUGGESTED_SEARCHES_URL, timeout=30).json()
        # Flatten suggestions
        suggestions = [item for cat in js.values() for item in cat]
        matched = [s for s in suggestions if any(k.lower() in s["title"].lower() for k in keywords)]
        if not matched:
            logger.warning("No suggested searches matched keywords %s", keywords)
        for sug in matched:
            params = build_fr_params(sug.get("search_conditions", {}))
            try:
                resp = requests.get(API_BASE, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                resp.raise_for_status()
                for doc in resp.json().get("results", []):
                    yield {
                        "id": doc.get("document_number"),
                        "title": doc.get("title"),
                        "published": doc.get("publication_date"),
                        "link": doc.get("html_url"),
                        "summary": doc.get("abstract", ""),
                    }
            except Exception as exc:
                logger.error("FR API error for suggested search %s: %s", sug.get("title"), exc)
    except Exception as exc:
        logger.error("Failed fetching suggested searches: %s", exc)


# -----------------------------
# Core processing
# -----------------------------

def process_entry(entry: Dict):
    entry_id = entry.get("id") or entry.get("link")
    title = entry.get("title", "(no title)")
    published = entry.get("published") or entry.get("updated")
    published_dt = None
    if published:
        try:
            published_dt = date_parser.parse(published)
        except Exception:
            published_dt = datetime.now(timezone.utc)
    
    summary_html = entry.get("summary", "") or ""
    content_html = entry.get("content", [{"value": summary_html}])
    
    # Handle different content structures safely
    if isinstance(content_html, list) and content_html:
        content_value = content_html[0].get("value", "") if isinstance(content_html[0], dict) else str(content_html[0])
    else:
        content_value = str(content_html) if content_html else summary_html
    
    text = clean_html(content_value)

    owner = detect_owner(title)

    # Compare with previous snapshot
    previous_text = load_snapshot(entry_id)
    if not previous_text:
        save_snapshot(entry_id, text)
        logger.info("[NEW] %s", title)
        notify_new(title, entry.get("link"), text, owner, published_dt)
    elif text != previous_text:
        diff_text, numeric_changes = summarize_changes(previous_text, text)
        save_snapshot(entry_id, text)
        logger.info("[UPDATED] %s", title)
        notify_update(title, entry.get("link"), diff_text, numeric_changes, owner, published_dt)
    else:
        logger.debug("No changes for %s", title)


# -----------------------------
# Notification (stdout for PoC)
# -----------------------------

def notify_new(title: str, link: str, text: str, owner: str, published_dt: datetime):
    table = Table(title="CMS Rulemaking – NEW", show_lines=True)
    table.add_column("Field")
    table.add_column("Value", style="cyan")
    table.add_row("Title", title)
    table.add_row("Link", link)
    table.add_row("Owner", owner)
    if published_dt:
        table.add_row("Published", published_dt.strftime("%Y-%m-%d %H:%M"))
    table.add_row("Preview", text[:600] + ("..." if len(text) > 600 else ""))
    console.print(table)


def notify_update(
    title: str,
    link: str,
    diff_text: str,
    numeric_changes: List[str],
    owner: str,
    published_dt: datetime,
):
    table = Table(title="CMS Rulemaking – UPDATED", show_lines=True)
    table.add_column("Field")
    table.add_column("Value", style="magenta")
    table.add_row("Title", title)
    table.add_row("Link", link)
    table.add_row("Owner", owner)
    if published_dt:
        table.add_row("Published", published_dt.strftime("%Y-%m-%d %H:%M"))
    table.add_row("Numeric changes", "; ".join(numeric_changes) if numeric_changes else "None")
    table.add_row("Diff", diff_text[:2000] + ("..." if len(diff_text) > 2000 else ""))
    console.print(table)


# -----------------------------
# CLI entry-point
# -----------------------------

def main():
    # Allow custom feeds via feeds.json
    feeds_path = Path("feeds.json")
    if feeds_path.exists():
        feed_urls = json.loads(feeds_path.read_text())
        logger.info("Loaded %d custom feeds from feeds.json", len(feed_urls))
    else:
        feed_urls = DEFAULT_FEED_URLS

    # RSS processing skipped (list empty)

    # Healthcare agency search
    logger.info("Fetching documents from healthcare agencies...")
    for entry in fetch_fr_search_entries():
        try:
            process_entry(entry)
        except Exception as exc:
            logger.exception("Error processing FR agency entry: %s", exc)

    # Healthcare topic search
    logger.info("Fetching documents by healthcare topics...")
    for entry in fetch_fr_topic_entries():
        try:
            process_entry(entry)
        except Exception as exc:
            logger.exception("Error processing FR topic entry: %s", exc)

    # Healthcare suggested searches
    logger.info("Fetching documents from healthcare suggested searches...")
    for entry in fetch_fr_suggested_entries():
        try:
            process_entry(entry)
        except Exception as exc:
            logger.exception("Error processing suggested FR entry: %s", exc)


if __name__ == "__main__":
    main() 