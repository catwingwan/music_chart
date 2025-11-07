#!/bin/bash

# Activate the virtual environment
source "$(dirname "$0")/.venv/bin/activate"

# Install required packages
pip install python-dotenv selenium google-auth google-api-python-client google-auth-oauthlib bs4

# Generate requirements.txt
pip freeze > requirements.txt

echo "Setup complete. Virtual environment activated and dependencies installed."
echo "To activate the environment later, run: source .venv/bin/activate"
