# Google Cloud Run Deployment Guide (with SQLite & UI)

## Phase 0: Pre-Deployment Manual Steps

### 0.1 Generate Google Calendar OAuth Token

1. On your local machine, run:

   ```bash
   python setup_calendar_auth.py
   ```

2. This will create a token file, usually at `~/.credentials/calendar_token.json`.
3. Copy this file into your project at:

   ```
   app/jarvis/credentials/calendar_token.json
   ```

### 0.2 Initialize the Database

1. On your local machine, run:

   ```bash
   cd app/jarvis/mcp_servers/sqllite
   python create_db.py
   ```

2. Ensure `database.db` is present at `app/jarvis/mcp_servers/sqllite/database.db`.

---

## Phase 1: Google Cloud Setup

### 1.1 Install Google Cloud SDK

```bash
# For Linux/macOS
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# For Windows
Download from https://cloud.google.com/sdk/docs/install
```

### 1.2 Create Google Cloud Project

```bash
gcloud projects create jarvis-develop-460215 --name="Jarvis Assistant"
gcloud config set project jarvis-develop-460215
```

### 1.3 Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com
```

---

## Phase 2: Database Persistence Setup

### 2.1 Create Cloud Storage Bucket

```bash
gsutil mb -l us-central1 gs://jarvis-db-$(gcloud config get-value project)
```

### 2.2 Upload Initial Database

```bash
gsutil cp app/jarvis/mcp_servers/sqllite/database.db gs://jarvis-db-$(gcloud config get-value project)/
```

---

## Phase 3: Credentials and Secrets

### 3.1 Store Secrets in Secret Manager

```bash
# Store Google API Key
echo -n "your_api_key_here" | gcloud secrets create google-api-key --data-file=-

# Store Google Calendar Credentials
gcloud secrets create google-credentials --data-file=credentials.json
```

### 3.2 Create Service Account and Grant Permissions

```bash
# Create service account
gcloud iam service-accounts create jarvis-sa --display-name="Jarvis Service Account"

# Grant Storage Admin role
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:jarvis-sa@$(gcloud config get-value project).iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Grant Secret Manager Access
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:jarvis-sa@$(gcloud config get-value project).iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant Cloud Logging Access
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:jarvis-sa@$(gcloud config get-value project).iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

---

## Phase 4: Dockerfile Setup

### 4.1 Update/Create Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directory for credentials
RUN mkdir -p /app/credentials

# Create an entrypoint script
RUN echo '#!/bin/sh\n\
# Write Google Calendar credentials if provided\n\
if [ -n "$GOOGLE_CREDENTIALS" ]; then\n\
    echo "$GOOGLE_CREDENTIALS" > credentials.json\n\
    echo "Credentials written to credentials.json"\n\
fi\n\
\n\
# Create a directory for token storage\n\
mkdir -p /tmp/credentials\n\
\n\
# Start the application\n\
exec uvicorn app.api.routes:app --host 0.0.0.0 --port ${PORT:-8080}' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8080
# This environment variable indicates we're running in Cloud Run
ENV K_SERVICE="true"
# Enable structured logging
ENV PYTHONUNBUFFERED=1

# Run the application
ENTRYPOINT ["/app/entrypoint.sh"]
```

---

## Phase 5: Deploy to Cloud Run

### 5.1 Build and Deploy

```bash
gcloud run deploy jarvis-assistant \
  --source . \
  --region us-central1 \
  --set-secrets=GOOGLE_CREDENTIALS=google-credentials:latest,GOOGLE_API_KEY=google-api-key:latest \
  --allow-unauthenticated \
  --timeout=600 \
  --cpu=1 \
  --memory=512Mi \
  --min-instances=0 \
  --max-instances=10 \
  --port=8080
```

---

## Phase 6: OAuth Redirect Configuration

1. Get your service URL:

   ```bash
   gcloud run services describe jarvis-assistant --platform managed --region us-central1 --format "value(status.url)"
   ```

2. Go to [Google Cloud Console > APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
3. Add `{SERVICE_URL}/auth/callback` to Authorized redirect URIs.

---

## Phase 7: Post-Deployment Verification

### 7.1 Check Service Status

```bash
# Get service URL
OPEN_URL=$(gcloud run services describe jarvis-assistant --platform managed --region us-central1 --format "value(status.url)")
echo "Access your service at: $OPEN_URL"
```

### 7.2 View Logs

```bash
# View all logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=jarvis-assistant" --limit 50

# View only errors
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=jarvis-assistant AND severity>=ERROR" --limit 50

# View logs for specific revision
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=jarvis-assistant AND resource.labels.revision_name=jarvis-assistant-00001-xyz" --limit 50
```

---

## Notes

### Port Configuration

- Local development: Uvicorn uses default port 8000

  ```bash
  uvicorn app.api.routes:app --reload  # Uses port 8000
  ```

- Cloud Run: Always uses port 8080 (set via environment variable)

  ```bash
  # PORT=8080 is automatically set by Cloud Run
  ```

### Logging Configuration

- Local: Logs to console with default Uvicorn logging
- Cloud Run: Uses structured logging with Google Cloud Logging
  - All logs are properly formatted and searchable in Cloud Console
  - Includes severity levels, timestamps, and metadata
  - Captures application logs, system logs, and request logs

### Environment Variables

- Local:
  - Uses `.env` file and local credentials
  - Default port 8000
- Cloud Run:
  - Uses Secret Manager for sensitive data
  - PORT=8080 (set by platform)
  - K_SERVICE="true" for environment detection

---

**You are now ready to deploy your full-stack Jarvis Assistant to Google Cloud Run!**
