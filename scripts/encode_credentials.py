#!/usr/bin/env python3
"""
Helper script to encode Google credentials and token for environment variables.
Run this script to generate the base64-encoded values needed for deployment.
"""

import base64
import json
import os
import sys
import pickle

def encode_file(filepath):
    """Encode a JSON file to base64. Handles both JSON and pickle formats."""
    if not os.path.exists(filepath):
        return None
    
    # Try JSON format first
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Try pickle format (for token.json)
        try:
            with open(filepath, 'rb') as f:
                creds_obj = pickle.load(f)
            if hasattr(creds_obj, 'to_json'):
                data = json.loads(creds_obj.to_json())
            else:
                print(f"Error: Unknown file format for {filepath}")
                return None
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return None
    
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode()).decode()
    return encoded

def main():
    print("=" * 70)
    print("Google Credentials Encoder for Cloud Deployment")
    print("=" * 70)
    print()
    
    # Encode credentials.json
    creds_path = os.path.join('config', 'credentials.json')
    print(f"Looking for credentials at: {creds_path}")
    
    creds_encoded = encode_file(creds_path)
    if creds_encoded:
        print("✓ Found credentials.json")
        print()
        print("Add this to your environment variables:")
        print("-" * 70)
        print(f"GOOGLE_CREDENTIALS_BASE64={creds_encoded}")
        print("-" * 70)
        print()
    else:
        print(f"✗ Could not find {creds_path}")
        print()
    
    # Encode token.json
    token_path = 'token.json'
    print(f"Looking for token at: {token_path}")
    
    token_encoded = encode_file(token_path)
    if token_encoded:
        print("✓ Found token.json")
        print()
        print("Add this to your environment variables:")
        print("-" * 70)
        print(f"GOOGLE_TOKEN_BASE64={token_encoded}")
        print("-" * 70)
        print()
    else:
        print(f"✗ Could not find {token_path}")
        print("  Run 'python scripts/auth_gdrive.py' first to generate token.")
        print()
    
    # Generate podcasts config example
    podcasts_path = os.path.join('config', 'podcasts.json')
    print(f"Looking for podcasts config at: {podcasts_path}")
    
    if os.path.exists(podcasts_path):
        with open(podcasts_path, 'r', encoding='utf-8') as f:
            podcasts_data = json.load(f)
        
        # Minify JSON for environment variable
        podcasts_str = json.dumps(podcasts_data, separators=(',', ':'))
        
        print("✓ Found podcasts.json")
        print()
        print("Add this to your environment variables:")
        print("-" * 70)
        print(f"PODCASTS_CONFIG={podcasts_str}")
        print("-" * 70)
        print()
    else:
        print(f"✗ Could not find {podcasts_path}")
        print()
    
    print("=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print("1. Copy the environment variables above")
    print("2. Add them to your cloud platform (Railway/Render)")
    print("3. Set DATABASE_URL to your PostgreSQL connection string")
    print("4. Set SECRET_KEY to a random string")
    print("5. Deploy your application")
    print()

if __name__ == "__main__":
    main()
