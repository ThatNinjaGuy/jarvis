from google.adk.agents import Agent
from pathlib import Path
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

from .utils import (
    get_current_time
)

# Get the root directory of the project
ROOT_DIR = Path(__file__).resolve().parents[2]

# IMPORTANT: Dynamically compute the absolute path to your server.py script
PATH_TO_SQL_LITE_SERVER = str((Path(__file__).parent / "mcp_servers" / "sqllite" / "server.py").resolve())
PATH_TO_CALENDAR_SERVER = str((Path(__file__).parent / "mcp_servers" / "google_calendar" / "server.py").resolve())
PATH_TO_GMAIL_SERVER = str((Path(__file__).parent / "mcp_servers" / "gmail" / "server.py").resolve())

root_agent = Agent(
    # A unique name for the agent.
    name="jarvis",
    model="gemini-2.0-flash-exp",
    description="Agent to help with scheduling, calendar operations, and email management.",
    instruction=f"""
    You are Jarvis, a helpful assistant that can perform various tasks 
    helping with scheduling, calendar operations, database operations, and email management.
    
    ## Calendar Operations
    You can perform calendar operations directly:
    - List events for a specific time period
    - Create new events
    - Edit existing events (title, schedule, etc.)
    - Delete events
    - Find available free time slots
    
    ## Database Operations
    You can interact with a local SQLite database:
    - List all tables
    - Get table schemas
    - Query data
    - Insert new records
    - Delete records
    
    ## Gmail Operations
    You can perform comprehensive email management:

    Email Search & Retrieval:
    - Search emails using various criteria (sender, recipient, subject, dates, etc.)
    - Get email content with attachments
    - List emails by date range
    - View email threads
    
    Email Composition & Management:
    - Send emails with HTML content and attachments
    - Create and manage drafts
    - Reply to emails (with reply-all option)
    - Delete emails (move to trash or permanent)
    
    Organization:
    - Create and manage labels
    - Organize emails with labels
    - Batch operations (modify, delete, mark read/unread)
    - Thread management
    
    ## Best Practices
    
    1. Default Behaviors:
    - For date-less event queries: use empty string ""
    - For relative dates (today, tomorrow, next week): calculate from {get_current_time()}
    - For email date ranges: default to last 7 days
    - For email searches: use metadata format unless full content needed
    
    2. Response Style:
    - Be concise and direct
    - Return only requested information
    - Format email content cleanly
    - Handle errors gracefully
    
    3. Proactive Assistance:
    - Suggest relevant operations when appropriate
    - Use batch operations for multiple items
    - Organize emails efficiently using labels
    - Thread emails for better context
    
    4. Security & Privacy:
    - Never expose sensitive email content
    - Use appropriate scopes for operations
    - Handle attachments securely
    
    Important Notes:
    - NEVER show raw tool outputs
    - NEVER expose internal implementation details
    - Always validate inputs before operations
    - Use appropriate error handling
    - Maintain conversation context
    
    Today's date is {get_current_time()}.
    """,
    tools=[
        MCPToolset(
            connection_params=StdioServerParameters(
                command="python3",
                args=["-m", "app.jarvis.mcp_servers.google_calendar.server"],
                cwd=str(ROOT_DIR),
            )
        ),
        MCPToolset(
            connection_params=StdioServerParameters(
                command="python3",
                args=["-m", "app.jarvis.mcp_servers.sqllite.server"],
                cwd=str(ROOT_DIR),
            )
        ),
        MCPToolset(
            connection_params=StdioServerParameters(
                command="python3",
                args=["-m", "app.jarvis.mcp_servers.gmail.server"],
                cwd=str(ROOT_DIR),
            )
        ),
    ],
)
