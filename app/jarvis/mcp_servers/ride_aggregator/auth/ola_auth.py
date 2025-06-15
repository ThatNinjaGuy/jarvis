"""
Ola Authentication Manager

Handles OAuth user token flow for Ola API access.
"""

import json
import webbrowser
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class OlaAuthSetup:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = "https://devapi.olacabs.com"
        
    def generate_oauth_url(self) -> str:
        """Generate OAuth URL for user authentication"""
        return (f"{self.base_url}/oauth2/authorize?"
                f"response_type=token&"
                f"client_id={self.client_id}&"
                f"redirect_uri={self.redirect_uri}&"
                f"scope=profile%20booking")
    
    def setup_user_authentication(self) -> Dict[str, str]:
        """One-time setup for Ola user authentication"""
        print("=" * 60)
        print("OLA AUTHENTICATION SETUP")
        print("=" * 60)
        print("\n1. A browser window will open for Ola authentication")
        print("2. Log in with your Ola account")
        print("3. Grant permissions to the application")
        print("4. Copy the access token from the redirect URL")
        print("\nStarting authentication process...")
        
        oauth_url = self.generate_oauth_url()
        print(f"\nOAuth URL: {oauth_url}")
        
        # Open browser for authentication
        webbrowser.open(oauth_url)
        
        # Get the redirect URL with access token
        print("\nAfter authentication, you'll be redirected to:")
        print(f"{self.redirect_uri}#access_token=YOUR_TOKEN&...")
        print("\nPlease paste the full redirect URL here:")
        
        redirect_url = input("Redirect URL: ").strip()
        
        # Parse access token from URL
        access_token = self._extract_token_from_url(redirect_url)
        
        if access_token:
            # Save token to configuration
            token_data = {
                "access_token": access_token,
                "client_id": self.client_id,
                "setup_completed": True
            }
            
            self._save_token_config(token_data)
            print(f"\n✅ Authentication setup completed!")
            print(f"Access token saved to configuration")
            return token_data
        else:
            raise Exception("Failed to extract access token from URL")
    
    def _extract_token_from_url(self, url: str) -> Optional[str]:
        """Extract access token from redirect URL"""
        try:
            # Parse fragment from URL
            if '#' in url:
                fragment = url.split('#')[1]
                params = dict(param.split('=') for param in fragment.split('&'))
                return params.get('access_token')
        except Exception as e:
            logger.error(f"Error extracting token: {e}")
        return None
    
    def _save_token_config(self, token_data: Dict[str, Any]):
        """Save token configuration to file"""
        config_dir = Path(__file__).parent.parent / "config"
        config_dir.mkdir(exist_ok=True)
        
        config_path = config_dir / "ola_auth_config.json"
        with open(config_path, 'w') as f:
            json.dump(token_data, f, indent=2)
        logger.info(f"Configuration saved to {config_path}")

class OlaAuthManager:
    def __init__(self, app_token: str):
        self.app_token = app_token
        self.user_access_token = None
        self._load_user_token()
        
    def _load_user_token(self):
        """Load user access token from configuration"""
        try:
            config_path = Path(__file__).parent.parent / "config" / "ola_auth_config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.user_access_token = config.get('access_token')
            else:
                logger.warning("Ola authentication not set up. Run setup first.")
        except Exception as e:
            logger.error(f"Error loading Ola token: {e}")
    
    def get_access_token(self) -> Optional[str]:
        """Get user access token for API calls"""
        return self.user_access_token
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.user_access_token is not None 