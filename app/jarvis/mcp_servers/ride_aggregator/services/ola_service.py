"""
Ola Service Implementation

This service handles all Ola API operations including:
- Getting ride estimates
- Booking rides
- Tracking ride status
"""

import aiohttp
from typing import Dict, Any, Optional
import logging
from ..auth.ola_auth import OlaAuthManager

logger = logging.getLogger(__name__)

class OlaService:
    def __init__(self, auth_manager: OlaAuthManager):
        self.auth_manager = auth_manager
        self.base_url = "https://devapi.olacabs.com"
        
    async def get_ride_estimates(
        self,
        pickup_lat: float,
        pickup_lng: float,
        drop_lat: Optional[float] = None,
        drop_lng: Optional[float] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get ride estimates from Ola API"""
        if not self.auth_manager.is_authenticated():
            return {"error": "Ola authentication required. Please run setup first."}
        
        url = f"{self.base_url}/v1/products"
        params = {
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng
        }
        
        if drop_lat and drop_lng:
            params.update({
                "drop_lat": drop_lat,
                "drop_lng": drop_lng,
                "service_type": "p2p"
            })
        
        if category:
            params["category"] = category
        
        headers = self._get_auth_headers()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Ola API error: {error_text}")
                        return {"error": f"API error: {response.status}", "details": error_text}
        except Exception as e:
            logger.error(f"Error getting Ola estimates: {e}")
            return {"error": f"Request failed: {str(e)}"}
    
    async def book_ride(
        self,
        pickup_lat: float,
        pickup_lng: float,
        drop_lat: float,
        drop_lng: float,
        category_id: str,
        rider_name: Optional[str] = None,
        rider_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Book a ride with Ola"""
        if not self.auth_manager.is_authenticated():
            return {"error": "Ola authentication required"}
        
        url = f"{self.base_url}/v1/bookings/create"
        
        payload = {
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng,
            "drop_lat": drop_lat,
            "drop_lng": drop_lng,
            "category": category_id
        }
        
        if rider_name:
            payload["rider_name"] = rider_name
        if rider_phone:
            payload["rider_phone"] = rider_phone
        
        headers = self._get_auth_headers()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Error booking Ola ride: {error_text}")
                        return {
                            "error": f"API error: {response.status}",
                            "error_description": error_text,
                            "status": "failed"
                        }
        except Exception as e:
            logger.error(f"Error booking Ola ride: {e}")
            return {"error": f"Request failed: {str(e)}", "status": "failed"}
    
    async def track_ride(self, booking_id: str) -> Dict[str, Any]:
        """Track an ongoing ride"""
        if not self.auth_manager.is_authenticated():
            return {"error": "Ola authentication required"}
        
        url = f"{self.base_url}/v1/bookings/{booking_id}/track"
        headers = self._get_auth_headers()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Error tracking Ola ride: {error_text}")
                        return {"error": f"API error: {response.status}", "details": error_text}
        except Exception as e:
            logger.error(f"Error tracking Ola ride: {e}")
            return {"error": f"Request failed: {str(e)}"}
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests"""
        headers = {
            "X-APP-TOKEN": self.auth_manager.app_token,
            "Content-Type": "application/json"
        }
        
        user_token = self.auth_manager.get_access_token()
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        
        return headers 