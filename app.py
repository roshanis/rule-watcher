"""app.py
HackerNews-style frontend for Keywatch – CMS Policy & Rulemaking Watcher.

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
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import ai_storage
import storage
import paper_fetcher
from utils import normalize_doc_id

# Basic imports first
try:
    import requests
except ImportError as e:
    logging.error(f"Failed to import requests: {e}")
    raise

try:
    from flask import Flask, render_template, request, jsonify, redirect, url_for, session
except ImportError as e:
    logging.error(f"Failed to import Flask components: {e}")
    raise

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logging.warning("python-dotenv not available, skipping .env file loading")

try:
    import bleach
except ImportError as e:
    logging.error(f"Failed to import bleach: {e}")
    raise

# Optional imports with fallbacks
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    logging.warning("Flask-Limiter not available, rate limiting disabled")


class NoOpLimiter:
    """Fallback limiter when Flask-Limiter is unavailable."""

    def limit(self, *args, **kwargs):
        def decorator(f):
            return f

        return decorator

try:
    from flask_talisman import Talisman
    TALISMAN_AVAILABLE = True
except ImportError:
    TALISMAN_AVAILABLE = False
    logging.warning("Flask-Talisman not available, security headers will be limited")

app = Flask(__name__)

# Configure logging for serverless
if not app.debug:
    logging.basicConfig(level=logging.INFO)

# Security Configuration
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
is_production = os.getenv('FLASK_ENV') == 'production'

# Session configuration - adjust for serverless
app.config['SESSION_COOKIE_SECURE'] = is_production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024  # 1MB max request size

# Security Headers - only if Talisman is available
if TALISMAN_AVAILABLE:
    try:
        Talisman(app, 
            force_https=is_production,
            strict_transport_security=is_production,
            strict_transport_security_max_age=31536000 if is_production else None,
            content_security_policy={
                'default-src': "'self'",
                'script-src': "'self'",
                'style-src': "'self'",
                'connect-src': "'self'",
                'img-src': "'self' data:",
                'font-src': "'self'",
                'frame-ancestors': "'none'",
            },
            referrer_policy='strict-origin-when-cross-origin',
            feature_policy={
                'geolocation': "'none'",
                'camera': "'none'",
                'microphone': "'none'",
            }
        )
    except Exception as e:
        logging.error(f"Failed to configure Talisman: {e}")

# Rate Limiting - use memory storage for serverless (will reset on cold starts)
if LIMITER_AVAILABLE:
    try:
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri="memory://"  # Use memory storage for serverless
        )
    except Exception as e:
        logging.error(f"Failed to initialize rate limiter: {e}")
        limiter = NoOpLimiter()
else:
    limiter = NoOpLimiter()

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
API_BASE = "https://www.federalregister.gov/api/v1/documents.json"
SUGGESTED_SEARCHES_URL = "https://www.federalregister.gov/api/v1/suggested_searches"

# Use /tmp for cache in serverless environments, local cache otherwise
if os.getenv('VERCEL') or os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
    CACHE_DIR = Path("/tmp/cache")
else:
    CACHE_DIR = Path("cache")

# Try to create cache directory, but don't fail if we can't
try:
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
except (OSError, PermissionError) as e:
    logging.warning(f"Could not create cache directory {CACHE_DIR}: {e}")
    # Use a temporary directory as fallback
    import tempfile
    CACHE_DIR = Path(tempfile.gettempdir()) / "cms_cache"
    try:
        CACHE_DIR.mkdir(exist_ok=True, parents=True)
    except Exception:
        logging.warning("Cache directory unavailable, caching disabled")

# Persistent vote token per session
def get_vote_token() -> str:
    token = session.get('vote_token')
    if not token:
        token = secrets.token_hex(16)
        session['vote_token'] = token
    return token

# Input validation patterns
DOCUMENT_ID_PATTERN = re.compile(r'^[0-9]{4}-[0-9]{5}$|^[A-Za-z0-9_\-]+$')  # Support both formats
QUERY_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_\.]+$')

def validate_document_id(doc_id: str) -> bool:
    """Validate document ID format."""
    if not doc_id or len(doc_id) > 50:
        return False
    return bool(DOCUMENT_ID_PATTERN.match(doc_id))

def validate_query(query: str) -> bool:
    """Validate search query."""
    if not query:
        return False
    return bool(QUERY_PATTERN.match(query)) and 3 <= len(query) <= 100

def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS."""
    if not text:
        return ""
    return bleach.clean(text, tags=[], attributes={}, strip=True)[:1000]  # Limit length


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

