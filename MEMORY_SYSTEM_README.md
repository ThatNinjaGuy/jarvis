# 🧠 Jarvis Multi-Tiered Memory System

This document describes the implementation of the Jarvis multi-tiered memory system, transforming your Google ADK agent into a sophisticated AI with persistent memory, user profiling, and contextual awareness.

## 🎯 **System Overview**

The multi-tiered memory system provides three levels of memory:

1. **Session Memory** (Tier 1): Current conversation context and immediate history
2. **User Profile Memory** (Tier 2): Long-term user preferences, communication style, and behavior patterns  
3. **Vector Memory** (Tier 3): Semantic search across all past interactions and stored knowledge

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Jarvis Agent                    │
├─────────────────────────────────────────────────────────────┤
│  Multi-Tiered Memory System                                │
│  ┌─────────────┬─────────────────┬─────────────────────────┐│
│  │ Session     │ User Profile    │ Vector Memory           ││
│  │ Memory      │ Memory          │ (ChromaDB)              ││
│  │ (Current)   │ (SQLAlchemy)    │ (Semantic Search)       ││
│  └─────────────┴─────────────────┴─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Enhanced Session Service & Memory Services                │
├─────────────────────────────────────────────────────────────┤
│  Original MCP Tools + Memory Profile Tools                 │
│  Calendar │ Gmail │ Maps │ YouTube │ Twitter │ Memory      │
└─────────────────────────────────────────────────────────────┘
```

## 📁 **File Structure**

```
app/
├── models/
│   └── database.py              # Database models for memory system
├── services/
│   ├── user_profile_service.py  # User profile and preference management
│   ├── memory_service.py        # Vector memory operations
│   └── enhanced_session_service.py # Enhanced session management
├── config/
│   ├── database.py              # Database configuration
│   └── enhanced_agent_session.py # Enhanced agent with memory
├── api/
│   └── enhanced_routes.py       # API endpoints with memory features
└── jarvis/
    └── mcp_servers/
        └── memory_profile/
            └── server.py         # MCP server for memory operations

setup_memory_system.py           # Setup script
requirements.txt                 # Updated dependencies
```

## 🚀 **Installation & Setup**

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Setup Script

```bash
python setup_memory_system.py
```

This will:

- Create database tables
- Initialize vector database (ChromaDB)
- Set up default configurations  
- Run health checks

### 3. Start Enhanced Application

Use the enhanced routes in your main application:

```python
# In your main.py or app startup
from app.api.enhanced_routes import app

# Or integrate with your existing FastAPI app
from app.config.enhanced_agent_session import start_enhanced_agent_session
```

## 💡 **Key Features**

### **Memory Capabilities**

- **Semantic Memory Search**: Find relevant past conversations using natural language
- **User Preference Learning**: Automatically learn and adapt to user preferences
- **Cross-Session Context**: Remember conversations across different sessions
- **Intelligent Memory Storage**: Store important interactions with relevance scoring
- **Contextual Retrieval**: Get relevant memories based on current conversation

### **User Profiling**

- **Communication Style Adaptation**: Learn user's preferred tone, verbosity, formality
- **Tool Usage Patterns**: Track and optimize based on user's preferred tools
- **Behavioral Learning**: Understand user patterns and proactively suggest actions
- **Preference Management**: Explicit and implicit preference tracking

### **Enhanced Session Management**

- **Context-Aware Sessions**: Sessions start with relevant historical context
- **Memory Capture**: Automatically store important session insights
- **Interaction Tracking**: Record and analyze all user-agent interactions
- **Session Insights**: Extract key topics, outcomes, and patterns

## 🔧 **Usage Examples**

### **API Endpoints**

```bash
# Get user profile
GET /api/user/{user_id}/profile

# Search memories
GET /api/user/{user_id}/memories/search?query=calendar%20meeting

# Get contextual memories
GET /api/user/{user_id}/memories/contextual?query=current%20conversation

# Update preferences
POST /api/user/{user_id}/preferences
{
  "key": "communication_style",
  "value": "casual",
  "category": "communication"
}

# Check memory system status
GET /api/memory/status
```

### **Agent Instructions Enhancement**

The enhanced agent now has memory-aware instructions:

```
Before each response:
1. Retrieve relevant context from past conversations
2. Consider user's communication style and preferences
3. Extract and store new preferences from interactions

