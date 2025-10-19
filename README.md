# CMS Rule Watcher 🏥

A **HackerNews-style web application** for monitoring CMS (Centers for Medicare & Medicaid Services) policy and rulemaking changes. Built for compliance teams to stay ahead of payment updates, quality-measure changes, and new guardrails.

![CMS Rule Watcher](https://img.shields.io/badge/CMS-Rule%20Watcher-orange)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)
![Security](https://img.shields.io/badge/security-hardened-red.svg)

## ✨ Features

- **📊 HackerNews-style Interface** - Clean, familiar design for browsing rules
- **🔍 Real-time Federal Register API** - Live data from official government sources
- **⬆️ Voting System** - Upvote important rules to prioritize team attention
- **💬 Team Comments** - Internal discussions on policy impacts
- **🔒 Security Hardened** - CSRF protection, rate limiting, input validation
- **📱 Responsive Design** - Works on desktop and mobile
- **⚡ Live Search** - Real-time search with URL persistence
- **🧠 AI Insights Feed** - Daily curated AI news for Optum & UHG teams

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/rule-watcher.git
cd rule-watcher

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Configuration

Create a `.env` file with the following variables:

```bash
# Security
SECRET_KEY=your-super-secret-key-here
FLASK_ENV=development  # Set to 'production' for production

# Server
HOST=127.0.0.1
PORT=8080

# Optional: OpenAI API for advanced summarization (defaults to gpt-5)
OPENAI_API_KEY=sk-your-openai-key-here
# OPENAI_MODEL=gpt-5
```

### Run the Application

```bash
# Development mode
python app.py

# Or use Flask CLI
export FLASK_APP=app.py
flask run --host=127.0.0.1 --port=8080
```

Visit **http://localhost:8080** to see your CMS Rule Watcher!

## 🔒 Security Features

This application includes enterprise-grade security features:

### Built-in Security
- **CSRF Protection** - Prevents cross-site request forgery attacks
- **Rate Limiting** - Prevents abuse and DoS attacks
- **Input Validation** - Sanitizes all user inputs
- **XSS Prevention** - Escapes HTML content
- **Security Headers** - CSP, HSTS, and other protective headers
- **Session Security** - Secure session cookies

### Rate Limits
- **General**: 200 requests/day, 50/hour per IP
- **Voting**: 10 votes/minute
- **Comments**: 5 comments/minute
- **Search**: 20 searches/minute

### Input Validation
- Document IDs must match Federal Register format
- Search queries are sanitized and length-limited
- Comments are limited to 1000 characters
- Author names limited to 50 characters

## 📖 API Documentation

### Endpoints

| Endpoint | Method | Description | Rate Limit |
|----------|--------|-------------|------------|
| `/` | GET | Main page with rule list | 30/min |
| `/api/documents` | GET | JSON API for documents | 20/min |
| `/vote` | POST | Upvote a document | 10/min |
| `/comment` | POST | Add comment to document | 5/min |
| `/searches` | GET | Suggested search categories | 10/min |
| `/ai` | GET | Latest AI-focused articles | 20/min |
| `/api/ai` | GET | JSON feed of AI articles | 20/min |

### Example API Usage

```bash
# Get latest Medicare/Medicaid documents
curl "http://localhost:8080/api/documents?q=medicare"

# Vote on a document (requires CSRF token)
curl -X POST "http://localhost:8080/vote" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "2024-12345", "csrf_token": "token"}'
```

## 🏗️ Architecture

```
rule-watcher/
├── app.py                 # Main Flask application
├── watcher.py            # Command-line rule watcher
├── cms_agent.py          # OpenAI-powered agent version
├── ai_ingest.py          # Daily AI news ingestion script
├── ai_fetchers.py        # External AI news sources
├── ai_storage.py         # Persistent storage for AI items
├── requirements.txt      # Python dependencies
├── .env                  # Environment configuration
├── templates/
│   └── index.html       # Main page template
├── static/
│   ├── css/style.css    # HackerNews-style CSS
│   └── js/app.js        # Interactive JavaScript
└── cache/               # API response cache
```

## 🔧 Development

### Adding New Features

1. **New Routes**: Add to `app.py` with appropriate rate limiting
2. **Frontend**: Update templates and static files
3. **Security**: Ensure CSRF protection and input validation

### Testing

```bash
# Run the command-line watcher
python watcher.py

# Run the AI ingestion job (populates cache/ai_updates.db)
python ai_ingest.py

# Test API endpoints
curl -s "http://localhost:8080/api/documents" | jq '.[0].title'

# Check security headers
curl -I "http://localhost:8080/"
```

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to all functions
- Validate all user inputs

## 🚀 Deployment

### Local Development

1. **Clone and Setup**:
   ```bash
   git clone https://github.com/roshanis/rule-watcher.git
   cd rule-watcher
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Run Application**:
   ```bash
   python app.py
   ```
   Visit: http://localhost:8080

### Vercel Deployment (Recommended)

**Quick Deploy:**
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/roshanis/rule-watcher)

**Manual Deployment:**
1. **Install Vercel CLI**:
   ```bash
   npm install -g vercel
   ```

2. **Deploy**:
   ```bash
   vercel login
   vercel
   ```

3. **Configure** (follow prompts):
   - Project name: `cms-rule-watcher`
   - Directory: `./`
   - Framework: `Other`

**📋 See [deploy.md](deploy.md) for detailed deployment instructions**

### Docker Deployment

```bash
docker-compose up -d
```
Visit: http://localhost:8080

### Scheduling Daily AI Ingestion

Add a cron entry to run the AI ingest script once per day (example: 6am UTC):

```
0 6 * * * /usr/bin/env bash -lc 'cd /path/to/rule-watcher && source .venv/bin/activate && python ai_ingest.py >> logs/ai_ingest.log 2>&1'
```

The script collects Hacker News stories, keeps the freshest 100 results, and purges anything older than 14 days.

### Environment Variables

Create `.env` file (optional):
```bash
OPENAI_API_KEY=your_openai_api_key_here  # For AI summaries
FLASK_ENV=production                      # For production
```

## 📊 Monitoring

### Key Metrics to Monitor

- **Response Times**: API endpoint performance
- **Error Rates**: 4xx/5xx response codes
- **Rate Limit Hits**: Blocked requests
- **Document Updates**: New rules detected
- **User Engagement**: Votes and comments

### Logging

The application logs to stdout in production-friendly format:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Add tests for new features
- Update documentation
- Follow security best practices
- Ensure rate limits are appropriate

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/rule-watcher/issues)
- **Documentation**: This README and inline code comments
- **Security**: Report security issues privately to security@your-org.com

## 🙏 Acknowledgments

- **Federal Register API** - For providing open access to government data
- **HackerNews** - For the inspiration for the clean, functional design
- **Flask Community** - For the excellent web framework and security extensions

---

**Built with ❤️ for healthcare compliance teams** 
