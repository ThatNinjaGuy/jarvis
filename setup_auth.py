#!/usr/bin/env python3
"""
Setup script for ride booking authentication.

This script handles:
1. Checking Uber credentials
2. Setting up Ola OAuth authentication
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from app.jarvis.mcp_servers.ride_aggregator.auth.ola_auth import OlaAuthSetup
import http.server
import socketserver
import threading
import webbrowser
import urllib.parse
import time

class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handle the OAuth callback"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        message = """
        <html>
        <body>
        <h1>Authentication Complete</h1>
        <p>You can close this window and return to the terminal.</p>
        <script>
            // Extract the token from the URL fragment
            var hash = window.location.hash.substring(1);
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/save-token?' + hash, true);
            xhr.send();
        </script>
        </body>
        </html>
        """
        self.wfile.write(message.encode())
    
    def log_message(self, format, *args):
        """Suppress logging"""
        return

def start_callback_server(port=8001):
    """Start a local server to handle the OAuth callback"""
    with socketserver.TCPServer(("", port), OAuthCallbackHandler) as httpd:
        print(f"\nStarting callback server on port {port}...")
        httpd.serve_forever()

def main():
    """Main setup function"""
    load_dotenv()
    
    print("🚗 Jarvis Ride Aggregator - Authentication Setup")
    print("=" * 50)
    
    # Check Uber configuration
    uber_client_id = os.getenv("UBER_CLIENT_ID")
    uber_client_secret = os.getenv("UBER_CLIENT_SECRET")
    
    if not uber_client_id or not uber_client_secret:
        print("❌ Uber credentials missing in .env file")
        print("Please add UBER_CLIENT_ID and UBER_CLIENT_SECRET")
        return False
    else:
        print("✅ Uber credentials configured (client credentials)")
    
    # Check Ola configuration
    ola_app_token = os.getenv("OLA_APP_TOKEN")
    ola_client_id = os.getenv("OLA_CLIENT_ID")
    ola_client_secret = os.getenv("OLA_CLIENT_SECRET")
    ola_redirect_uri = os.getenv("OLA_REDIRECT_URI", "http://127.0.0.1:8001/callback")
    
    if not all([ola_app_token, ola_client_id, ola_client_secret]):
        print("❌ Ola credentials missing in .env file")
        print("Please add OLA_APP_TOKEN, OLA_CLIENT_ID, and OLA_CLIENT_SECRET")
        return False
    
    # Check if Ola is already set up
    config_path = Path(__file__).parent / "app" / "jarvis" / "mcp_servers" / "ride_aggregator" / "config" / "ola_auth_config.json"
    if config_path.exists():
        print("✅ Ola authentication already configured")
        choice = input("Reconfigure Ola authentication? (y/N): ").lower()
        if choice != 'y':
            print("Setup complete!")
            return True
    
    # Set up Ola authentication
    print("\n🔧 Setting up Ola authentication...")
    try:
        # Start the callback server in a separate thread
        server_thread = threading.Thread(target=start_callback_server, daemon=True)
        server_thread.start()
        
        # Initialize Ola setup
        ola_setup = OlaAuthSetup(
            client_id=ola_client_id,
            client_secret=ola_client_secret,
            redirect_uri=ola_redirect_uri
        )
        
        # Generate and open OAuth URL
        oauth_url = ola_setup.generate_oauth_url()
        print("\nOpening browser for Ola authentication...")
        print(f"If the browser doesn't open automatically, visit:\n{oauth_url}\n")
        webbrowser.open(oauth_url)
        
        print("Waiting for authentication to complete...")
        print("(Check your browser and grant the requested permissions)")
        
        # Wait for the callback
        time.sleep(60)  # Wait up to 60 seconds for authentication
        
        if not config_path.exists():
            print("\n❌ Authentication timed out or failed.")
            print("Please try again and make sure to complete the authentication in the browser.")
            return False
        
        print("\n🎉 Setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return False
    finally:
        # Cleanup (the server thread will be terminated when the main thread exits)
        print("\nSetup process complete.")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 