#!/usr/bin/env python3
"""
Memory Profile MCP Server

This server provides tools for memory and user profile operations,
allowing the agent to interact with the multi-tiered memory system.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from pathlib import Path
import sys
import os

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(project_root))

from app.config.database import db_config
from app.services.user_profile_service import UserProfileService
from app.services.memory_service import JarvisMemoryService

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory-profile-server")

# Initialize database and services
try:
    db_config.create_tables()
    db_session = next(db_config.get_db_session())
    
    user_profile_service = UserProfileService(db_session)
    memory_service = JarvisMemoryService(db_session)
    
    logger.info("Memory profile services initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize memory profile services: {str(e)}")
    user_profile_service = None
    memory_service = None

# Create the server instance
server = Server("memory-profile-server")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available memory and profile tools"""
    return [
        types.Tool(
            name="get_user_profile",
            description="Get comprehensive user profile information",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    }
                },
                "required": ["user_id"]
            }
        ),
        types.Tool(
            name="get_user_preferences",
            description="Get user preferences and settings",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "category": {
                        "type": "string",
                        "description": "Preference category (optional)"
                    }
                },
                "required": ["user_id"]
            }
        ),
        types.Tool(
            name="search_memories",
            description="Search user memories using semantic search",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "memory_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Types of memories to search (optional)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5
                    },
                    "importance_threshold": {
                        "type": "number",
                        "description": "Minimum importance score",
                        "default": 0.0
                    }
                },
                "required": ["user_id", "query"]
            }
        ),
        types.Tool(
            name="get_contextual_memories",
            description="Get contextually relevant memories for current conversation",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "current_query": {
                        "type": "string",
                        "description": "Current user query or context"
                    },
                    "session_topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topics discussed in current session"
                    },
                    "recent_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Recently used tools"
                    },
                    "max_memories": {
                        "type": "integer",
                        "description": "Maximum number of memories to retrieve",
                        "default": 10
                    }
                },
                "required": ["user_id"]
            }
        ),
        types.Tool(
            name="store_memory",
            description="Store a new memory or important information",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "content": {
                        "type": "string",
                        "description": "Memory content to store"
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "Type of memory (conversation, fact, preference, etc.)",
                        "default": "conversation"
                    },
                    "importance_score": {
                        "type": "number",
                        "description": "Importance score (0.0 to 1.0)",
                        "default": 0.5
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags for the memory"
                    }
                },
                "required": ["user_id", "content"]
            }
        ),
        types.Tool(
            name="update_user_preference",
            description="Update or create a user preference",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "key": {
                        "type": "string",
                        "description": "Preference key"
                    },
                    "value": {
                        "type": "string",
                        "description": "Preference value"
                    },
                    "preference_type": {
                        "type": "string",
                        "description": "Type of preference (explicit, implicit, inferred)",
                        "default": "explicit"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score (0.0 to 1.0)",
                        "default": 1.0
                    },
                    "category": {
                        "type": "string",
                        "description": "Preference category",
                        "default": "general"
                    }
                },
                "required": ["user_id", "key", "value"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls for memory and profile operations"""
    
    if not user_profile_service or not memory_service:
        return [types.TextContent(
            type="text",
            text="Error: Memory profile services not available"
        )]
    
    try:
        if name == "get_user_profile":
            result = await _get_user_profile(arguments)
        elif name == "get_user_preferences":
            result = await _get_user_preferences(arguments)
        elif name == "search_memories":
            result = await _search_memories(arguments)
        elif name == "get_contextual_memories":
            result = await _get_contextual_memories(arguments)
        elif name == "store_memory":
            result = await _store_memory(arguments)
        elif name == "update_user_preference":
            result = await _update_user_preference(arguments)
        else:
            result = f"Unknown tool: {name}"
        
        return [types.TextContent(type="text", text=str(result))]
        
    except Exception as e:
        logger.error(f"Error in tool {name}: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error executing {name}: {str(e)}"
        )]

async def _get_user_profile(arguments: dict) -> dict:
    """Get user profile information"""
    user_id = arguments["user_id"]
    profile = await user_profile_service.get_user_profile(user_id)
    return {
        "user_id": user_id,
        "profile": profile,
        "status": "success"
    }

async def _get_user_preferences(arguments: dict) -> dict:
    """Get user preferences"""
    user_id = arguments["user_id"]
    category = arguments.get("category")
    preferences = await user_profile_service.get_user_preferences(user_id, category)
    return {
        "user_id": user_id,
        "preferences": preferences,
        "category": category,
        "status": "success"
    }

async def _search_memories(arguments: dict) -> dict:
    """Search user memories"""
    user_id = arguments["user_id"]
    query = arguments["query"]
    memory_types = arguments.get("memory_types")
    limit = arguments.get("limit", 5)
    importance_threshold = arguments.get("importance_threshold", 0.0)
    
    memories = await memory_service.search_memories(
        user_id=user_id,
        query=query,
        memory_types=memory_types,
        limit=limit,
        importance_threshold=importance_threshold
    )
    
    return {
        "user_id": user_id,
        "query": query,
        "memories": memories,
        "count": len(memories),
        "status": "success"
    }

async def _get_contextual_memories(arguments: dict) -> dict:
    """Get contextually relevant memories"""
    user_id = arguments["user_id"]
    current_context = {}
    
    if "current_query" in arguments:
        current_context["query"] = arguments["current_query"]
    if "session_topics" in arguments:
        current_context["session_topics"] = arguments["session_topics"]
    if "recent_tools" in arguments:
        current_context["recent_tools"] = arguments["recent_tools"]
    
    max_memories = arguments.get("max_memories", 10)
    
    context_result = await memory_service.get_contextual_memories(
        user_id=user_id,
        current_context=current_context,
        max_memories=max_memories
    )
    
    return {
        "user_id": user_id,
        "context": current_context,
        "contextual_memories": context_result,
        "status": "success"
    }

async def _store_memory(arguments: dict) -> dict:
    """Store a new memory"""
    user_id = arguments["user_id"]
    content = arguments["content"]
    memory_type = arguments.get("memory_type", "conversation")
    importance_score = arguments.get("importance_score", 0.5)
    tags = arguments.get("tags", "")
    
    memory_id = await memory_service.store_memory(
        user_id=user_id,
        content=content,
        memory_type=memory_type,
        importance_score=importance_score,
        tags=tags
    )
    
    return {
        "user_id": user_id,
        "memory_id": memory_id,
        "content_preview": content[:100] + "..." if len(content) > 100 else content,
        "status": "success"
    }

async def _update_user_preference(arguments: dict) -> dict:
    """Update user preference"""
    user_id = arguments["user_id"]
    key = arguments["key"]
    value = arguments["value"]
    preference_type = arguments.get("preference_type", "explicit")
    confidence = arguments.get("confidence", 1.0)
    category = arguments.get("category", "general")
    
    await user_profile_service.update_preference(
        user_id=user_id,
        key=key,
        value=value,
        preference_type=preference_type,
        confidence=confidence,
        category=category
    )
    
    return {
        "user_id": user_id,
        "preference": {
            "key": key,
            "value": value,
            "type": preference_type,
            "category": category
        },
        "status": "success"
    }

async def main():
    """Main server function"""
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="memory-profile-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main()) 