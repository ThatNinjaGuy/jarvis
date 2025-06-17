import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from google.adk.sessions import DatabaseSessionService, Session
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.exc import IntegrityError

from app.models.database import SessionHistory, UserProfile
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService
from app.config.constants import DEFAULT_USER_ID, APP_NAME  # Import from constants instead

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
        
        # Generate unique session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Get user profile and preferences (always use default user)
        user_profile = await self.user_profile_service.get_user_profile(DEFAULT_USER_ID)
        user_preferences = await self.user_profile_service.get_user_preferences(DEFAULT_USER_ID)
        
        # Get contextual memories (with better default context)
        try:
            contextual_memories = await self.memory_service.get_contextual_memories(
                user_id=DEFAULT_USER_ID,
                current_context={"query": "session initialization", "session_start": True},
                max_memories=5
            )
        except Exception as e:
            self.logger.warning(f"Failed to get contextual memories: {str(e)}")
            contextual_memories = {"relevant_memories": [], "context_summary": ""}
        
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
        
        # Create ADK session with retry logic for unique constraint
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = await super().create_session(
                    app_name=app_name,
                    user_id=DEFAULT_USER_ID,  # Always use default user
                    session_id=session_id if attempt == 0 else str(uuid.uuid4())
                )
                break
            except IntegrityError:
                if attempt == max_retries - 1:
                    raise
                continue
        
        # Create or update session history record with JSON-safe data
        try:
            current_time = datetime.utcnow()
            
            # Check for existing session history
            existing_session = self.db_session.query(SessionHistory).filter(
                SessionHistory.session_id == session.id
            ).first()
            
            if existing_session:
                # Update existing session
                existing_session.is_active = True
                existing_session.session_metadata.update({
                    "app_name": app_name,
                    "context_memories_count": len(contextual_memories.get("relevant_memories", [])),
                    "user_preferences_count": len(user_preferences),
                    "initial_context": initial_context or {},
                    "start_time": current_time.isoformat()
                })
            else:
                # Create new session history
                session_history = SessionHistory(
                    session_id=session.id,
                    user_id=DEFAULT_USER_ID,  # Always use default user
                    created_at=current_time,
                    session_metadata={
                        "app_name": app_name,
                        "context_memories_count": len(contextual_memories.get("relevant_memories", [])),
                        "user_preferences_count": len(user_preferences),
                        "initial_context": initial_context or {},
                        "start_time": current_time.isoformat()
                    },
                    is_active=True
                )
                self.db_session.add(session_history)
            
            try:
                self.db_session.commit()
            except Exception as e:
                self.db_session.rollback()
                self.logger.warning(f"Failed to update session history, continuing anyway: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Failed to create session history: {str(e)}")
            # Continue anyway as this is not critical
        
        # Track session for memory management
        self.active_sessions[session.id] = {
            "user_id": DEFAULT_USER_ID,  # Always use default user
            "start_time": datetime.utcnow().isoformat(),
            "interactions": [],
            "topics_discussed": [],
            "tools_used": set(),
            "session_context": enriched_context
        }
        
        self.logger.info(f"Created enhanced session {session.id} for default user")
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
        
        # Record interaction if we have both input and response
        if user_input or agent_response:  # Changed to allow partial updates
            current_time = datetime.utcnow().isoformat()
            
            # Get existing interaction or create new one
            last_interaction = (session_data["interactions"][-1] 
                              if session_data["interactions"] else {})
            
            interaction = {
                "user_input": user_input or last_interaction.get("user_input", ""),
                "agent_response": agent_response or last_interaction.get("agent_response", ""),
                "timestamp": current_time,
                "tools_used": tools_used or last_interaction.get("tools_used", []),
                "importance_score": self._calculate_interaction_importance(
                    user_input or last_interaction.get("user_input", ""),
                    agent_response or last_interaction.get("agent_response", ""),
                    tools_used
                )
            }
            
            # Only append if this is a new interaction
            if user_input or (agent_response and not last_interaction.get("agent_response")):
                session_data["interactions"].append(interaction)
            else:
                # Update the last interaction
                session_data["interactions"][-1].update(interaction)
            
            # Update tools used
            if tools_used:
                session_data["tools_used"].update(tools_used)
            
            # Extract topics from interaction
            if user_input and agent_response:  # Only extract topics for complete interactions
                topics = await self._extract_topics_from_interaction(user_input, agent_response)
                session_data["topics_discussed"].extend(topics)
            
            # Record interaction in user profile service
            await self.user_profile_service.record_interaction(
                user_id=DEFAULT_USER_ID,  # Always use default user
                session_id=session_id,
                user_input=user_input or last_interaction.get("user_input", ""),
                agent_response=agent_response or last_interaction.get("agent_response", ""),
                tools_used=tools_used,
                context_data=new_context
            )
            
            # Learn preferences from complete interactions
            if user_input and agent_response:
                await self._learn_preferences_from_interaction(
                    DEFAULT_USER_ID,  # Always use default user
                    user_input,
                    agent_response,
                    tools_used
                )
        
        # Update session context
        session_data["session_context"].update(new_context)
        
        # Get updated session from ADK
        session = await self.get_session(
            session_id=session_id,
            app_name=APP_NAME,
            user_id=DEFAULT_USER_ID
        )
        if session:
            # Update session state with new context
            updated_state = session.state.copy()
            updated_state.update(new_context)
            
            # Add dynamic context from current session
            updated_state["session_stats"] = {
                "interactions_count": len(session_data["interactions"]),
                "tools_used": list(session_data["tools_used"]),
                "topics_discussed": list(set(session_data["topics_discussed"])),
                "session_duration": (datetime.utcnow() - datetime.fromisoformat(session_data["start_time"])).seconds
            }
            
            # Update memory context for any significant interaction
            if user_input or agent_response:
                await self._update_contextual_memory(
                    session_id=session_id,
                    user_id=DEFAULT_USER_ID,  # Always use default user
                    interaction=interaction
                )
    
    async def end_session_with_memory_capture(self, session_id: str) -> Optional[Dict[str, Any]]:
        """End session and capture memories and insights"""
        
        if session_id not in self.active_sessions:
            self.logger.warning(f"Session {session_id} not found in active sessions")
            return None
        
        session_data = self.active_sessions[session_id]
        user_id = session_data["user_id"]
        
        try:
            # Extract session insights
            session_insights = await self._extract_session_insights(session_data)
            
            # Update session history
            session_history = self.db_session.query(SessionHistory).filter(
                SessionHistory.session_id == session_id
            ).first()
            
            if session_history:
                session_history.ended_at = datetime.utcnow()
                session_history.session_summary = session_insights["summary"]
                session_history.topics_discussed = session_insights["topics"]
                session_history.outcomes = session_insights["outcomes"]
                session_history.is_active = False
                
                # Update metadata
                metadata = session_history.session_metadata or {}
                metadata.update({
                    "total_interactions": session_insights["total_interactions"],
                    "session_duration": session_insights["session_duration"],
                    "tools_effectiveness": session_insights["tools_effectiveness"]
                })
                session_history.session_metadata = metadata
                
                try:
                    self.db_session.commit()
                except Exception as e:
                    self.db_session.rollback()
                    self.logger.warning(f"Failed to update session history on end: {str(e)}")
            
            # Store session memories even if history update fails
            await self.memory_service.store_session_memory(
                session_id=session_id,
                user_id=user_id,
                session_data={
                    "summary": session_insights["summary"],
                    "topics": session_insights["topics"],
                    "tools_used": list(session_data["tools_used"]),
                    "interactions": session_data["interactions"],
                    "outcomes": session_insights["outcomes"],
                    "session_length": session_insights["session_duration"]
                }
            )
            
            # Update user preferences based on session
            await self._update_user_preferences_from_session(user_id, session_data, session_insights)
            
            # Clean up active session
            del self.active_sessions[session_id]
            
            self.logger.info(f"Ended session {session_id} with memory capture for user {user_id}")
            return session_history.to_dict() if session_history else None
            
        except Exception as e:
            self.logger.error(f"Error ending session {session_id}: {str(e)}")
            return None
    
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
            "session_duration": (datetime.utcnow() - datetime.fromisoformat(session_data["start_time"])).seconds,
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
        
        return session_history
    
    async def _learn_preferences_from_interaction(
        self,
        user_id: str,
        user_input: str,
        agent_response: str,
        tools_used: Optional[List[str]]
    ):
        """Learn user preferences from interactions"""
        
        # Detect explicit preferences with more patterns
        preference_patterns = [
            ("I prefer", 0.9),
            ("I like", 0.8),
            ("I want", 0.8),
            ("I need", 0.8),
            ("I always", 0.85),
            ("I usually", 0.75),
            ("I don't like", 0.85),
            ("I hate", 0.9),
            ("please", 0.6),
            ("could you", 0.6)
        ]
        
        # Extract preferences from user input
        for phrase, confidence in preference_patterns:
            if phrase.lower() in user_input.lower():
                sentences = user_input.split('.')
                for sentence in sentences:
                    if phrase.lower() in sentence.lower():
                        # Determine preference category
                        category = self._determine_preference_category(sentence, tools_used)
                        
                        # Store the preference
                        await self.user_profile_service.update_preference(
                            user_id=user_id,
                            key=f"preference_{category}",
                            value=sentence.strip(),
                            preference_type="explicit",
                            confidence=confidence,
                            category=category
                        )
        
        # Learn communication style preferences
        await self._learn_communication_style(user_id, user_input, agent_response)
        
        # Learn tool preferences with more context
        if tools_used:
            for tool in tools_used:
                await self.user_profile_service.update_preference(
                    user_id=user_id,
                    key=f"tool_usage_{tool}",
                    value={
                        "frequency": 1,
                        "context": user_input[:200],
                        "last_used": datetime.utcnow().isoformat(),
                        "success_indicator": "positive" if "thank" in user_input.lower() else "neutral"
                    },
                    preference_type="implicit",
                    confidence=0.7,
                    category="functionality"
                )
    
    def _determine_preference_category(self, text: str, tools_used: Optional[List[str]] = None) -> str:
        """Determine the category of a preference based on its content"""
        text = text.lower()
        
        # Communication preferences
        if any(word in text for word in ["say", "tell", "explain", "show", "respond"]):
            return "communication"
        
        # Tool preferences
        if tools_used and any(tool.lower() in text for tool in tools_used):
            return "functionality"
        
        # Interface preferences
        if any(word in text for word in ["display", "format", "layout", "style"]):
            return "interface"
        
        # Task preferences
        if any(word in text for word in ["when", "how", "what", "workflow", "process"]):
            return "task"
        
        return "general"
    
    async def _learn_communication_style(self, user_id: str, user_input: str, agent_response: str):
        """Learn communication style preferences from interaction"""
        
        # Analyze formality
        formal_indicators = ["please", "would you", "could you", "kindly"]
        informal_indicators = ["hey", "hi", "thanks", "cool"]
        
        formality_score = sum(1 for word in formal_indicators if word in user_input.lower())
        informality_score = sum(1 for word in informal_indicators if word in user_input.lower())
        
        if formality_score > informality_score:
            style = "formal"
        elif informality_score > formality_score:
            style = "informal"
        else:
            style = "balanced"
        
        # Analyze verbosity preference
        words = user_input.split()
        if len(words) > 30:
            verbosity = "detailed"
        elif len(words) < 10:
            verbosity = "concise"
        else:
            verbosity = "balanced"
        
        # Update communication style preferences
        await self.user_profile_service.update_preference(
            user_id=user_id,
            key="communication_style",
            value={
                "formality": style,
                "verbosity": verbosity,
                "last_updated": datetime.utcnow().isoformat()
            },
            preference_type="implicit",
            confidence=0.65,
            category="communication"
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
        """Calculate importance score for an interaction"""
        importance = 0.3  # Base importance
        
        # Check for preference indicators
        preference_indicators = [
            "I prefer", "I like", "I want", "I need",
            "I always", "I usually", "I don't like", "I hate",
            "my name is", "call me"
        ]
        
        # Increase importance for preference-related interactions
        for indicator in preference_indicators:
            if indicator.lower() in user_input.lower():
                importance += 0.3
                break
        
        # Increase importance based on tools used
        if tools_used:
            importance += 0.2
        
        # Increase importance for longer, more detailed interactions
        if len(user_input) > 50 or len(agent_response) > 100:
            importance += 0.1
        
        # Increase importance for interactions with specific topics
        important_topics = [
            "schedule", "reminder", "preference", "profile",
            "remember", "forget", "always", "never"
        ]
        
        for topic in important_topics:
            if topic in user_input.lower() or topic in agent_response.lower():
                importance += 0.1
                break
        
        return min(1.0, importance)  # Cap at 1.0
    
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
        user_id: str,  # This will be ignored
        interaction: Dict[str, Any]
    ):
        """Update contextual memory with significant interactions"""
        
        # Lower threshold to capture more interactions
        if interaction.get("importance_score", 0) > 0.3:  # Lowered from 0.6
            # Extract key information from the interaction
            user_input = interaction['user_input']
            agent_response = interaction['agent_response']
            
            # Extract facts and preferences
            facts = []
            preferences = []
            
            # Look for facts in user input (statements about themselves)
            fact_indicators = ["I am", "I'm", "my name is", "I work", "I live"]
            for indicator in fact_indicators:
                if indicator.lower() in user_input.lower():
                    # Get the sentence containing the fact
                    sentences = user_input.split('.')
                    for sentence in sentences:
                        if indicator.lower() in sentence.lower():
                            facts.append(sentence.strip())
            
            # Look for preferences in user input
            preference_indicators = ["I prefer", "I like", "I want", "I need", "I don't like"]
            for indicator in preference_indicators:
                if indicator.lower() in user_input.lower():
                    sentences = user_input.split('.')
                    for sentence in sentences:
                        if indicator.lower() in sentence.lower():
                            preferences.append(sentence.strip())
            
            # If we found facts or preferences, store them separately
            for fact in facts:
                # Check if this fact already exists
                existing_memories = await self.memory_service.search_memories(
                    user_id=DEFAULT_USER_ID,
                    query=fact,
                    memory_type="fact",
                    limit=1
                )
                
                if not existing_memories or not any(
                    memory["content"] == fact for memory in existing_memories
                ):
                    await self.memory_service.store_memory(
                        user_id=DEFAULT_USER_ID,
                        content=fact,
                        memory_type="fact",
                        session_id=session_id,
                        importance_score=0.8,  # Facts are important
                        tags=["fact", "user_information"],
                        metadata={
                            "source": "conversation",
                            "interaction_type": "fact",
                            "extracted_from": user_input[:100]
                        }
                    )
            
            for preference in preferences:
                # Check if this preference already exists
                existing_memories = await self.memory_service.search_memories(
                    user_id=DEFAULT_USER_ID,
                    query=preference,
                    memory_type="preference",
                    limit=1
                )
                
                if not existing_memories or not any(
                    memory["content"] == preference for memory in existing_memories
                ):
                    await self.memory_service.store_memory(
                        user_id=DEFAULT_USER_ID,
                        content=preference,
                        memory_type="preference",
                        session_id=session_id,
                        importance_score=0.7,  # Preferences are important
                        tags=["preference", "user_preference"],
                        metadata={
                            "source": "conversation",
                            "interaction_type": "preference",
                            "extracted_from": user_input[:100]
                        }
                    )
            
            # For general conversation, only store if it's significant
            if interaction.get("importance_score", 0) > 0.5:
                # Extract key information from the conversation
                key_info = []
                
                # Add user question/request
                if "?" in user_input or any(word in user_input.lower() for word in ["how", "what", "why", "when", "where", "can you", "could you"]):
                    key_info.append(f"User asked: {user_input}")
                
                # Add important agent responses (decisions, actions, confirmations)
                if any(word in agent_response.lower() for word in ["i have", "i will", "i've", "done", "completed", "created", "updated", "here's"]):
                    key_info.append(f"Assistant action: {agent_response}")
                
                if key_info:
                    memory_content = "\n".join(key_info)
                    
                    # Check if similar content exists
                    existing_memories = await self.memory_service.search_memories(
                        user_id=DEFAULT_USER_ID,
                        query=memory_content,
                        memory_type="conversation",
                        limit=1
                    )
                    
                    # Only store if it's not too similar to existing memories
                    if not existing_memories or all(
                        memory["relevance_score"] < 0.8 for memory in existing_memories
                    ):
                        await self.memory_service.store_memory(
                            user_id=DEFAULT_USER_ID,
                            content=memory_content,
                            memory_type="conversation",
                            session_id=session_id,
                            importance_score=interaction["importance_score"],
                            tags=interaction.get("tools_used", []) + ["conversation"],
                            metadata={
                                "interaction_timestamp": interaction.get("timestamp"),
                                "memory_type": "conversation",
                                "interaction_type": "dialogue",
                                "tools_used": interaction.get("tools_used", [])
                            }
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
    
    async def get_session(self, session_id: str, app_name: str = None, user_id: str = None) -> Optional[Session]:
        """Get a session by ID with proper error handling"""
        try:
            # Use stored app_name and user_id from active sessions if available
            if session_id in self.active_sessions:
                app_name = app_name or APP_NAME
                user_id = user_id or DEFAULT_USER_ID
            elif not app_name or not user_id:
                self.logger.warning(f"Session {session_id} not found in active sessions and missing required parameters")
                return None

            # Call parent class method with correct signature
            session = await super().get_session(
                session_id=session_id,
                app_name=app_name,
                user_id=user_id
            )
            
            # If session exists, enrich it with our tracked data
            if session and session_id in self.active_sessions:
                session_data = self.active_sessions[session_id]
                session.state.update({
                    "session_stats": {
                        "interactions_count": len(session_data["interactions"]),
                        "tools_used": list(session_data["tools_used"]),
                        "topics_discussed": list(set(session_data["topics_discussed"])),
                        "session_duration": (datetime.utcnow() - datetime.fromisoformat(session_data["start_time"])).seconds
                    }
                })
            
            return session
        
        except Exception as e:
            self.logger.error(f"Error getting session {session_id}: {str(e)}")
            return None