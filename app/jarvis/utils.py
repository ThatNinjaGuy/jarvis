"""
Utility functions.
"""

from datetime import datetime
from pytz import timezone

def get_current_time() -> dict:
    """
    Get the current time and date in IST timezone
    """
    # Get current time in IST 
    now = datetime.now(timezone('Asia/Kolkata'))

    # Format date as MM-DD-YYYY
    formatted_date = now.strftime("%m-%d-%Y")

    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "formatted_date": formatted_date,
    }
