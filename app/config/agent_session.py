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

# Enhanced imports for memory system
from app.config.database import db_config
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService
from app.services.enhanced_session_service import EnhancedSessionService

import asyncio

# Setup cloud logging
setup_cloud_logging()

# Load environment variables
load_environment()

# Only load .env in development
if not os.environ.get("K_SERVICE"):  # K_SERVICE is set in Cloud Run
    from dotenv import load_dotenv
    load_dotenv()

APP_NAME = "Jarvis"

# Initialize both session services for backward compatibility
session_service = InMemorySessionService()

# Initialize enhanced memory system
MEMORY_ENABLED = False
user_profile_service = None
memory_service = None
enhanced_session_service = None

async def initialize_memory_system():
    """Initialize the memory system asynchronously"""
    global MEMORY_ENABLED, user_profile_service, memory_service, enhanced_session_service
    
    try:
        db_config.create_tables()
        db_session = next(db_config.get_db_session())
        
        # Initialize services
        user_profile_service = UserProfileService(db_session)
        memory_service = JarvisMemoryService(db_session)
        
        # Test memory service connection
        try:
            await asyncio.wait_for(
                memory_service.search_memories(
                    user_id="test",
                    query="test connection",
                    limit=1
                ),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            raise Exception("Memory service connection timed out")
        except Exception as e:
            logging.warning(f"Memory service test failed: {str(e)}")
            # Continue anyway, might work during actual usage
        
        # Create enhanced session service
        enhanced_session_service = EnhancedSessionService(
            db_url=db_config.database_url,
            db_session=db_session,
            user_profile_service=user_profile_service,
            memory_service=memory_service
        )
        
        MEMORY_ENABLED = True
        logging.info("Enhanced memory system initialized successfully")
        
    except Exception as e:
        logging.warning(f"Memory system initialization failed: {str(e)}")
        MEMORY_ENABLED = False
        user_profile_service = None
        memory_service = None
        enhanced_session_service = None

async def start_agent_session(session_id, is_audio=False, use_memory=True):  # Re-enable memory
    """Starts an agent session and returns the necessary components for communication
    
    Args:
        session_id: Unique session identifier
        is_audio: Whether to enable audio mode
        use_memory: Whether to use enhanced memory capabilities (defaults to True)
    """
    
    logging.info(f"Starting agent session for user {session_id}, audio mode: {is_audio}, memory: {use_memory and MEMORY_ENABLED}")
    
    # Use enhanced session service if available and requested
    if use_memory and MEMORY_ENABLED and enhanced_session_service:
        try:
            return await _start_enhanced_session(session_id, is_audio)
        except Exception as e:
            logging.warning(f"Enhanced session failed, falling back to basic mode: {str(e)}")
            return await _start_basic_session(session_id, is_audio)
    else:
        return await _start_basic_session(session_id, is_audio)


async def _start_enhanced_session(session_id, is_audio=False):
    """Start session with enhanced memory capabilities"""
    
    try:
        # Get user context and memories
        user_profile = await user_profile_service.get_user_profile(session_id)
        user_preferences = await user_profile_service.get_user_preferences(session_id)
        
        # Get contextual memories (with better default context)
        try:
            contextual_memories = await memory_service.get_contextual_memories(
                user_id=session_id,
                current_context={"query": "session initialization", "session_start": True},
                max_memories=5
            )
        except Exception as e:
            logging.warning(f"Failed to get contextual memories: {str(e)}")
            contextual_memories = {"relevant_memories": [], "context_summary": ""}
        
        # Create enhanced session with context
        session = await enhanced_session_service.create_session_with_context(
            user_id=session_id,
            app_name=APP_NAME,
            session_id=session_id,
            initial_context={
                "websocket_connection": True,
                "audio_mode": is_audio,
                "user_profile": user_profile,
                "contextual_memories": contextual_memories
            }
        )
        
        logging.debug(f"Created enhanced session with ID: {session_id}")

        # Create a Runner with original agent (enhanced agent is used internally)
        runner = Runner(
            app_name=APP_NAME,
            agent=root_agent,
            session_service=enhanced_session_service,
        )
        logging.debug("Created enhanced agent runner")

        # Create speech config with voice settings
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        )
        logging.debug("Configured speech settings with voice: Puck")

        # Create run config with basic settings
        config = {
            "response_modalities": [types.Modality.AUDIO if is_audio else types.Modality.TEXT],
            "speech_config": speech_config,
            "streaming_mode": StreamingMode.BIDI
        }

        # Add output_audio_transcription when audio is enabled
        if is_audio:
            config["output_audio_transcription"] = {}
            logging.debug("Added audio transcription to config")

        run_config = RunConfig(**config)
        logging.debug("Created run configuration")

        # Create a LiveRequestQueue for this session
        live_request_queue = LiveRequestQueue()

        # Start enhanced agent session
        live_events = runner.run_live(
            session=session,
            live_request_queue=live_request_queue,
            run_config=run_config,
        )
        
        logging.info(f"Enhanced agent session {session_id} started successfully")
        
        return {
            "session": session,
            "live_events": live_events,
            "live_request_queue": live_request_queue,
            "runner": runner,
            "session_service": enhanced_session_service,
            "memory_enabled": True,
            "user_profile": user_profile,
            "contextual_memories": contextual_memories
        }
        
    except Exception as e:
        logging.error(f"Error in enhanced session setup: {str(e)}")
        raise  # Re-raise to trigger fallback


async def _start_basic_session(session_id, is_audio=False):
    """Start basic session (original functionality)"""
    
    # Create a Session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )
    logging.debug(f"Created basic session with ID: {session_id}")

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
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    )
    logging.debug("Configured speech settings with voice: Puck")

    # Create run config with basic settings
    config = {
        "response_modalities": [types.Modality.AUDIO if is_audio else types.Modality.TEXT],
        "speech_config": speech_config,
        "streaming_mode": StreamingMode.BIDI
    }

    # Add output_audio_transcription when audio is enabled
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
    
    logging.info(f"Basic agent session {session_id} started successfully")
    
    return {
        "session": session,
        "live_events": live_events,
        "live_request_queue": live_request_queue,
        "runner": runner,
        "memory_enabled": False
    }


async def end_agent_session(session_id):
    """End agent session with optional memory capture"""
    
    if MEMORY_ENABLED and enhanced_session_service:
        # Try to end with memory capture
        try:
            session = await enhanced_session_service.end_session_with_memory_capture(session_id)
            if session:
                logging.info(f"Agent session {session_id} ended with memory capture")
                return session
        except Exception as e:
            logging.warning(f"Memory capture failed for session {session_id}: {str(e)}")
    
    # Fallback to basic session ending
    logging.info(f"Agent session {session_id} ended (basic mode)")
    return None


# Utility functions for memory integration
async def update_session_memory(session_id, user_input, agent_response, tools_used=None):
    """Update session memory with new interaction (if memory is enabled)"""
    
    if MEMORY_ENABLED and enhanced_session_service:
        try:
            await enhanced_session_service.update_session_context(
                session_id=session_id,
                new_context={"last_interaction": {"input": user_input, "response": agent_response}},
                user_input=user_input,
                agent_response=agent_response,
                tools_used=tools_used
            )
        except Exception as e:
            logging.warning(f"Failed to update session memory: {str(e)}")


def is_memory_enabled():
    """Check if memory system is available"""
    return MEMORY_ENABLED


def get_memory_services():
    """Get memory services if available"""
    if MEMORY_ENABLED:
        return {
            "user_profile_service": user_profile_service,
            "memory_service": memory_service,
            "enhanced_session_service": enhanced_session_service
        }
    return None 