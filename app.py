"""app.py
HackerNews-style frontend for CMS Policy & Rulemaking Watcher.

Features:
- Clean, minimal design like HN
- List of latest rules with upvote-style ranking
- Click-through to Federal Register documents
- Real-time updates from Federal Register API
- Comment system for internal team discussions
- Security: CSRF protection, rate limiting, input validation
"""
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from dotenv import load_dotenv
import bleach

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Security Configuration
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Security Headers
Talisman(app, 
    force_https=False,  # Set to True in production with HTTPS
    strict_transport_security=False,  # Enable in production
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",  # Needed for inline JS
        'style-src': "'self' 'unsafe-inline'",   # Needed for inline CSS
        'connect-src': "'self'",
        'img-src': "'self' data:",
        'font-src': "'self'",
    }
)

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Configuration
API_BASE = "https://www.federalregister.gov/api/v1/documents.json"
SUGGESTED_SEARCHES_URL = "https://www.federalregister.gov/api/v1/suggested_searches"
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# Simple in-memory storage (use database in production)
votes = {}  # document_id -> vote_count
comments = {}  # document_id -> [comment_list]

# Input validation patterns
DOCUMENT_ID_PATTERN = re.compile(r'^[0-9]{4}-[0-9]{5}$')
QUERY_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_\.]+$')

def validate_document_id(doc_id: str) -> bool:
    """Validate document ID format."""
    return bool(DOCUMENT_ID_PATTERN.match(doc_id)) if doc_id else False

def validate_query(query: str) -> bool:
    """Validate search query."""
    return bool(QUERY_PATTERN.match(query)) and len(query) <= 100 if query else False

def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS."""
    return bleach.clean(text, tags=[], attributes={}, strip=True)

def generate_csrf_token():
    """Generate CSRF token for forms."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']

def validate_csrf_token(token: str) -> bool:
    """Validate CSRF token."""
    return token and session.get('csrf_token') == token

@app.before_request
def before_request():
    """Security checks before each request."""
    # Generate CSRF token for session
    generate_csrf_token()

@app.context_processor
def inject_csrf_token():
    """Inject CSRF token into templates."""
    return dict(csrf_token=generate_csrf_token())