def fetch_documents(query="medicare medicaid healthcare", per_page=20):
    """Fetch documents from Federal Register API with healthcare agency filters"""
    try:
        params = {
            "conditions[term]": query,
            "order": "newest",
            "per_page": min(per_page, 50),  # Limit to prevent abuse
            "page": 1
        }
        
        # Add multiple healthcare agency filters
        for i, agency in enumerate(HEALTHCARE_AGENCIES):
            params[f"conditions[agencies][{i}]"] = agency
        
        response = requests.get(API_BASE, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        documents = []
        
        for doc in data.get("results", []):
            # Handle None values safely
            abstract = doc.get("abstract") or ""
            title = doc.get("title") or "Untitled Document"
            agency_names = doc.get("agency_names") or []
            
            documents.append({
                "id": doc.get("document_number", ""),
                "title": title,
                "summary": abstract[:500] + "..." if len(abstract) > 500 else abstract,
                "url": doc.get("html_url", ""),
                "date": doc.get("publication_date", ""),
                "agency": ", ".join(agency_names) if agency_names else "Unknown Agency",
                "type": doc.get("type", ""),
                "up_votes": 0,
                "down_votes": 0,
                "score": 0,
                "comments": []  # Default empty comments
            })
        
        return documents
    except Exception as e:
        app.logger.error(f"Error fetching documents: {e}")
        print(f"Error fetching documents: {e}")
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


def collect_search_documents():
    """Aggregate documents from multiple sources for search."""
    documents = []

    for doc in fetch_documents():
        doc_id = normalize_doc_id(doc.get("id"))
        documents.append({
            "id": doc_id,
            "title": doc.get("title", ""),
            "summary": doc.get("summary", ""),
            "url": doc.get("url", ""),
            "published": doc.get("date", ""),
            "source": "govt",
        })

    for item in ai_storage.get_recent_items():
        doc_id = normalize_doc_id(item.get("external_id") or item.get("url"))
        documents.append({
            "id": doc_id,
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "url": item.get("url", ""),
            "published": item.get("published") or item.get("fetched_at"),
            "source": "ai",
        })

    paper = paper_fetcher.get_paper_of_the_day()
    if paper:
        doc_id = normalize_doc_id(paper.get("id") or paper.get("link"))
        documents.append({
            "id": doc_id,
            "title": paper.get("title", ""),
            "summary": paper.get("summary", ""),
            "url": paper.get("link", ""),
            "published": paper.get("published", ""),
            "source": "paper",
        })

    return [doc for doc in documents if doc["id"]]


def format_time_ago(date_str):
    """Convert date string to 'X days ago' format."""
    try:
        if not date_str:
            return ""
        cleaned = date_str.replace("Z", "")
        if "T" in cleaned:
            date = datetime.fromisoformat(cleaned)
        else:
            date = datetime.strptime(cleaned, "%Y-%m-%d")
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
    documents = fetch_documents()
    vote_token = get_vote_token()

    # Log document count for debugging
    if not documents:
        app.logger.info("No healthcare documents found for the current query")
        documents = []  # Ensure documents is always a list

    # Add vote counts and format dates
    for doc in documents:
        doc_id = doc.get("id", "")
        if doc_id:
            record = storage.get_vote_record(doc_id, vote_token)
            doc["up_votes"] = record["up"]
            doc["down_votes"] = record["down"]
            doc["score"] = record["score"]
            doc["user_vote"] = record["user_vote"]
            doc["comment_count"] = storage.get_comment_count(doc_id)
        else:
            doc["up_votes"] = doc["down_votes"] = 0
            doc["score"] = 0
            doc["user_vote"] = None
            doc["comment_count"] = 0
        doc["time_ago"] = format_time_ago(doc.get("date", ""))

        # Agency is already formatted in fetch_documents
        # No need to process further

        # Title is already set in fetch_documents
        # No need to process further
    
    # Sort by vote count (HN style) with recent bias
    def score_doc(doc):
        votes_score = doc.get("score", 0)
        recency_bonus = 0
        try:
            date = datetime.strptime(doc.get("date", ""), "%Y-%m-%d")
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
    direction = (data.get('direction') or 'up').lower()

    if not validate_csrf_token(csrf_token):
        return jsonify({"success": False, "error": "Invalid CSRF token"}), 403
        
    if not validate_document_id(doc_id):
        return jsonify({"success": False, "error": "Invalid document ID"}), 400

    if direction not in {'up', 'down'}:
        return jsonify({"success": False, "error": "Invalid vote direction"}), 400

    vote_token = get_vote_token()
    result = storage.toggle_vote(doc_id, vote_token, direction)

    return jsonify({
        "success": True,
        "up_votes": result["up"],
        "down_votes": result["down"],
        "score": result["score"],
        "direction": result["direction"],
        "previous_direction": result["previous_direction"],
    })

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
    
    comment_count = storage.add_comment(doc_id, author, comment_text)
    
    return jsonify({"success": True, "comment_count": comment_count})

@app.route('/api/documents')
@limiter.limit("20 per minute")
def api_documents():
    """API endpoint for documents (for AJAX updates)."""
    query = request.args.get('q', 'medicare medicaid')
    if not validate_query(query):
        return jsonify({"error": "Invalid query"}), 400
        
    documents = fetch_documents(query)
    vote_token = get_vote_token()
    for doc in documents:
        doc_id = doc.get("id", "")
        if doc_id:
            record = storage.get_vote_record(doc_id, vote_token)
            doc["up_votes"] = record["up"]
            doc["down_votes"] = record["down"]
            doc["score"] = record["score"]
            doc["user_vote"] = record["user_vote"]
            doc["comment_count"] = storage.get_comment_count(doc_id)
        else:
            doc["up_votes"] = doc["down_votes"] = 0
            doc["score"] = 0
            doc["user_vote"] = None
            doc["comment_count"] = 0
    return jsonify(documents)

@app.route('/search')
@limiter.limit("20 per minute")
def internal_search():
    """Search across site content using BM25 and cosine similarity."""
    query = (request.args.get('q') or '').strip()
    results = []
    vote_token = get_vote_token()

    if query:
        documents = collect_search_documents()
        ranked = search_index.rank(query, documents)
        for doc in ranked:
            doc_id = doc.get('id')
            if doc_id:
                record = storage.get_vote_record(doc_id, vote_token)
                doc['up_votes'] = record['up']
                doc['down_votes'] = record['down']
                doc['score'] = record['score']
                doc['user_vote'] = record['user_vote']
                doc['comment_count'] = storage.get_comment_count(doc_id)
            else:
                doc['up_votes'] = doc['down_votes'] = 0
                doc['score'] = doc.get('score', 0)
                doc['user_vote'] = None
                doc['comment_count'] = 0
            doc['time_ago'] = format_time_ago(doc.get('published', ''))
            results.append(doc)

    return render_template('search.html', query=query, results=results)


@app.route('/searches')
def legacy_search():
    """Redirect legacy /searches route to /search"""
    query = request.args.get('q')
    if query:
        return redirect(url_for('internal_search', q=query))
    return redirect(url_for('internal_search'))


@app.route('/ai')
@limiter.limit("20 per minute")
def ai_updates():
    """Render latest AI-focused news items."""
    ai_storage.purge_expired()
    items = ai_storage.get_recent_items()
    vote_token = get_vote_token()
    for item in items:
        stamp = item.get('published_at') or item.get('fetched_at')
        item['time_ago'] = format_time_ago(stamp)
        doc_id = normalize_doc_id(item.get('external_id') or item.get('url'))
        item['id'] = doc_id
        if doc_id:
            record = storage.get_vote_record(doc_id, vote_token)
            item['up_votes'] = record['up']
            item['down_votes'] = record['down']
            item['score'] = record['score']
            item['user_vote'] = record['user_vote']
            item['comment_count'] = storage.get_comment_count(doc_id)
        else:
            item['up_votes'] = item['down_votes'] = 0
            item['score'] = 0
            item['user_vote'] = None
            item['comment_count'] = 0
    return render_template('ai.html', items=items)


@app.route('/api/ai')
@limiter.limit("20 per minute")
def api_ai_items():
    """Return AI updates as JSON."""
    ai_storage.purge_expired()
    items = ai_storage.get_recent_items()
    vote_token = get_vote_token()
    for item in items:
        stamp = item.get('published_at') or item.get('fetched_at')
        item['time_ago'] = format_time_ago(stamp)
        doc_id = normalize_doc_id(item.get('external_id') or item.get('url'))
        item['id'] = doc_id
        if doc_id:
            record = storage.get_vote_record(doc_id, vote_token)
            item['up_votes'] = record['up']
            item['down_votes'] = record['down']
            item['score'] = record['score']
            item['user_vote'] = record['user_vote']
            item['comment_count'] = storage.get_comment_count(doc_id)
        else:
            item['up_votes'] = item['down_votes'] = 0
            item['score'] = 0
            item['user_vote'] = None
            item['comment_count'] = 0
    return jsonify(items)


@app.route('/paper')
@limiter.limit("10 per minute")
def paper_of_the_day():
    """Showcase a curated arXiv paper with voting and comments."""
    paper = paper_fetcher.get_paper_of_the_day()
    vote_token = get_vote_token()

    if not paper:
        return render_template('paper.html', paper=None)

    paper_id = normalize_doc_id(paper.get('id') or paper.get('link') or paper.get('title'))
    record = storage.get_vote_record(paper_id, vote_token)
    paper_context = {
        "id": paper_id,
        "title": paper.get('title', 'Untitled arXiv paper'),
        "summary": paper.get('summary', ''),
        "published": paper.get('published', ''),
        "authors": paper.get('authors', []),
        "link": paper.get('link', ''),
        "pdf_url": paper.get('pdf_url', ''),
        "categories": [tag.get('term', '') for tag in paper.get('categories', [])],
        "score": record['score'],
        "up_votes": record['up'],
        "down_votes": record['down'],
        "user_vote": record['user_vote'],
        "comment_count": storage.get_comment_count(paper_id),
    }
    paper_context['time_ago'] = format_time_ago(paper_context['published'])
    return render_template('paper.html', paper=paper_context)

@app.route('/health')
def health_check():
    """Simple health check endpoint for debugging deployment."""
    return jsonify({
        'status': 'ok',
        'message': 'Keywatch is running',
        'environment': os.getenv('FLASK_ENV', 'unknown'),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'dependencies': {
            'flask': True,
            'requests': True,
            'talisman': TALISMAN_AVAILABLE,
            'limiter': hasattr(limiter, 'limit')
        }
    })

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
    # For local development - use secure defaults
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    host = '127.0.0.1' if debug_mode else '0.0.0.0'  # Secure default for development
    port = int(os.getenv('PORT', 8080))
    
    app.run(host=host, port=port, debug=debug_mode)
else:
    # For production/serverless deployment
    # The app object will be imported by the WSGI server
    pass 
