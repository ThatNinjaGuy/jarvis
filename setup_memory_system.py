#!/usr/bin/env python3
"""
Memory System Setup Script

This script initializes the Jarvis multi-tiered memory system by:
- Creating database tables
- Setting up vector database
- Initializing default configurations
- Running system health checks
"""

import asyncio
import logging
import os
import sys
import subprocess
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_and_install_dependencies():
    """Check and install required dependencies"""
    logger.info("Checking required packages...")
    
    required_packages = {
        'chromadb': 'chromadb>=0.4.0',
        'google-cloud-aiplatform': 'google-cloud-aiplatform>=1.35.0',
        'sqlalchemy': 'SQLAlchemy>=2.0.0',
        'mcp': 'mcp>=1.9.1',
        'aiosqlite': 'aiosqlite>=0.20.0'
    }
    
    missing_packages = []
    
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
            logger.info(f"✅ {package} is available")
        except ImportError:
            missing_packages.append(pip_name)
            logger.warning(f"❌ Missing package: {package}")
    
    if missing_packages:
        logger.error("Missing required packages. Installing...")
        try:
            cmd = [sys.executable, "-m", "pip", "install"] + missing_packages
            subprocess.check_call(cmd)
            logger.info("✅ Successfully installed missing packages")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install packages: {e}")
            logger.error("Please install manually: pip install " + " ".join(missing_packages))
            return False
    
    return True

async def setup_database():
    """Set up database tables"""
    logger.info("Setting up database...")
    
    try:
        # Import after dependency check
        from app.config.database import db_config
        from app.services.user_profile_service import UserProfileService
        
        # Create all tables
        db_config.create_tables()
        logger.info("✅ Database tables created successfully")
        
        # Test database connection
        db_session = next(db_config.get_db_session())
        user_profile_service = UserProfileService(db_session)
        
        # Create a test user profile to verify everything works
        test_profile = await user_profile_service.get_user_profile("setup_test")
        logger.info("✅ Database connection verified")
        
        db_session.close()
        
    except Exception as e:
        logger.error(f"❌ Database setup failed: {str(e)}")
        logger.error("Make sure all dependencies are installed: pip install -r requirements.txt")
        raise

async def setup_vector_database():
    """Set up vector database"""
    logger.info("Setting up vector database...")
    
    try:
        # Import after dependency check
        from app.config.database import db_config
        from app.services.memory_service import JarvisMemoryService
        
        # Initialize database session
        db_session = next(db_config.get_db_session())
        
        # Initialize memory service (this creates the vector collection)
        logger.info("Initializing Vertex AI embeddings...")
        memory_service = JarvisMemoryService(db_session)
        
        # Test vector database with a simple operation
        test_memory_id = await memory_service.store_memory(
            user_id="setup_test",
            content="This is a test memory to verify the vector database is working correctly.",
            memory_type="fact",
            importance_score=0.5,
            tags="setup,test"
        )
        
        logger.info(f"✅ Vector database setup successful. Test memory ID: {test_memory_id}")
        
        # Test search functionality
        search_results = await memory_service.search_memories(
            user_id="setup_test",
            query="test memory",
            limit=1
        )
        
        if search_results:
            logger.info("✅ Vector search functionality verified")
        else:
            logger.warning("⚠️ Vector search returned no results")
        
        db_session.close()
        
    except Exception as e:
        logger.error(f"❌ Vector database setup failed: {str(e)}")
        if "google.cloud" in str(e).lower():
            logger.error("Make sure GOOGLE_CLOUD_PROJECT and VERTEX_ENDPOINT_ID are set in your environment")
        elif "chromadb" in str(e).lower():
            logger.error("Try installing: pip install chromadb")
        raise

async def setup_default_configurations():
    """Set up default system configurations"""
    logger.info("Setting up default configurations...")
    
    try:
        # Import after dependency check
        from app.config.database import db_config
        from app.services.user_profile_service import UserProfileService
        
        # Initialize database session
        db_session = next(db_config.get_db_session())
        user_profile_service = UserProfileService(db_session)
        
        # Create default system user profile
        system_profile = await user_profile_service.get_user_profile("system")
        logger.info("✅ System user profile created")
        
        # Set up default preferences for the system
        await user_profile_service.update_preference(
            user_id="system",
            key="default_communication_style",
            value="professional",
            preference_type="explicit",
            confidence=1.0,
            category="system"
        )
        
        await user_profile_service.update_preference(
            user_id="system",
            key="memory_retention_days",
            value=90,
            preference_type="explicit",
            confidence=1.0,
            category="system"
        )
        
        logger.info("✅ Default system preferences configured")
        
        db_session.close()
        
    except Exception as e:
        logger.error(f"❌ Default configuration setup failed: {str(e)}")
        raise

