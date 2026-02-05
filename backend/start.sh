#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Run migrations or init db if needed
# python init_db.py

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000
