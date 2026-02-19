from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.config.logging_config import setup_cloud_logging
from app.config.database import db_config
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService

# Setup cloud logging
setup_cloud_logging()

# Create FastAPI app
app = FastAPI(
    title="Enhanced Jarvis API", description="Jarvis with Multi-tiered Memory System"
)

# Get the directory containing this file
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Initialize services for API endpoints
db_session = next(db_config.get_db_session())
user_profile_service = UserProfileService(db_session)
memory_service = JarvisMemoryService(db_session)

# Import routers after app creation to avoid circular imports
from .routers import ui, memory, chatbot

# Include routers
app.include_router(ui.router, tags=["UI"])
app.include_router(memory.router, prefix="/api", tags=["Memory"])
app.include_router(chatbot.router, tags=["Chatbot"])
