<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Implementation Plan for Jarvis Ride Aggregator with Uber/Ola Authentication

## Architecture Overview

Your analysis is correct - Uber's authentication can be handled dynamically using client credentials, while Ola requires a one-time OAuth setup for user access tokens[^1][^2]. This implementation plan provides a comprehensive approach for building the ride aggregator system with proper authentication handling for both services.

## Phase 1: Project Structure Setup

### Directory Structure

Create the following project structure in Cursor:

```
jarvis-ride-aggregator/
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── auth_config.json
├── services/
│   ├── __init__.py
│   ├── uber_service.py
│   ├── ola_service.py
│   └── aggregator_service.py
├── auth/
│   ├── __init__.py
│   ├── uber_auth.py
│   ├── ola_auth.py
│   └── token_manager.py
├── mcp_servers/
│   ├── __init__.py
│   ├── uber_mcp_server.py
│   ├── ola_mcp_server.py
│   └── ride_aggregator_mcp.py
├── utils/
│   ├── __init__.py
│   ├── exceptions.py
│   └── logging_config.py
├── tests/
├── requirements.txt
├── .env.example
├── .env
└── main.py
```


### Dependencies Installation

Create `requirements.txt` with the following packages:

```txt
aiohttp>=3.9.0
python-dotenv>=1.0.0
pyjwt>=2.8.0
cryptography>=41.0.0
requests-oauthlib>=1.3.1
mcp>=1.0.0
asyncio-throttle>=1.0.2
tenacity>=8.2.0
```


## Phase 2: Authentication Implementation

### Uber Client Credentials Authentication

Uber supports client credentials flow for server-to-server authentication[^1][^3][^4]. Create `auth/uber_auth.py`:

```python
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

class UberAuthManager:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://auth.uber.com"
        self.access_token = None
        self.token_expires_at = None
        self.logger = logging.getLogger(__name__)
        
    async def get_access_token(self) -> str:
        """Get access token using client credentials flow"""
        if self.access_token and self._is_token_valid():
            return self.access_token
            
        await self._refresh_token()
        return self.access_token
    
    async def _refresh_token(self):
        """Refresh access token using client credentials"""
        url = f"{self.base_url}/oauth/v2/token"
        
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials',
            'scope': 'request'  # Adjust scopes as needed
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data['access_token']
                    expires_in = data.get('expires_in', 3600)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                    self.logger.info("Uber access token refreshed successfully")
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get Uber access token: {response.status} - {error_text}")
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid"""
        return self.token_expires_at and datetime.now() < self.token_expires_at
```


### Ola One-Time Authentication Setup

Ola requires OAuth flow for user access tokens[^5][^6]. Create `auth/ola_auth.py`:

```python
import json
import webbrowser
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional
import logging

class OlaAuthSetup:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = "https://devapi.olacabs.com"
        self.logger = logging.getLogger(__name__)
        
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
                fragment = url.split('#')[^1]
                params = dict(param.split('=') for param in fragment.split('&'))
                return params.get('access_token')
        except Exception as e:
            self.logger.error(f"Error extracting token: {e}")
        return None
    
    def _save_token_config(self, token_data: Dict[str, Any]):
        """Save token configuration to file"""
        config_path = "config/ola_auth_config.json"
        with open(config_path, 'w') as f:
            json.dump(token_data, f, indent=2)
        print(f"Configuration saved to {config_path}")

class OlaAuthManager:
    def __init__(self, app_token: str):
        self.app_token = app_token
        self.user_access_token = None
        self._load_user_token()
        
    def _load_user_token(self):
        """Load user access token from configuration"""
        try:
            with open("config/ola_auth_config.json", 'r') as f:
                config = json.load(f)
                self.user_access_token = config.get('access_token')
        except FileNotFoundError:
            print("⚠️  Ola authentication not set up. Run setup first.")
    
    def get_access_token(self) -> Optional[str]:
        """Get user access token for API calls"""
        return self.user_access_token
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return self.user_access_token is not None
```


## Phase 3: Service Implementation

### Uber Service Implementation

Create `services/uber_service.py` with client credentials authentication[^1][^4]:

```python
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional
from auth.uber_auth import UberAuthManager

class UberService:
    def __init__(self, auth_manager: UberAuthManager):
        self.auth_manager = auth_manager
        self.base_url = "https://api.uber.com"
        
    async def get_price_estimates(
        self,
        start_latitude: float,
        start_longitude: float,
        end_latitude: float,
        end_longitude: float
    ) -> Dict[str, Any]:
        """Get price estimates from Uber API"""
        url = f"{self.base_url}/v1.2/estimates/price"
        params = {
            "start_latitude": start_latitude,
            "start_longitude": start_longitude,
            "end_latitude": end_latitude,
            "end_longitude": end_longitude
        }
        
        headers = await self._get_auth_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"Uber API error: {response.status}", "details": error_text}
    
    async def get_time_estimates(
        self,
        start_latitude: float,
        start_longitude: float,
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get time estimates from Uber API"""
        url = f"{self.base_url}/v1.2/estimates/time"
        params = {
            "start_latitude": start_latitude,
            "start_longitude": start_longitude
        }
        
        if product_id:
            params["product_id"] = product_id
        
        headers = await self._get_auth_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"Uber API error: {response.status}", "details": error_text}
    
    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        access_token = await self.auth_manager.get_access_token()
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept-Language": "en_US",
            "Content-Type": "application/json"
        }
```


### Ola Service Implementation

Create `services/ola_service.py` with app token and user access token[^5][^7]:

```python
import aiohttp
from typing import Dict, Any, Optional
from auth.ola_auth import OlaAuthManager

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
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"Ola API error: {response.status}", "details": error_text}
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {
            "X-APP-TOKEN": self.auth_manager.app_token,
            "Content-Type": "application/json"
        }
        
        user_token = self.auth_manager.get_access_token()
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        
        return headers
```


## Phase 4: MCP Server Implementation

### Aggregator MCP Server

Create `mcp_servers/ride_aggregator_mcp.py`:

```python
import asyncio
import json
from typing import Dict, Any, List
from mcp.server import Server
from mcp.types import Tool
from services.uber_service import UberService
from services.ola_service import OlaService
from auth.uber_auth import UberAuthManager
from auth.ola_auth import OlaAuthManager

class RideAggregatorMCP:
    def __init__(self):
        self.server = Server("ride-aggregator")
        self.uber_service = None
        self.ola_service = None
        self._setup_services()
        self._register_tools()
    
    def _setup_services(self):
        """Initialize service instances"""
        # Load configuration
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        # Initialize Uber service
        uber_auth = UberAuthManager(
            client_id=os.getenv("UBER_CLIENT_ID"),
            client_secret=os.getenv("UBER_CLIENT_SECRET")
        )
        self.uber_service = UberService(uber_auth)
        
        # Initialize Ola service
        ola_auth = OlaAuthManager(
            app_token=os.getenv("OLA_APP_TOKEN")
        )
        self.ola_service = OlaService(ola_auth)
    
    def _register_tools(self):
        """Register MCP tools"""
        
        @self.server.tool()
        async def get_ride_estimates(
            pickup_latitude: float,
            pickup_longitude: float,
            drop_latitude: float,
            drop_longitude: float
        ) -> str:
            """Get ride estimates from both Uber and Ola in parallel"""
            
            # Create parallel tasks
            tasks = [
                self.uber_service.get_price_estimates(
                    pickup_latitude, pickup_longitude,
                    drop_latitude, drop_longitude
                ),
                self.uber_service.get_time_estimates(
                    pickup_latitude, pickup_longitude
                ),
                self.ola_service.get_ride_estimates(
                    pickup_latitude, pickup_longitude,
                    drop_latitude, drop_longitude
                )
            ]
            
            # Execute in parallel
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                uber_prices = results[^0] if not isinstance(results[^0], Exception) else {"error": str(results[^0])}
                uber_times = results[^1] if not isinstance(results[^1], Exception) else {"error": str(results[^1])}
                ola_estimates = results[^2] if not isinstance(results[^2], Exception) else {"error": str(results[^2])}
                
                # Combine and format results
                combined_results = self._format_combined_results(
                    uber_prices, uber_times, ola_estimates
                )
                
                return json.dumps(combined_results, indent=2)
                
            except Exception as e:
                return json.dumps({"error": f"Aggregation failed: {str(e)}"})
        
        @self.server.tool()
        async def check_authentication_status() -> str:
            """Check authentication status for both services"""
            status = {
                "uber": {
                    "authenticated": True,  # Client credentials are always available
                    "method": "client_credentials"
                },
                "ola": {
                    "authenticated": self.ola_service.auth_manager.is_authenticated(),
                    "method": "oauth_user_token"
                }
            }
            
            return json.dumps(status, indent=2)
    
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
                    "price_estimates": uber_prices,
                    "time_estimates": uber_times
                },
                "ola": {
                    "estimates": ola_estimates
                }
            },
            "comparison": [],
            "recommendation": None
        }
        
        # Process and rank options (simplified)
        comparison_options = []
        
        # Process Uber estimates
        if "prices" in uber_prices:
            uber_time_map = {}
            if "times" in uber_times:
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
        
        # Process Ola estimates
        if "categories" in ola_estimates:
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
        
        # Sort by ETA (simplified ranking)
        valid_options = [opt for opt in comparison_options if opt.get("eta_minutes", -1) > 0]
        valid_options.sort(key=lambda x: x.get("eta_minutes", 999))
        
        combined["comparison"] = valid_options
        combined["recommendation"] = valid_options[^0] if valid_options else None
        
        return combined

# Entry point for MCP server
async def main():
    aggregator = RideAggregatorMCP()
    
    import mcp.server.stdio
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await aggregator.server.run(
            read_stream, 
            write_stream, 
            aggregator.server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
```


