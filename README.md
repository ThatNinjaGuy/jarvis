# Jarvis Assistant

This document explains how to set up and use the Jarvis Assistant. This has multiple functionalities integrated with it via MCP servers to enable user journey.

## Setup Instructions

### 1. Install Dependencies

First, create a virtual environment:

```bash
# Create a virtual environment
python -m venv .venv
```

Activate the virtual environment:

On Windows:

```bash
# Activate virtual environment on Windows
.venv\Scripts\activate
```

On macOS/Linux:

```bash
# Activate virtual environment on macOS/Linux
source .venv/bin/activate
```

Then, install all required Python packages using pip:

```bash
# Install all dependencies
pip install -r requirements.txt
```

### 2. Set Up Gemini API Key

1. Create or use an existing [Google AI Studio](https://aistudio.google.com/) account
2. Get your Gemini API key from the [API Keys section](https://aistudio.google.com/app/apikeys)
3. Set the API key as an environment variable:

Create a `.env` file in the project root with:

```
GOOGLE_API_KEY=your_api_key_here
```

### 3. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API for your project:
   - In the sidebar, navigate to "APIs & Services" > "Library"
   - Search for "Google Calendar API" and enable it

### 4. Create OAuth 2.0 Credentials

1. In the Google Cloud Console, navigate to "APIs & Services" > "Credentials"
2. Click "Create Credentials" and select "OAuth client ID"
3. For application type, select "Desktop application"
4. Name your OAuth client (e.g., "ADK Voice Calendar Integration")
5. Click "Create"
6. Download the credentials JSON file
7. Save the file as `credentials.json` in the root directory of this project

### 5. Run the Setup Script

Run the setup script to authenticate with Google Calendar:

```bash
python setup_calendar_auth.py
```

This will:

1. Start the OAuth 2.0 authorization flow
2. Open your browser to authorize the application
3. Save the access token securely for future use
4. Test the connection to your Google Calendar

### 6. SQLite Database Integration

The application includes a SQLite MCP server that provides database functionality for storing and managing application data. This integration allows for persistent storage and querying of data through MCP tools.

#### Setting Up the SQLite Database

1. Navigate to the SQLite MCP server directory:

```bash
cd app/jarvis/mcp_servers/sqllite
```

2. Run the database creation script:

```bash
python create_db.py
```

This script will:

- Create a new SQLite database file (`database.db`) if it doesn't exist
- Set up the initial tables:
  - `users`: Stores user information (id, username, email)
  - `todos`: Stores todo items (id, user_id, task, completed)
- Populate the tables with some sample data

#### Available SQLite MCP Tools

The SQLite MCP server exposes several database operations as tools:

- `list_db_tables`: Lists all tables in the database
- `get_table_schema`: Retrieves the schema (columns and types) for a specific table
- `query_db_table`: Executes SELECT queries with optional conditions
- `insert_data`: Inserts new records into a table
- `delete_data`: Deletes records from a table based on conditions

These tools can be used through the voice assistant to interact with the database.

#### Database Location

The SQLite database file (`database.db`) is stored in the `app/jarvis/mcp_servers/sqllite` directory. This file contains all your application data and can be backed up or moved as needed.

## Running the Application

After completing the setup, you can run the application using the following command:

```bash
# Start the ADK Voice Assistant with hot-reloading enabled
uvicorn main:app --reload
```

This will start the application server, and you can interact with your voice assistant through the provided interface.

## Troubleshooting

### Token Errors

If you encounter authentication errors:

1. Delete the token file at `~/.credentials/calendar_token.json`
2. Run the setup script again

### Permission Issues

If you need additional calendar permissions:

1. Delete the token file at `~/.credentials/calendar_token.json`
2. Edit the `SCOPES` variable in `app/jarvis/tools/calendar_utils.py`
3. Run the setup script again

### API Quota

Google Calendar API has usage quotas. If you hit quota limits:

1. Check your [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to "APIs & Services" > "Dashboard"
3. Select "Google Calendar API"
4. View your quota usage and consider upgrading if necessary

### Package Installation Issues

If you encounter issues installing the required packages:

1. Make sure you're using Python 3.8 or newer
2. Try upgrading pip: `pip install --upgrade pip`
3. Install packages individually if a specific package is causing problems

## Security Considerations

- The OAuth token is stored securely in your user directory
- Never share your `credentials.json` file or the generated token
- The application only requests the minimum permissions needed for calendar operations
