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
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

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
        # Create a no-op limiter if initialization fails
        class NoOpLimiter:
            def limit(self, *args, **kwargs):
                def decorator(f):
                    return f
                return decorator
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
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

# In-memory storage for votes and comments (for serverless deployment)
# Note: This will reset on each cold start, but works for demo purposes
# For production, you'd want to use a database like Redis or PostgreSQL
votes = {}
comments = {}

# Input validation patterns
DOCUMENT_ID_PATTERN = re.compile(r'^[0-9]{4}-[0-9]{5}$|^[A-Za-z0-9\-]+$')  # Support both formats
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
                "votes": 0,  # Default vote count
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
    documents = fetch_documents()
    
    # Log document count for debugging
    if not documents:
        app.logger.info("No healthcare documents found for the current query")
        documents = []  # Ensure documents is always a list
    
    # Add vote counts and format dates
    for doc in documents:
        doc_id = doc.get("id", "")
        doc["votes"] = votes.get(doc_id, 0)  # Use "votes" to match template
        doc["comment_count"] = len(comments.get(doc_id, []))
        doc["time_ago"] = format_time_ago(doc.get("date", ""))
        
        # Agency is already formatted in fetch_documents
        # No need to process further
        
        # Title is already set in fetch_documents
        # No need to process further
    
    # Sort by vote count (HN style) with recent bias
    def score_doc(doc):
        votes_score = doc.get("votes", 0)
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
        
    documents = fetch_documents(query)
    return jsonify(documents)

@app.route('/searches')
@limiter.limit("10 per minute")
def suggested_searches():
    """Page showing suggested search categories."""
    searches = fetch_suggested_searches()
    return render_template('searches.html', searches=searches)

@app.route('/health')
def health_check():
    """Simple health check endpoint for debugging deployment."""
    return jsonify({
        'status': 'ok',
        'message': 'CMS Rule Watcher is running',
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