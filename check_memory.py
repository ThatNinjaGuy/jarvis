#!/usr/bin/env python3
"""
Jarvis Memory Checker
A permanent tool to inspect your Jarvis agent's saved memory data across all three tiers.

Usage:
    python check_memory.py                    # Full memory report
    python check_memory.py --user USER_ID    # Specific user's memory
    python check_memory.py --stats           # Just statistics
    python check_memory.py --recent          # Recent activity only
    python check_memory.py --search QUERY    # Search memories
    python check_memory.py --all             # Show ALL memories (no limits)
    python check_memory.py --full-content    # Show full content (no truncation)
"""

import sqlite3
import json
import os
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class JarvisMemoryChecker:
    def __init__(self, db_path: str = "jarvis_memory.db", show_all: bool = False, full_content: bool = False):
        self.db_path = db_path
        self.conn = None
        self.show_all = show_all
        self.full_content = full_content
    
    def connect(self):
        """Connect to the memory database"""
        if not os.path.exists(self.db_path):
            print(f"❌ Memory database not found: {self.db_path}")
            print("   Make sure you've run your Jarvis app and had some conversations.")
            return False
        
        try:
            self.conn = sqlite3.connect(self.db_path)
            return True
        except Exception as e:
            print(f"❌ Error connecting to database: {str(e)}")
            return False
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def format_json(self, data, indent=2):
        """Format JSON data for display"""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                return data
        return json.dumps(data, indent=indent, ensure_ascii=False)
    
    def truncate_text(self, text: str, max_length: int = 100) -> str:
        """Truncate text for display unless full_content is enabled"""
        if self.full_content or len(text) <= max_length:
            return text
        return text[:max_length] + "..."
    
    def get_statistics(self):
        """Get comprehensive memory statistics"""
        if not self.conn:
            return None
        
        cursor = self.conn.cursor()
        stats = {}
        
        try:
            # Basic counts
            tables = ['user_profiles', 'memory_vectors', 'user_preferences', 
                     'session_interactions', 'sessions', 'session_history', 'life_events']
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            
            # Memory type distribution
            cursor.execute("""
                SELECT memory_type, COUNT(*), AVG(importance_score), AVG(access_count)
                FROM memory_vectors 
                GROUP BY memory_type 
                ORDER BY COUNT(*) DESC
            """)
            stats['memory_types'] = cursor.fetchall()
            
            # Most active users
            cursor.execute("""
                SELECT user_id, COUNT(*) as memory_count
                FROM memory_vectors 
                GROUP BY user_id 
                ORDER BY COUNT(*) DESC 
                LIMIT {}
            """.format(20 if self.show_all else 5))
            stats['active_users'] = cursor.fetchall()
            
            # Recent activity (last 7 days)
            cursor.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM memory_vectors 
                WHERE created_at >= date('now', '-7 days')
                GROUP BY DATE(created_at) 
                ORDER BY date DESC
            """)
            stats['recent_activity'] = cursor.fetchall()
            
            return stats
            
        except Exception as e:
            print(f"❌ Error getting statistics: {str(e)}")
            return None
    
    def get_all_memories(self):
        """Get ALL memories from the database"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM memory_vectors ORDER BY created_at DESC")
            memories = cursor.fetchall()
            
            formatted_memories = []
            for memory in memories:
                formatted_memories.append({
                    'id': memory[0],
                    'user_id': memory[1],
                    'session_id': memory[2],
                    'content': memory[3],
                    'content_summary': memory[4],
                    'vector_id': memory[5],
                    'memory_type': memory[6],
                    'importance': memory[7],
                    'created_at': memory[8],
                    'last_accessed': memory[9],
                    'access_count': memory[10],
                    'tags': memory[11]
                })
            
            return formatted_memories
            
        except Exception as e:
            print(f"❌ Error getting all memories: {str(e)}")
            return []
    
    def get_user_memory(self, user_id: str):
        """Get all memory data for a specific user"""
        if not self.conn:
            return None
        
        cursor = self.conn.cursor()
        user_data = {}
        
        try:
            # User profile
            cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
            profile = cursor.fetchone()
            if profile:
                user_data['profile'] = {
                    'user_id': profile[0],
                    'created_at': profile[1],
                    'updated_at': profile[2],
                    'preferences': json.loads(profile[3]) if profile[3] else {},
                    'interaction_stats': json.loads(profile[4]) if profile[4] else {},
                    'communication_style': json.loads(profile[5]) if profile[5] else {}
                }
            
            # User preferences
            cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
            preferences = cursor.fetchall()
            user_data['preferences'] = []
            for pref in preferences:
                user_data['preferences'].append({
                    'key': pref[2],
                    'value': pref[3],
                    'confidence': pref[4],
                    'last_reinforced': pref[5],
                    'type': pref[6],
                    'category': pref[7]
                })
            
            # Memory vectors
            cursor.execute("SELECT * FROM memory_vectors WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            memories = cursor.fetchall()
            user_data['memories'] = []
            for memory in memories:
                user_data['memories'].append({
                    'id': memory[0],
                    'content': memory[3],
                    'memory_type': memory[6],
                    'importance': memory[7],
                    'created_at': memory[8],
                    'access_count': memory[10],
                    'tags': memory[11]
                })
            
            # Session interactions (check if table has user_id column)
            try:
                cursor.execute("SELECT * FROM session_interactions WHERE session_id LIKE ? ORDER BY timestamp DESC LIMIT 10", (f"%{user_id}%",))
                interactions = cursor.fetchall()
                user_data['recent_interactions'] = []
                for interaction in interactions:
                    user_data['recent_interactions'].append({
                        'session_id': interaction[1],
                        'user_input': interaction[2],
                        'agent_response': interaction[3],
                        'timestamp': interaction[4],
                        'tools_used': json.loads(interaction[5]) if interaction[5] else []
                    })
            except:
                # If no user_id column or no interactions, skip
                user_data['recent_interactions'] = []
            
            return user_data
            
        except Exception as e:
            print(f"❌ Error getting user memory: {str(e)}")
            return None
    
    def search_memories(self, query: str, user_id: Optional[str] = None):
        """Search memories by content"""
        if not self.conn:
            return []
        
        cursor = self.conn.cursor()
        
        try:
            if user_id:
                cursor.execute("""
                    SELECT * FROM memory_vectors 
                    WHERE user_id = ? AND (content LIKE ? OR tags LIKE ?)
                    ORDER BY importance_score DESC, created_at DESC
                """, (user_id, f"%{query}%", f"%{query}%"))
            else:
                cursor.execute("""
                    SELECT * FROM memory_vectors 
                    WHERE content LIKE ? OR tags LIKE ?
                    ORDER BY importance_score DESC, created_at DESC
                """, (f"%{query}%", f"%{query}%"))
            
            results = cursor.fetchall()
            memories = []
            
            for memory in results:
                memories.append({
                    'id': memory[0],
                    'user_id': memory[1],
                    'content': memory[3],
                    'memory_type': memory[6],
                    'importance': memory[7],
                    'created_at': memory[8],
                    'access_count': memory[10],
                    'tags': memory[11]
                })
            
            return memories
            
        except Exception as e:
            print(f"❌ Error searching memories: {str(e)}")
            return []
    
    def get_recent_activity(self, days: int = 7):
        """Get recent memory activity"""
        if not self.conn:
            return None
        
        cursor = self.conn.cursor()
        
        try:
            # Recent memories
            cursor.execute("""
                SELECT * FROM memory_vectors 
                WHERE created_at >= date('now', '-{} days')
                ORDER BY created_at DESC
            """.format(days))
            
            recent_memories = cursor.fetchall()
            
            # Recent sessions
            cursor.execute("""
                SELECT * FROM sessions 
                WHERE create_time >= date('now', '-{} days')
                ORDER BY create_time DESC
            """.format(days))
            
            recent_sessions = cursor.fetchall()
            
            return {
                'memories': recent_memories,
                'sessions': recent_sessions,
                'days': days
            }
            
        except Exception as e:
            print(f"❌ Error getting recent activity: {str(e)}")
            return None
    
    def print_all_memories(self):
        """Print ALL memories in the database"""
        memories = self.get_all_memories()
        
        print("🧠 ALL STORED MEMORIES")
        print("=" * 80)
        print(f"📊 Total memories: {len(memories)}")
        print()
        
        if not memories:
            print("❌ No memories found in database")
            return
        
        # Group by memory type
        memory_types = {}
        for memory in memories:
            mem_type = memory['memory_type']
            if mem_type not in memory_types:
                memory_types[mem_type] = []
            memory_types[mem_type].append(memory)
        
        # Display each type
        for mem_type, type_memories in memory_types.items():
            print(f"\n📂 {mem_type.upper()} MEMORIES ({len(type_memories)} total)")
            print("-" * 60)
            
            for i, memory in enumerate(type_memories, 1):
                print(f"\n{i}. Memory ID: {memory['id']}")
                print(f"   User: {memory['user_id']}")
                print(f"   Session: {memory['session_id'] or 'N/A'}")
                print(f"   Created: {memory['created_at']}")
                print(f"   Importance: {memory['importance']:.2f}")
                print(f"   Access Count: {memory['access_count']}")
                print(f"   Last Accessed: {memory['last_accessed'] or 'Never'}")
                
                # Content (full or truncated based on settings)
                content = memory['content']
                if self.full_content:
                    print(f"   Content: {content}")
                else:
                    print(f"   Content: {self.truncate_text(content, 150)}")
                
                # Summary if different from content
                if memory['content_summary'] and memory['content_summary'] != content:
                    summary = memory['content_summary']
                    print(f"   Summary: {self.truncate_text(summary, 100)}")
                
                # Tags
                if memory['tags']:
                    try:
                        tags = json.loads(memory['tags']) if isinstance(memory['tags'], str) else memory['tags']
                        if isinstance(tags, list):
                            print(f"   Tags: {', '.join(tags)}")
                        else:
                            print(f"   Tags: {tags}")
                    except:
                        print(f"   Tags: {memory['tags']}")
                
                print(f"   Vector ID: {memory['vector_id']}")
    
    def print_statistics(self):
        """Print comprehensive statistics"""
        stats = self.get_statistics()
        if not stats:
            return
        
        print("📊 JARVIS MEMORY STATISTICS")
        print("=" * 50)
        print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        print("📈 Overall Counts:")
        print(f"   👥 User Profiles: {stats['user_profiles']}")
        print(f"   🧠 Memory Vectors: {stats['memory_vectors']}")
        print(f"   ⚙️  User Preferences: {stats['user_preferences']}")
        print(f"   💬 Session Interactions: {stats['session_interactions']}")
        print(f"   🔄 Active Sessions: {stats['sessions']}")
        print(f"   📚 Session History: {stats['session_history']}")
        print(f"   🎯 Life Events: {stats['life_events']}")
        
        if stats['memory_types']:
            print(f"\n📋 Memory Types:")
            for mem_type, count, avg_importance, avg_access in stats['memory_types']:
                print(f"   {mem_type}: {count} memories (avg importance: {avg_importance:.2f})")
        
        if stats['active_users']:
            print(f"\n🏆 Most Active Users:")
            for user_id, memory_count in stats['active_users']:
                print(f"   {user_id}: {memory_count} memories")
        
        if stats['recent_activity']:
            print(f"\n📅 Recent Activity (Last 7 days):")
            for date, count in stats['recent_activity']:
                print(f"   {date}: {count} memories created")
    
    def print_user_memory(self, user_id: str):
        """Print detailed memory for a specific user"""
        user_data = self.get_user_memory(user_id)
        if not user_data:
            print(f"❌ No memory data found for user: {user_id}")
            return
        
        print(f"👤 MEMORY DATA FOR USER: {user_id}")
        print("=" * 60)
        
        # Profile
        if 'profile' in user_data:
            profile = user_data['profile']
            print(f"📊 Profile:")
            print(f"   Created: {profile['created_at']}")
            print(f"   Updated: {profile['updated_at']}")
            
            if profile['preferences']:
                print(f"   Preferences:")
                for key, value in profile['preferences'].items():
                    print(f"     • {key}: {value}")
            
            if profile['communication_style']:
                print(f"   Communication Style:")
                for key, value in profile['communication_style'].items():
                    print(f"     • {key}: {value}")
        
        # Detailed preferences
        if user_data['preferences']:
            print(f"\n⚙️  Detailed Preferences ({len(user_data['preferences'])}):")
            for pref in user_data['preferences']:
                print(f"   • {pref['key']}: {pref['value']}")
                print(f"     Confidence: {pref['confidence']:.2f} | Category: {pref['category']}")
        
        # Memories
        if user_data['memories']:
            print(f"\n🧠 Stored Memories ({len(user_data['memories'])}):")
            for i, memory in enumerate(user_data['memories'], 1):
                content = memory['content']
                if self.full_content:
                    print(f"   {i}. [{memory['memory_type']}] {content}")
                else:
                    print(f"   {i}. [{memory['memory_type']}] {self.truncate_text(content, 100)}")
                print(f"      Importance: {memory['importance']:.2f} | Accessed: {memory['access_count']} times")
                if memory['tags']:
                    print(f"      Tags: {memory['tags']}")
                print()
        
        # Recent interactions
        if user_data['recent_interactions']:
            print(f"\n💬 Recent Interactions ({len(user_data['recent_interactions'])}):")
            for interaction in user_data['recent_interactions']:
                print(f"   [{interaction['timestamp']}]")
                print(f"   User: {self.truncate_text(interaction['user_input'], 80)}")
                print(f"   Agent: {self.truncate_text(interaction['agent_response'], 80)}")
                print()
    
    def print_search_results(self, query: str, user_id: Optional[str] = None):
        """Print search results"""
        memories = self.search_memories(query, user_id)
        
        user_filter = f" for user '{user_id}'" if user_id else ""
        print(f"🔍 SEARCH RESULTS for '{query}'{user_filter}")
        print("=" * 60)
        
        if not memories:
            print("❌ No memories found matching your search.")
            return
        
        print(f"Found {len(memories)} matching memories:")
        print()
        
        for i, memory in enumerate(memories, 1):
            print(f"{i}. [{memory['memory_type']}] User: {memory['user_id']}")
            if self.full_content:
                print(f"   Content: {memory['content']}")
            else:
                print(f"   Content: {self.truncate_text(memory['content'], 150)}")
            print(f"   Importance: {memory['importance']:.2f} | Accessed: {memory['access_count']} times")
            print(f"   Created: {memory['created_at']}")
            if memory['tags']:
                print(f"   Tags: {memory['tags']}")
            print()
    
    def print_recent_activity(self, days: int = 7):
        """Print recent activity"""
        activity = self.get_recent_activity(days)
        if not activity:
            return
        
        print(f"📅 RECENT ACTIVITY (Last {days} days)")
        print("=" * 50)
        
        limit = None if self.show_all else 50
        memories_to_show = activity['memories'][:limit] if limit else activity['memories']
        sessions_to_show = activity['sessions'][:limit] if limit else activity['sessions']
        
        print(f"🧠 Recent Memories ({len(memories_to_show)} shown, {len(activity['memories'])} total):")
        for memory in memories_to_show:
            content = self.truncate_text(memory[3], 80)
            print(f"   [{memory[8]}] {memory[1]}: {content}")
        
        print(f"\n🔄 Recent Sessions ({len(sessions_to_show)} shown, {len(activity['sessions'])} total):")
        for session in sessions_to_show:
            print(f"   [{session[4]}] User: {session[1]} | Session: {session[2]}")
    
    def print_full_report(self):
        """Print comprehensive memory report"""
        print("🔍 COMPREHENSIVE JARVIS MEMORY REPORT")
        print("=" * 80)
        print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.show_all:
            print("🔍 Mode: SHOW ALL (no limits)")
        if self.full_content:
            print("📄 Mode: FULL CONTENT (no truncation)")
        print()
        
        # Statistics
        self.print_statistics()
        
        # Recent activity
        print("\n" + "=" * 80)
        self.print_recent_activity()
        
        # All users summary
        if self.conn:
            cursor = self.conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM memory_vectors ORDER BY user_id")
            users = cursor.fetchall()
            
            if users:
                print(f"\n" + "=" * 80)
                print(f"👥 USERS WITH STORED MEMORIES ({len(users)} total)")
                print("=" * 80)
                
                users_to_show = users if self.show_all else users[:5]
                
                for user_id, in users_to_show:
                    print(f"\n👤 {user_id}:")
                    user_data = self.get_user_memory(user_id)
                    if user_data and user_data['memories']:
                        print(f"   🧠 {len(user_data['memories'])} memories stored")
                        print(f"   ⚙️  {len(user_data['preferences'])} preferences learned")
                        
                        # Show most important memory
                        top_memory = max(user_data['memories'], key=lambda x: x['importance'])
                        content = self.truncate_text(top_memory['content'], 60)
                        print(f"   🌟 Top memory: {content}")
                
                if not self.show_all and len(users) > 5:
                    print(f"\n   ... and {len(users) - 5} more users")

def main():
    parser = argparse.ArgumentParser(description="Check Jarvis Memory System")
    parser.add_argument('--user', '-u', help="Show memory for specific user ID")
    parser.add_argument('--stats', '-s', action='store_true', help="Show only statistics")
    parser.add_argument('--recent', '-r', type=int, default=7, help="Show recent activity (days)")
    parser.add_argument('--search', '-q', help="Search memories by content")
    parser.add_argument('--all', '-a', action='store_true', help="Show ALL data (no limits)")
    parser.add_argument('--full-content', '-f', action='store_true', help="Show full content (no truncation)")
    parser.add_argument('--all-memories', action='store_true', help="Show ALL memories in detail")
    parser.add_argument('--db', default="jarvis_memory.db", help="Database path")
    
    args = parser.parse_args()
    
    checker = JarvisMemoryChecker(args.db, args.all, args.full_content)
    
    if not checker.connect():
        return
    
    try:
        if args.all_memories:
            checker.print_all_memories()
        elif args.stats:
            checker.print_statistics()
        elif args.user:
            checker.print_user_memory(args.user)
        elif args.search:
            checker.print_search_results(args.search, args.user)
        elif args.recent != 7:
            checker.print_recent_activity(args.recent)
        else:
            checker.print_full_report()
    
    finally:
        checker.close()

if __name__ == "__main__":
    main() 