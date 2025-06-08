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
3. Enable the required Google APIs for your project:
   - In the sidebar, navigate to "APIs & Services" > "Library"
   - Search for and enable:
     - "Google Calendar API"
     - "Gmail API"
     - "Distance Matrix API"
     - "YouTube Data API v3"

### 4. Create OAuth 2.0 Credentials

1. In the Google Cloud Console, navigate to "APIs & Services" > "Credentials"
2. Click "Create Credentials" and select "OAuth client ID"
3. For application type, select "Desktop application"
4. Name your OAuth client (e.g., "ADK Voice Integration")
5. Click "Create"
6. Download the credentials JSON file
7. Save the file as `credentials.json` in the root directory of this project

### 5. Set Up Google Maps API Key

Run the Maps API setup script:

```bash
python setup_maps_auth.py
```

This script will:

1. Guide you through creating an API key in Google Cloud Console
2. Test the API key with a sample distance calculation
3. Save the API key securely in your `.env` file

### 6. Run the Setup Scripts

Run the setup scripts to authenticate with Google services:

```bash
# Set up Calendar authentication
python setup_calendar_auth.py

# Set up Gmail authentication
python setup_gmail_auth.py

# Set up YouTube authentication
python setup_youtube_auth.py
```

These scripts will:

1. Start the OAuth 2.0 authorization flow
2. Open your browser to authorize the application
3. Save the access tokens securely for future use
4. Test the connection to the respective Google services

### 7. SQLite Database Integration

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

### 8. Twitter Integration Setup

#### A. Install Node.js and Twitter MCP Server

1. Install Node.js (v20.x or higher):

```bash
# On macOS using Homebrew
brew install node

# On Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version  # Should output v20.x or higher
npm --version
```

2. Install the Twitter MCP server globally:

```bash
npm install -g @enescinar/twitter-mcp
```

#### B. Get Twitter API Credentials

