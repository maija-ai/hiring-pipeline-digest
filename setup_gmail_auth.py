#!/usr/bin/env python3
"""One-time setup: obtain Gmail OAuth2 refresh token.

Prerequisites:
1. Create a Google Cloud Project at https://console.cloud.google.com/
2. Enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop App type)
4. Download the credentials JSON file as 'credentials.json' in this directory
5. Set the OAuth consent screen to "Production" status
   (Testing mode tokens expire in 7 days!)

Usage:
  python setup_gmail_auth.py
"""

import json

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def main():
    print("=== Gmail OAuth2 Setup ===\n")
    print("This will open your browser for Google authentication.")
    print("Make sure 'credentials.json' is in this directory.\n")

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes=SCOPES)
    creds = flow.run_local_server(
        port=8080,
        prompt="consent",
        access_type="offline",
    )

    with open("credentials.json") as f:
        creds_data = json.load(f)
        installed = creds_data.get("installed", creds_data.get("web", {}))

    print("\n=== Setup Complete ===\n")
    print("Store these as GitHub Secrets:\n")
    print(f"  GMAIL_REFRESH_TOKEN = {creds.refresh_token}")
    print(f"  GMAIL_CLIENT_ID     = {installed['client_id']}")
    print(f"  GMAIL_CLIENT_SECRET = {installed['client_secret']}")
    print("\nIMPORTANT:")
    print("- Set your OAuth consent screen to 'Production' to avoid 7-day token expiry.")
    print("- Do NOT commit credentials.json to your repository.")


if __name__ == "__main__":
    main()
