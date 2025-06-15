"""
Ride Aggregator Service

This service combines results from multiple ride providers and handles the aggregation logic.
"""

import asyncio
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class RideAggregatorService:
    def __init__(self, uber_service=None, ola_service=None):
        self.uber_service = uber_service
        self.ola_service = ola_service
    
    async def get_ride_estimates(
        self,
        pickup_latitude: float,
        pickup_longitude: float,
        drop_latitude: float,
        drop_longitude: float
    ) -> Dict[str, Any]:
        """Get ride estimates from all available providers"""
        
        # Create tasks for available services
        tasks = []
        uber_price_task = None
        uber_time_task = None
        ola_task = None
        
        if self.uber_service:
            uber_price_task = self.uber_service.get_price_estimates(
                pickup_latitude, pickup_longitude,
                drop_latitude, drop_longitude
            )
            uber_time_task = self.uber_service.get_time_estimates(
                pickup_latitude, pickup_longitude
            )
            tasks.extend([uber_price_task, uber_time_task])
            
        if self.ola_service and self.ola_service.auth_manager.is_authenticated():
            ola_task = self.ola_service.get_ride_estimates(
                pickup_latitude, pickup_longitude,
                drop_latitude, drop_longitude
            )
            tasks.append(ola_task)
        
        # Execute available tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        uber_prices = {"error": "Uber service not available"}
        uber_times = {"error": "Uber service not available"}
        ola_estimates = {"error": "Ola service not available"}
        
        if uber_price_task and uber_time_task:
            uber_prices = results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
            uber_times = results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
        
        if ola_task:
            ola_estimates = results[-1] if not isinstance(results[-1], Exception) else {"error": str(results[-1])}
        
        # Format and return combined results
        return self._format_combined_results(uber_prices, uber_times, ola_estimates)
    
    def _format_combined_results(
        self, 
        uber_prices: Dict[str, Any],
        uber_times: Dict[str, Any],
        ola_estimates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format and combine results from both services"""
        
        combined = {
            "timestamp": asyncio.get_event_loop().time(),
            "providers": {
                "uber": {
                    "status": "available" if not uber_prices.get("error") else "error",
                    "error": uber_prices.get("error"),
                    "price_estimates": uber_prices if not uber_prices.get("error") else None,
                    "time_estimates": uber_times if not uber_times.get("error") else None
                },
                "ola": {
                    "status": "unavailable" if ola_estimates.get("error") else "available",
                    "error": ola_estimates.get("error"),
                    "estimates": ola_estimates if not ola_estimates.get("error") else None
                }
            },
            "comparison": [],
            "recommendation": None,
            "available_providers": []
        }
        
        # Process and rank options
        comparison_options = []
        
        # Process Uber estimates if available
        if not uber_prices.get("error") and "prices" in uber_prices:
            combined["available_providers"].append("uber")
            uber_time_map = {}
            if not uber_times.get("error") and "times" in uber_times:
                uber_time_map = {
                    t.get("product_id"): t.get("estimate", 0) 
                    for t in uber_times["times"]
                }
            
            for price in uber_prices["prices"]:
                product_id = price.get("product_id")
                eta_seconds = uber_time_map.get(product_id, 0)
                
                option = {
                    "provider": "uber",
                    "product_id": product_id,
                    "display_name": price.get("display_name"),
                    "price_estimate": price.get("estimate"),
                    "eta_minutes": eta_seconds // 60 if eta_seconds > 0 else -1,
                    "currency": price.get("currency_code"),
                    "surge_multiplier": price.get("surge_multiplier", 1.0)
                }
                comparison_options.append(option)
        
        # Process Ola estimates if available
        if not ola_estimates.get("error") and "categories" in ola_estimates:
            combined["available_providers"].append("ola")
            for category in ola_estimates["categories"]:
                option = {
                    "provider": "ola",
                    "category_id": category.get("id"),
                    "display_name": category.get("display_name"),
                    "eta_minutes": category.get("eta", -1),
                    "currency": category.get("currency", "INR"),
                    "ride_estimate": category.get("ride_estimate", {})
                }
                comparison_options.append(option)
        
        # Sort by ETA and add to results
        valid_options = [opt for opt in comparison_options if opt.get("eta_minutes", -1) > 0]
        valid_options.sort(key=lambda x: (x.get("eta_minutes", 999), x.get("price_estimate", 999999)))
        
        combined["comparison"] = valid_options
        combined["recommendation"] = valid_options[0] if valid_options else None
        
        # Add summary if no providers are available
        if not combined["available_providers"]:
            combined["status"] = "error"
            combined["error"] = "No ride services are currently available"
        else:
            combined["status"] = "success"
            combined["message"] = f"Found rides from {', '.join(combined['available_providers'])}"
        
        return combined 