import sys
import os

# Add the parent directory to the path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment for production
os.environ.setdefault('FLASK_ENV', 'production')

try:
    # Try to import the main Flask app
    from app import app
    
    # Configure for serverless
    app.config['ENV'] = 'production'
    
    # Ensure template/static folders point to the project root (deployed under /var/task)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    template_dir = os.path.join(project_root, 'templates')
    static_dir = os.path.join(project_root, 'static')

    if os.path.exists(template_dir):
        app.template_folder = template_dir
    if os.path.exists(static_dir):
        app.static_folder = static_dir
    
    # Expose for Vercel
    application = app

except Exception:
    # If import fails, create a simple diagnostic app
    import traceback
    from flask import Flask, jsonify
    
    # Capture the error details
    error_details = traceback.format_exc()
    
    # Create minimal Flask app for error reporting
    app = Flask(__name__)
    
    @app.route('/')
    @app.route('/<path:path>')
    def show_error(path=''):
        return jsonify({
            'status': 'error',
            'message': 'Failed to import main application',
            'traceback': error_details,
            'path_info': sys.path,
            'working_directory': os.getcwd(),
            'environment': dict(os.environ)
        }), 500
    
    application = app

# Vercel entry point
if __name__ == "__main__":
    app.run(debug=False) 
