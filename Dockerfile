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
# Print environment for debugging\n\
echo "GOOGLE_API_KEY is set: ${GOOGLE_API_KEY:+yes}"\n\
echo "PORT is set to: $PORT"\n\
echo "PYTHONPATH is set to: $PYTHONPATH"\n\
\n\
# Start the application with proper logging\n\
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --log-level info' > /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8080
# This environment variable indicates we're running in Cloud Run
ENV K_SERVICE="true"
# Enable structured logging
ENV PYTHONUNBUFFERED=1

# Run the application
ENTRYPOINT ["/app/entrypoint.sh"] 