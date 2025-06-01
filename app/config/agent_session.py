import os
from dotenv import load_dotenv
from google.adk.agents import LiveRequestQueue, Agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from app.jarvis.agent import root_agent

# Load Gemini API Key
load_dotenv()

APP_NAME = "Jarvis"
session_service = InMemorySessionService()


def start_agent_session(session_id, is_audio=False):
    """Starts an agent session and returns the necessary components for communication"""
    
    # Create a Session
    session = session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )

    # Create a Runner
    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )

    # Create speech config with voice settings
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )

    # Create run config with basic settings
    config = {
        "response_modalities": [types.Modality.AUDIO if is_audio else types.Modality.TEXT],
        "speech_config": speech_config,
        "streaming_mode": StreamingMode.BIDI  # Use bidirectional streaming
    }

    # Add output_audio_transcription when audio is enabled to get both audio and text
    if is_audio:
        config["output_audio_transcription"] = {}

    run_config = RunConfig(**config)

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    
    return {
        "session": session,
        "live_events": live_events,
        "live_request_queue": live_request_queue
    } 