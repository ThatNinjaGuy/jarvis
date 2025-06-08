import os
import logging
from google.adk.agents import LiveRequestQueue, Agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from app.jarvis.agent import root_agent
from app.jarvis.utils import load_environment
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

# Load environment variables
load_environment()

# Only load .env in development
if not os.environ.get("K_SERVICE"):  # K_SERVICE is set in Cloud Run
    from dotenv import load_dotenv
    load_dotenv()

APP_NAME = "Jarvis"
session_service = InMemorySessionService()


async def start_agent_session(session_id, is_audio=False):
    """Starts an agent session and returns the necessary components for communication"""
    
    logging.info(f"Starting new agent session for user {session_id}, audio mode: {is_audio}")
    
    # Create a Session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )
    logging.debug(f"Created session with ID: {session_id}")

    # Create a Runner
    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )
    logging.debug("Created agent runner")

    # Create speech config with voice settings
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )
    logging.debug("Configured speech settings with voice: Puck")

    # Create run config with basic settings
    config = {
        "response_modalities": [types.Modality.AUDIO if is_audio else types.Modality.TEXT],
        "speech_config": speech_config,
        "streaming_mode": StreamingMode.BIDI  # Use bidirectional streaming
    }

    # Add output_audio_transcription when audio is enabled to get both audio and text
    if is_audio:
        config["output_audio_transcription"] = {}
        logging.debug("Added audio transcription to config")

    run_config = RunConfig(**config)
    logging.debug("Created run configuration")

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    logging.info(f"Agent session {session_id} started successfully")
    
    return {
        "session": session,
        "live_events": live_events,
        "live_request_queue": live_request_queue,
        "runner": runner  # Add runner to keep it in scope
    } 