1. Create a Twitter Developer Account:
   - Visit [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
   - Sign in with your Twitter account
   - Click on "Sign up" for a developer account if you haven't already
   - Follow the application process and select the appropriate access level

2. Create a New Project and App:
   - Go to the [Developer Portal Dashboard](https://developer.twitter.com/en/portal/dashboard)
   - Click "Create Project"
   - Give your project a name and select your use case
   - Click "Create App" within your project

3. Generate API Keys and Tokens:
   - In your app settings, navigate to the "Keys and Tokens" tab
   - Generate/Regenerate the following credentials:
     - API Key and Secret
     - Access Token and Secret
   - Save these credentials securely; they will be shown only once

4. Set up Environment Variables:
   - Create or update your `.env` file in the project root:

```env
TWITTER_API_KEY=your_api_key_here
TWITTER_API_SECRET=your_api_secret_here
TWITTER_ACCESS_TOKEN=your_access_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here
```

#### C. Verify Installation

Test your Twitter integration:

```bash
# Start the ADK Voice Assistant
uvicorn app.main:app --reload
```

The server should start without any Twitter credential errors.

## Features

### Google Maps Integration

The assistant includes Google Maps functionality through the Maps MCP server. Available features include:

1. Distance Matrix Calculations:
   - Calculate driving distance and duration between locations
   - Support for multiple origins and destinations
   - Real-time traffic information
   - Multiple transportation modes (driving, walking, bicycling, transit)
   - Route customization (avoid tolls, highways, ferries)
   - Support for both metric and imperial units

The Maps integration uses the Google Maps Distance Matrix API to provide accurate distance and time calculations, taking into account real-time traffic conditions when available.

### Gmail Integration

The assistant includes Gmail functionality through the Gmail MCP server. Available features include:

1. Email Management:
   - List and search emails with various filters
   - Get detailed email content including attachments
   - Send new emails with HTML content and attachments
   - Delete emails (move to trash or permanent deletion)
   - Reply to emails (including reply-all)

2. Draft Management:
   - Create new email drafts
   - List existing drafts
   - Update draft content
   - Delete drafts

The Gmail integration uses secure OAuth 2.0 authentication and provides a comprehensive set of tools for email management through voice commands or text interactions.

### Calendar Integration

The assistant includes Google Calendar functionality through the Google Calendar MCP server. Available features include:

1. Event Management:
   - Add new events
   - List existing events
   - Update event details
   - Delete events

2. Reminder Management:
   - Set reminders for events
   - List upcoming events
   - Update reminder settings
   - Delete reminders

The calendar integration uses secure OAuth 2.0 authentication and provides a comprehensive set of tools for event and reminder management through voice commands or text interactions.

### YouTube Integration

The assistant includes YouTube functionality through the YouTube MCP server. Available features include:

1. Video Search:
   - Search for videos with customizable parameters
   - Filter by relevance, view count, rating, or date
   - Specify maximum results to return
   - Get comprehensive video metadata

2. Video Details:
   - Get detailed information about specific videos
   - View statistics (views, likes, comments)
   - Get video duration and publish date
   - Access video thumbnails and channel information

3. Channel Information:
   - Retrieve channel details and statistics
   - Get subscriber count and total views
   - Access channel description and custom URL
   - View channel thumbnails and branding

4. Comments Management:
   - Get video comments with engagement metrics
   - View comment author information
   - See reply counts and like counts
   - Access comment timestamps

The YouTube integration uses secure OAuth 2.0 authentication and provides comprehensive access to YouTube data through voice commands or text interactions. It respects YouTube's content policies and API quotas while providing rich metadata about videos, channels, and user engagement.

### Twitter Integration

The assistant includes Twitter functionality through the Twitter MCP server. Available features include:

1. Tweet Management:
   - Post new tweets
   - Delete tweets
   - Like/unlike tweets
   - Retweet/quote tweets
   - Thread creation

2. Search and Filtering:
   - Search tweets by keywords
   - Filter by date range
   - Search by hashtags
   - Get trending topics
   - Advanced search operators

3. User Interactions:
   - Follow/unfollow users
   - Get user profiles
   - View user timelines
   - List management
   - Block/mute users

4. Analytics:
   - Tweet engagement metrics
   - Follower statistics
   - Tweet performance
   - Hashtag tracking
   - Audience insights

The Twitter integration uses secure OAuth 1.0a authentication and provides comprehensive access to Twitter's API features through voice commands or text interactions.

## Running the Application

After completing the setup, you can run the application using the following command:

```bash
# Start the ADK Voice Assistant with hot-reloading enabled
uvicorn app.main:app --reload
```

This will start the application server, and you can interact with your voice assistant through the provided interface.

## Troubleshooting

### Token Errors

If you encounter authentication errors:

1. Delete the relevant token file:
   - Calendar: `~/.credentials/calendar_token.json`
   - Gmail: `~/.credentials/gmail_token.json`
   - YouTube: `~/.credentials/youtube_token.json`
   - Twitter: Check your `.env` file for correct credentials
2. Run the corresponding setup script again

### Permission Issues

If you need additional permissions:

1. Delete the relevant token file
2. Edit the `SCOPES` variable in the corresponding setup script:
   - Calendar: `setup_calendar_auth.py`
   - Gmail: `setup_gmail_auth.py`
   - YouTube: `setup_youtube_auth.py`
3. Run the setup script again

### API Quota

Google APIs and Twitter API have usage quotas. If you hit quota limits:

1. Check your respective developer portals:
   - [Google Cloud Console](https://console.cloud.google.com/)
   - [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Review your API usage and limits
3. Consider upgrading your API access level if needed

Note: Twitter API has different access tiers with varying rate limits and features. Ensure your access level matches your usage requirements.

### Package Installation Issues

If you encounter issues installing the required packages:

1. Make sure you're using Python 3.8 or newer
2. Try upgrading pip: `pip install --upgrade pip`
3. Install packages individually if a specific package is causing problems

## Security Considerations

- The OAuth tokens are stored securely in your user directory
- Never share your `credentials.json` file or the generated tokens
- The application only requests the minimum permissions needed for each service
- YouTube content restrictions and age limits are respected
- All API calls are made over secure HTTPS connections
- All API credentials are stored securely in your `.env` file
- Never commit your `.env` file to version control
- The application only requests the minimum permissions needed for each service
- Twitter API calls use OAuth 1.0a for secure authentication
- All API communications are made over secure HTTPS connections
- Regular monitoring of API usage to prevent quota exhaustion
