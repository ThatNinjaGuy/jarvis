"""
MCP Ride Aggregator Server package for handling ride booking operations through MCP protocol.

This package provides functionality to:
- Get ride estimates from multiple providers (Uber, Ola)
- Compare prices and ETAs
- Book rides
- Track ride status
"""

from .services import UberService, OlaService, RideAggregatorService
from .auth import UberAuthManager, OlaAuthManager, OlaAuthSetup

__all__ = [
    'UberService',
    'OlaService',
    'RideAggregatorService',
    'UberAuthManager',
    'OlaAuthManager',
    'OlaAuthSetup'
] 