def fetch_fr_documents(query="medicare medicaid", per_page=30):
    """Fetch documents from Federal Register API."""
    if not validate_query(query):
        return []
        
    params = {
        "conditions[term]": query,
        "conditions[agency_ids]": 54,  # CMS
        "order": "newest",
        "per_page": min(per_page, 50),  # Limit to prevent abuse
        "page": 1,
    }
    
    try:
        resp = requests.get(
            API_BASE, 
            params=params, 
            headers={"User-Agent": "CMS-Rule-Watcher/1.0"}, 
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        app.logger.error(f"API Error: {e}")
        return []

def fetch_suggested_searches():
    """Get Medicare/Medicaid related suggested searches."""
    try:
        resp = requests.get(
            SUGGESTED_SEARCHES_URL, 
            headers={"User-Agent": "CMS-Rule-Watcher/1.0"}, 
            timeout=30
        )
        resp.raise_for_status()
        js = resp.json()
        
        # Find Medicare/Medicaid suggestions
        suggestions = []
        for category, items in js.items():
            for item in items:
                if any(keyword in item["title"].lower() for keyword in ["medicare", "medicaid", "health"]):
                    suggestions.append(item)
        return suggestions
    except Exception as e:
        app.logger.error(f"Suggested searches error: {e}")
        return []

def format_time_ago(date_str):
    """Convert date string to 'X days ago' format."""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        delta = datetime.now() - date
        
        if delta.days == 0:
            return "today"
        elif delta.days == 1:
            return "1 day ago"
        elif delta.days < 30:
            return f"{delta.days} days ago"
        elif delta.days < 365:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    except:
        return date_str

@app.route('/')
@limiter.limit("30 per minute")
def index():
    """Main page - HackerNews style list of rules."""
    documents = fetch_fr_documents()
    
    # Add vote counts and format dates
    for doc in documents:
        doc_id = doc.get("document_number", "")
        doc["vote_count"] = votes.get(doc_id, 0)
        doc["comment_count"] = len(comments.get(doc_id, []))
        doc["time_ago"] = format_time_ago(doc.get("publication_date", ""))
        
        # Extract agency names for display
        agencies = doc.get("agency_names", [])
        doc["agency_display"] = ", ".join(agencies[:2])  # Show first 2 agencies
        
        # Truncate title if too long
        title = doc.get("title", "")
        if len(title) > 120:
            doc["title_display"] = title[:120] + "..."
        else:
            doc["title_display"] = title
    
    # Sort by vote count (HN style) with recent bias
    def score_doc(doc):
        votes_score = doc["vote_count"]
        recency_bonus = 0
        try:
            date = datetime.strptime(doc.get("publication_date", ""), "%Y-%m-%d")
            days_old = (datetime.now() - date).days
            if days_old < 7:
                recency_bonus = (7 - days_old) * 2
        except:
            pass
        return votes_score + recency_bonus
    
    documents.sort(key=score_doc, reverse=True)
    
    return render_template('index.html', documents=documents)

@app.route('/vote', methods=['POST'])
@limiter.limit("10 per minute")
def vote():
    """Handle upvotes for documents."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request"}), 400
        
    data = request.get_json()
    csrf_token = data.get('csrf_token')
    doc_id = data.get('document_id')
    
    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Invalid CSRF token"}), 403
        
    if not validate_document_id(doc_id):
        return jsonify({"success": False, "error": "Invalid document ID"}), 400
    
    # Simple rate limiting per document per session
    voted_docs = session.get('voted_documents', set())
    if doc_id in voted_docs:
        return jsonify({"success": False, "error": "Already voted"}), 400
    
    votes[doc_id] = votes.get(doc_id, 0) + 1
    voted_docs.add(doc_id)
    session['voted_documents'] = voted_docs
    
    return jsonify({"success": True, "vote_count": votes[doc_id]})

@app.route('/document/<document_id>')
def document_detail(document_id):
    """Document detail page with comments."""
    if not validate_document_id(document_id):
        return "Invalid document ID", 400
        
    # In a real app, you'd fetch the specific document
    # For now, redirect to Federal Register
    return redirect(f"https://www.federalregister.gov/documents/{document_id}")

@app.route('/comment', methods=['POST'])
@limiter.limit("5 per minute")
def add_comment():
    """Add comment to a document."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request"}), 400
        
    data = request.get_json()
    csrf_token = data.get('csrf_token')
    doc_id = data.get('document_id')
    comment_text = sanitize_input(data.get('comment', '').strip())
    author = sanitize_input(data.get('author', 'Anonymous').strip())
    
    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Invalid CSRF token"}), 403
        
    if not validate_document_id(doc_id):
        return jsonify({"success": False, "error": "Invalid document ID"}), 400
        
    if not comment_text or len(comment_text) > 1000:
        return jsonify({"success": False, "error": "Invalid comment"}), 400
        
    if len(author) > 50:
        return jsonify({"success": False, "error": "Author name too long"}), 400
    
    if doc_id not in comments:
        comments[doc_id] = []
    
    comment = {
        "author": author,
        "text": comment_text,
        "timestamp": datetime.now().isoformat(),
        "time_ago": "just now"
    }
    comments[doc_id].append(comment)
    
    return jsonify({"success": True, "comment_count": len(comments[doc_id])})

@app.route('/api/documents')
@limiter.limit("20 per minute")
def api_documents():
    """API endpoint for documents (for AJAX updates)."""
    query = request.args.get('q', 'medicare medicaid')
    if not validate_query(query):
        return jsonify({"error": "Invalid query"}), 400
        
    documents = fetch_fr_documents(query)
    return jsonify(documents)

@app.route('/searches')
@limiter.limit("10 per minute")
def suggested_searches():
    """Page showing suggested search categories."""
    searches = fetch_suggested_searches()
    return render_template('searches.html', searches=searches)

@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded."""
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors."""
    app.logger.error(f"Internal error: {e}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Use environment variables for configuration
    debug = os.getenv('FLASK_ENV') != 'production'
    port = int(os.getenv('PORT', 8080))
    host = os.getenv('HOST', '127.0.0.1')  # More secure default
    
    app.run(debug=debug, host=host, port=port) 