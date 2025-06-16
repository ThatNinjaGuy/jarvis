#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
import random
from pathlib import Path
from typing import List, Dict
from datetime import datetime

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[4])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import mcp.server.stdio
from app.config.logging_config import setup_cloud_logging
from app.jarvis.utils import load_environment

# Setup cloud logging
setup_cloud_logging()

# Playwright imports
from playwright.async_api import async_playwright

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

# ADK Tool Imports
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

# Load environment variables
load_environment()

# --- Logging Setup ---
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "mcp_server_activity.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
    ],
)

# --- LinkedIn Automation Class ---
class LinkedInAutomation:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.user_data_dir = "/Users/deadshot/Library/Application Support/Microsoft Edge/Default"
        self._initialization_lock = asyncio.Lock()
        
    async def ensure_initialized(self):
        """Ensure browser is initialized only when needed, with proper locking"""
        async with self._initialization_lock:
            if self.browser is None:
                logging.info("Initializing LinkedIn browser automation...")
                await self._initialize_browser()
                
    async def _initialize_browser(self):
        """Internal browser initialization method"""
        try:
            playwright = await async_playwright().start()
            # Enhanced browser configuration to avoid detection
            self.browser = await playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                channel="msedge",
                headless=False,
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,  # Retina display
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                ignore_default_args=["--enable-automation"],
                bypass_csp=True,
            )

            self.page = await self.browser.new_page()
            
            # Enhanced anti-detection measures
            await self.apply_stealth_mode()
            
            logging.info("LinkedIn browser automation initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize browser: {str(e)}", exc_info=True)
            raise

    async def apply_stealth_mode(self):
        """Apply various anti-detection measures"""
        try:
            # Override permissions
            await self.browser.grant_permissions(['notifications'])
            
            # Override navigator.webdriver
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Add realistic user agent and other headers
            await self.page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            })

            # Override screen properties
            await self.page.add_init_script("""
                Object.defineProperty(screen, 'width', { get: () => 1920 });
                Object.defineProperty(screen, 'height', { get: () => 1080 });
                Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
                Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
            """)

            # Add realistic viewport and window properties
            await self.page.add_init_script("""
                Object.defineProperty(window, 'innerWidth', { get: () => 1920 });
                Object.defineProperty(window, 'innerHeight', { get: () => 969 });
                Object.defineProperty(window, 'outerWidth', { get: () => 1920 });
                Object.defineProperty(window, 'outerHeight', { get: () => 1080 });
            """)

            # Add plugins and mime types
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Microsoft Edge PDF Plugin', filename: 'internal-pdf-viewer' }
                    ]
                });
            """)

            # Add language and platform
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
                Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)

        except Exception as e:
            logging.warning(f"Failed to apply some stealth mode features: {str(e)}")

    async def search_jobs(self, max_results: int = 10) -> List[Dict[str, str]]:
        """
        Fetch recommended jobs from LinkedIn.
        
        Args:
            max_results (int): Maximum number of jobs to return (default: 10)
            
        Returns:
            List[Dict[str, str]]: List of job postings with details
        """
        try:
            # Ensure browser is initialized
            await self.ensure_initialized()
            
            # Go to LinkedIn jobs page (recommended jobs)
            await self.page.goto('https://www.linkedin.com/jobs/collections/recommended/', wait_until='domcontentloaded')
            
            # Wait for the jobs section to be visible - using selectors from the screenshot
            try:
                # Wait for either the job results count or the first job card
                await self.page.wait_for_selector('div.jobs-search-results-list', timeout=15000)
                logging.info("Jobs list container found")
                
                # Small delay to let dynamic content load
                await asyncio.sleep(2)
                
                # Get job cards - using the exact class names from screenshot
                job_cards = await self.page.query_selector_all('div.job-card-container')
                results = []
                
                # Process only up to max_results
                for i, card in enumerate(job_cards[:max_results]):
                    try:
                        # Using exact selectors from the screenshot
                        title_elem = await card.query_selector('.job-card-list__title')
                        company_elem = await card.query_selector('.job-card-container__company-name')
                        location_elem = await card.query_selector('.job-card-container__metadata-item')
                        link_elem = await card.query_selector('a.job-card-container__link')
                        
                        title = await title_elem.text_content() if title_elem else 'N/A'
                        company = await company_elem.text_content() if company_elem else 'N/A'
                        location = await location_elem.text_content() if location_elem else 'N/A'
                        url = await link_elem.get_attribute('href') if link_elem else 'N/A'
                        
                        # Add small delay between processing cards
                        await asyncio.sleep(0.2)
                        
                        results.append({
                            'title': title.strip(),
                            'company': company.strip(),
                            'location': location.strip(),
                            'url': url,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        logging.info(f"Successfully processed job {i+1}: {title.strip()}")
                        
                    except Exception as e:
                        logging.error(f"Error processing job card {i}: {str(e)}")
                        continue
                
                if not results:
                    logging.warning("No jobs were found on the page")
                    
                return results
                
            except Exception as e:
                logging.error(f"Error waiting for job results: {str(e)}")
                raise Exception(f"Failed to load job results: {str(e)}")
                
        except Exception as e:
            logging.error(f"Error in search_jobs: {str(e)}")
            raise Exception(f"Failed to fetch LinkedIn jobs: {str(e)}")

    async def cleanup(self):
        if self.browser:
            await self.browser.close()

# Create a shared automation instance
linkedin_automation = LinkedInAutomation()

# --- LinkedIn Functions ---
async def search_jobs(max_results: int = 5) -> List[Dict[str, str]]:
    """
    Fetch recommended jobs from LinkedIn.
    
    Args:
        max_results (int): Maximum number of jobs to return (default: 5, max: 10)
        
    Returns:
        List[Dict[str, str]]: List of job postings with details
    """
    try:
        result = await linkedin_automation.search_jobs(max_results)
        return result
    except Exception as e:
        logging.error(f"Error in search_jobs function: {str(e)}")
        # Don't cleanup on error to allow retries
        raise

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for LinkedIn...")
app = Server("linkedin-mcp-server")

# Wrap LinkedIn functions as ADK FunctionTools
ADK_LINKEDIN_TOOLS = {
    "search_jobs": FunctionTool(func=search_jobs),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_LINKEDIN_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name

        mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_instance)
        logging.info(
            f"MCP Server: Advertising tool: {mcp_tool_schema.name}, InputSchema: {mcp_tool_schema.inputSchema}"
        )
        mcp_tools_list.append(mcp_tool_schema)
    return mcp_tools_list

@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """MCP handler to execute a tool call requested by an MCP client."""
    logging.info(
        f"MCP Server: Received call_tool request for '{name}' with args: {arguments}"
    )

    if name in ADK_LINKEDIN_TOOLS:
        adk_tool_instance = ADK_LINKEDIN_TOOLS[name]
        try:
            adk_tool_response = await adk_tool_instance.run_async(
                args=arguments,
                tool_context=None,  # type: ignore
            )
            logging.info(
                f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}"
            )
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            logging.error(
                f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True
            )
            error_payload = {
                "success": False,
                "message": f"Failed to execute tool '{name}': {str(e)}",
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        error_payload = {
            "success": False,
            "message": f"Tool '{name}' not implemented by this server.",
        }
        error_text = json.dumps(error_payload)
        return [mcp_types.TextContent(type="text", text=error_text)]

# --- MCP Server Runner ---
async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logging.info("MCP Stdio Server: Starting handshake with client...")
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=app.name,
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
        logging.info("MCP Stdio Server: Run loop finished or client disconnected.")

if __name__ == "__main__":
    logging.info("Launching LinkedIn MCP Server via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        logging.info("\nMCP Server (stdio) stopped by user.")
    except Exception as e:
        logging.critical(
            f"MCP Server (stdio) encountered an unhandled error: {e}", exc_info=True
        )
    finally:
        logging.info("MCP Server (stdio) process exiting.") 