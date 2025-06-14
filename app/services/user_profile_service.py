import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import and_, desc
from app.models.database import UserProfile, UserPreference, LifeEvent, SessionHistory, SessionInteraction

class UserProfileService:
    def __init__(self, db_session: DBSession):
        self.db = db_session
        self.logger = logging.getLogger(__name__)
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get complete user profile with preferences and statistics"""
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            profile = await self.create_user_profile(user_id)
        
        # Get recent session count
        recent_sessions = self.db.query(SessionHistory).filter(
            SessionHistory.user_id == user_id
        ).count()
        
        return {
            "user_id": profile.user_id,
            "preferences": profile.preferences,
            "interaction_stats": {
                **profile.interaction_stats,
                "total_sessions": recent_sessions
            },
            "communication_style": profile.communication_style,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at
        }
    
    async def create_user_profile(self, user_id: str) -> UserProfile:
        """Create a new user profile with default settings"""
        profile = UserProfile(
            user_id=user_id,
            preferences={
                "communication_style": "professional",
                "response_length": "medium",
                "proactive_suggestions": True,
                "remember_context": True
            },
            interaction_stats={
                "total_sessions": 0, 
                "total_interactions": 0,
                "avg_session_length": 0,
                "preferred_tools": []
            },
            communication_style={
                "verbosity": "medium", 
                "tone": "professional",
                "formality": "balanced",
                "emoji_usage": "minimal"
            }
        )
        self.db.add(profile)
        self.db.commit()
        self.logger.info(f"Created new user profile for {user_id}")
        return profile
    
    async def get_user_preferences(self, user_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get user preferences, optionally filtered by category"""
        query = self.db.query(UserPreference).filter(UserPreference.user_id == user_id)
        
        if category:
            query = query.filter(UserPreference.preference_category == category)
            
        preferences = query.order_by(desc(UserPreference.confidence_score)).all()
        
        return [
            {
                "key": pref.preference_key,
                "value": pref.preference_value,
                "confidence": pref.confidence_score,
                "type": pref.preference_type,
                "category": pref.preference_category,
                "last_reinforced": pref.last_reinforced
            }
            for pref in preferences
        ]
    
    async def update_preference(
        self, 
        user_id: str, 
        key: str, 
        value: Any, 
        preference_type: str = "explicit",
        confidence: float = 1.0,
        category: str = "general"
    ):
        """Update or create a user preference"""
        existing = self.db.query(UserPreference).filter(
            and_(
                UserPreference.user_id == user_id,
                UserPreference.preference_key == key
            )
        ).first()
        
        if existing:
            # Update existing preference, adjust confidence based on reinforcement
            if existing.preference_value == value:
                # Reinforce existing preference
                existing.confidence_score = min(1.0, existing.confidence_score + 0.1)
            else:
                # Update with new value
                existing.preference_value = value
                existing.confidence_score = confidence
            
            existing.preference_type = preference_type
            existing.preference_category = category
            existing.last_reinforced = datetime.utcnow()
            
            self.logger.info(f"Updated preference {key} for user {user_id}")
        else:
            new_pref = UserPreference(
                user_id=user_id,
                preference_key=key,
                preference_value=value,
                confidence_score=confidence,
                preference_type=preference_type,
                preference_category=category
            )
            self.db.add(new_pref)
            self.logger.info(f"Created new preference {key} for user {user_id}")
        
        self.db.commit()
    
    async def record_interaction(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
        agent_response: str,
        tools_used: List[str] = None,
        context_data: Dict[str, Any] = None
    ):
        """Record a user-agent interaction"""
        interaction = SessionInteraction(
            session_id=session_id,
            user_input=user_input,
            agent_response=agent_response,
            tools_used=tools_used or [],
            context_data=context_data or {}
        )
        self.db.add(interaction)
        
        # Update user interaction stats
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile:
            stats = profile.interaction_stats
            stats["total_interactions"] = stats.get("total_interactions", 0) + 1
            
            # Track tool usage
            if tools_used:
                preferred_tools = stats.get("preferred_tools", {})
                for tool in tools_used:
                    preferred_tools[tool] = preferred_tools.get(tool, 0) + 1
                stats["preferred_tools"] = preferred_tools
            
            profile.interaction_stats = stats
            profile.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.logger.debug(f"Recorded interaction for user {user_id} in session {session_id}")
    
    async def add_life_event(
        self,
        user_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        event_date: datetime = None,
        importance_score: float = 0.5,
        tags: List[str] = None
    ):
        """Add a significant life event for the user"""
        life_event = LifeEvent(
            user_id=user_id,
            event_type=event_type,
            event_data=event_data,
            event_date=event_date or datetime.utcnow(),
            importance_score=importance_score,
            tags=tags or []
        )
        self.db.add(life_event)
        self.db.commit()
        self.logger.info(f"Added life event {event_type} for user {user_id}")
    
    async def get_life_events(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get user's life events"""
        query = self.db.query(LifeEvent).filter(LifeEvent.user_id == user_id)
        
        if event_type:
            query = query.filter(LifeEvent.event_type == event_type)
            
        events = query.order_by(desc(LifeEvent.importance_score)).limit(limit).all()
        
        return [
            {
                "id": event.id,
                "event_type": event.event_type,
                "event_data": event.event_data,
                "event_date": event.event_date,
                "importance_score": event.importance_score,
                "tags": event.tags,
                "created_at": event.created_at
            }
            for event in events
        ]
    
    async def update_communication_style(
        self,
        user_id: str,
        style_updates: Dict[str, Any]
    ):
        """Update user's communication style preferences"""
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile:
            current_style = profile.communication_style
            current_style.update(style_updates)
            profile.communication_style = current_style
            profile.updated_at = datetime.utcnow()
            self.db.commit()
            self.logger.info(f"Updated communication style for user {user_id}")
    
    async def get_session_summary(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """Get detailed session summary with interactions"""
        session = self.db.query(SessionHistory).filter(
            and_(
                SessionHistory.user_id == user_id,
                SessionHistory.session_id == session_id
            )
        ).first()
        
        if not session:
            return {}
            
        interactions = self.db.query(SessionInteraction).filter(
            SessionInteraction.session_id == session_id
        ).order_by(SessionInteraction.timestamp).all()
        
        return {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "ended_at": session.ended_at,
            "session_summary": session.session_summary,
            "topics_discussed": session.topics_discussed,
            "outcomes": session.outcomes,
            "interactions": [
                {
                    "user_input": interaction.user_input,
                    "agent_response": interaction.agent_response,
                    "timestamp": interaction.timestamp,
                    "tools_used": interaction.tools_used
                }
                for interaction in interactions
            ]
        } 