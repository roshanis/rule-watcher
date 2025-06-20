import sys
import os
import traceback

# Add the parent directory to the path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Set environment variables for production
    os.environ.setdefault('FLASK_ENV', 'production')
    
    # Import the Flask app with error handling
    from app import app
    
    # Ensure the app is configured for serverless
    app.config['ENV'] = 'production'
    
    # For Vercel, we need to expose the app as a handler function
    def handler(request, response):
        return app(request, response)
    
    # Also expose app directly for backwards compatibility
    application = app
    
except Exception as e:
    # Create a minimal error app if main app fails to import
    from flask import Flask, jsonify
    
    error_app = Flask(__name__)
    
    @error_app.route('/')
    @error_app.route('/<path:path>')
    def error_handler(path=''):
        return jsonify({
            'error': 'Application failed to initialize',
            'details': str(e),
            'traceback': traceback.format_exc()
        }), 500
    
    app = error_app
    application = error_app

# Vercel expects the app to be available as 'app'
if __name__ == "__main__":
    app.run(debug=False) 