#!/usr/bin/env python3
"""
Setup script for Amazon MCP Server.
This script installs Playwright browsers and sets up the environment.
"""

import subprocess
import sys
import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def run_command(command, description):
    """Run a shell command and handle errors."""
    logging.info(f"Running: {description}")
    logging.info(f"Command: {' '.join(command)}")

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        logging.info(f"Success: {description}")
        if result.stdout:
            logging.info(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed: {description}")
        logging.error(f"Error: {e.stderr}")
        return False


def check_playwright_installation():
    """Check if playwright is installed."""
    try:
        import playwright

        logging.info("Playwright is already installed")
        return True
    except ImportError:
        logging.info("Playwright is not installed")
        return False


def install_playwright():
    """Install playwright if not already installed."""
    if not check_playwright_installation():
        logging.info("Installing playwright...")
        if not run_command(
            [sys.executable, "-m", "pip", "install", "playwright"],
            "Installing playwright package",
        ):
            return False

    # Install browsers
    logging.info("Installing Playwright browsers...")
    return run_command(
        [sys.executable, "-m", "playwright", "install"],
        "Installing Playwright browsers",
    )


def setup_environment():
    """Setup environment variables and configuration."""
    logging.info("Setting up environment...")

    # Create .env file template if it doesn't exist
    env_file = Path(".env")
    if not env_file.exists():
        logging.info("Creating .env template file...")
        env_template = """
# Amazon MCP Server Configuration
AMAZON_PROXY=
# Example: AMAZON_PROXY=http://username:password@proxy-server:port

# Optional: Custom user agents (semicolon separated)
USER_AGENTS=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36;Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
"""
        with open(env_file, "w") as f:
            f.write(env_template)
        logging.info(
            "Created .env template file. Please configure proxy settings if needed."
        )

    # Create log directory
    log_dir = Path("app/jarvis/mcp_servers/amazon")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Created log directory: {log_dir}")


def test_amazon_server():
    """Test if the Amazon MCP server can be imported."""
    logging.info("Testing Amazon MCP server import...")

    try:
        # Add current directory to Python path
        sys.path.insert(0, str(Path.cwd()))

        # Try to import the server module
        from app.jarvis.mcp_servers.amazon import server

        logging.info("✅ Amazon MCP server imported successfully")

        # Test browser manager creation
        from app.jarvis.mcp_servers.amazon.server import AmazonBrowserManager

        browser_mgr = AmazonBrowserManager()
        logging.info("✅ AmazonBrowserManager created successfully")

        return True
    except ImportError as e:
        logging.error(f"❌ Failed to import Amazon MCP server: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Error testing Amazon MCP server: {e}")
        return False


def main():
    """Main setup function."""
    logging.info("🚀 Setting up Amazon MCP Server...")

    # Check Python version
    if sys.version_info < (3, 8):
        logging.error("Python 3.8 or higher is required")
        sys.exit(1)

    logging.info(f"Python version: {sys.version}")

    # Install playwright
    if not install_playwright():
        logging.error("Failed to install Playwright")
        sys.exit(1)

    # Setup environment
    setup_environment()

    # Test the server
    if test_amazon_server():
        logging.info("✅ Amazon MCP Server setup completed successfully!")
        logging.info("\n📝 Next steps:")
        logging.info("1. Configure proxy settings in .env file if needed")
        logging.info(
            "2. Test the server: python -m app.jarvis.mcp_servers.amazon.server"
        )
        logging.info("3. Use the Amazon shopping tools in your ADK agent")
    else:
        logging.error("❌ Amazon MCP Server setup completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
