import base64
import json

from fastapi import WebSocket
from google.adk.agents import LiveRequestQueue
from google.genai import types


async def handle_client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue
):
    """Handle communication from client to agent"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        message = json.loads(message_json)
        
        # Process message based on mime type
        await _process_client_message(websocket, live_request_queue, message)


async def _process_client_message(
    websocket: WebSocket, live_request_queue: LiveRequestQueue, message: dict
):
    """Process client message based on mime type"""
    mime_type = message["mime_type"]
    data = message["data"]
    role = message.get("role", "user")  # Default to 'user' if role is not provided

    if mime_type == "text/plain":
        await _handle_text_message(live_request_queue, data, role)
    elif mime_type == "audio/pcm":
        await _handle_audio_message(live_request_queue, data)
    else:
        raise ValueError(f"Mime type not supported: {mime_type}")


async def _handle_text_message(
    live_request_queue: LiveRequestQueue, data: str, role: str
):
    """Handle text message from client"""
    content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
    live_request_queue.send_content(content=content)
    print(f"[CLIENT TO AGENT PRINT]: {data}")


async def _handle_audio_message(live_request_queue: LiveRequestQueue, data: str):
    """Handle audio message from client"""
    decoded_data = base64.b64decode(data)
    live_request_queue.send_realtime(
        types.Blob(data=decoded_data, mime_type="audio/pcm")
    )
    print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes") 