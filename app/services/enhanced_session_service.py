import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from google.adk.sessions import DatabaseSessionService, Session
from sqlalchemy.orm import Session as DBSession

from app.models.database import SessionHistory, UserProfile
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService

class EnhancedSessionService(DatabaseSessionService):
    def __init__(
        self, 
        db_url: str, 
        db_session: DBSession,
        user_profile_service: UserProfileService,
        memory_service: JarvisMemoryService
    ):
        super().__init__(db_url=db_url)
        self.db_session = db_session
        self.user_profile_service = user_profile_service
        self.memory_service = memory_service
        self.logger = logging.getLogger(__name__)
        
        # Track active sessions for memory management
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    async def create_session_with_context(
        self, 
        user_id: str, 
        app_name: str, 
        session_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Session:
        """Create session with enriched user context and memory"""
        
        # Get user profile and preferences
        user_profile = await self.user_profile_service.get_user_profile(user_id)
        user_preferences = await self.user_profile_service.get_user_preferences(user_id)
        
        # Get contextual memories
        context_for_memory = {
            "query": initial_context.get("initial_query", "") if initial_context else "",
            "session_topics": initial_context.get("topics", []) if initial_context else [],
            "recent_tools": []
        }
        
        contextual_memories = await self.memory_service.get_contextual_memories(
            user_id=user_id,
            current_context=context_for_memory
        )
        
        # Build enriched context
        enriched_context = {
            "user_profile": user_profile,
            "user_preferences": user_preferences,
            "contextual_memories": contextual_memories,
            "session_context": initial_context or {},
            "memory_summary": contextual_memories.get("context_summary", ""),
            "communication_style": user_profile.get("communication_style", {}),
            "session_start_time": datetime.utcnow().isoformat()
        }
        
        # Create ADK session (without state_context as it's not supported)
        session = await self.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
        
        # Store enriched context in our session tracking
        # (The ADK session doesn't support custom state_context, so we manage it ourselves)
        
        # Create session history record
        session_history = SessionHistory(
            session_id=session.id,
            user_id=user_id,
            session_metadata={
                "app_name": app_name,
                "context_memories_count": len(contextual_memories.get("relevant_memories", [])),
                "user_preferences_count": len(user_preferences),
                "initial_context": initial_context
            }
        )
        
        self.db_session.add(session_history)
        self.db_session.commit()
        
        # Track session for memory management
        self.active_sessions[session.id] = {
            "user_id": user_id,
            "start_time": datetime.utcnow(),
            "interactions": [],
            "topics_discussed": [],
            "tools_used": set(),
            "session_context": enriched_context
        }
        
        self.logger.info(f"Created enhanced session {session.id} for user {user_id}")
        return session
    
    async def update_session_context(
        self,
        session_id: str,
        new_context: Dict[str, Any],
        user_input: Optional[str] = None,
        agent_response: Optional[str] = None,
        tools_used: Optional[List[str]] = None
    ):
        """Update session context with new interaction data"""
        
        if session_id not in self.active_sessions:
            self.logger.warning(f"Session {session_id} not found in active sessions")
            return
        
        session_data = self.active_sessions[session_id]
        user_id = session_data["user_id"]
        
        # Record interaction
        if user_input and agent_response:
            interaction = {
                "user_input": user_input,
                "agent_response": agent_response,
                "timestamp": datetime.utcnow().isoformat(),
                "tools_used": tools_used or [],
                "importance_score": self._calculate_interaction_importance(
                    user_input, agent_response, tools_used
                )
            }
            
            session_data["interactions"].append(interaction)
            
            # Update tools used
            if tools_used:
                session_data["tools_used"].update(tools_used)
            
            # Extract topics from interaction
            topics = await self._extract_topics_from_interaction(user_input, agent_response)
            session_data["topics_discussed"].extend(topics)
            
            # Record interaction in user profile service
            await self.user_profile_service.record_interaction(
                user_id=user_id,
                session_id=session_id,
                user_input=user_input,
                agent_response=agent_response,
                tools_used=tools_used,
                context_data=new_context
            )
            
            # Learn preferences from interaction
            await self._learn_preferences_from_interaction(
                user_id, user_input, agent_response, tools_used
            )
        
        # Update session context
        session_data["session_context"].update(new_context)
        
        # Get updated session from ADK
        session = await self.get_session(session_id)
        if session:
            # Update session state with new context
            updated_state = session.state.copy()
            updated_state.update(new_context)
            
            # Add dynamic context from current session
            updated_state["session_stats"] = {
                "interactions_count": len(session_data["interactions"]),
                "tools_used": list(session_data["tools_used"]),
                "topics_discussed": list(set(session_data["topics_discussed"])),
                "session_duration": (datetime.utcnow() - session_data["start_time"]).seconds
            }
            
            # Update memory context if significant interaction
            if user_input and len(user_input) > 50:  # Significant interaction threshold
                await self._update_contextual_memory(session_id, user_id, interaction)
    
    async def end_session_with_memory_capture(self, session_id: str) -> Optional[Session]:
        """End session and capture memories and insights"""
        
        session = await self.get_session(session_id)
        if not session:
            return None
        
        if session_id in self.active_sessions:
            session_data = self.active_sessions[session_id]
            user_id = session_data["user_id"]
            
            # Extract session insights
            session_insights = await self._extract_session_insights(session_data)
            
            # Update session history
            await self._update_session_history(session_id, session_insights)
            
            # Store session memories
            await self.memory_service.store_session_memory(
                session_id=session_id,
                user_id=user_id,
                session_data={
                    "summary": session_insights["summary"],
                    "topics": session_insights["topics"],
                    "tools_used": list(session_data["tools_used"]),
                    "interactions": session_data["interactions"],
                    "outcomes": session_insights["outcomes"],
                    "session_length": (datetime.utcnow() - session_data["start_time"]).seconds
                }
            )
            
            # Update user preferences based on session
            await self._update_user_preferences_from_session(user_id, session_data, session_insights)
            
            # Clean up active session
            del self.active_sessions[session_id]
            
            self.logger.info(f"Ended session {session_id} with memory capture for user {user_id}")
        
        return session
    
    async def _extract_session_insights(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key insights from session data"""
        
        interactions = session_data["interactions"]
        tools_used = list(session_data["tools_used"])
        topics = list(set(session_data["topics_discussed"]))
        
        # Generate session summary
        summary_parts = []
        if len(interactions) > 0:
            summary_parts.append(f"Session with {len(interactions)} interactions")
        
        if tools_used:
            summary_parts.append(f"Used tools: {', '.join(tools_used)}")
            
        if topics:
            summary_parts.append(f"Discussed: {', '.join(topics[:3])}")
        
        summary = ". ".join(summary_parts) if summary_parts else "Brief session"
        
        # Identify outcomes
        outcomes = []
        high_importance_interactions = [
            i for i in interactions if i.get("importance_score", 0) > 0.7
        ]
        
        if high_importance_interactions:
            outcomes.append(f"Completed {len(high_importance_interactions)} significant tasks")
        
        if "calendar" in str(tools_used).lower():
            outcomes.append("Calendar management")
            
        if "email" in str(tools_used).lower() or "gmail" in str(tools_used).lower():
            outcomes.append("Email management")
        
        return {
            "summary": summary,
            "topics": topics,
            "outcomes": outcomes,
            "total_interactions": len(interactions),
            "session_duration": (datetime.utcnow() - session_data["start_time"]).seconds,
            "tools_effectiveness": self._calculate_tools_effectiveness(interactions, tools_used)
        }
    
    async def _update_session_history(self, session_id: str, insights: Dict[str, Any]):
        """Update session history with insights"""
        
        session_history = self.db_session.query(SessionHistory).filter(
            SessionHistory.session_id == session_id
        ).first()
        
        if session_history:
            session_history.ended_at = datetime.utcnow()
            session_history.session_summary = insights["summary"]
            session_history.topics_discussed = insights["topics"]
            session_history.outcomes = insights["outcomes"]
            session_history.is_active = False
            
            # Update metadata
            metadata = session_history.session_metadata or {}
            metadata.update({
                "total_interactions": insights["total_interactions"],
                "session_duration": insights["session_duration"],
                "tools_effectiveness": insights["tools_effectiveness"]
            })
            session_history.session_metadata = metadata
            
            self.db_session.commit()
    
    async def _learn_preferences_from_interaction(
        self,
        user_id: str,
        user_input: str,
        agent_response: str,
        tools_used: Optional[List[str]]
    ):
        """Learn user preferences from interactions"""
        
        # Detect explicit preferences
        preference_phrases = ["I prefer", "I like", "I want", "I need", "I always", "I usually"]
        
        for phrase in preference_phrases:
            if phrase.lower() in user_input.lower():
                # Extract preference context
                sentences = user_input.split('.')
                for sentence in sentences:
                    if phrase.lower() in sentence.lower():
                        await self.user_profile_service.update_preference(
                            user_id=user_id,
                            key="communication_preference",
                            value=sentence.strip(),
                            preference_type="explicit",
                            confidence=0.8,
                            category="communication"
                        )
                        break
        
        # Learn tool preferences
        if tools_used:
            for tool in tools_used:
                await self.user_profile_service.update_preference(
                    user_id=user_id,
                    key=f"tool_usage_{tool}",
                    value={"frequency": 1, "context": user_input[:100]},
                    preference_type="implicit",
                    confidence=0.6,
                    category="functionality"
                )
    
    async def _extract_topics_from_interaction(
        self, 
        user_input: str, 
        agent_response: str
    ) -> List[str]:
        """Extract topics from interaction using simple keyword analysis"""
        
        topics = []
        
        # Common topic keywords
        topic_keywords = {
            "calendar": ["schedule", "appointment", "meeting", "event", "calendar"],
            "email": ["email", "mail", "message", "send", "inbox"],
            "travel": ["directions", "drive", "location", "address", "map"],
            "entertainment": ["video", "youtube", "watch", "music"],
            "social": ["tweet", "twitter", "post", "social"],
            "productivity": ["reminder", "task", "todo", "organize"],
            "weather": ["weather", "temperature", "forecast", "rain"],
            "shopping": ["buy", "purchase", "order", "shopping"]
        }
        
        combined_text = (user_input + " " + agent_response).lower()
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in combined_text for keyword in keywords):
                topics.append(topic)
        
        return topics
    
    def _calculate_interaction_importance(
        self,
        user_input: str,
        agent_response: str,
        tools_used: Optional[List[str]] = None
    ) -> float:
        """Calculate importance score for interaction"""
        
        score = 0.5  # Base score
        
        # Length factor
        if len(user_input) > 100:
            score += 0.1
        
        # Tool usage factor
        if tools_used and len(tools_used) > 0:
            score += 0.2
        
        # Complexity factor (questions, detailed responses)
        if "?" in user_input:
            score += 0.1
            
        if len(agent_response) > 200:
            score += 0.1
        
        # Preference indication factor
        preference_indicators = ["prefer", "like", "want", "need", "always", "never"]
        if any(indicator in user_input.lower() for indicator in preference_indicators):
            score += 0.2
        
        return min(1.0, score)  # Cap at 1.0
    
    def _calculate_tools_effectiveness(
        self,
        interactions: List[Dict[str, Any]],
        tools_used: List[str]
    ) -> Dict[str, float]:
        """Calculate effectiveness of tools used in session"""
        
        effectiveness = {}
        
        for tool in tools_used:
            tool_interactions = [
                i for i in interactions 
                if tool in i.get("tools_used", [])
            ]
            
            if tool_interactions:
                avg_importance = sum(
                    i.get("importance_score", 0.5) for i in tool_interactions
                ) / len(tool_interactions)
                effectiveness[tool] = avg_importance
            else:
                effectiveness[tool] = 0.5
        
        return effectiveness
    
    async def _update_contextual_memory(
        self,
        session_id: str,
        user_id: str,
        interaction: Dict[str, Any]
    ):
        """Update contextual memory with significant interactions"""
        
        if interaction.get("importance_score", 0) > 0.6:
            await self.memory_service.store_memory(
                user_id=user_id,
                content=f"User: {interaction['user_input']}\nAssistant: {interaction['agent_response']}",
                memory_type="conversation",
                session_id=session_id,
                importance_score=interaction["importance_score"],
                tags=interaction.get("tools_used", [])
            )
    
    async def _update_user_preferences_from_session(
        self,
        user_id: str,
        session_data: Dict[str, Any],
        session_insights: Dict[str, Any]
    ):
        """Update user preferences based on overall session patterns"""
        
        # Update communication style based on session
        if len(session_data["interactions"]) > 3:
            avg_response_length = sum(
                len(i.get("agent_response", "")) for i in session_data["interactions"]
            ) / len(session_data["interactions"])
            
            if avg_response_length > 300:
                response_style = "detailed"
            elif avg_response_length < 100:
                response_style = "concise"
            else:
                response_style = "balanced"
            
            await self.user_profile_service.update_communication_style(
                user_id=user_id,
                style_updates={"preferred_response_length": response_style}
            )
        
        # Update tool preferences
        if session_data["tools_used"]:
            for tool in session_data["tools_used"]:
                await self.user_profile_service.update_preference(
                    user_id=user_id,
                    key=f"tool_preference_{tool}",
                    value=True,
                    preference_type="implicit",
                    confidence=0.7,
                    category="functionality"
                ) 