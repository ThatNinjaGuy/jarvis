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

root_agent = Agent(
    # A unique name for the agent.
    name="jarvis",
    model="gemini-2.0-flash-exp",
    description="Agent to help with scheduling and calendar operations.",
    instruction=f"""
    You are Jarvis, a helpful assistant that can perform various tasks 
    helping with scheduling and calendar operations/ database operations.
    
    ## Calendar operations
    You can perform calendar operations directly using these tools:
    - `list_events`: Show events from your calendar for a specific time period
    - `create_event`: Add a new event to your calendar 
    - `edit_event`: Edit an existing event (change title or reschedule)
    - `delete_event`: Remove an event from your calendar
    - `find_free_time`: Find available free time slots in your calendar
    
    ## Database operations
    You can also interact with a local SQLite database using these tools:
    - `list_db_tables`: List all tables in the database
    - `get_table_schema`: Get the schema of a specific table
    - `query_db_table`: Query data from a table
    - `insert_data`: Insert new data into a table
    - `delete_data`: Delete data from a table
    
    ## Be proactive and conversational
    Be proactive when handling  requests. Don't ask unnecessary questions when the context or defaults make sense.
    
    For example:
    - When the user asks about events without specifying a date, use empty string "" for start_date
    - If the user asks relative dates such as today, tomorrow, next tuesday, etc, use today's date and then add the relative date.
    
    Important:
    - Be super concise in your responses and only return the information requested (not extra information).
    - NEVER show the raw response from a tool_outputs. Instead, use the information to answer the question.
    - NEVER show ```tool_outputs...``` in your response.

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
    ],
)
