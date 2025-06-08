#!/usr/bin/env python3
"""
YouTube Data API Authentication Setup Script

This script helps you set up OAuth 2.0 credentials for YouTube Data API integration.
Follow the instructions in the console.
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Define scopes needed for YouTube Data API
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

# Path for token storage
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/youtube_token.json"))
CREDENTIALS_PATH = Path("credentials.json")


def setup_oauth():
    """Set up OAuth 2.0 for YouTube Data API"""
    print("\n=== YouTube Data API OAuth Setup ===\n")

    if not CREDENTIALS_PATH.exists():
        print(f"Error: {CREDENTIALS_PATH} not found!")
        print("\nTo set up YouTube Data API integration:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select an existing one")
        print("3. Enable the YouTube Data API v3")
        print("4. Create OAuth 2.0 credentials (Desktop application)")
        print("5. Download the credentials and save them as 'credentials.json' in this directory")
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
        print("\nTesting connection to YouTube Data API...")
        youtube = build("youtube", "v3", credentials=creds)

        # Try to get the authenticated user's channel info
        channels_response = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            mine=True
        ).execute()

        if channels_response["items"]:
            channel = channels_response["items"][0]
            print("\nSuccess! Connected to your YouTube channel:")
            print(f"- Channel Name: {channel['snippet']['title']}")
            print(f"- Channel ID: {channel['id']}")
            print(f"- Subscriber Count: {channel['statistics'].get('subscriberCount', 'N/A')}")
            print(f"- Video Count: {channel['statistics'].get('videoCount', 'N/A')}")
            print(f"- View Count: {channel['statistics'].get('viewCount', 'N/A')}")
        else:
            print("\nSuccess! Connected to YouTube Data API, but no channel found.")

        # Test search functionality
        print("\nTesting search functionality...")
        search_response = youtube.search().list(
            part="snippet",
            q="Test video",
            type="video",
            maxResults=1
        ).execute()

        if search_response["items"]:
            print("Search functionality working correctly!")
        else:
            print("Search functionality working, but no results found.")

        print("\nOAuth setup complete! You can now use the YouTube Data API integration.")
        return True

    except HttpError as e:
        print(f"\nYouTube API Error: {str(e)}")
        return False
    except Exception as e:
        print(f"\nError during setup: {str(e)}")
        return False


if __name__ == "__main__":
    setup_oauth() 