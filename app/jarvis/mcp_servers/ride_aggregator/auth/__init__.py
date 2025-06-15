"""
Authentication package for ride booking services.

This package provides authentication managers for:
- Uber (client credentials flow)
- Ola (OAuth user token flow)
"""

from .uber_auth import UberAuthManager
from .ola_auth import OlaAuthManager, OlaAuthSetup

__all__ = ['UberAuthManager', 'OlaAuthManager', 'OlaAuthSetup'] 