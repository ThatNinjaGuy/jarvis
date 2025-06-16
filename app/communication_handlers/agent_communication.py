import base64
import json
import logging
import asyncio
from typing import AsyncIterable, Optional

from fastapi import WebSocket
from google.adk.events.event import Event
from google.genai import types
from starlette.websockets import WebSocketDisconnect, WebSocketState

# Import memory integration
from app.config.agent_session import update_session_memory, is_memory_enabled


async def handle_agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None], session_data=None
):
    """Handle communication from agent to client with optional memory tracking"""
    
    session_id = None
    current_response = ""
    
    # Extract session info if available
    if session_data and isinstance(session_data, dict):
        session_id = getattr(session_data.get("session"), "id", None)
    
    try:
        async for event in live_events:
            if event is None:
                continue

            # Check WebSocket state before processing
            if websocket.client_state == WebSocketState.DISCONNECTED:
                logging.warning("WebSocket disconnected, stopping message processing")
                break

            try:
                # Handle turn completion or interruption
                if event.turn_complete or event.interrupted:
                    await _send_turn_status(websocket, event)
                    
                    # Store complete response in memory if available
                    if session_id and current_response and is_memory_enabled():
                        try:
                            await update_session_memory(
                                session_id=session_id,
                                user_input="",
                                agent_response=current_response,
                                tools_used=_extract_tools_from_response(current_response)
                            )
                            current_response = ""  # Reset for next interaction
                        except Exception as e:
                            logging.warning(f"Failed to store agent response in memory: {str(e)}")
                    
                    continue

                # Process event content with WebSocket state check
                if websocket.client_state == WebSocketState.CONNECTED:
                    await _process_event_content(websocket, event, session_id)
                else:
                    logging.warning("Skipping message processing - WebSocket not connected")
                    break
                
                # Accumulate response text for memory storage
                part = event.content and event.content.parts and event.content.parts[0]
                if part and isinstance(part, types.Part) and part.text and event.partial:
                    current_response += part.text

            except WebSocketDisconnect:
                logging.info("WebSocket disconnected during message processing")
                break
            except Exception as e:
                logging.error(f"Error processing event: {str(e)}", exc_info=True)
                # Continue processing other events unless WebSocket is disconnected
                if websocket.client_state == WebSocketState.DISCONNECTED:
                    break
                
    except Exception as e:
        logging.error(f"Error in agent-to-client messaging: {str(e)}", exc_info=True)
        raise


async def _send_turn_status(websocket: WebSocket, event: Event):
    """Send turn completion or interruption status"""
    message = {
        "turn_complete": event.turn_complete,
        "interrupted": event.interrupted,
    }
    await websocket.send_text(json.dumps(message))
    logging.info(f"[AGENT TO CLIENT]: Turn status - {message}")


async def _process_event_content(websocket: WebSocket, event: Event, session_id=None):
    """Process and send event content to client"""
    try:
        # Read the Content and its first Part
        part = event.content and event.content.parts and event.content.parts[0]
        if not part or not isinstance(part, types.Part):
            return

        # Check WebSocket state before sending
        if websocket.client_state != WebSocketState.CONNECTED:
            logging.warning("Cannot send message - WebSocket not connected")
            return

        # Handle text content
        if part.text and event.partial:
            await _send_text_content(websocket, part.text)

        # Handle audio content
        if _is_audio_part(part):
            await _send_audio_content(websocket, part)
            
    except WebSocketDisconnect:
        logging.info("WebSocket disconnected while processing event content")
        raise
    except Exception as e:
        logging.error(f"Error processing event content: {str(e)}", exc_info=True)
        raise


def _is_audio_part(part: types.Part) -> bool:
    """Check if the part contains audio data"""
    return (
        part.inline_data
        and part.inline_data.mime_type
        and part.inline_data.mime_type.startswith("audio/pcm")
    )


async def _send_text_content(websocket: WebSocket, text: str):
    """Send text content over WebSocket with state check"""
    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            logging.warning("Cannot send text - WebSocket not connected")
            return
            
        message = {
            "mime_type": "text/plain",
            "data": text,
            "role": "model"
        }
        await websocket.send_text(json.dumps(message))
    except Exception as e:
        logging.error(f"Error sending text content: {str(e)}", exc_info=True)
        raise


async def _send_audio_content(websocket: WebSocket, part: types.Part):
    """Send audio content to client"""
    audio_data = part.inline_data and part.inline_data.data
    if audio_data:
        message = {
            "mime_type": "audio/pcm",
            "data": base64.b64encode(audio_data).decode("ascii"),
            "role": "model",
        }
        await websocket.send_text(json.dumps(message))
        logging.debug(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.") 


def _extract_tools_from_response(response_text: str) -> list:
    """Extract tool usage from response text (simple heuristic)"""
    tools = []
    
    # Common tool indicators
    tool_indicators = {
        "calendar": ["scheduled", "appointment", "meeting", "event"],
        "email": ["sent email", "email sent", "message sent"],
        "maps": ["directions", "distance", "route"],
        "youtube": ["video", "found videos", "youtube"],
        "twitter": ["tweet", "posted", "twitter"],
        "database": ["query", "database", "table"]
    }
    
    response_lower = response_text.lower()
    for tool, indicators in tool_indicators.items():
        if any(indicator in response_lower for indicator in indicators):
            tools.append(tool)
    
    return tools 