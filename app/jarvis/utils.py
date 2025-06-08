"""
Utility functions.
"""

import os
from pathlib import Path
import json
from typing import Optional, Dict, List, Tuple
import datetime
from pytz import timezone

def get_current_time() -> dict:
    """
    Get the current time and date in IST timezone
    """
    # Get current time in IST 
    now = datetime.datetime.now(timezone('Asia/Kolkata'))

    # Format date as MM-DD-YYYY
    formatted_date = now.strftime("%m-%d-%Y")

    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "formatted_date": formatted_date,
    }

def is_cloud_run() -> bool:
    """Check if we're running in Cloud Run"""
    return bool(os.environ.get("K_SERVICE"))

def get_credentials_path() -> Path:
    """Get the appropriate path for credentials.json"""
    if is_cloud_run():
        return Path("/app/credentials.json")
    return Path("credentials.json")

def get_token_path() -> Path:
    """Get the appropriate path for token storage"""
    if is_cloud_run():
        return Path("/tmp/calendar_token.json")
    return Path(os.path.expanduser("~/.credentials/calendar_token.json"))

def get_google_credentials() -> Optional[dict]:
    """Get Google Calendar credentials from environment or file"""
    # First try environment variable (Cloud Run)
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        try:
            return json.loads(creds_json)
        except json.JSONDecodeError:
            print("Error: Invalid JSON in GOOGLE_CREDENTIALS environment variable")
            return None

    # Then try local file (development)
    creds_path = get_credentials_path()
    if creds_path.exists():
        try:
            return json.loads(creds_path.read_text())
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {creds_path}")
            return None
        except Exception as e:
            print(f"Error reading {creds_path}: {e}")
            return None

    return None

def get_twitter_credentials() -> Dict[str, str]:
    """
    Get Twitter API credentials from environment variables.
    Returns a dictionary with the credentials or raises ValueError if any are missing.
    """
    required_vars = {
        'API_KEY': 'TWITTER_API_KEY',
        'API_SECRET_KEY': 'TWITTER_API_SECRET',
        'ACCESS_TOKEN': 'TWITTER_ACCESS_TOKEN',
        'ACCESS_TOKEN_SECRET': 'TWITTER_ACCESS_TOKEN_SECRET'
    }
    
    credentials = {}
    missing_vars = []
    
    for key, env_var in required_vars.items():
        value = os.getenv(env_var)
        if not value:
            missing_vars.append(env_var)
        credentials[key] = str(value or "")
    
    if missing_vars:
        raise ValueError(f"Missing required Twitter credentials: {', '.join(missing_vars)}")
    
    return credentials

def load_environment():
    """Load environment variables appropriately for the current environment"""
    if not is_cloud_run():
        from dotenv import load_dotenv
        load_dotenv()
