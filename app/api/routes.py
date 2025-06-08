import os
from pathlib import Path
import logging
from fastapi import FastAPI, Query, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
import asyncio

from app.config.agent_session import start_agent_session
from app.communication_handlers import handle_agent_to_client_messaging, handle_client_to_agent_messaging
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

app = FastAPI()

# Get the directory containing this file
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    """Serves the index.html"""
    logging.info("Serving index.html")
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Client websocket endpoint"""
    try:
        # Wait for client connection
        await websocket.accept()
        logging.info(f"Client #{session_id} connected, audio mode: {is_audio}")
        
        # Start agent session
        session_data = await start_agent_session(session_id, is_audio == "true")
        
        # Start tasks
        agent_to_client_task = asyncio.create_task(
            handle_agent_to_client_messaging(websocket, session_data["live_events"])
        )
        client_to_agent_task = asyncio.create_task(
            handle_client_to_agent_messaging(websocket, session_data["live_request_queue"])
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
            
    except Exception as e:
        logging.error(f"Error setting up WebSocket for client #{session_id}: {str(e)}", exc_info=True)
        raise 