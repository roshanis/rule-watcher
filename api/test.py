#!/usr/bin/env python3
"""
Minimal test to diagnose import issues
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Python version:", sys.version)
print("Working directory:", os.getcwd())
print("Python path:", sys.path[:3])  # Show first 3 entries

# Test individual imports
try:
    import flask
    print("✓ Flask import successful")
except Exception as e:
    print("✗ Flask import failed:", e)

try:
    import requests
    print("✓ Requests import successful")
except Exception as e:
    print("✗ Requests import failed:", e)

try:
    from flask import Flask
    test_app = Flask(__name__)
    print("✓ Basic Flask app creation successful")
except Exception as e:
    print("✗ Flask app creation failed:", e)

# Test main app import
try:
    print("Attempting to import main app...")
    import app
    print("✓ Main app import successful")
except Exception as e:
    print("✗ Main app import failed:", e)
    import traceback
    traceback.print_exc()

if __name__ == "__main__":
    print("Test completed") 