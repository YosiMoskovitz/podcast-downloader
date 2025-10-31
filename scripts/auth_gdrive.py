#!/usr/bin/env python3
"""Headless OAuth helper for Podcast Downloader

Use this script to perform OAuth in a headless environment (console-based).
It will guide you to visit a URL and paste the authorization code back into the console.

Defaults:
 - credentials: config/credentials.json
 - token: token.json (saved to repository root)

Example:
  python scripts/auth_gdrive.py --credentials config/credentials.json --token token.json
"""
from __future__ import annotations
import argparse
import os
import pickle
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except Exception as e:
    print("Missing dependencies: google-auth-oauthlib and google-auth are required. Install with: pip install google-auth-oauthlib google-auth", file=sys.stderr)
    raise

SCOPES = ['https://www.googleapis.com/auth/drive']


def main():
    parser = argparse.ArgumentParser(description='Headless OAuth helper for Google Drive')
    parser.add_argument('--credentials', '-c', default=os.path.join('config', 'credentials.json'), help='Path to client credentials JSON (client_secret / credentials.json)')
    parser.add_argument('--token', '-t', default='token.json', help='Path where token will be saved (default: token.json)')
    args = parser.parse_args()

    cred_path = args.credentials
    token_path = args.token

    if not os.path.exists(cred_path):
        print(f'Credentials file not found: {cred_path}', file=sys.stderr)
        sys.exit(2)

    # If a token already exists, try to load and report
    if os.path.exists(token_path):
        try:
            with open(token_path, 'rb') as f:
                creds = pickle.load(f)
            if getattr(creds, 'valid', False):
                print(f'Token at {token_path} already valid. No action needed.')
                return
            if getattr(creds, 'expired', False) and getattr(creds, 'refresh_token', None):
                try:
                    creds.refresh(Request())
                    with open(token_path, 'wb') as f:
                        pickle.dump(creds, f)
                    print(f'Token refreshed and saved to {token_path}')
                    return
                except Exception:
                    # Fall through to performing full flow
                    pass
        except Exception:
            print('Existing token file is invalid or unreadable; starting new OAuth flow.')

    print('Starting console OAuth flow. You will be prompted to visit a URL and paste the resulting code here.')
    flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
    creds = flow.run_console()

    # Persist credentials
    try:
        with open(token_path, 'wb') as f:
            pickle.dump(creds, f)
        print(f'Credentials saved to {token_path}')
    except Exception as e:
        print(f'Failed to save credentials to {token_path}: {e}', file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()
