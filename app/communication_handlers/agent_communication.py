import base64
import json
from typing import AsyncIterable

from fastapi import WebSocket
from google.adk.events.event import Event
from google.genai import types


async def handle_agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Handle communication from agent to client"""
    try:
        async for event in live_events:
            if event is None:
                continue

            # Handle turn completion or interruption
            if event.turn_complete or event.interrupted:
                await _send_turn_status(websocket, event)
                continue

            # Process event content
            await _process_event_content(websocket, event)
    except Exception as e:
        print(f"Error in agent-to-client messaging: {str(e)}")
        raise


async def _send_turn_status(websocket: WebSocket, event: Event):
    """Send turn completion or interruption status"""
    message = {
        "turn_complete": event.turn_complete,
        "interrupted": event.interrupted,
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: {message}")


async def _process_event_content(websocket: WebSocket, event: Event):
    """Process and send event content to client"""
    # Read the Content and its first Part
    part = event.content and event.content.parts and event.content.parts[0]
    if not part or not isinstance(part, types.Part):
        return

    # Handle text content
    if part.text and event.partial:
        await _send_text_content(websocket, part.text)

    # Handle audio content
    if _is_audio_part(part):
        await _send_audio_content(websocket, part)


def _is_audio_part(part: types.Part) -> bool:
    """Check if the part contains audio data"""
    return (
        part.inline_data
        and part.inline_data.mime_type
        and part.inline_data.mime_type.startswith("audio/pcm")
    )


async def _send_text_content(websocket: WebSocket, text: str):
    """Send text content to client"""
    message = {
        "mime_type": "text/plain",
        "data": text,
        "role": "model",
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: text/plain: {text}")


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
        print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.") 