#!/usr/bin/env python3
"""
Spotify Authentication Setup Script

This script helps you set up OAuth 2.0 credentials for Spotify integration.
Follow the instructions in the console.
"""

import os
from pathlib import Path
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Define scopes needed for Spotify
SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "streaming",
    "app-remote-control",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-read-private",
    "user-read-email"
]

# Path for token storage
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/spotify_token.json"))

def setup_oauth():
    """Set up OAuth 2.0 for Spotify"""
    print("\n=== Spotify OAuth Setup ===\n")

    # Load environment variables
    load_dotenv()
    
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        print("Error: Missing Spotify credentials in .env file!")
        print("\nTo set up Spotify integration:")
        print("1. Go to https://developer.spotify.com/dashboard")
        print("2. Create a new application or select an existing one")
        print("3. Get your Client ID and Client Secret")
        print("4. Add a redirect URI (e.g., http://localhost:8888/callback)")
        print("5. Create/update your .env file with:")
        print("   SPOTIFY_CLIENT_ID=your_client_id")
        print("   SPOTIFY_CLIENT_SECRET=your_client_secret")
        print("   SPOTIFY_REDIRECT_URI=your_redirect_uri")
        print("\nThen run this script again.")
        return False

    try:
        print("Found Spotify credentials. Setting up OAuth flow...")

        # Initialize Spotify OAuth
        auth_manager = SpotifyOAuth(
            scope=SCOPES,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            open_browser=True
        )

        # Get access token (this will trigger the OAuth flow)
        token_info = auth_manager.get_access_token(as_dict=True)

        # Save the token
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(json.dumps(token_info))

        print(f"\nSuccessfully saved credentials to {TOKEN_PATH}")

        # Test the API connection
        print("\nTesting connection to Spotify API...")
        spotify = spotipy.Spotify(auth_manager=auth_manager)
        user = spotify.current_user()
        
        if user:
            print(f"\nSuccess! Connected as: {user['display_name']} ({user['id']})")
            
            # Test playback state
            playback = spotify.current_playback()
            if playback:
                print("\nCurrent playback:")
                print(f"- Device: {playback['device']['name']}")
                if playback['item']:
                    print(f"- Track: {playback['item']['name']} by {playback['item']['artists'][0]['name']}")
            else:
                print("\nNo active playback session found.")
        
        print("\nOAuth setup complete! You can now use the Spotify integration.")
        return True

    except Exception as e:
        print(f"\nError during setup: {str(e)}")
        if "invalid_client" in str(e).lower():
            print("\nTip: Make sure your Client ID and Client Secret are correct in the .env file.")
        elif "redirect_uri_mismatch" in str(e).lower():
            print("\nTip: Make sure the redirect URI in your .env file matches exactly what's configured in your Spotify app settings.")
        return False

if __name__ == "__main__":
    setup_oauth() 