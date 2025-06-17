import logging
import os
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers import setup_logging

def setup_cloud_logging():
    """Configure logging for Google Cloud environment"""
    if os.environ.get("K_SERVICE"):  # Running in Cloud Run
        # Create the Cloud Logging client
        client = google.cloud.logging.Client()
        
        # Get the default handler
        handler = CloudLoggingHandler(client)
        
        # Create a custom format that includes relevant information
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        
        # Also log werkzeug (web server) logs
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.addHandler(handler)
        
        # Log websocket activity
        websocket_logger = logging.getLogger('websockets')
        websocket_logger.setLevel(logging.INFO)
        websocket_logger.addHandler(handler)
        
        # Setup FastAPI logging
        fastapi_logger = logging.getLogger("fastapi")
        fastapi_logger.setLevel(logging.INFO)
        fastapi_logger.addHandler(handler)
        
        # Setup uvicorn logging
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.addHandler(handler)
        
        # Log a test message
        logging.info("Google Cloud Logging has been configured")
    else:
        # Local development logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ) 