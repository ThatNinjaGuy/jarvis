import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.database import Base

class DatabaseConfig:
    def __init__(self, database_url: str = None):
        # Use environment variable or default to SQLite for development
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", 
            "sqlite:///./jarvis_memory.db"
        )
        
        # Create synchronous engine first (always works)
        self.engine = create_engine(
            self.database_url,
            connect_args={"check_same_thread": False} if "sqlite" in self.database_url else {}
        )
        
        # Create session maker
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Try to set up async engine (optional for now)
        self.async_engine = None
        self.AsyncSessionLocal = None
        
        try:
            self._setup_async_engine()
        except ImportError as e:
            logging.warning(f"Async database support not available: {e}")
            logging.info("Continuing with synchronous database operations only")
        except Exception as e:
            logging.warning(f"Could not setup async engine: {e}")
            logging.info("Continuing with synchronous database operations only")
        
        logging.info(f"Database configured with URL: {self.database_url}")
        
    def _setup_async_engine(self):
        """Set up async engine if dependencies are available"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            
            # Convert database URL for async operations
            if self.database_url.startswith("sqlite"):
                self.async_database_url = self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            else:
                self.async_database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")
            
            # Create async engine
            self.async_engine = create_async_engine(self.async_database_url)
            
            # Create async session maker
            self.AsyncSessionLocal = sessionmaker(
                self.async_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            logging.info("Async database support enabled")
            
        except ImportError:
            raise ImportError("Async database dependencies not installed. Run: pip install aiosqlite asyncpg")
        
    def get_adk_session_service(self):
        """Get ADK DatabaseSessionService for session persistence"""
        try:
            from google.adk.sessions import DatabaseSessionService
            return DatabaseSessionService(db_url=self.database_url)
        except Exception as e:
            logging.error(f"Could not create ADK session service: {e}")
            return None
        
    def create_tables(self):
        """Create all database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {e}")
            raise
        
    def get_db_session(self):
        """Get synchronous database session"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
            
    async def get_async_db_session(self):
        """Get asynchronous database session"""
        if self.AsyncSessionLocal is None:
            raise RuntimeError("Async database support not available")
            
        async with self.AsyncSessionLocal() as session:
            yield session
            
    def close_connections(self):
        """Close all database connections"""
        if self.engine:
            self.engine.dispose()
        if self.async_engine:
            self.async_engine.dispose()

# Global database instance - only create when needed
_db_config = None

def get_db_config():
    """Get database config instance (lazy loading)"""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config

# For backward compatibility
db_config = get_db_config() 