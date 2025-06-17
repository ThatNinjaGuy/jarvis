#!/usr/bin/env python3
"""
Google Maps API Setup Script

This script helps you set up the Google Maps API key for Distance Matrix functionality.
Follow the instructions in the console.
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv, set_key

def setup_maps_api():
    """Set up Google Maps API key"""
    print("\n=== Google Maps API Setup ===\n")

    # Check if API key exists in .env
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv()
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if api_key:
            print("Found existing Google Maps API key in .env file.")
            should_update = input("Would you like to update it? (y/n): ").lower()
            if should_update != 'y':
                print("\nKeeping existing API key.")
                return True
    
    # Get API key from user
    print("\nTo set up Google Maps integration:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a new project or select an existing one")
    print("3. Enable the Distance Matrix API")
    print("4. Create API credentials")
    print("5. Copy your API key")
    print("\nEnter your Google Maps API key:")
    api_key = input().strip()

    if not api_key:
        print("Error: API key cannot be empty!")
        return False

    # Test the API key
    print("\nTesting API key with a sample request...")
    test_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    test_params = {
        "origins": "Washington,DC",
        "destinations": "New York City,NY",
        "key": api_key
    }

    try:
        response = requests.get(test_url, params=test_params)
        data = response.json()

        if data.get("status") == "OK":
            print("\nAPI key test successful!")
            
            # Save API key to .env file
            if not env_path.exists():
                env_path.touch()
            
            set_key(env_path, "GOOGLE_MAPS_API_KEY", api_key)
            print(f"\nAPI key saved to {env_path}")
            
            # Show sample results
            if data["rows"][0]["elements"][0]["status"] == "OK":
                distance = data["rows"][0]["elements"][0]["distance"]["text"]
                duration = data["rows"][0]["elements"][0]["duration"]["text"]
                print(f"\nSample result:")
                print(f"Distance from Washington DC to New York City: {distance}")
                print(f"Estimated travel time: {duration}")
            
            return True
        else:
            print(f"\nError: API key test failed. Status: {data.get('status')}")
            print("Please check your API key and try again.")
            return False

    except Exception as e:
        print(f"\nError testing API key: {str(e)}")
        return False

if __name__ == "__main__":
    setup_maps_api() 