## Phase 5: Configuration and Setup

### Environment Configuration

Create `.env.example`:

```bash
# Uber API Configuration
UBER_CLIENT_ID=your_uber_client_id
UBER_CLIENT_SECRET=your_uber_client_secret

# Ola API Configuration
OLA_APP_TOKEN=your_ola_app_token
OLA_CLIENT_ID=your_ola_client_id
OLA_CLIENT_SECRET=your_ola_client_secret
OLA_REDIRECT_URI=http://localhost:8080/callback
```


### One-Time Setup Script

Create `setup_auth.py`:

```python
#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv
from auth.ola_auth import OlaAuthSetup

def main():
    load_dotenv()
    
    print("🚗 Jarvis Ride Aggregator - Authentication Setup")
    print("=" * 50)
    
    # Check Uber configuration
    uber_client_id = os.getenv("UBER_CLIENT_ID")
    uber_client_secret = os.getenv("UBER_CLIENT_SECRET")
    
    if not uber_client_id or not uber_client_secret:
        print("❌ Uber credentials missing in .env file")
        print("Please add UBER_CLIENT_ID and UBER_CLIENT_SECRET")
        return False
    else:
        print("✅ Uber credentials configured (client credentials)")
    
    # Check Ola configuration
    ola_app_token = os.getenv("OLA_APP_TOKEN")
    ola_client_id = os.getenv("OLA_CLIENT_ID")
    ola_redirect_uri = os.getenv("OLA_REDIRECT_URI")
    
    if not all([ola_app_token, ola_client_id, ola_redirect_uri]):
        print("❌ Ola credentials missing in .env file")
        print("Please add OLA_APP_TOKEN, OLA_CLIENT_ID, and OLA_REDIRECT_URI")
        return False
    
    # Check if Ola is already set up
    if os.path.exists("config/ola_auth_config.json"):
        print("✅ Ola authentication already configured")
        choice = input("Reconfigure Ola authentication? (y/N): ").lower()
        if choice != 'y':
            print("Setup complete!")
            return True
    
    # Set up Ola authentication
    print("\n🔧 Setting up Ola authentication...")
    try:
        ola_setup = OlaAuthSetup(
            client_id=ola_client_id,
            client_secret=os.getenv("OLA_CLIENT_SECRET"),
            redirect_uri=ola_redirect_uri
        )
        
        ola_setup.setup_user_authentication()
        print("\n🎉 Setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```


## Phase 6: Integration with Jarvis Agent

### Agent Integration

Create `jarvis_integration.py`:

```python
from typing import Dict, Any
import asyncio
import subprocess
import json

class JarvisRideIntegration:
    def __init__(self):
        self.mcp_process = None
        
    async def start_mcp_server(self):
        """Start the MCP server as a subprocess"""
        self.mcp_process = await asyncio.create_subprocess_exec(
            "python", "mcp_servers/ride_aggregator_mcp.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )
        
    async def get_ride_options(
        self, 
        pickup_coords: tuple, 
        drop_coords: tuple
    ) -> Dict[str, Any]:
        """Get ride options through MCP server"""
        if not self.mcp_process:
            await self.start_mcp_server()
        
        # Format MCP request
        request = {
            "method": "tools/call",
            "params": {
                "name": "get_ride_estimates",
                "arguments": {
                    "pickup_latitude": pickup_coords[^0],
                    "pickup_longitude": pickup_coords[^1],
                    "drop_latitude": drop_coords[^0],
                    "drop_longitude": drop_coords[^1]
                }
            }
        }
        
        # Send request to MCP server
        request_json = json.dumps(request) + "\n"
        self.mcp_process.stdin.write(request_json.encode())
        await self.mcp_process.stdin.drain()
        
        # Read response
        response_line = await self.mcp_process.stdout.readline()
        response = json.loads(response_line.decode())
        
        return response
    
    async def check_service_status(self) -> Dict[str, Any]:
        """Check authentication status of services"""
        if not self.mcp_process:
            await self.start_mcp_server()
        
        request = {
            "method": "tools/call", 
            "params": {
                "name": "check_authentication_status"
            }
        }
        
        request_json = json.dumps(request) + "\n"
        self.mcp_process.stdin.write(request_json.encode())
        await self.mcp_process.stdin.drain()
        
        response_line = await self.mcp_process.stdout.readline()
        response = json.loads(response_line.decode())
        
        return response
```


