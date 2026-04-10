#!/usr/bin/env python3

import sys
import os

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

# Path to the virtual environment's site-packages
# Adjust 'python3.9' if a different Python version is used in the virtual environment
venv_path = os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.9', 'site-packages')
if os.path.exists(venv_path):
    sys.path.insert(0, venv_path)
else:
    # Try common alternative for Python 3.x
    venv_path = os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.8', 'site-packages')
    if os.path.exists(venv_path):
        sys.path.insert(0, venv_path)
    else:
        # Fallback for other potential Python 3 versions or structures
        for item in os.listdir(os.path.join(os.path.dirname(__file__), '.venv', 'lib')):
            if item.startswith('python3.'):
                venv_path = os.path.join(os.path.dirname(__file__), '.venv', 'lib', item, 'site-packages')
                if os.path.exists(venv_path):
                    sys.path.insert(0, venv_path)
                    break


# Set PYTHON_EGG_CACHE to a writable directory (important for cPanel)
tmp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
os.makedirs(tmp_dir, exist_ok=True)
os.environ['PYTHON_EGG_CACHE'] = tmp_dir

# Set the FLASK_APP environment variable to point to your app.py module
os.environ['FLASK_APP'] = 'app'

# Import the Flask application instance
from app import app as application

# Run the Flask application using WSGI handler for CGI
from wsgiref.handlers import CGIHandler
CGIHandler().run(application)