async def run_health_checks():
    """Run comprehensive health checks"""
    logger.info("Running system health checks...")
    
    try:
        # Import after dependency check
        from app.config.database import db_config
        from app.services.user_profile_service import UserProfileService
        from app.services.memory_service import JarvisMemoryService
        
        # Database health check
        db_session = next(db_config.get_db_session())
        user_profile_service = UserProfileService(db_session)
        memory_service = JarvisMemoryService(db_session)
        
        # Test user profile operations
        test_user = "health_check_user"
        profile = await user_profile_service.get_user_profile(test_user)
        logger.info("✅ User profile service operational")
        
        # Test memory operations
        memories = await memory_service.search_memories(
            user_id=test_user,
            query="health check",
            limit=1
        )
        logger.info("✅ Memory service operational")
        
        # Test contextual memory retrieval
        context_result = await memory_service.get_contextual_memories(
            user_id=test_user,
            current_context={"query": "health check"},
            max_memories=5
        )
        logger.info("✅ Contextual memory service operational")
        
        # Test preference management
        await user_profile_service.update_preference(
            user_id=test_user,
            key="test_preference",
            value="test_value",
            preference_type="explicit"
        )
        
        preferences = await user_profile_service.get_user_preferences(test_user)
        logger.info("✅ Preference management operational")
        
        db_session.close()
        
        logger.info("🎉 All health checks passed! Memory system is ready.")
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        raise

def print_system_info():
    """Print system information"""
    logger.info("=== Jarvis Multi-tiered Memory System ===")
    logger.info(f"Python Version: {sys.version}")
    logger.info(f"Working Directory: {os.getcwd()}")
    logger.info("==========================================")

def print_setup_complete():
    """Print setup completion message"""
    logger.info("\n🎉 SETUP COMPLETE! 🎉")
    logger.info("Your Jarvis multi-tiered memory system is now ready!")
    logger.info("\nNext steps:")
    logger.info("1. Update your application to use enhanced routes")
    logger.info("2. Test the enhanced API endpoints")
    logger.info("3. Interact with Jarvis to see memory capabilities in action")
    logger.info("\nMemory features now available:")
    logger.info("• User profile learning and adaptation")
    logger.info("• Cross-session conversation memory")
    logger.info("• Semantic memory search")
    logger.info("• Contextual memory retrieval")
    logger.info("• Preference learning and application")
    logger.info("\nDatabase files created:")
    logger.info("• jarvis_memory.db (SQLite database)")
    logger.info("• jarvis_memory_db/ (Vector database)")
    logger.info("\nExample API endpoints:")
    logger.info("• GET /api/user/{user_id}/profile")
    logger.info("• GET /api/user/{user_id}/memories/search")
    logger.info("• GET /api/memory/status")
    logger.info("• WebSocket /ws/{session_id} (enhanced)")

async def main():
    """Main setup function"""
    print_system_info()
    
    try:
        logger.info("Starting Jarvis memory system setup...")
        
        # Step 0: Check and install dependencies
        if not check_and_install_dependencies():
            logger.error("❌ Dependency installation failed")
            sys.exit(1)
        
        # Step 1: Set up database
        await setup_database()
        
        # Step 2: Set up vector database
        await setup_vector_database()
        
        # Step 3: Configure defaults
        await setup_default_configurations()
        
        # Step 4: Run health checks
        await run_health_checks()
        
        print_setup_complete()
        
    except KeyboardInterrupt:
        logger.info("Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Setup failed: {str(e)}")
        logger.error("\nTroubleshooting tips:")
        logger.error("1. Make sure you're in the project root directory")
        logger.error("2. Install requirements: pip install -r requirements.txt")
        logger.error("3. Check Python version (3.8+ required)")
        logger.error("4. Try running with verbose logging: python -v setup_memory_system.py")
        sys.exit(1)

if __name__ == "__main__":
    # Run the setup
    asyncio.run(main())