import os
import logging
from google.adk.agents import LiveRequestQueue, Agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.genai import types
from pathlib import Path

from app.jarvis.agent import root_agent
from app.jarvis.utils import load_environment
from app.config.logging_config import setup_cloud_logging
from app.config.database import db_config
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService
from app.services.enhanced_session_service import EnhancedSessionService

# Setup cloud logging
setup_cloud_logging()

# Load environment variables
load_environment()

# Only load .env in development
if not os.environ.get("K_SERVICE"):  # K_SERVICE is set in Cloud Run
    from dotenv import load_dotenv
    load_dotenv()

APP_NAME = "Jarvis"

# Initialize database and services
db_config.create_tables()
db_session = next(db_config.get_db_session())

# Initialize services
user_profile_service = UserProfileService(db_session)
memory_service = JarvisMemoryService(db_session)

# Create enhanced session service
session_service = EnhancedSessionService(
    db_url=db_config.database_url,
    db_session=db_session,
    user_profile_service=user_profile_service,
    memory_service=memory_service
)

# Get the root directory of the project
ROOT_DIR = Path(__file__).resolve().parents[2]

# Create enhanced agent with memory tools
def create_enhanced_agent():
    """Create an enhanced agent with memory capabilities"""
    
    # Get all existing tools from root_agent
    existing_tools = root_agent.tools if hasattr(root_agent, 'tools') else []
    
    # Add memory profile MCP tool
    memory_tool = MCPToolset(
        connection_params=StdioServerParameters(
            command="python3",
            args=["-m", "app.jarvis.mcp_servers.memory_profile.server"],
            cwd=str(ROOT_DIR),
        )
    )
    
    # Create enhanced agent
    enhanced_agent = Agent(
        name="jarvis-enhanced",
        model="gemini-2.0-flash-exp",
        description="Enhanced Jarvis with multi-tiered memory and user profiling capabilities",
        instruction=f"""
        You are Jarvis, an advanced AI assistant with sophisticated memory and user profiling capabilities.
        
        ## Core Capabilities
        You maintain everything from your original capabilities:
        - Calendar Operations (scheduling, events, management)
        - Database Operations (SQLite queries and management)  
        - Gmail Operations (comprehensive email management)
        - Maps & Distance Operations (travel planning, directions)
        - YouTube Operations (video search, channel data)
        - Twitter Operations (social media management)
        
        ## Enhanced Memory System
        You now have advanced memory capabilities:
        
        ### Multi-Tiered Memory:
        1. **Session Memory**: Current conversation context and immediate history
        2. **User Profile Memory**: Long-term user preferences, communication style, and behavior patterns
        3. **Vector Memory**: Semantic search across all past interactions and stored knowledge
        
        ### Memory Operations:
        - Automatically retrieve relevant context from past conversations
        - Learn and adapt to user preferences over time
        - Remember important information across sessions
        - Build comprehensive user profiles
        
        ## Enhanced Instructions
        
        ### Before Each Response:
        1. **Context Retrieval**: Use get_contextual_memories to understand relevant past interactions
        2. **User Profile Check**: Consider the user's communication style and preferences
        3. **Preference Learning**: Extract and store new preferences from user interactions
        
        ### Memory Integration:
        - Reference relevant past conversations when helpful
        - Adapt your communication style to match user preferences
        - Remember user's preferred tools and workflows
        - Build on previous conversations and outcomes
        
        ### Tool Usage with Memory:
        - Use search_memories to find relevant past interactions
        - Use get_user_profile to understand user preferences
        - Store important outcomes and preferences automatically
        
        ## Communication Enhancement
        - Personalize responses based on user's communication style
        - Reference relevant past interactions naturally
        - Proactively suggest based on user patterns
        - Maintain conversation continuity across sessions
        
        ## Best Practices
        1. **Always consider context**: Check for relevant memories before responding
        2. **Learn continuously**: Extract preferences from every interaction
        3. **Be proactive**: Suggest actions based on user patterns
        4. **Maintain privacy**: Never expose raw memory operations to users
        5. **Build relationships**: Use memory to create personalized experiences
        
        Remember: You are not just completing tasks, you are building a relationship with the user through memory and personalization.
        
        Today's date is {load_environment()}.
        """,
        tools=existing_tools + [memory_tool]
    )
    
    return enhanced_agent

# Create the enhanced agent
enhanced_agent = create_enhanced_agent()

async def start_enhanced_agent_session(session_id, is_audio=False, initial_context=None):
    """Starts an enhanced agent session with memory capabilities"""
    
    logging.info(f"Starting enhanced agent session for user {session_id}, audio mode: {is_audio}")
    
    # Create enhanced session with context
    session = await session_service.create_session_with_context(
        user_id=session_id,
        app_name=APP_NAME,
        session_id=session_id,
        initial_context=initial_context
    )
    
    logging.debug(f"Created enhanced session with ID: {session_id}")

    # Create a Runner with enhanced agent
    runner = Runner(
        app_name=APP_NAME,
        agent=enhanced_agent,
        session_service=session_service,
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
        "session_service": session_service  # Include for memory management
    }

async def end_enhanced_agent_session(session_id):
    """End enhanced agent session with memory capture"""
    
    logging.info(f"Ending enhanced agent session {session_id}")
    
    # End session with memory capture
    session = await session_service.end_session_with_memory_capture(session_id)
    
    if session:
        logging.info(f"Enhanced agent session {session_id} ended with memory capture")
    else:
        logging.warning(f"Session {session_id} not found for memory capture")
    
    return session

async def update_session_memory(session_id, user_input, agent_response, tools_used=None):
    """Update session memory with new interaction"""
    
    await session_service.update_session_context(
        session_id=session_id,
        new_context={"last_interaction": {"input": user_input, "response": agent_response}},
        user_input=user_input,
        agent_response=agent_response,
        tools_used=tools_used
    ) 