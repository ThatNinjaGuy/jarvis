from app.api.enhanced_routes import app
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
if not os.environ.get("K_SERVICE"):  # Not running in Cloud Run
    load_dotenv()

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
