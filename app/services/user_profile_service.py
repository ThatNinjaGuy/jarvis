import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import and_, desc
from app.models.database import UserProfile, UserPreference, LifeEvent, SessionHistory, SessionInteraction
from app.config.constants import DEFAULT_USER_ID

class UserProfileService:
    def __init__(self, db_session: DBSession):
        self.db = db_session
        self.logger = logging.getLogger(__name__)
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get complete user profile with preferences and statistics"""
        # Always use default user ID
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == DEFAULT_USER_ID).first()
        if not profile:
            profile = await self.create_user_profile(DEFAULT_USER_ID)
        
        # Get recent session count and preferences
        recent_sessions = self.db.query(SessionHistory).filter(
            SessionHistory.user_id == DEFAULT_USER_ID
        ).count()
        
        preferences = await self.get_user_preferences(DEFAULT_USER_ID)
        
        # Get recent life events
        recent_events = await self.get_life_events(DEFAULT_USER_ID, limit=5)
        
        return {
            "user_id": DEFAULT_USER_ID,
            "preferences": profile.preferences,
            "interaction_stats": {
                **profile.interaction_stats,
                "total_sessions": recent_sessions,
                "recent_preferences": [p for p in preferences if p["confidence"] > 0.7],
                "recent_events": recent_events
            },
            "communication_style": profile.communication_style,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "memory_settings": {
                "retention_days": profile.preferences.get("memory_retention_days", 90),
                "min_importance_threshold": profile.preferences.get("min_memory_importance", 0.3)
            }
        }
    
    async def create_user_profile(self, user_id: str) -> UserProfile:
        """Create a new user profile with default settings"""
        # Always use default user ID
        profile = UserProfile(
            user_id=DEFAULT_USER_ID,
            preferences={
                "communication_style": "professional",
                "response_length": "medium",
                "proactive_suggestions": True,
                "remember_context": True,
                "memory_retention_days": 90,
                "min_memory_importance": 0.3,
                "auto_learn_preferences": True
            },
            interaction_stats={
                "total_sessions": 0, 
                "total_interactions": 0,
                "avg_session_length": 0,
                "preferred_tools": [],
                "common_topics": [],
                "preference_confidence": {}
            },
            communication_style={
                "verbosity": "medium", 
                "tone": "professional",
                "formality": "balanced",
                "emoji_usage": "minimal",
                "technical_level": "adaptive"
            }
        )
        self.db.add(profile)
        self.db.commit()
        self.logger.info(f"Created new default user profile")
        return profile
    
    async def get_user_preferences(self, user_id: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get user preferences, optionally filtered by category"""
        # Always use default user ID
        query = self.db.query(UserPreference).filter(UserPreference.user_id == DEFAULT_USER_ID)
        
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
        """Update or create a user preference with improved confidence handling"""
        # Always use default user ID
        existing = self.db.query(UserPreference).filter(
            and_(
                UserPreference.user_id == DEFAULT_USER_ID,
                UserPreference.preference_key == key
            )
        ).first()
        
        current_time = datetime.utcnow()
        
        if existing:
            # Update existing preference with smarter confidence adjustment
            if existing.preference_value == value:
                # Reinforce existing preference
                time_factor = min(1.0, (current_time - existing.last_reinforced).days / 30)
                confidence_boost = 0.1 * time_factor
                existing.confidence_score = min(1.0, existing.confidence_score + confidence_boost)
            else:
                # Update with new value, consider history
                if existing.confidence_score > 0.8:
                    # High confidence in old value, be conservative with change
                    confidence = min(confidence, 0.7)
                existing.preference_value = value
                existing.confidence_score = confidence
            
            existing.preference_type = preference_type
            existing.preference_category = category
            existing.last_reinforced = current_time
            
            # Track preference history
            history = existing.preference_history or []
            history.append({
                "old_value": existing.preference_value,
                "new_value": value,
                "timestamp": current_time.isoformat(),
                "confidence": confidence,
                "type": preference_type
            })
            existing.preference_history = history[-10:]  # Keep last 10 changes
            
            self.logger.info(f"Updated preference {key} for default user (confidence: {existing.confidence_score:.2f})")
        else:
            new_pref = UserPreference(
                user_id=DEFAULT_USER_ID,
                preference_key=key,
                preference_value=value,
                confidence_score=confidence,
                preference_type=preference_type,
                preference_category=category,
                preference_history=[{
                    "value": value,
                    "timestamp": current_time.isoformat(),
                    "confidence": confidence,
                    "type": preference_type
                }]
            )
            self.db.add(new_pref)
            self.logger.info(f"Created new preference {key} for default user")
        
        # Update profile stats
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == DEFAULT_USER_ID).first()
        if profile:
            stats = profile.interaction_stats
            preference_confidence = stats.get("preference_confidence", {})
            preference_confidence[key] = confidence
            stats["preference_confidence"] = preference_confidence
            profile.interaction_stats = stats
            profile.updated_at = current_time
        
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
        """Record a user-agent interaction with enhanced analytics"""
        # Always use default user ID
        interaction = SessionInteraction(
            session_id=session_id,
            user_input=user_input,
            agent_response=agent_response,
            tools_used=tools_used or [],
            context_data=context_data or {}
        )
        self.db.add(interaction)
        
        # Update user interaction stats with more detailed tracking
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == DEFAULT_USER_ID).first()
        if profile:
            stats = profile.interaction_stats
            stats["total_interactions"] = stats.get("total_interactions", 0) + 1
            
            # Track tool usage patterns
            if tools_used:
                preferred_tools = stats.get("preferred_tools", {})
                for tool in tools_used:
                    preferred_tools[tool] = preferred_tools.get(tool, 0) + 1
                stats["preferred_tools"] = preferred_tools
            
            # Track common topics
            if context_data and "topics" in context_data:
                common_topics = stats.get("common_topics", {})
                for topic in context_data["topics"]:
                    common_topics[topic] = common_topics.get(topic, 0) + 1
                stats["common_topics"] = dict(sorted(
                    common_topics.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:20])  # Keep top 20 topics
            
            # Update average session length
            if "session_duration" in context_data:
                current_avg = stats.get("avg_session_length", 0)
                total_sessions = stats.get("total_sessions", 0)
                stats["avg_session_length"] = (
                    (current_avg * total_sessions + context_data["session_duration"]) /
                    (total_sessions + 1)
                )
            
            profile.interaction_stats = stats
            profile.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.logger.debug(f"Recorded interaction for default user in session {session_id}")
    
    async def add_life_event(
        self,
        user_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        event_date: datetime = None,
        importance_score: float = 0.5,
        tags: List[str] = None
    ):
        """Add a significant life event for the user with memory integration"""
        # Always use default user ID
        life_event = LifeEvent(
            user_id=DEFAULT_USER_ID,
            event_type=event_type,
            event_data=event_data,
            event_date=event_date or datetime.utcnow(),
            importance_score=importance_score,
            tags=tags or []
        )
        self.db.add(life_event)
        
        # Update profile with event context
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == DEFAULT_USER_ID).first()
        if profile:
            # Add event to recent significant events
            events = profile.preferences.get("significant_events", [])
            events.append({
                "type": event_type,
                "date": event_date.isoformat() if event_date else datetime.utcnow().isoformat(),
                "importance": importance_score,
                "tags": tags
            })
            profile.preferences["significant_events"] = sorted(
                events,
                key=lambda x: x["importance"],
                reverse=True
            )[:10]  # Keep top 10 significant events
            
            profile.updated_at = datetime.utcnow()
            
        self.db.commit()
        self.logger.info(f"Added life event {event_type} for default user")
    
    async def get_life_events(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get user's life events"""
        # Always use default user ID
        query = self.db.query(LifeEvent).filter(LifeEvent.user_id == DEFAULT_USER_ID)
        
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
        """Update user's communication style preferences with learning"""
        # Always use default user ID
        profile = self.db.query(UserProfile).filter(UserProfile.user_id == DEFAULT_USER_ID).first()
        if profile:
            current_style = profile.communication_style
            
            # Smart update of communication style
            for key, new_value in style_updates.items():
                if key in current_style:
                    old_value = current_style[key]
                    if old_value != new_value:
                        # Track style changes
                        style_history = profile.preferences.get("communication_style_history", {})
                        if key not in style_history:
                            style_history[key] = []
                        
                        style_history[key].append({
                            "old_value": old_value,
                            "new_value": new_value,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        # Keep last 5 changes for each style aspect
                        style_history[key] = style_history[key][-5:]
                        profile.preferences["communication_style_history"] = style_history
            
            current_style.update(style_updates)
            profile.communication_style = current_style
            profile.updated_at = datetime.utcnow()
            self.db.commit()
            self.logger.info(f"Updated communication style for default user")
    
    async def get_session_summary(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """Get detailed session summary with interactions"""
        # Always use default user ID
        session = self.db.query(SessionHistory).filter(
            and_(
                SessionHistory.user_id == DEFAULT_USER_ID,
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