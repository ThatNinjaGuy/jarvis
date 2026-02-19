from fastapi import APIRouter
from fastapi.responses import FileResponse
import logging
from pathlib import Path
from app.config.agent_session import is_memory_enabled

router = APIRouter()

# Get the directory containing this file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"


@router.get("/")
async def root():
    """Serves the index.html"""
    logging.info("Serving index.html")
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Enhanced Jarvis API",
        "memory_system": "active" if is_memory_enabled() else "disabled",
        "features": {
            "basic_agent": "active",
            "memory_system": is_memory_enabled(),
            "user_profiles": is_memory_enabled(),
            "contextual_memory": is_memory_enabled(),
        },
    }
