import logging
import uuid
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import asyncio
import json
import os
import re

import chromadb
from chromadb.config import Settings
import vertexai
from vertexai.preview.language_models import TextEmbeddingModel, TextEmbeddingInput
import numpy as np
from sqlalchemy.orm import Session as DBSession

from app.models.database import MemoryVector
from app.config.constants import DEFAULT_USER_ID

class JarvisMemoryService:
    def __init__(self, db_session: DBSession, collection_name: str = "jarvis_memory"):
        self.db = db_session
        self.logger = logging.getLogger(__name__)
        self.collection_name = collection_name
        
        # Initialize ChromaDB with proper settings
        persist_directory = os.path.abspath("./jarvis_memory_db")
        os.makedirs(persist_directory, exist_ok=True)
        
        self.chroma_client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False,
            is_persistent=True
        ))
        
        # Initialize Vertex AI
        vertexai.init(project=os.getenv("GOOGLE_CLOUD_PROJECT", "jarvis-develop-460215"))
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
        
        # Get or create collection
        try:
            # Try to get existing collection
            self.collection = self.chroma_client.get_collection(name=collection_name)
            self.logger.info(f"Loaded existing memory collection: {collection_name}")
        except Exception as e:
            # Collection doesn't exist, create it
            try:
                self.collection = self.chroma_client.create_collection(
                    name=collection_name,
                    metadata={"description": "Jarvis long-term memory storage"}
                )
                self.logger.info(f"Created new memory collection: {collection_name}")
            except Exception as e:
                self.logger.error(f"Error creating ChromaDB collection: {str(e)}")
                raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding using Vertex AI Text Embeddings"""
        
        # Validate input text
        if not text or not text.strip():
            # Return a default embedding for empty text
            self.logger.warning("Empty text provided for embedding, using default")
            text = "empty content"
        
        # Ensure text is not too short (minimum 3 characters)
        if len(text.strip()) < 3:
            text = f"short content: {text.strip()}"
        
        try:
            text_input = TextEmbeddingInput(
                text=text.strip(),
                task_type="RETRIEVAL_DOCUMENT"  # Using RETRIEVAL_DOCUMENT since we're storing text for later retrieval
            )
            embeddings = self.embedding_model.get_embeddings([text_input])
            return embeddings[0].values
        except Exception as e:
            self.logger.error(f"Error generating embedding for text '{text[:50]}...': {str(e)}")
            # Return a zero vector as fallback (this should match the embedding dimension)
            return [0.0] * 768  # Default dimension for text-embedding-005
    
    async def store_memory(
        self,
        user_id: str,  # This will be ignored
        content: str,
        memory_type: str = "conversation",
        session_id: Optional[str] = None,
        importance_score: float = 0.5,
        tags: Union[List[str], str] = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store a memory in the vector database with enhanced metadata"""
        
        # Generate unique ID for this memory
        memory_id = str(uuid.uuid4())
        
        # Create embedding using Vertex AI
        embedding = await self._get_embedding(content)
        
        # Generate a summary for long content
        content_summary = await self._generate_content_summary(content) if len(content) > 200 else content
        
        # Convert tags to string if needed
        tags_str = tags
        if isinstance(tags, list):
            tags_str = ", ".join(tags)
        elif tags is None:
            tags_str = ""
        
        # Create memory metadata
        memory_metadata = {
            "user_id": DEFAULT_USER_ID,  # Always use default user
            "memory_type": memory_type,
            "session_id": session_id or "",
            "importance_score": float(importance_score),
            "timestamp": datetime.utcnow().isoformat(),
            "tags": tags_str,
            "content_length": len(content),
            "has_summary": bool(content_summary != content),
            "memory_category": self._determine_memory_category(content, memory_type)
        }
        
        # Add additional metadata if provided
        if metadata:
            # Ensure all metadata values are primitive types
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    memory_metadata[key] = value
        
        # Store in ChromaDB
        try:
            self.collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[memory_metadata],
                ids=[memory_id]
            )
            
            # Store reference in SQL database
            memory_vector = MemoryVector(
                user_id=DEFAULT_USER_ID,  # Always use default user
                session_id=session_id,
                content=content,
                content_summary=content_summary,
                vector_id=memory_id,
                memory_type=memory_type,
                importance_score=importance_score,
                tags=tags,  # Store as list in SQL
                metadata=memory_metadata
            )
            self.db.add(memory_vector)
            
            # Update related memories
            await self._update_related_memories(memory_vector)
            
            # Cleanup old memories if needed
            await self._cleanup_old_memories(DEFAULT_USER_ID)  # Always use default user
            
            self.db.commit()
            self.logger.info(f"Stored memory {memory_id} for default user")
            
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Error storing memory: {str(e)}")
            self.db.rollback()
            return None
    
    def _calculate_memory_importance(
        self,
        content: str,
        memory_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate memory importance based on content and context"""
        importance = 0.5  # Base importance
        
        # Content-based factors
        if len(content) > 500:  # Long, detailed content
            importance += 0.1
        if "?" in content:  # Questions are important
            importance += 0.1
        
        # Type-based factors
        type_weights = {
            "session_summary": 0.2,
            "preference": 0.15,
            "fact": 0.1,
            "conversation": 0.0
        }
        importance += type_weights.get(memory_type, 0.0)
        
        # Metadata-based factors
        if metadata:
            if metadata.get("explicit_preference"):
                importance += 0.2
            if metadata.get("tools_used"):
                importance += 0.1
        
        return min(1.0, importance)
    
    async def _generate_content_summary(self, content: str) -> str:
        """Generate a concise summary for long content"""
        if len(content) <= 200:
            return content
            
        # Simple extractive summarization
        sentences = content.split('.')
        if len(sentences) <= 2:
            return content
            
        # Take first and last meaningful sentences
        summary = f"{sentences[0].strip()}... {sentences[-2].strip()}"
        return summary[:200] + "..." if len(summary) > 200 else summary
    
    async def _enhance_memory_tags(self, content: str, existing_tags: List[str]) -> List[str]:
        """Enhance memory tags with extracted topics"""
        tags = set(existing_tags)
        
        # Add content-based tags
        if "?" in content:
            tags.add("question")
        if any(word in content.lower() for word in ["how", "what", "why", "when", "where"]):
            tags.add("inquiry")
        if any(word in content.lower() for word in ["error", "problem", "issue", "bug"]):
            tags.add("troubleshooting")
        if any(word in content.lower() for word in ["thanks", "thank you", "appreciate"]):
            tags.add("gratitude")
        
        return list(tags)
    
    def _determine_memory_category(self, content: str, memory_type: str) -> str:
        """Determine the category of a memory based on its content and type"""
        content = content.lower()
        
        if memory_type == "session_summary":
            return "session"
        
        if any(word in content for word in ["error", "exception", "failed", "bug"]):
            return "troubleshooting"
        
        if any(word in content for word in ["how to", "example", "tutorial"]):
            return "learning"
        
        if "preference" in memory_type or any(word in content for word in ["i prefer", "i like", "i want"]):
            return "preference"
        
        return "general"
    
    async def _update_related_memories(self, memory: MemoryVector):
        """Update relationships between related memories"""
        try:
            # Search for related memories
            embedding = await self._get_embedding(memory.content)
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=5,
                where={"user_id": memory.user_id}
            )
            
            if not results or not results.get("ids"):
                return
            
            # Get related memory IDs
            related_ids = results["ids"][0]
            
            # Update access count for related memories
            for vector_id in related_ids:
                if vector_id != memory.vector_id:  # Don't update the current memory
                    related_memory = self.db.query(MemoryVector).filter(
                        MemoryVector.vector_id == vector_id
                    ).first()
                    
                    if related_memory:
                        related_memory.access_count += 1
                        related_memory.last_accessed = datetime.utcnow()
            
            self.db.commit()
            
        except Exception as e:
            self.logger.warning(f"Error updating related memories: {str(e)}")
            self.db.rollback()
    
    async def _cleanup_old_memories(self, user_id: str):
        """Clean up old, low-importance memories"""
        try:
            # Get retention days from user preferences (default 90 days)
            retention_days = 90  # TODO: Get from user preferences
            
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Find old memories with low importance
            old_memories = self.db.query(MemoryVector).filter(
                MemoryVector.user_id == user_id,
                MemoryVector.created_at < cutoff_date,
                MemoryVector.importance_score < 0.3,
                MemoryVector.access_count < 2
            ).all()
            
            # Delete from both databases
            for memory in old_memories:
                try:
                    self.collection.delete(ids=[memory.vector_id])
                    self.db.delete(memory)
                except Exception as e:
                    self.logger.warning(f"Error deleting memory {memory.vector_id}: {str(e)}")
            
            self.db.commit()
            
        except Exception as e:
            self.logger.warning(f"Error during memory cleanup: {str(e)}")
            self.db.rollback()
    
    async def search_memories(
        self,
        user_id: str,  # This will be ignored
        query: str,
        limit: int = 10,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Search for relevant memories using semantic similarity"""
        try:
            # Log the search request
            self.logger.info(f"Searching memories with query: '{query}', type: {memory_type}, min_importance: {min_importance}")
            
            # Get embedding for query
            query_embedding = await self._get_embedding(query)
            self.logger.debug(f"Generated embedding for query: {query[:50]}...")
            
            # Build where clause with proper operator syntax
            conditions = []
            conditions.append({"user_id": DEFAULT_USER_ID})
            
            if memory_type:
                conditions.append({"memory_type": memory_type})
            
            if min_importance > 0:
                conditions.append({"importance_score": {"$gte": min_importance}})
            
            # Use $and operator to combine conditions
            where = {"$and": conditions} if len(conditions) > 1 else conditions[0]
            self.logger.debug(f"Search filters: {where}")
            
            # Search in ChromaDB with increased limit for better recall
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(limit * 2, 20),  # Double the requested limit but cap at 20
                where=where
            )
            
            self.logger.debug(f"Raw search results: {results}")
            
            memories = []
            if not results or not results.get("documents"):
                self.logger.warning(f"No results found for query: {query}")
                # Try a fallback search without memory type filter if no results
                if memory_type:
                    self.logger.info("Attempting fallback search without memory type filter")
                    where = {"user_id": DEFAULT_USER_ID}  # Only keep user filter
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(limit * 2, 20),
                        where=where
                    )
            
            if results and results.get("documents"):
                # Process results with more lenient distance threshold
                distances = results.get("distances", [[]])[0] if results.get("distances") else []
                
                for idx, (doc, metadata) in enumerate(zip(
                    results["documents"][0],
                    results["metadatas"][0]
                )):
                    # Calculate similarity score - if distances not available, use a default high score
                    similarity = 1 - distances[idx] if distances else 0.8
                    
                    # Log the match details
                    self.logger.debug(f"Memory match: similarity={similarity:.3f}, type={metadata.get('memory_type')}")
                    self.logger.debug(f"Content preview: {doc[:100]}...")
                    
                    # Include results with lower similarity threshold
                    if similarity > 0.3:  # More lenient threshold
                        memories.append({
                            "content": doc,
                            "metadata": metadata,
                            "relevance_score": similarity,
                            "memory_type": metadata.get("memory_type", "unknown"),
                            "importance_score": metadata.get("importance_score", 0.0),
                            "timestamp": metadata.get("timestamp"),
                            "tags": metadata.get("tags", [])
                        })
                
                # Sort by relevance and limit results
                memories.sort(key=lambda x: x["relevance_score"], reverse=True)
                memories = memories[:limit]
                
                # Update access count for retrieved memories
                if results.get("ids"):
                    await self._update_memory_access(results["ids"][0][:len(memories)])
                
                self.logger.info(f"Retrieved {len(memories)} memories with relevance scores: " + 
                               ", ".join([f"{m['relevance_score']:.2f}" for m in memories]))
            
            return memories
            
        except Exception as e:
            self.logger.error(f"Error searching memories: {str(e)}", exc_info=True)
            return []
    
    async def get_contextual_memories(
        self,
        user_id: str,  # This will be ignored
        current_context: Dict[str, Any],
        max_memories: int = 10
    ) -> Dict[str, Any]:
        """Get contextually relevant memories based on current conversation state"""
        
        # Extract context elements for search
        context_elements = []
        
        # Process query with more weight
        if "query" in current_context:
            query = current_context["query"]
            context_elements.append(query)  # Add original query
            # Add variations for better matching
            context_elements.append(f"user asked about {query}")
            context_elements.append(f"information about {query}")
        
        # Add session topics with explicit context
        if "session_topics" in current_context:
            for topic in current_context["session_topics"]:
                context_elements.append(f"topic: {topic}")
                context_elements.append(f"discussed {topic}")
        
        # Add tool context
        if "recent_tools" in current_context:
            for tool in current_context["recent_tools"]:
                context_elements.append(f"using {tool}")
                context_elements.append(f"tool: {tool}")
        
        # Build search query with weighted elements
        search_query = " ".join(context_elements) if context_elements else "general conversation"
        self.logger.info(f"Built context query: {search_query}")
        
        # Try different memory types in priority order
        memory_types = ["fact", "preference", "conversation"]
        all_memories = []
        
        for memory_type in memory_types:
            # Search with current memory type
            memories = await self.search_memories(
                user_id=DEFAULT_USER_ID,  # Always use default user
                query=search_query,
                limit=max_memories,
                memory_type=memory_type,
                min_importance=0.0  # No minimum importance to get more results
            )
            all_memories.extend(memories)
        
        # Deduplicate memories based on content
        seen_contents = set()
        unique_memories = []
        for memory in all_memories:
            if memory["content"] not in seen_contents:
                seen_contents.add(memory["content"])
                unique_memories.append(memory)
        
        # Sort by relevance and limit
        unique_memories.sort(key=lambda x: x["relevance_score"], reverse=True)
        unique_memories = unique_memories[:max_memories]
        
        # Categorize memories by type
        categorized_memories = {
            "conversation": [],
            "preference": [],
            "fact": [],
            "experience": []
        }
        
        for memory in unique_memories:
            memory_type = memory.get("memory_type", "conversation")
            if memory_type in categorized_memories:
                categorized_memories[memory_type].append(memory)
        
        # Generate context summary
        context_summary = await self._generate_context_summary(unique_memories)
        
        # Extract preferences from memories
        preferences = await self._extract_preferences_from_memories(unique_memories)
        
        # Log retrieval results
        self.logger.info(f"Retrieved {len(unique_memories)} unique memories")
        for memory_type, memories in categorized_memories.items():
            if memories:
                self.logger.info(f"- {memory_type}: {len(memories)} memories")
        
        return {
            "relevant_memories": unique_memories,
            "categorized_memories": categorized_memories,
            "context_summary": context_summary,
            "inferred_preferences": preferences,
            "memory_count": len(unique_memories)
        }
    
    async def store_session_memory(
        self,
        session_id: str,
        user_id: str,
        session_data: Dict[str, Any]
    ):
        """Store session-level memories and insights"""
        
        # Create comprehensive session summary
        session_content = self._create_session_content(session_data)
        
        # Extract topics and key insights
        topics = session_data.get("topics", [])
        tools_used = session_data.get("tools_used", [])
        
        # Check if similar session summary exists
        existing_summaries = await self.search_memories(
            user_id=user_id,
            query=session_content,
            memory_type="session_summary",
            limit=1
        )
        
        # Only store if it's not too similar to existing summaries
        if not existing_summaries or all(
            memory["relevance_score"] < 0.8 for memory in existing_summaries
        ):
            # Store main session memory with higher importance
            await self.store_memory(
                user_id=user_id,
                content=session_content,
                memory_type="session_summary",
                session_id=session_id,
                importance_score=0.8,  # High importance for session summaries
                tags=topics + tools_used + ["session_summary"],
                metadata={
                    "session_length": session_data.get("session_length", 0),
                    "tools_used": tools_used,
                    "outcomes": session_data.get("outcomes", []),
                    "interaction_count": len(session_data.get("interactions", [])),
                    "memory_type": "session_summary"
                }
            )
        
        # Store significant individual interactions
        if "interactions" in session_data:
            for interaction in session_data["interactions"]:
                # Only store high-importance interactions
                if interaction.get("importance_score", 0) > 0.5:  # Increased threshold
                    # Extract key information
                    user_input = interaction['user_input']
                    agent_response = interaction['agent_response']
                    
                    # Only store if it contains valuable information
                    if any(indicator in user_input.lower() for indicator in [
                        "i am", "i'm", "my name is", "i work", "i live",  # Facts
                        "i prefer", "i like", "i want", "i need",  # Preferences
                        "how", "what", "why", "when", "where", "can you"  # Questions
                    ]):
                        # Extract the relevant part
                        sentences = user_input.split('.')
                        relevant_sentences = []
                        for sentence in sentences:
                            if any(indicator in sentence.lower() for indicator in [
                                "i am", "i'm", "my name is", "i work", "i live",
                                "i prefer", "i like", "i want", "i need",
                                "how", "what", "why", "when", "where", "can you"
                            ]):
                                relevant_sentences.append(sentence.strip())
                        
                        if relevant_sentences:
                            interaction_content = "\n".join(relevant_sentences)
                            
                            # Check if similar content exists
                            existing_memories = await self.search_memories(
                                user_id=user_id,
                                query=interaction_content,
                                limit=1
                            )
                            
                            # Only store if not duplicate
                            if not existing_memories or all(
                                memory["relevance_score"] < 0.8 for memory in existing_memories
                            ):
                                # Extract potential preferences
                                preferences = self._extract_preferences_from_text(interaction_content)
                                
                                # Add preference tags if found
                                tags = interaction.get("tools_used", []) + ["interaction"]
                                if preferences:
                                    tags.extend([f"preference:{p}" for p in preferences])
                                
                                await self.store_memory(
                                    user_id=user_id,
                                    content=interaction_content,
                                    memory_type="conversation",
                                    session_id=session_id,
                                    importance_score=max(0.6, interaction.get("importance_score", 0.5)),
                                    tags=tags,
                                    metadata={
                                        "interaction_timestamp": interaction.get("timestamp"),
                                        "memory_type": "conversation",
                                        "interaction_type": "dialogue",
                                        "preferences_found": preferences,
                                        "tools_used": interaction.get("tools_used", [])
                                    }
                                )
    
    async def _update_memory_access(self, memory_ids: List[str]):
        """Update access count and last accessed time for memories"""
        if not memory_ids:
            return
            
        try:
            memory_vectors = self.db.query(MemoryVector).filter(
                MemoryVector.vector_id.in_(memory_ids)
            ).all()
            
            for memory in memory_vectors:
                memory.access_count += 1
                memory.last_accessed = datetime.utcnow()
            
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Error updating memory access: {str(e)}")
            self.db.rollback()
    
    def _create_session_content(self, session_data: Dict[str, Any]) -> str:
        """Create a comprehensive text representation of session data"""
        content_parts = []
        
        if "summary" in session_data:
            content_parts.append(f"Session Summary: {session_data['summary']}")
        
        if "topics" in session_data:
            content_parts.append(f"Topics Discussed: {', '.join(session_data['topics'])}")
        
        if "key_interactions" in session_data:
            content_parts.append("Key Interactions:")
            for interaction in session_data["key_interactions"]:
                content_parts.append(f"- {interaction}")
        
        if "outcomes" in session_data:
            content_parts.append(f"Session Outcomes: {session_data['outcomes']}")
        
        return "\n".join(content_parts)
    
    async def _generate_context_summary(self, memories: List[Dict[str, Any]]) -> str:
        """Generate a summary of retrieved memories for context"""
        if not memories:
            return "No relevant context from previous interactions."
        
        # Group memories by type and importance
        high_importance = [m for m in memories if m.get("importance_score", 0) > 0.7]
        recent_conversations = [m for m in memories if m.get("memory_type") == "conversation"]
        
        summary_parts = []
        
        if high_importance:
            summary_parts.append(f"Important context: {len(high_importance)} significant past interactions")
        
        if recent_conversations:
            summary_parts.append(f"Recent conversations covered: {len(recent_conversations)} related topics")
        
        # Extract common themes
        all_tags = []
        for memory in memories:
            all_tags.extend(memory.get("tags", []))
        
        if all_tags:
            from collections import Counter
            common_tags = Counter(all_tags).most_common(3)
            if common_tags:
                summary_parts.append(f"Common themes: {', '.join([tag for tag, _ in common_tags])}")
        
        return ". ".join(summary_parts) if summary_parts else "Limited relevant context available."
    
    async def _extract_preferences_from_memories(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract potential preferences from memory content"""
        preferences = []
        
        preference_indicators = [
            "I prefer", "I like", "I always", "I usually", "I want",
            "I need", "My favorite", "I don't like", "I hate"
        ]
        
        for memory in memories:
            content = memory.get("content", "").lower()
            for indicator in preference_indicators:
                if indicator.lower() in content:
                    # Extract the sentence containing the preference
                    sentences = content.split('.')
                    for sentence in sentences:
                        if indicator.lower() in sentence:
                            preferences.append({
                                "text": sentence.strip(),
                                "confidence": memory.get("importance_score", 0.5),
                                "source": "memory_analysis",
                                "timestamp": memory.get("timestamp")
                            })
                            break
        
        return preferences[:5]  # Return top 5 potential preferences
    
    def _extract_preferences_from_text(self, text: str) -> List[str]:
        """Extract potential user preferences from text"""
        preferences = []
        
        # Common preference indicators
        preference_patterns = [
            (r"(?i)I prefer", 0.9),
            (r"(?i)I like", 0.8),
            (r"(?i)I want", 0.7),
            (r"(?i)I need", 0.7),
            (r"(?i)I always", 0.85),
            (r"(?i)I usually", 0.75),
            (r"(?i)I don't like", 0.85),
            (r"(?i)I hate", 0.9),
            (r"(?i)please", 0.6),
            (r"(?i)could you", 0.6),
            (r"(?i)my name is", 0.95),
            (r"(?i)call me", 0.9),
            (r"(?i)schedule for", 0.8),
            (r"(?i)remind me", 0.8)
        ]
        
        # Check each pattern
        for pattern, confidence in preference_patterns:
            if re.search(pattern, text):
                # Get the context after the pattern
                match = re.search(pattern + r"\s+(.+?)(?:\.|\n|$)", text)
                if match:
                    preference = match.group(1).strip()
                    if len(preference) > 3:  # Minimum length to be meaningful
                        preferences.append(preference)
        
        return preferences 