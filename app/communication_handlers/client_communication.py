import base64
import json
import logging
import asyncio
from typing import Optional

from fastapi import WebSocket
from google.adk.agents import LiveRequestQueue
from google.genai import types
from starlette.websockets import WebSocketDisconnect

# Import memory integration
from app.config.agent_session import update_session_memory, is_memory_enabled

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

async def handle_client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue, session_data=None
):
    """Handle communication from client to agent with optional memory tracking"""
    
    session_id = None
    retry_count = 0
    
    # Extract session info if available
    if session_data and isinstance(session_data, dict):
        session_id = getattr(session_data.get("session"), "id", None)
    
    while True:
        try:
            # Decode JSON message with timeout
            try:
                message_json = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60  # 60 second timeout for receiving messages
                )
                message = json.loads(message_json)
                retry_count = 0  # Reset retry count on successful message
            except asyncio.TimeoutError:
                logging.warning("WebSocket receive timeout")
                continue
            except WebSocketDisconnect:
                logging.info("WebSocket disconnected normally")
                break
            
            # Process message based on mime type
            await _process_client_message(websocket, live_request_queue, message, session_id)
            
        except Exception as e:
            retry_count += 1
            if retry_count >= MAX_RETRIES:
                logging.error(f"Max retries ({MAX_RETRIES}) reached. Error: {str(e)}", exc_info=True)
                raise
            
            logging.warning(f"Error processing client message (attempt {retry_count}/{MAX_RETRIES}): {str(e)}")
            await asyncio.sleep(RETRY_DELAY * retry_count)  # Exponential backoff
            continue


async def _process_client_message(
    websocket: WebSocket, live_request_queue: LiveRequestQueue, message: dict, session_id=None
):
    """Process client message based on mime type"""
    try:
        mime_type = message["mime_type"]
        data = message["data"]
        role = message.get("role", "user")  # Default to 'user' if role is not provided

        if mime_type == "text/plain":
            await _handle_text_message(live_request_queue, data, role, session_id)
        elif mime_type == "audio/pcm":
            await _handle_audio_message(live_request_queue, data, session_id)
        else:
            raise ValueError(f"Mime type not supported: {mime_type}")
    except KeyError as e:
        raise ValueError(f"Invalid message format: missing required field {str(e)}")
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}", exc_info=True)
        raise


async def _handle_text_message(
    live_request_queue: LiveRequestQueue, data: str, role: str, session_id=None
):
    """Handle text message from client"""
    content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
    live_request_queue.send_content(content=content)
    logging.info(f"[CLIENT TO AGENT]: {data}")

    # Store user input in memory if available
    if session_id and data and is_memory_enabled():
        try:
            # Store user input - agent response will be captured separately
            await update_session_memory(
                session_id=session_id,
                user_input=data,
                agent_response="",  # Will be updated when agent responds
                tools_used=[]
            )
        except Exception as e:
            logging.warning(f"Failed to store user input in memory: {str(e)}")


async def _handle_audio_message(live_request_queue: LiveRequestQueue, data: str, session_id=None):
    """Handle audio message from client"""
    decoded_data = base64.b64decode(data)
    live_request_queue.send_realtime(
        types.Blob(data=decoded_data, mime_type="audio/pcm")
    )
    logging.debug(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes") 
    
    # Note: Audio transcription would need to be handled separately for memory storage
    # This could be implemented when audio transcription is available 