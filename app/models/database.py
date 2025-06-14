from sqlalchemy import create_engine, Column, String, DateTime, JSON, Text, ForeignKey, Integer, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import uuid

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    
    user_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    preferences = Column(JSON, default=dict)
    interaction_stats = Column(JSON, default=dict)
    communication_style = Column(JSON, default=dict)
    
    sessions = relationship("SessionHistory", back_populates="user")
    preferences_records = relationship("UserPreference", back_populates="user")
    life_events = relationship("LifeEvent", back_populates="user")

def _ensure_json_serializable(obj):
    """Recursively convert a dictionary to ensure all values are JSON serializable."""
    if isinstance(obj, dict):
        return {key: _ensure_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_ensure_json_serializable(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

class SessionHistory(Base):
    __tablename__ = 'session_history'
    
    session_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    session_summary = Column(Text)
    topics_discussed = Column(JSON, default=list)
    outcomes = Column(JSON, default=dict)
    session_metadata = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    
    user = relationship("UserProfile", back_populates="sessions")
    interactions = relationship("SessionInteraction", back_populates="session")
    
    def __init__(self, **kwargs):
        """Initialize with JSON serializable data"""
        if 'session_metadata' in kwargs:
            kwargs['session_metadata'] = _ensure_json_serializable(kwargs['session_metadata'])
        if 'topics_discussed' in kwargs:
            kwargs['topics_discussed'] = _ensure_json_serializable(kwargs['topics_discussed'])
        if 'outcomes' in kwargs:
            kwargs['outcomes'] = _ensure_json_serializable(kwargs['outcomes'])
        super().__init__(**kwargs)
    
    def to_dict(self):
        """Convert to dictionary with JSON-safe values"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "session_summary": self.session_summary,
            "topics_discussed": self.topics_discussed,
            "outcomes": self.outcomes,
            "session_metadata": self.session_metadata,
            "is_active": self.is_active
        }

class SessionInteraction(Base):
    __tablename__ = 'session_interactions'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, ForeignKey('session_history.session_id'))
    user_input = Column(Text)
    agent_response = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    tools_used = Column(JSON, default=list)
    context_data = Column(JSON, default=dict)
    
    session = relationship("SessionHistory", back_populates="interactions")

class UserPreference(Base):
    __tablename__ = 'user_preferences'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    preference_key = Column(String)
    preference_value = Column(JSON)
    confidence_score = Column(Float, default=0.5)
    last_reinforced = Column(DateTime, default=datetime.utcnow)
    preference_type = Column(String)  # 'explicit', 'implicit', 'inferred'
    preference_category = Column(String)  # 'communication', 'functionality', 'personal', etc.
    
    user = relationship("UserProfile", back_populates="preferences_records")

class LifeEvent(Base):
    __tablename__ = 'life_events'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    event_type = Column(String)  # 'recurring', 'significant', 'milestone'
    event_data = Column(JSON)
    event_date = Column(DateTime)
    importance_score = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)
    tags = Column(JSON, default=list)
    
    user = relationship("UserProfile", back_populates="life_events")

class MemoryVector(Base):
    __tablename__ = 'memory_vectors'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('user_profiles.user_id'))
    session_id = Column(String, ForeignKey('session_history.session_id'), nullable=True)
    content = Column(Text)
    content_summary = Column(Text)
    vector_id = Column(String)  # ID in vector database
    memory_type = Column(String)  # 'conversation', 'preference', 'fact', 'experience'
    importance_score = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    access_count = Column(Integer, default=0)
    tags = Column(JSON, default=list) 