Use memory tools:
- get_contextual_memories: Understand relevant past interactions
- get_user_profile: Access user preferences and communication style
- search_memories: Find specific past conversations
```

### **Memory Tool Usage**

```python
# In your agent, use the new memory tools:
# - get_user_profile
# - search_user_memories  
# - get_contextual_memories
# - update_user_preference
```

## 🎛️ **Configuration**

### **Environment Variables**

```bash
# Database Configuration
DATABASE_URL=sqlite:///./jarvis_memory.db

# Memory System Configuration  
MEMORY_COLLECTION_NAME=jarvis_memory
VECTOR_DB_PERSIST_DIR=./jarvis_memory_db
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Session Configuration
MAX_SESSION_MEMORY_DAYS=90
MEMORY_CLEANUP_THRESHOLD=0.3
DEFAULT_IMPORTANCE_THRESHOLD=0.5
```

### **Database Models**

- **UserProfile**: Core user information and preferences
- **SessionHistory**: Session records with summaries and outcomes
- **UserPreference**: Detailed preference tracking with confidence scores
- **LifeEvent**: Important user events and milestones
- **MemoryVector**: Vector database references and metadata
- **SessionInteraction**: Individual user-agent interactions

## 🧪 **Testing the System**

### **1. Basic Memory Test**

Start a conversation and mention preferences:

```
User: "I prefer brief responses and I always use Google Calendar"
Jarvis: [Learns preferences automatically]
```

### **2. Cross-Session Memory Test**

Start a new session:

```
User: "What calendar events do I have?"
Jarvis: [Remembers your preference for Google Calendar and brief responses]
```

### **3. Contextual Memory Test**

```
User: "Remember that meeting we discussed yesterday?"
Jarvis: [Searches memory for relevant past conversations about meetings]
```

## 📊 **Memory Analytics**

### **User Profile Insights**

- Communication style preferences (formal/casual, brief/detailed)
- Tool usage patterns and preferences
- Interaction frequency and session patterns
- Learning confidence scores

### **Memory Statistics**

- Total memories stored per user
- Memory access patterns
- Relevance scores and importance ratings
- Cross-session context utilization

## 🔍 **Monitoring & Debugging**

### **Health Checks**

```bash
# Check overall system health
GET /health

# Check memory system status
GET /api/memory/status
```

### **Logging**

The system provides detailed logging for:

- Memory storage and retrieval operations
- User preference learning
- Session insights extraction
- Vector database operations

### **Debug Mode**

Set `DEBUG_MODE=true` in environment for verbose logging.

## 🚀 **Migration from In-Memory Sessions**

Your existing application can be gradually migrated:

1. **Keep existing routes**: Current WebSocket endpoints still work
2. **Use enhanced routes**: Switch to `/ws/{session_id}` with enhanced features
3. **Add memory endpoints**: Integrate new API endpoints for memory features
4. **Update agent instructions**: Enhanced agent provides better context

## 🎯 **Benefits**

### **For Users**

- Personalized interactions that improve over time
- Jarvis remembers preferences and past conversations
- Contextual responses based on history
- Consistent experience across sessions

### **For Developers**

- Rich user analytics and behavior insights
- Flexible preference management system
- Scalable memory architecture
- Comprehensive API for memory operations

## 🔧 **Customization**

### **Memory Types**

- `conversation`: Chat interactions
- `preference`: User preferences
- `fact`: Important factual information
- `experience`: Significant user experiences

### **Preference Categories**

- `communication`: Style and format preferences
- `functionality`: Tool and feature preferences
- `personal`: Personal information and context
- `system`: System-level configurations

### **Importance Scoring**

- 0.0-0.3: Low importance (may be cleaned up)
- 0.4-0.6: Medium importance
- 0.7-1.0: High importance (long-term retention)

## 🚨 **Important Notes**

1. **Data Privacy**: All memory data is stored locally by default
2. **Performance**: Vector operations may take longer on first run (model download)
3. **Storage**: Memory database will grow over time; cleanup functions available
4. **Backup**: Regular backup of `jarvis_memory.db` and `jarvis_memory_db/` recommended

## 🎉 **What's Next?**

Your Jarvis agent now has:

- ✅ Multi-tiered memory system
- ✅ User preference learning
- ✅ Cross-session context retention
- ✅ Semantic memory search
- ✅ Enhanced session management
- ✅ Comprehensive memory analytics

**Start chatting with your enhanced Jarvis and watch it learn and adapt to your preferences!**
