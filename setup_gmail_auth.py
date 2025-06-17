#!/usr/bin/env python3
"""
Gmail Authentication Setup Script

This script helps you set up OAuth 2.0 credentials for Gmail integration.
Follow the instructions in the console.
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define scopes needed for Gmail
SCOPES = ['https://mail.google.com/']  # Full access scope needed for search

# Path for token storage
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/gmail_token.json"))
CREDENTIALS_PATH = Path("credentials.json")


def setup_oauth():
    """Set up OAuth 2.0 for Gmail"""
    print("\n=== Gmail OAuth Setup ===\n")

    if not CREDENTIALS_PATH.exists():
        print(f"Error: {CREDENTIALS_PATH} not found!")
        print("\nTo set up Gmail integration:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select an existing one")
        print("3. Enable the Gmail API")
        print("4. Create OAuth 2.0 credentials (Desktop application)")
        print(
            "5. Download the credentials and save them as 'credentials.json' in this directory"
        )
        print("\nThen run this script again.")
        return False

    print(f"Found credentials.json. Setting up OAuth flow...")

    try:
        # Run the OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

        print(f"\nSuccessfully saved credentials to {TOKEN_PATH}")

        # Test the API connection
        print("\nTesting connection to Gmail API...")
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId='me').execute()

        if profile:
            print(f"\nSuccess! Connected as: {profile['emailAddress']}")
            print(f"Messages total: {profile['messagesTotal']}")
            print(f"Threads total: {profile['threadsTotal']}")
        else:
            print("\nSuccess! Connected to Gmail API, but couldn't fetch profile.")

        print("\nOAuth setup complete! You can now use the Gmail integration.")
        return True

    except Exception as e:
        print(f"\nError during setup: {str(e)}")
        return False


if __name__ == "__main__":
    setup_oauth() 