import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import json
import os

import chromadb
from chromadb.config import Settings
import vertexai
from vertexai.preview.language_models import TextEmbeddingModel, TextEmbeddingInput
import numpy as np
from sqlalchemy.orm import Session as DBSession

from app.models.database import MemoryVector

class JarvisMemoryService:
    def __init__(self, db_session: DBSession, collection_name: str = "jarvis_memory"):
        self.db = db_session
        self.logger = logging.getLogger(__name__)
        self.collection_name = collection_name
        
        # Initialize ChromaDB
        self.chroma_client = chromadb.Client(Settings(
            persist_directory="./jarvis_memory_db",
            anonymized_telemetry=False
        ))
        
        # Initialize Vertex AI
        vertexai.init(project=os.getenv("GOOGLE_CLOUD_PROJECT", "jarvis-develop-460215"))
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
        
        # Get or create collection
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
            self.logger.info(f"Loaded existing memory collection: {collection_name}")
        except:
            self.collection = self.chroma_client.create_collection(
                name=collection_name,
                metadata={"description": "Jarvis long-term memory storage"}
            )
            self.logger.info(f"Created new memory collection: {collection_name}")
    
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
        user_id: str,
        content: str,
        memory_type: str = "conversation",
        session_id: Optional[str] = None,
        importance_score: float = 0.5,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Store a memory in the vector database"""
        
        # Generate unique ID for this memory
        memory_id = str(uuid.uuid4())
        
        # Create embedding using Vertex AI
        embedding = await self._get_embedding(content)
        
        # Prepare metadata
        memory_metadata = {
            "user_id": user_id,
            "memory_type": memory_type,
            "session_id": session_id or "",
            "importance_score": importance_score,
            "timestamp": datetime.utcnow().isoformat(),
            "tags": tags or [],
            **(metadata or {})
        }
        
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
                user_id=user_id,
                session_id=session_id,
                content=content,
                content_summary=content[:200] + "..." if len(content) > 200 else content,
                vector_id=memory_id,
                memory_type=memory_type,
                importance_score=importance_score,
                tags=tags or []
            )
            self.db.add(memory_vector)
            self.db.commit()
            
            self.logger.info(f"Stored memory {memory_id} for user {user_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Error storing memory: {str(e)}")
            self.db.rollback()
            raise
    
    async def search_memories(
        self,
        user_id: str,
        query: str,
        memory_types: List[str] = None,
        limit: int = 5,
        importance_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Search for relevant memories using semantic similarity"""
        
        try:
            # Generate query embedding using Vertex AI
            query_embedding = await self._get_embedding(query)
            
            # Prepare where clause for filtering
            where_clause = {"user_id": user_id}
            if memory_types:
                where_clause["memory_type"] = {"$in": memory_types}
            if importance_threshold > 0:
                where_clause["importance_score"] = {"$gte": importance_threshold}
            
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
            memories = []
            if results and results["documents"]:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                )):
                    memories.append({
                        "content": doc,
                        "metadata": metadata,
                        "relevance_score": 1 - distance,  # Convert distance to similarity
                        "memory_type": metadata.get("memory_type", "unknown"),
                        "importance_score": metadata.get("importance_score", 0.0),
                        "timestamp": metadata.get("timestamp"),
                        "tags": metadata.get("tags", [])
                    })
            
            # Update access count for retrieved memories
            await self._update_memory_access(results.get("ids", [[]])[0] if results else [])
            
            self.logger.debug(f"Retrieved {len(memories)} memories for query: {query[:50]}...")
            return memories
            
        except Exception as e:
            self.logger.error(f"Error searching memories: {str(e)}")
            return []
    
    async def get_contextual_memories(
        self,
        user_id: str,
        current_context: Dict[str, Any],
        max_memories: int = 10
    ) -> Dict[str, Any]:
        """Get contextually relevant memories based on current conversation state"""
        
        # Extract context elements for search
        context_elements = []
        
        if "query" in current_context:
            context_elements.append(current_context["query"])
        
        if "session_topics" in current_context:
            context_elements.extend(current_context["session_topics"])
            
        if "recent_tools" in current_context:
            context_elements.extend([f"using {tool}" for tool in current_context["recent_tools"]])
        
        search_query = " ".join(context_elements) if context_elements else "general conversation"
        
        # Search for relevant memories
        memories = await self.search_memories(
            user_id=user_id,
            query=search_query,
            limit=max_memories
        )
        
        # Categorize memories by type
        categorized_memories = {
            "conversation": [],
            "preference": [],
            "fact": [],
            "experience": []
        }
        
        for memory in memories:
            memory_type = memory.get("memory_type", "conversation")
            if memory_type in categorized_memories:
                categorized_memories[memory_type].append(memory)
        
        # Generate context summary
        context_summary = await self._generate_context_summary(memories)
        
        # Extract preferences from memories
        preferences = await self._extract_preferences_from_memories(memories)
        
        return {
            "relevant_memories": memories,
            "categorized_memories": categorized_memories,
            "context_summary": context_summary,
            "inferred_preferences": preferences,
            "memory_count": len(memories)
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
        
        # Store main session memory
        await self.store_memory(
            user_id=user_id,
            content=session_content,
            memory_type="conversation",
            session_id=session_id,
            importance_score=0.7,
            tags=topics + tools_used,
            metadata={
                "session_length": session_data.get("session_length", 0),
                "tools_used": tools_used,
                "outcomes": session_data.get("outcomes", [])
            }
        )
        
        # Store significant individual interactions
        if "interactions" in session_data:
            for interaction in session_data["interactions"]:
                if interaction.get("importance_score", 0) > 0.6:
                    await self.store_memory(
                        user_id=user_id,
                        content=f"User: {interaction['user_input']}\nAssistant: {interaction['agent_response']}",
                        memory_type="conversation",
                        session_id=session_id,
                        importance_score=interaction.get("importance_score", 0.5),
                        tags=interaction.get("tools_used", []),
                        metadata={"interaction_timestamp": interaction.get("timestamp")}
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
    
    async def cleanup_old_memories(self, user_id: str, days_threshold: int = 90):
        """Clean up old, low-importance memories"""
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)
        
        # Find old, low-importance memories
        old_memories = self.db.query(MemoryVector).filter(
            MemoryVector.user_id == user_id,
            MemoryVector.created_at < cutoff_date,
            MemoryVector.importance_score < 0.3,
            MemoryVector.access_count < 2
        ).all()
        
        vector_ids_to_delete = [memory.vector_id for memory in old_memories]
        
        if vector_ids_to_delete:
            try:
                # Delete from ChromaDB
                self.collection.delete(ids=vector_ids_to_delete)
                
                # Delete from SQL database
                for memory in old_memories:
                    self.db.delete(memory)
                
                self.db.commit()
                self.logger.info(f"Cleaned up {len(vector_ids_to_delete)} old memories for user {user_id}")
                
            except Exception as e:
                self.logger.error(f"Error cleaning up memories: {str(e)}")
                self.db.rollback() 