## Phase 7: Testing and Deployment

### Testing Scripts

Create `test_integration.py`:

```python
import asyncio
from jarvis_integration import JarvisRideIntegration

async def test_ride_aggregation():
    """Test the ride aggregation functionality"""
    integration = JarvisRideIntegration()
    
    # Test coordinates (Bangalore locations)
    pickup_coords = (12.9716, 77.5946)  # MG Road
    drop_coords = (12.9352, 77.6245)    # Koramangala
    
    print("Testing ride aggregation...")
    
    # Check service status
    status = await integration.check_service_status()
    print("Service Status:", status)
    
    # Get ride options
    ride_options = await integration.get_ride_options(pickup_coords, drop_coords)
    print("Ride Options:", ride_options)

if __name__ == "__main__":
    asyncio.run(test_ride_aggregation())
```


## Implementation Timeline

### Week 1: Foundation Setup

- Set up project structure and dependencies[^8]
- Implement Uber client credentials authentication[^1][^4]
- Create basic service classes


### Week 2: Ola Integration

- Implement Ola OAuth setup workflow[^5][^6]
- Create one-time authentication script
- Test both authentication mechanisms


### Week 3: MCP Server Development

- Build aggregator MCP server[^8][^9]
- Implement parallel request handling
- Add error handling and resilience patterns


### Week 4: Integration and Testing

- Integrate with Jarvis agent
- Comprehensive testing of both services
- Performance optimization and monitoring setup

This implementation plan provides a robust foundation for your Jarvis ride aggregator, correctly handling the different authentication requirements of Uber (dynamic client credentials) and Ola (one-time OAuth setup)[^1][^5]. The modular architecture ensures maintainability while the MCP server integration provides seamless connectivity with your Jarvis agent.

<div style="text-align: center">⁂</div>

[^1]: https://developer.uber.com/docs/businesses/receipts/guides/authentication

[^2]: https://developer.uber.com/docs/deliveries/guides/authentication

[^3]: https://developer.uber.com/docs/vouchers/guides/authentication

[^4]: https://developer.uber.com/docs/consumer-identity/guides/client-access-token

[^5]: https://developers.olacabs.com/docs/access-token

[^6]: https://developers.olacabs.com/docs/login-signup

[^7]: https://developers.olacabs.com/docs/cab-booking

[^8]: https://stytch.com/blog/oauth-for-mcp-explained-with-a-real-world-example/

[^9]: https://modelcontextprotocol.io/specification/draft/basic/authorization

[^10]: https://developer.uber.com/docs/drivers/guides/authentication

[^11]: https://developer.uber.com/docs/consumer-identity/api/asymmetric_key_auth

[^12]: https://developer.uber.com/docs/scim/guides/authentication

[^13]: https://developer.uber.com/docs/riders/guides/authentication/introduction

[^14]: https://maps.olakrutrim.com/docs/auth

[^15]: https://stackoverflow.com/questions/28527665/how-to-get-ola-cabs-api-key

[^16]: https://www.youtube.com/watch?v=xl0tKarMgrw

[^17]: https://docs.oracle.com/en/cloud/paas/integration-cloud/oracle-integration-gov/configure-oauth-authentication-using-client-credentials.html

[^18]: https://stackoverflow.com/questions/43973468/how-to-integrate-ola-cab-api-and-get-the-amount-to-be-paid-for-the-cab

[^19]: https://www.youtube.com/watch?v=evb02h5nIYs

[^20]: https://www.descope.com/blog/post/mcp-auth-spec

[^21]: https://stackoverflow.com/questions/36719540/how-can-i-get-an-oauth2-access-token-using-python

[^22]: https://stytch.com/blog/mcp-authentication-and-authorization-servers/

[^23]: https://developer.uber.com/docs/eats/guides/authentication

[^24]: https://developer.adobe.com/developer-console/docs/guides/authentication/ServerToServerAuthentication/implementation/

[^25]: https://maps.olakrutrim.com/docs

[^26]: https://support.instamojo.com/hc/en-us/articles/212214265-How-do-I-get-my-Client-ID-and-Client-Secret

[^27]: https://google.github.io/adk-docs/tools/authentication/

[^28]: https://aaronparecki.com/2025/04/03/15/oauth-for-model-context-protocol

[^29]: https://cloud.google.com/blog/topics/developers-practitioners/use-google-adk-and-mcp-with-an-external-server

[^30]: https://developers.google.com/identity/protocols/oauth2

