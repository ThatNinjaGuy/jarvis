"""
Uber Service Implementation

Handles interaction with Uber APIs for estimates and ride booking.
"""

import aiohttp
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class UberService:
    """Service class for interacting with Uber APIs"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.api_base = "https://api.uber.com/v1.2"
        
    async def get_price_estimates(
        self,
        start_latitude: float,
        start_longitude: float,
        end_latitude: float,
        end_longitude: float,
        seat_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get price estimates for all available products"""
        url = f"{self.api_base}/estimates/price"
        
        params = {
            'start_latitude': start_latitude,
            'start_longitude': start_longitude,
            'end_latitude': end_latitude,
            'end_longitude': end_longitude
        }
        
        if seat_count is not None:
            params['seat_count'] = min(seat_count, 2)  # Max 2 seats for uberPOOL
            
        headers = {
            'Authorization': f'Token {self.auth_manager.get_server_token()}',
            'Accept-Language': 'en_US',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('prices', [])
                    elif response.status == 422:
                        error_data = await response.json()
                        logger.error(f"Invalid parameters for price estimates: {error_data}")
                        raise ValueError(f"Invalid parameters: {error_data.get('message')}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get Uber price estimates: {error_text}")
                        raise Exception(f"Failed to get price estimates: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error getting Uber price estimates: {e}")
            raise
            
    async def get_time_estimates(
        self,
        start_latitude: float,
        start_longitude: float,
        product_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get time estimates for all available products"""
        url = f"{self.api_base}/estimates/time"
        
        params = {
            'start_latitude': start_latitude,
            'start_longitude': start_longitude
        }
        
        if product_id:
            params['product_id'] = product_id
            
        try:
            # Get OAuth token for time estimates
            token = await self.auth_manager.get_oauth_token()
            
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept-Language': 'en_US',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('times', [])
                    elif response.status == 422:
                        error_data = await response.json()
                        logger.error(f"Invalid parameters for time estimates: {error_data}")
                        raise ValueError(f"Invalid parameters: {error_data.get('message')}")
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get Uber time estimates: {error_text}")
                        raise Exception(f"Failed to get time estimates: {response.status} - {error_text}")
        except Exception as e:
            logger.error(f"Error getting Uber time estimates: {e}")
            raise
            
    def format_estimate_response(
        self,
        price_estimates: List[Dict[str, Any]],
        time_estimates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format and combine price and time estimates"""
        combined_estimates = []
        
        # Create a map of product_id to time estimate
        time_map = {t['product_id']: t['estimate'] for t in time_estimates}
        
        for price in price_estimates:
            product_id = price['product_id']
            estimate = {
                'service': price['display_name'],
                'price_range': price['estimate'],
                'currency': price.get('currency_code'),
                'surge_multiplier': price.get('surge_multiplier', 1.0),
                'distance': price.get('distance'),
                'duration': price.get('duration'),
                'eta_seconds': time_map.get(product_id),
                'product_id': product_id
            }
            combined_estimates.append(estimate)
            
        return combined_estimates 