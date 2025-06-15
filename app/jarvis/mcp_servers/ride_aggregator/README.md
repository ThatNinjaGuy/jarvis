# Ride Aggregator MCP Server

This MCP server provides ride booking functionality through multiple providers (Uber, Ola) for the Jarvis agent. It allows comparing prices and ETAs across providers and booking rides.

## Features

- Get ride estimates from multiple providers (Uber, Ola)
- Compare prices and ETAs
- Get best recommendations based on price and ETA
- Book rides with any available provider
- Track ride status and location
- Check authentication status for providers

## Setup

1. Add the following environment variables to your `.env` file:

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

2. For Ola authentication, run the setup script:

```bash
python setup_auth.py
```

## Available Tools

### 1. get_ride_estimates

Gets ride estimates from all available providers.

**Parameters:**

- pickup_latitude: float
- pickup_longitude: float
- drop_latitude: float
- drop_longitude: float

**Returns:**

```json
{
  "timestamp": 1234567890,
  "providers": {
    "uber": {
      "price_estimates": {...},
      "time_estimates": {...}
    },
    "ola": {
      "estimates": {...}
    }
  },
  "comparison": [
    {
      "provider": "uber",
      "product_id": "...",
      "display_name": "UberX",
      "price_estimate": "₹200-250",
      "eta_minutes": 5,
      "currency": "INR",
      "surge_multiplier": 1.0
    },
    {
      "provider": "ola",
      "category_id": "...",
      "display_name": "Mini",
      "eta_minutes": 7,
      "currency": "INR",
      "ride_estimate": {...}
    }
  ],
  "recommendation": {...}
}
```

### 2. book_ride

Books a ride with the specified provider.

**Parameters:**

- provider: str ("uber" or "ola")
- pickup_latitude: float
- pickup_longitude: float
- drop_latitude: float
- drop_longitude: float
- product_id: str (Uber's product_id or Ola's category_id)
- payment_method_id: Optional[str]
- rider_name: Optional[str]
- rider_phone: Optional[str]

**Returns:**

```json
{
  "success": true,
  "provider": "uber",
  "booking_id": "...",
  "status": "accepted",
  "driver_details": {
    "name": "John Doe",
    "phone": "+1234567890",
    "rating": 4.8
  },
  "vehicle_details": {
    "make": "Toyota",
    "model": "Camry",
    "license_plate": "ABC123",
    "color": "Black"
  },
  "estimated_pickup_time": "2024-03-20T14:30:00Z"
}
```

### 3. track_ride

Tracks the status and location of a booked ride.

**Parameters:**

- provider: str ("uber" or "ola")
- booking_id: str

**Returns:**

```json
{
  "success": true,
  "provider": "uber",
  "booking_id": "...",
  "status": "en_route",
  "current_location": {
    "latitude": 12.9716,
    "longitude": 77.5946
  },
  "estimated_arrival_time": "2024-03-20T14:35:00Z"
}
```

### 4. check_auth_status

Checks authentication status for all ride providers.

**Parameters:** None

**Returns:**

```json
{
  "uber": {
    "authenticated": true,
    "method": "client_credentials"
  },
  "ola": {
    "authenticated": true,
    "method": "oauth_user_token"
  }
}
```

## Integration with Jarvis Agent

The server is automatically integrated with the Jarvis agent through the MCP protocol. The agent can access the ride booking functionality through the following tools:

```python
# Example agent usage

# Get ride estimates
estimates = await agent.tools.get_ride_estimates(
    pickup_latitude=12.9716,
    pickup_longitude=77.5946,
    drop_latitude=12.9352,
    drop_longitude=77.6245
)

# Book a ride
booking = await agent.tools.book_ride(
    provider="uber",
    pickup_latitude=12.9716,
    pickup_longitude=77.5946,
    drop_latitude=12.9352,
    drop_longitude=77.6245,
    product_id="UberX",
    rider_name="John Doe",
    rider_phone="+1234567890"
)

# Track the ride
status = await agent.tools.track_ride(
    provider="uber",
    booking_id=booking["booking_id"]
)
```

## Error Handling

The server handles various error cases:

- Authentication failures
- API errors from providers
- Invalid coordinates or parameters
- Network issues
- Booking failures
- Tracking failures

All errors are properly logged and returned in a structured format.
