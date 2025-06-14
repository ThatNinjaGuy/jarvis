# 🔍 Jarvis Memory Checker Guide

A comprehensive tool to inspect your Jarvis agent's saved memory data across all three memory tiers.

## 🚀 Quick Start

```bash
# Full comprehensive memory report
python check_memory.py

# Just show statistics
python check_memory.py --stats

# Show memory for a specific user
python check_memory.py --user "your_user_id"

# Search for specific memories
python check_memory.py --search "calendar"

# Show recent activity (last 3 days)
python check_memory.py --recent 3

# Show ALL memories with full content (no truncation)
python check_memory.py --all-memories --full-content

# Show everything with no limits
python check_memory.py --all --full-content
```

## 📋 Available Commands

### 🧠 **All Memories** (NEW!)

```bash
python check_memory.py --all-memories --full-content
```

Shows ALL memories with complete content:

- Every single memory in your database
- Full content without truncation
- Organized by memory type (preference, conversation, fact)
- Complete metadata for each memory

### 🔍 **Full Report** (Default)

```bash
python check_memory.py
```

Shows comprehensive memory report including:

- Overall statistics
- Recent activity
- Top users with stored memories
- Sample memories for each user

### 📊 **Statistics Only**

```bash
python check_memory.py --stats
```

Shows just the key statistics:

- Total counts for each memory tier
- Memory type distribution
- Most active users
- Recent activity summary

### 👤 **User-Specific Memory**

```bash
python check_memory.py --user "USER_ID"
```

Shows detailed memory for a specific user:

- User profile and preferences
- All stored memories
- Communication style learned
- Recent interactions

### 🔍 **Search Memories**

```bash
python check_memory.py --search "QUERY"
```

Search through all memories for specific content:

- Searches both content and tags
- Shows relevance-ranked results
- Displays memory type and importance

### 📅 **Recent Activity**

```bash
python check_memory.py --recent 7
```

Shows activity from the last N days:

- Recently created memories
- New user sessions
- Memory creation patterns

## 🎯 **Understanding the Output**

### **Memory Tiers Explained:**

#### 🎯 **Tier 1: Session Memory**

- Active conversation sessions
- Current context and state
- Recent interactions

#### 👤 **Tier 2: User Profile Memory**

- Learned user preferences
- Behavioral patterns
- Communication styles
- Long-term user insights

#### 🧠 **Tier 3: Vector Memory**

- Semantic memories for search
- Categorized by type:
  - **preference**: User preferences and habits
  - **conversation**: Important conversation snippets
  - **fact**: Factual information to remember

### **Key Metrics:**

- **Importance Score**: 0.0-1.0 (higher = more important)
- **Access Count**: How often the memory has been retrieved
- **Confidence**: How certain the system is about preferences
- **Tags**: Categories for easy searching

## 💡 **Usage Tips**

### **Finding Your User ID:**

1. Look at recent sessions in the full report
2. Check your browser's WebSocket connection
3. Your user ID is usually the session ID

### **Common Searches:**

```bash
# Find calendar-related memories
python check_memory.py --search "calendar"

# Find communication preferences
python check_memory.py --search "communication"

# Find meeting-related memories
python check_memory.py --search "meeting"

# Find notification preferences
python check_memory.py --search "notification"
```

### **Monitoring Memory Growth:**

```bash
# Check daily activity
python check_memory.py --recent 1

# Check weekly trends
python check_memory.py --recent 7

# Get current statistics
python check_memory.py --stats
```

## 🔧 **Advanced Usage**

### **Custom Database Path:**

```bash
python check_memory.py --db "/path/to/custom/jarvis_memory.db"
```

### **Combining Options:**

```bash
# Search within a specific user's memories
python check_memory.py --search "calendar" --user "your_user_id"
```

## 📈 **What Good Memory Data Looks Like**

### **Healthy Memory System:**

- ✅ Multiple memory types (preference, conversation, fact)
- ✅ Increasing access counts on important memories
- ✅ High importance scores (0.7+) for key preferences
- ✅ Regular memory creation over time
- ✅ Diverse tags and categories

### **Signs to Watch For:**

- ⚠️ No recent memory creation (system not learning)
- ⚠️ All memories have 0 access count (not being retrieved)
- ⚠️ Very low importance scores (< 0.3)
- ⚠️ No user preferences being learned

## 🎉 **Example Output Interpretation**

```
🏆 Most Active Users:
   user_12345: 15 memories
```

This user has had 15 memories stored - shows active learning!

```
📋 Memory Types:
   preference: 8 memories (avg importance: 0.75)
```

8 preferences learned with high importance - great personalization!

```
📅 Recent Activity (Last 7 days):
   2025-06-14: 12 memories created
```

Active memory creation - system is learning from conversations!

---

**💡 Pro Tip:** Run `python check_memory.py --stats` regularly to monitor how well your Jarvis agent is learning and remembering your preferences!
