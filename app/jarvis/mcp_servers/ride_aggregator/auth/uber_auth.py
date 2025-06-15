"""
Uber Authentication Manager

Handles both server token and OAuth authentication for Uber API access.
"""

import aiohttp
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class UberAuthManager:
    """Manages authentication for Uber API using both server token and OAuth flows"""
    
    def __init__(self, client_id: str, client_secret: str, server_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.server_token = server_token
        self.base_url = "https://api.uber.com"
        self.auth_url = "https://auth.uber.com"
        self.access_token = None
        self.token_expires_at = None
        
    def get_server_token(self) -> str:
        """Get server token for price estimates"""
        return self.server_token
            
    async def get_oauth_token(self) -> str:
        """Get OAuth token for time estimates and ride requests"""
        if self.access_token and self._is_token_valid():
            return self.access_token
            
        await self._refresh_oauth_token()
        return self.access_token
    
    async def _refresh_oauth_token(self):
        """Refresh OAuth token using client credentials"""
        url = f"{self.auth_url}/oauth/v2/token"
        
        # For time estimates, we only need a basic scope
        # For ride requests, we would need the 'request' scope which requires approval
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials',
            'scope': 'profile' # Basic scope that works for time estimates
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=payload, headers=headers) as response:
                    response_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            self.access_token = data['access_token']
                            expires_in = data.get('expires_in', 3600)
                            # Set expiration 5 minutes before actual expiry
                            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                            logger.info("Uber OAuth token refreshed successfully")
                        except Exception as e:
                            logger.error(f"Error parsing Uber token response: {e}. Response: {response_text}")
                            raise Exception(f"Failed to parse Uber token response: {str(e)}")
                    else:
                        logger.error(f"Failed to get Uber OAuth token: {response_text}")
                        raise Exception(f"Failed to get Uber OAuth token: {response.status} - {response_text}")
        except Exception as e:
            logger.error(f"Error refreshing Uber token: {e}")
            raise
    
    def _is_token_valid(self) -> bool:
        """Check if current OAuth token is still valid"""
        return self.token_expires_at and datetime.now() < self.token_expires_at 