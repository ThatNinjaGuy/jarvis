import asyncio
import json
import logging
import os
import sys
import base64
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any
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
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

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

# --- Web Browser Automation Class ---
class WebBrowserAutomation:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.user_data_dir = "/Users/deadshot/Library/Application Support/Microsoft Edge/Default"
        self._initialization_lock = asyncio.Lock()
        self._operation_timeout = 30000  # 30 seconds default timeout
        self._max_retries = 3  # Maximum number of retries for operations
        self._is_connected = False
        self._pages = []  # Track all pages
        
    def _kill_existing_edge_processes(self):
        """Kill any existing Edge processes to avoid conflicts"""
        # Disable killing existing processes to preserve user's session
        logging.info("Skipping killing existing Edge processes to preserve user session")
        return

    async def ensure_initialized(self):
        """Ensure browser is initialized only when needed, with proper locking"""
        async with self._initialization_lock:
            if self.browser is None:
                logging.info("Initializing web browser automation...")
                # Kill existing Edge processes to avoid conflicts
                self._kill_existing_edge_processes()
                await asyncio.sleep(1)  # Wait a moment for processes to close
                await self._initialize_browser()
                
    async def _initialize_browser(self):
        """Internal browser initialization method"""
        try:
            playwright = await async_playwright().start()
            
            try:
                # Enhanced browser configuration with persistent context
                self.browser = await playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    channel="msedge",
                    headless=False,
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                    ignore_default_args=["--enable-automation"],
                    bypass_csp=True,
                )
                
                # Get all pages and use the first active one or create new
                self._pages = self.browser.pages
                self.page = self._pages[0] if self._pages else await self.browser.new_page()
                self._is_connected = True
                logging.info(f"Web browser automation initialized with persistent context. Active pages: {len(self._pages)}")
                
            except Exception as persistent_error:
                logging.warning(f"Persistent context failed: {str(persistent_error)}, trying regular browser")
                
                # Fallback to regular browser launch
                self.browser = await playwright.chromium.launch(
                    channel="msedge",
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                
                self.context = await self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                    bypass_csp=True,
                )
                self.page = await self.context.new_page()
                self._pages = [self.page]
                self._is_connected = True
                logging.info("Web browser automation initialized with regular context")
            
            # Apply stealth mode
            await self.apply_stealth_mode()
            
        except Exception as e:
            self._is_connected = False
            logging.error(f"Failed to initialize browser: {str(e)}", exc_info=True)
            raise

    async def apply_stealth_mode(self):
        """Apply various anti-detection measures"""
        try:
            # Override navigator.webdriver
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            # Add realistic user agent and headers
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
            """)

        except Exception as e:
            logging.warning(f"Failed to apply some stealth mode features: {str(e)}")

    async def _with_timeout(self, coro, timeout=None):
        """Execute coroutine with timeout"""
        try:
            return await asyncio.wait_for(coro, timeout=timeout or self._operation_timeout/1000)
        except asyncio.TimeoutError:
            logging.error(f"Operation timed out after {timeout or self._operation_timeout/1000} seconds")
            raise TimeoutError("Browser operation timed out")

    async def _with_retry(self, operation, *args, **kwargs):
        """Execute operation with retry logic"""
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                logging.warning(f"Operation failed (attempt {attempt + 1}/{self._max_retries}): {str(e)}")
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                    await self.ensure_initialized()  # Reinitialize browser if needed
        raise last_error

    async def navigate_to_url(self, url: str, wait_for: str = "domcontentloaded") -> Dict[str, Any]:
        """Navigate to a specific URL and return basic page information."""
        try:
            await self.ensure_initialized()
            
            if not self._is_connected:
                raise RuntimeError("Browser is not properly connected")
            
            logging.info(f"Navigating to: {url}")
            
            # Create a new tab instead of using the same page
            try:
                if self.browser:
                    self.page = await self.browser.new_page()
                    self._pages.append(self.page)
                elif self.context:
                    self.page = await self.context.new_page()
                    self._pages.append(self.page)
                logging.info(f"Created new tab for navigation. Total active tabs: {len(self._pages)}")
            except Exception as e:
                logging.warning(f"Failed to create new tab, using existing: {str(e)}")
            
            # Use timeout and retry wrapper
            async def _navigate():
                try:
                    await self._with_timeout(
                        self.page.goto(url, wait_until=wait_for),
                        timeout=45  # 45 seconds timeout for navigation
                    )
                    
                    # Get basic page information
                    title = await self.page.title()
                    current_url = self.page.url
                    
                    # Get meta description if available
                    description = ""
                    try:
                        description_elem = await self.page.query_selector('meta[name="description"]')
                        if description_elem:
                            description = await description_elem.get_attribute('content') or ""
                    except Exception as e:
                        logging.warning(f"Failed to get meta description: {str(e)}")
                    
                    return {
                        "success": True,
                        "url": current_url,
                        "title": title,
                        "description": description,
                        "timestamp": datetime.now().isoformat(),
                        "message": f"Successfully navigated to {title}"
                    }
                except Exception as e:
                    logging.error(f"Navigation failed: {str(e)}")
                    raise
            
            result = await self._with_retry(_navigate)
            logging.info(f"Successfully navigated to: {result['title']}")
            return result
            
        except TimeoutError as e:
            self._is_connected = False  # Mark as disconnected on timeout
            logging.error(f"Timeout navigating to URL {url}: {str(e)}")
            return {
                "success": False,
                "url": url,
                "error": f"Navigation timeout: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self._is_connected = False  # Mark as disconnected on error
            logging.error(f"Error navigating to URL {url}: {str(e)}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def extract_text_content(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract text content from the current page.
        
        Args:
            selector (Optional[str]): CSS selector to extract specific content. If None, extracts all text.
            
        Returns:
            Dict[str, Any]: Extracted text content
        """
        try:
            await self.ensure_initialized()
            
            if selector:
                # Extract text from specific elements
                elements = await self.page.query_selector_all(selector)
                texts = []
                for element in elements:
                    text = await element.text_content()
                    if text and text.strip():
                        texts.append(text.strip())
                
                result = {
                    "success": True,
                    "selector": selector,
                    "texts": texts,
                    "count": len(texts),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                # Extract all text content
                body_text = await self.page.text_content('body')
                
                result = {
                    "success": True,
                    "selector": "body (all text)",
                    "text": body_text.strip() if body_text else "",
                    "word_count": len(body_text.split()) if body_text else 0,
                    "timestamp": datetime.now().isoformat()
                }
            
            logging.info(f"Successfully extracted text content using selector: {selector or 'body'}")
            return result
            
        except Exception as e:
            logging.error(f"Error extracting text content: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def extract_elements(self, selector: str, attributes: List[str] = None) -> Dict[str, Any]:
        """
        Extract specific elements and their attributes from the page.
        
        Args:
            selector (str): CSS selector to find elements
            attributes (List[str]): List of attributes to extract from each element
            
        Returns:
            Dict[str, Any]: Information about found elements
        """
        try:
            await self.ensure_initialized()
            
            elements = await self.page.query_selector_all(selector)
            results = []
            
            for element in elements:
                element_data = {}
                
                # Get text content
                text = await element.text_content()
                if text:
                    element_data["text"] = text.strip()
                
                # Get specified attributes
                if attributes:
                    for attr in attributes:
                        value = await element.get_attribute(attr)
                        if value:
                            element_data[attr] = value
                
                if element_data:  # Only add if we got some data
                    results.append(element_data)
            
            result = {
                "success": True,
                "selector": selector,
                "elements": results,
                "count": len(results),
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"Successfully extracted {len(results)} elements using selector: {selector}")
            return result
            
        except Exception as e:
            logging.error(f"Error extracting elements: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def take_screenshot(self, full_page: bool = False) -> Dict[str, Any]:
        """
        Take a screenshot of the current page.
        
        Args:
            full_page (bool): Whether to capture the full page or just the viewport
            
        Returns:
            Dict[str, Any]: Screenshot information with base64 encoded image
        """
        try:
            await self.ensure_initialized()
            
            # Create screenshots directory if it doesn't exist
            screenshots_dir = Path(__file__).parent / "screenshots"
            screenshots_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            # Take screenshot
            screenshot_bytes = await self.page.screenshot(
                path=str(filepath),
                full_page=full_page
            )
            
            # Convert to base64 for JSON response
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            result = {
                "success": True,
                "filename": filename,
                "filepath": str(filepath),
                "full_page": full_page,
                "screenshot_base64": screenshot_base64,
                "size_bytes": len(screenshot_bytes),
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"Successfully took screenshot: {filename}")
            return result
            
        except Exception as e:
            logging.error(f"Error taking screenshot: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def search_page_content(self, search_terms: List[str]) -> Dict[str, Any]:
        """
        Search for specific terms in the page content.
        
        Args:
            search_terms (List[str]): Terms to search for
            
        Returns:
            Dict[str, Any]: Search results with context
        """
        try:
            await self.ensure_initialized()
            
            page_text = await self.page.text_content('body')
            if not page_text:
                return {
                    "success": False,
                    "error": "No text content found on page",
                    "timestamp": datetime.now().isoformat()
                }
            
            results = {}
            page_text_lower = page_text.lower()
            
            for term in search_terms:
                term_lower = term.lower()
                occurrences = []
                
                # Find all occurrences
                start = 0
                while True:
                    index = page_text_lower.find(term_lower, start)
                    if index == -1:
                        break
                    
                    # Get context around the found term (100 chars before/after)
                    context_start = max(0, index - 100)
                    context_end = min(len(page_text), index + len(term) + 100)
                    context = page_text[context_start:context_end].strip()
                    
                    occurrences.append({
                        "position": index,
                        "context": context
                    })
                    
                    start = index + 1
                
                results[term] = {
                    "count": len(occurrences),
                    "occurrences": occurrences[:5]  # Limit to first 5 occurrences
                }
            
            result = {
                "success": True,
                "search_terms": search_terms,
                "results": results,
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"Successfully searched for terms: {search_terms}")
            return result
            
        except Exception as e:
            logging.error(f"Error searching page content: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def get_page_links(self, filter_pattern: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract all links from the current page.
        
        Args:
            filter_pattern (Optional[str]): Pattern to filter links (contains match)
            
        Returns:
            Dict[str, Any]: List of links found on the page
        """
        try:
            await self.ensure_initialized()
            
            # Get all link elements
            link_elements = await self.page.query_selector_all('a[href]')
            links = []
            
            for element in link_elements:
                href = await element.get_attribute('href')
                text = await element.text_content()
                
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith('/'):
                        base_url = f"{self.page.url.split('/')[0]}//{self.page.url.split('/')[2]}"
                        href = base_url + href
                    elif href.startswith('./'):
                        href = href[2:]
                    
                    link_data = {
                        "url": href,
                        "text": text.strip() if text else ""
                    }
                    
                    # Apply filter if provided
                    if filter_pattern:
                        if filter_pattern.lower() in href.lower() or filter_pattern.lower() in (text or "").lower():
                            links.append(link_data)
                    else:
                        links.append(link_data)
            
            result = {
                "success": True,
                "links": links,
                "count": len(links),
                "filter_pattern": filter_pattern,
                "timestamp": datetime.now().isoformat()
            }
            
            logging.info(f"Successfully extracted {len(links)} links")
            return result
            
        except Exception as e:
            logging.error(f"Error extracting links: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def click_element(self, selector: str) -> Dict[str, Any]:
        """
        Click on an element specified by CSS selector.
        
        Args:
            selector (str): CSS selector for the element to click
            
        Returns:
            Dict[str, Any]: Result of the click operation
        """
        try:
            await self.ensure_initialized()
            
            # Wait for the element to be visible and clickable
            await self.page.wait_for_selector(selector, timeout=10000)
            element = await self.page.query_selector(selector)
            
            if not element:
                return {
                    "success": False,
                    "error": f"Element not found: {selector}",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Click the element
            await element.click()
            await self.page.wait_for_load_state('domcontentloaded')
            
            result = {
                "success": True,
                "selector": selector,
                "current_url": self.page.url,
                "timestamp": datetime.now().isoformat(),
                "message": f"Successfully clicked element: {selector}"
            }
            
            logging.info(f"Successfully clicked element: {selector}")
            return result
            
        except Exception as e:
            logging.error(f"Error clicking element {selector}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "selector": selector,
                "timestamp": datetime.now().isoformat()
            }

    async def smart_google_search_and_extract(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """
        Perform a Google search, then automatically visit the top results and extract content.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of search results to visit and extract content from
            
        Returns:
            Dict[str, Any]: Search results with extracted content from top websites
        """
        try:
            await self.ensure_initialized()
            
            # Perform Google search
            google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            logging.info(f"Performing Google search: {google_url}")
            
            await self.page.goto(google_url, wait_until='domcontentloaded')
            await asyncio.sleep(2)  # Let page load fully
            
            # Extract search result links (skip ads and irrelevant results)
            search_results = []
            result_selectors = [
                'div.g h3 a',  # Main search results
                'div[data-ved] h3 a',  # Alternative search result format
                '.yuRUbf a'  # Another format for search results
            ]
            
            for selector in result_selectors:
                elements = await self.page.query_selector_all(selector)
                for element in elements[:max_results * 2]:  # Get more than needed to filter
                    href = await element.get_attribute('href')
                    text_elem = await element.query_selector('h3') or element
                    title = await text_elem.text_content() if text_elem else ""
                    
                    if href and href.startswith('http') and len(search_results) < max_results:
                        # Skip common non-content sites
                        skip_domains = ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com', 'pinterest.com']
                        if not any(domain in href for domain in skip_domains):
                            search_results.append({
                                'title': title.strip(),
                                'url': href,
                                'extracted_content': None
                            })
                
                if len(search_results) >= max_results:
                    break
            
            logging.info(f"Found {len(search_results)} search results to visit")
            
            # Visit each result and extract content
            for i, result in enumerate(search_results):
                try:
                    logging.info(f"Visiting result {i+1}: {result['url']}")
                    
                    # Navigate to the result page
                    await self.page.goto(result['url'], wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(1)
                    
                    # Extract main content (try multiple selectors for better content extraction)
                    content_selectors = [
                        'article',
                        'main',
                        '[role="main"]',
                        '.content',
                        '.main-content',
                        '.post-content',
                        '.entry-content',
                        '.article-content',
                        'body'
                    ]
                    
                    extracted_text = ""
                    for selector in content_selectors:
                        try:
                            element = await self.page.query_selector(selector)
                            if element:
                                text = await element.text_content()
                                if text and len(text.strip()) > 200:  # Ensure substantial content
                                    extracted_text = text.strip()[:2000]  # Limit to 2000 chars
                                    break
                        except:
                            continue
                    
                    # If no substantial content found, get page text
                    if not extracted_text:
                        page_text = await self.page.text_content('body')
                        if page_text:
                            # Remove navigation and header content
                            lines = page_text.split('\n')
                            content_lines = [line.strip() for line in lines if len(line.strip()) > 50]
                            extracted_text = '\n'.join(content_lines[:20])[:2000]  # First 20 substantial lines
                    
                    result['extracted_content'] = extracted_text
                    result['page_title'] = await self.page.title()
                    
                except Exception as e:
                    logging.warning(f"Failed to extract content from {result['url']}: {str(e)}")
                    result['extracted_content'] = f"Error extracting content: {str(e)}"
            
            return {
                "success": True,
                "query": query,
                "results": search_results,
                "total_results": len(search_results),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logging.error(f"Error in smart Google search: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "timestamp": datetime.now().isoformat()
            }

    async def research_topic(self, topic: str, max_sources: int = 3) -> Dict[str, Any]:
        """
        Intelligently research a topic by searching and extracting content from multiple sources.
        
        Args:
            topic (str): Topic to research
            max_sources (int): Maximum number of sources to research
            
        Returns:
            Dict[str, Any]: Comprehensive research results from multiple sources
        """
        try:
            # First, perform the smart Google search
            search_result = await self.smart_google_search_and_extract(topic, max_sources)
            
            if not search_result.get('success'):
                return search_result
            
            # Analyze and summarize the collected information
            sources = search_result.get('results', [])
            research_summary = {
                "topic": topic,
                "sources_analyzed": len(sources),
                "sources": [],
                "key_findings": [],
                "timestamp": datetime.now().isoformat()
            }
            
            for source in sources:
                if source.get('extracted_content'):
                    source_info = {
                        "title": source.get('page_title', source.get('title', 'Unknown')),
                        "url": source['url'],
                        "content_preview": source['extracted_content'][:500] + "..." if len(source['extracted_content']) > 500 else source['extracted_content'],
                        "content_length": len(source['extracted_content'])
                    }
                    research_summary["sources"].append(source_info)
                    
                    # Extract key sentences that might be findings
                    content = source['extracted_content']
                    sentences = content.split('.')
                    key_sentences = [s.strip() for s in sentences if len(s.strip()) > 50 and len(s.strip()) < 200]
                    research_summary["key_findings"].extend(key_sentences[:3])  # Top 3 from each source
            
            # Limit key findings
            research_summary["key_findings"] = research_summary["key_findings"][:10]
            
            return {
                "success": True,
                "research_summary": research_summary,
                "raw_sources": sources,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logging.error(f"Error researching topic {topic}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "topic": topic,
                "timestamp": datetime.now().isoformat()
            }

    async def cleanup(self):
        """Close browser and cleanup resources"""
        try:
            # Don't close the browser, just clean up our tracked pages
            for page in self._pages:
                try:
                    if page and not page.is_closed():
                        await page.close()
                except Exception as e:
                    logging.warning(f"Error closing page: {str(e)}")
            
            self._pages = []
            self._is_connected = False
            logging.info("Cleaned up browser pages while preserving user session")
            
        except Exception as e:
            logging.warning(f"Error during cleanup: {str(e)}")

# Create a shared automation instance
web_browser = WebBrowserAutomation()

# --- Web Browser Functions ---
async def navigate_to_website(url: str, wait_for: str = "domcontentloaded") -> Dict[str, Any]:
    """
    Navigate to a specific website and return basic information.
    
    Args:
        url (str): The URL to navigate to
        wait_for (str): What to wait for - 'domcontentloaded', 'load', or 'networkidle' (default: 'domcontentloaded')
        
    Returns:
        Dict[str, Any]: Navigation result with page information
    """
    try:
        result = await web_browser.navigate_to_url(url, wait_for)
        return result
    except Exception as e:
        logging.error(f"Error in navigate_to_website function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to navigate to website: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def extract_page_text(selector: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract text content from the current page.
    
    Args:
        selector (Optional[str]): CSS selector to extract specific content. If None, extracts all text.
        
    Returns:
        Dict[str, Any]: Extracted text content
    """
    try:
        result = await web_browser.extract_text_content(selector)
        return result
    except Exception as e:
        logging.error(f"Error in extract_page_text function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to extract page text: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def extract_page_elements(selector: str, attributes: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Extract specific elements and their attributes from the page.
    
    Args:
        selector (str): CSS selector to find elements
        attributes (List[str]): List of attributes to extract from each element
        
    Returns:
        Dict[str, Any]: Information about found elements
    """
    try:
        if attributes is None:
            attributes = []
        result = await web_browser.extract_elements(selector, attributes)
        return result
    except Exception as e:
        logging.error(f"Error in extract_page_elements function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to extract page elements: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def take_page_screenshot(full_page: bool = False) -> Dict[str, Any]:
    """
    Take a screenshot of the current page.
    
    Args:
        full_page (bool): Whether to capture the full page or just the viewport (default: False)
        
    Returns:
        Dict[str, Any]: Screenshot information
    """
    try:
        result = await web_browser.take_screenshot(full_page)
        return result
    except Exception as e:
        logging.error(f"Error in take_page_screenshot function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to take screenshot: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def search_in_page(search_terms: List[str]) -> Dict[str, Any]:
    """
    Search for specific terms in the current page content.
    
    Args:
        search_terms (List[str]): Terms to search for
        
    Returns:
        Dict[str, Any]: Search results with context
    """
    try:
        result = await web_browser.search_page_content(search_terms)
        return result
    except Exception as e:
        logging.error(f"Error in search_in_page function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to search in page: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def get_all_links(filter_pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract all links from the current page.
    
    Args:
        filter_pattern (Optional[str]): Pattern to filter links (contains match)
        
    Returns:
        Dict[str, Any]: List of links found on the page
    """
    try:
        result = await web_browser.get_page_links(filter_pattern)
        return result
    except Exception as e:
        logging.error(f"Error in get_all_links function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to get page links: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def click_page_element(selector: str) -> Dict[str, Any]:
    """
    Click on an element on the current page.
    
    Args:
        selector (str): CSS selector for the element to click
        
    Returns:
        Dict[str, Any]: Result of the click operation
    """
    try:
        result = await web_browser.click_element(selector)
        return result
    except Exception as e:
        logging.error(f"Error in click_page_element function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to click element: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def smart_search_and_extract(query: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Intelligently search Google and automatically extract content from top results.
    
    Args:
        query (str): Search query
        max_results (int): Maximum number of search results to visit and extract content from (default: 3)
        
    Returns:
        Dict[str, Any]: Search results with extracted content from top websites
    """
    try:
        result = await web_browser.smart_google_search_and_extract(query, max_results)
        return result
    except Exception as e:
        logging.error(f"Error in smart_search_and_extract function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to perform smart search: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

async def research_topic_comprehensive(topic: str, max_sources: int = 3) -> Dict[str, Any]:
    """
    Conduct comprehensive research on a topic using multiple web sources.
    
    Args:
        topic (str): Topic to research
        max_sources (int): Maximum number of sources to analyze (default: 3)
        
    Returns:
        Dict[str, Any]: Comprehensive research results with analysis and key findings
    """
    try:
        result = await web_browser.research_topic(topic, max_sources)
        return result
    except Exception as e:
        logging.error(f"Error in research_topic_comprehensive function: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to research topic: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Web Browser...")
app = Server("web-browser-mcp-server")

# Wrap web browser functions as ADK FunctionTools
ADK_WEB_BROWSER_TOOLS = {
    "navigate_to_website": FunctionTool(func=navigate_to_website),
    "extract_page_text": FunctionTool(func=extract_page_text),
    "extract_page_elements": FunctionTool(func=extract_page_elements),
    "take_page_screenshot": FunctionTool(func=take_page_screenshot),
    "search_in_page": FunctionTool(func=search_in_page),
    "get_all_links": FunctionTool(func=get_all_links),
    "click_page_element": FunctionTool(func=click_page_element),
    "smart_search_and_extract": FunctionTool(func=smart_search_and_extract),
    "research_topic_comprehensive": FunctionTool(func=research_topic_comprehensive),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_WEB_BROWSER_TOOLS.items():
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

    if name in ADK_WEB_BROWSER_TOOLS:
        adk_tool_instance = ADK_WEB_BROWSER_TOOLS[name]
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
    logging.info("Launching Web Browser MCP Server via stdio...")
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
        # Cleanup
        try:
            asyncio.run(web_browser.cleanup())
        except:
            pass 