import os
from pathlib import Path
import logging
from fastapi import FastAPI, Query, WebSocket, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
import asyncio
from typing import Dict, Any, Optional

# Import your existing functionality
from app.config.agent_session import (
    start_agent_session, 
    end_agent_session,
    update_session_memory,
    is_memory_enabled,
    get_memory_services
)
from app.communication_handlers import handle_agent_to_client_messaging, handle_client_to_agent_messaging
from app.config.logging_config import setup_cloud_logging
from app.config.database import db_config
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService

# Setup cloud logging
setup_cloud_logging()

app = FastAPI(title="Enhanced Jarvis API", description="Jarvis with Multi-tiered Memory System")

# Get the directory containing this file
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Initialize services for API endpoints
db_session = next(db_config.get_db_session())
user_profile_service = UserProfileService(db_session)
memory_service = JarvisMemoryService(db_session)

@app.get("/")
async def root():
    """Serves the index.html"""
    logging.info("Serving index.html")
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)

# Memory API endpoints (only available if memory is enabled)
@app.get("/api/user/{user_id}/profile")
async def get_user_profile(user_id: str):
    """Get user profile information"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        profile = await services["user_profile_service"].get_user_profile(user_id)
        return {"status": "success", "data": profile}
    except Exception as e:
        logging.error(f"Error getting user profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/preferences")
async def get_user_preferences(user_id: str, category: Optional[str] = None):
    """Get user preferences"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        preferences = await services["user_profile_service"].get_user_preferences(user_id, category)
        return {"status": "success", "data": preferences}
    except Exception as e:
        logging.error(f"Error getting user preferences: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/preferences")
async def update_user_preference(
    user_id: str,
    preference_data: Dict[str, Any]
):
    """Update user preference"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        await services["user_profile_service"].update_preference(
            user_id=user_id,
            key=preference_data["key"],
            value=preference_data["value"],
            preference_type=preference_data.get("preference_type", "explicit"),
            confidence=preference_data.get("confidence", 1.0),
            category=preference_data.get("category", "general")
        )
        return {"status": "success", "message": "Preference updated successfully"}
    except Exception as e:
        logging.error(f"Error updating user preference: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/memories/search")
async def search_memories(
    user_id: str,
    query: str,
    memory_types: Optional[str] = None,
    limit: int = 5,
    importance_threshold: float = 0.0
):
    """Search user memories"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        memory_types_list = memory_types.split(",") if memory_types else None
        memories = await services["memory_service"].search_memories(
            user_id=user_id,
            query=query,
            memory_types=memory_types_list,
            limit=limit,
            importance_threshold=importance_threshold
        )
        return {"status": "success", "data": memories}
    except Exception as e:
        logging.error(f"Error searching memories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/memories/contextual")
async def get_contextual_memories(
    user_id: str,
    query: Optional[str] = None,
    session_topics: Optional[str] = None,
    recent_tools: Optional[str] = None,
    max_memories: int = 10
):
    """Get contextually relevant memories"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        current_context = {}
        if query:
            current_context["query"] = query
        if session_topics:
            current_context["session_topics"] = session_topics.split(",")
        if recent_tools:
            current_context["recent_tools"] = recent_tools.split(",")
            
        context_result = await services["memory_service"].get_contextual_memories(
            user_id=user_id,
            current_context=current_context,
            max_memories=max_memories
        )
        return {"status": "success", "data": context_result}
    except Exception as e:
        logging.error(f"Error getting contextual memories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/memories")
async def store_memory(user_id: str, memory_data: Dict[str, Any]):
    """Store a new memory"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        memory_id = await services["memory_service"].store_memory(
            user_id=user_id,
            content=memory_data["content"],
            memory_type=memory_data.get("memory_type", "conversation"),
            session_id=memory_data.get("session_id"),
            importance_score=memory_data.get("importance_score", 0.5),
            tags=memory_data.get("tags", [])
        )
        return {"status": "success", "data": {"memory_id": memory_id}}
    except Exception as e:
        logging.error(f"Error storing memory: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/sessions/{session_id}/summary")
async def get_session_summary(user_id: str, session_id: str):
    """Get session summary"""
    if not is_memory_enabled():
        raise HTTPException(status_code=503, detail="Memory system not available")
    
    try:
        services = get_memory_services()
        summary = await services["user_profile_service"].get_session_summary(user_id, session_id)
        return {"status": "success", "data": summary}
    except Exception as e:
        logging.error(f"Error getting session summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced WebSocket endpoint using your existing communication handlers
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Enhanced client websocket endpoint with memory capabilities"""
    try:
        # Wait for client connection
        await websocket.accept()
        logging.info(f"Client #{session_id} connected, audio mode: {is_audio}")
        
        # Start agent session (will use enhanced session if memory is available)
        session_data = await start_agent_session(
            session_id, 
            is_audio == "true",
            use_memory=True  # Try to use memory if available
        )
        
        # Create communication handlers with session data for memory tracking
        agent_to_client_task = asyncio.create_task(
            handle_agent_to_client_messaging(
                websocket, 
                session_data["live_events"],
                session_data  # Pass session data for memory tracking
            )
        )
        client_to_agent_task = asyncio.create_task(
            handle_client_to_agent_messaging(
                websocket, 
                session_data["live_request_queue"],
                session_data  # Pass session data for memory tracking
            )
        )
        
        try:
            await asyncio.gather(agent_to_client_task, client_to_agent_task)
        except WebSocketDisconnect:
            logging.info(f"Client #{session_id} disconnected normally")
        except Exception as e:
            logging.error(f"Error in WebSocket connection for client #{session_id}: {str(e)}", exc_info=True)
        finally:
            # Clean up tasks
            agent_to_client_task.cancel()
            client_to_agent_task.cancel()
            try:
                await agent_to_client_task
                await client_to_agent_task
            except asyncio.CancelledError:
                pass
            
            # End session (will capture memory if available)
            await end_agent_session(session_id)
            
    except Exception as e:
        logging.error(f"Error setting up WebSocket for client #{session_id}: {str(e)}", exc_info=True)
        raise

# Health check endpoint
@app.get("/health")
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
            "contextual_memory": is_memory_enabled()
        }
    }

# Memory system status endpoint
@app.get("/api/memory/status")
async def memory_system_status():
    """Get memory system status"""
    if not is_memory_enabled():
        return {
            "status": "disabled",
            "message": "Memory system is not available",
            "services": {
                "user_profile_service": "disabled",
                "memory_service": "disabled",
                "enhanced_session_service": "disabled"
            }
        }
    
    try:
        services = get_memory_services()
        # Check if memory service is working
        test_result = await services["memory_service"].search_memories(
            user_id="health_check",
            query="test",
            limit=1
        )
        
        return {
            "status": "active",
            "vector_database": "connected",
            "sql_database": "connected",
            "services": {
                "user_profile_service": "active",
                "memory_service": "active",
                "enhanced_session_service": "active"
            }
        }
    except Exception as e:
        logging.error(f"Memory system health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "services": {
                "user_profile_service": "unknown",
                "memory_service": "error",
                "enhanced_session_service": "unknown"
            }
        }