from app.api.routes import app
import uvicorn
import os
from dotenv import load_dotenv
from app.config.agent_session import initialize_memory_system

# Load environment variables
if not os.environ.get("K_SERVICE"):  # Not running in Cloud Run
    load_dotenv()

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await initialize_memory_system()

if __name__ == "__main__":
    # Get port from environment or default to 8000
    port = int(os.environ.get("PORT", 8000))
    
    # Run the FastAPI app with uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
