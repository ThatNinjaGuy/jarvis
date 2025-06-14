import asyncio
import json
import logging
import os
import sys
import datetime
from pathlib import Path
from base64 import urlsafe_b64decode
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Dict, List, Union, Any, Tuple

# Add the root directory to Python path for imports
root_dir = str(Path(__file__).resolve().parents[4])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import mcp.server.stdio
from app.jarvis.utils import get_token_path, get_google_credentials, load_environment
from app.config.logging_config import setup_cloud_logging

# Setup cloud logging
setup_cloud_logging()

# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ADK Tool Imports
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

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

# --- Gmail Utilities ---
# Define scopes needed for Gmail
SCOPES = ['https://mail.google.com/']  # Full access scope needed for search

# Get paths from environment utility
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/gmail_token.json"))

def get_gmail_service():
    """
    Authenticate and create a Gmail service object.

    Returns:
        A Gmail service object or None if authentication fails
    """
    creds = None

    # Check if token exists and is valid
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(TOKEN_PATH.read_text()), SCOPES
            )
            logging.debug("Successfully loaded existing credentials")
        except Exception as e:
            logging.warning(f"Failed to load existing credentials: {e}", exc_info=True)
            # If token is corrupted or invalid, we'll create new credentials
            pass

    # If credentials don't exist or are invalid, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Successfully refreshed expired credentials")
            except Exception as e:
                logging.error(f"Failed to refresh credentials: {e}", exc_info=True)
                return None
        else:
            # Get credentials from environment or file
            creds_info = get_google_credentials()
            if not creds_info:
                logging.error("No valid credentials found. Please check configuration.")
                return None

            try:
                flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
                creds = flow.run_local_server(port=0)
                logging.info("Successfully created new credentials through OAuth flow")
            except Exception as e:
                logging.error(f"Error in authentication flow: {e}", exc_info=True)
                return None

        # Save the credentials for the next run
        try:
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(creds.to_json())
            logging.debug(f"Saved credentials to {TOKEN_PATH}")
        except Exception as e:
            logging.warning(f"Failed to save credentials: {e}", exc_info=True)

    # Create and return the Gmail service
    try:
        service = build("gmail", "v1", credentials=creds)
        logging.debug("Successfully created Gmail service")
        return service
    except Exception as e:
        logging.error(f"Failed to create Gmail service: {e}", exc_info=True)
        return None

def parse_date(date_str):
    """
    Parse a date string into a datetime object.

    Args:
        date_str (str): A string representing a date

    Returns:
        datetime: A datetime object or None if parsing fails
    """
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
    ]

    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None

def get_email_body(service: Any, user_id: str, msg: Dict[str, Any]) -> Dict[str, Union[str, List[Dict[str, Any]]]]:
    """
    Get the email body from a message object with support for multiple MIME types.

    Args:
        service: Gmail API service instance
        user_id (str): User's email address
        msg (dict): Message object from Gmail API

    Returns:
        dict: Email body with text and HTML content
    """
    try:
        if 'payload' not in msg:
            return {"text": "", "html": "", "attachments": []}

        def decode_part(part: Dict[str, Any]) -> str:
            """Helper function to decode message parts."""
            if 'body' in part and 'data' in part['body']:
                return urlsafe_b64decode(part['body']['data']).decode()
            return ""

        def process_parts(
            parts: List[Dict[str, Any]], 
            text_content: Optional[List[str]] = None,
            html_content: Optional[List[str]] = None,
            attachments: Optional[List[Dict[str, Any]]] = None
        ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
            """Recursively process message parts."""
            if text_content is None:
                text_content = []
            if html_content is None:
                html_content = []
            if attachments is None:
                attachments = []

            for part in parts:
                mime_type = part.get('mimeType', '')
                filename = part.get('filename', '')
                
                if filename:  # This is an attachment
                    attachment_id = part['body'].get('attachmentId', '')
                    size = part['body'].get('size', 0)
                    attachments.append({
                        'filename': filename,
                        'mimeType': mime_type,
                        'size': size,
                        'attachmentId': attachment_id
                    })
                elif mime_type == 'text/plain':
                    text_content.append(decode_part(part))
                elif mime_type == 'text/html':
                    html_content.append(decode_part(part))
                elif mime_type.startswith('multipart/'):
                    if 'parts' in part:
                        process_parts(part['parts'], text_content, html_content, attachments)

            return text_content, html_content, attachments

        payload = msg['payload']
        mime_type = payload.get('mimeType', '')

        if mime_type.startswith('multipart/'):
            text_parts, html_parts, attachments = process_parts(payload.get('parts', []))
        else:
            # Handle single-part messages
            if mime_type == 'text/plain':
                text_parts = [decode_part(payload)]
                html_parts = []
            elif mime_type == 'text/html':
                text_parts = []
                html_parts = [decode_part(payload)]
            else:
                text_parts = []
                html_parts = []
            attachments = []

        return {
            "text": '\n'.join(text_parts),
            "html": '\n'.join(html_parts),
            "attachments": attachments
        }

    except Exception as e:
        logging.error(f"Error getting email body: {e}", exc_info=True)
        return {"text": "", "html": "", "attachments": []}

def get_attachment(
    service: Any,
    user_id: str,
    message_id: str,
    attachment_id: str
) -> Optional[bytes]:
    """
    Get an email attachment by its ID.

    Args:
        service: Gmail API service instance
        user_id (str): User's email address
        message_id (str): ID of the email message
        attachment_id (str): ID of the attachment

    Returns:
        dict: Attachment data and metadata
    """
    try:
        attachment = service.users().messages().attachments().get(
            userId=user_id,
            messageId=message_id,
            id=attachment_id
        ).execute()

        data = attachment.get('data', '')
        file_data = base64.urlsafe_b64decode(data)

        return file_data
    except Exception as e:
        logging.error(f"Error fetching attachment: {e}", exc_info=True)
        return None

def list_emails(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 50
) -> dict:
    """
    List emails within a specified date range (metadata only).

    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format
        max_results (int): Maximum number of emails to return (default: 50)

    Returns:
        dict: Information about emails or error details
    """
    try:
        logging.info(f"Listing emails - Start date: {start_date}, End date: {end_date}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "emails": [],
            }

        # Parse dates
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date)

        if not start_dt or not end_dt:
            return {
                "status": "error",
                "message": "Invalid date format. Please use YYYY-MM-DD format.",
                "emails": [],
            }

        # Adjust end date to include the entire day
        end_dt = end_dt + datetime.timedelta(days=1)

        # Create Gmail API query using RFC 3339 date format
        start_str = start_dt.strftime('%Y/%m/%d')
        end_str = end_dt.strftime('%Y/%m/%d')
        
        # Create Gmail API query
        query = f"after:{start_str} before:{end_str}"
        logging.info(f"Gmail API Query: {query}")
        
        # Call the Gmail API
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        
        if not messages:
            logging.info("No messages found matching the query")
            return {
                "status": "success",
                "message": "No emails found in the specified date range.",
                "emails": [],
            }

        # Get metadata for each email
        emails = []
        for message in messages:
            # Get only metadata using format='metadata' and fields parameter
            msg = service.users().messages().get(
                userId='me',
                id=message['id'],
                format='metadata',
                metadataHeaders=['subject', 'from', 'date']
            ).execute()

            # Extract headers
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')

            email_data = {
                'id': msg['id'],
                'threadId': msg['threadId'],
                'subject': subject,
                'from': from_email,
                'date': date,
                'snippet': msg.get('snippet', '')
            }
            emails.append(email_data)

        return {
            "status": "success",
            "message": f"Found {len(emails)} email(s).",
            "emails": emails,
        }

    except Exception as e:
        logging.error(f"Error fetching emails: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error fetching emails: {str(e)}",
            "emails": [],
        }

def get_email_content(
    email_id: str,
    include_attachments: bool = False
) -> dict:
    """
    Get the full content of a specific email.

    Args:
        email_id (str): The ID of the email to fetch
        include_attachments (bool): Whether to include attachment data (default: False)

    Returns:
        dict: Full email content and details
    """
    try:
        logging.info(f"Fetching email content for ID: {email_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "email": None,
            }

        # Get the full email content
        msg = service.users().messages().get(
            userId='me',
            id=email_id,
            format='full'
        ).execute()

        # Extract headers
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
        from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
        to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown Recipient')
        cc = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')

        # Get email body with all content types
        body_content = get_email_body(service, 'me', msg)
        
        email_data = {
            'id': msg['id'],
            'threadId': msg['threadId'],
            'subject': subject,
            'from': from_email,
            'to': to_email,
            'cc': cc,
            'date': date,
            'snippet': msg.get('snippet', ''),
            'body': {
                'text': body_content['text'],
                'html': body_content['html']
            },
            'labels': msg.get('labelIds', []),
            'attachments': []
        }

        # Handle attachments if present and requested
        if body_content['attachments'] and include_attachments:
            attachments = []
            for attachment_info in body_content['attachments']:
                if include_attachments:
                    attachment_data = get_attachment(
                        service, 
                        'me', 
                        email_id, 
                        attachment_info['attachmentId']
                    )
                    if attachment_data:
                        attachments.append({
                            'filename': attachment_info['filename'],
                            'mimeType': attachment_info['mimeType'],
                            'size': attachment_info['size'],
                            'data': base64.b64encode(attachment_data).decode('utf-8')
                        })
                else:
                    # Include only attachment metadata
                    attachments.append({
                        'filename': attachment_info['filename'],
                        'mimeType': attachment_info['mimeType'],
                        'size': attachment_info['size']
                    })
            email_data['attachments'] = attachments

        return {
            "status": "success",
            "message": "Email content retrieved successfully.",
            "email": email_data,
        }

    except Exception as e:
        logging.error(f"Error fetching email content: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error fetching email content: {str(e)}",
            "email": None,
        }

def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html_content: str = "",
    attachments: Optional[List[Dict[str, Union[str, bytes]]]] = None,
    importance: str = "normal"
) -> dict:
    """
    Send an email with support for HTML content and attachments.

    Args:
        to (str): Recipient email address(es), comma-separated
        subject (str): Email subject
        body (str): Plain text email body content
        cc (str, optional): CC email address(es), comma-separated
        bcc (str, optional): BCC email address(es), comma-separated
        html_content (str, optional): HTML version of the email body
        attachments (list, optional): List of attachment objects with structure:
            [
                {
                    'filename': str,  # Name of the file
                    'content': bytes,  # File content as bytes
                    'mime_type': str,  # MIME type of the file
                }
            ]
        importance (str, optional): Email importance ('low', 'normal', 'high')

    Returns:
        dict: Status of the send operation
    """
    try:
        logging.info(f"Sending email to: {to}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Create message container
        message = MIMEMultipart('mixed' if attachments else 'alternative')
        message['to'] = to
        message['subject'] = subject

        # Add CC and BCC if provided
        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc

        # Set importance header if specified
        if importance.lower() in ['low', 'high']:
            message['Importance'] = importance.lower()
            if importance.lower() == 'high':
                message['X-Priority'] = '1'
            elif importance.lower() == 'low':
                message['X-Priority'] = '5'

        # Create the plain text part
        text_part = MIMEText(body, 'plain')
        
        if html_content:
            # Create the HTML part
            html_part = MIMEText(html_content, 'html')
            
            # Create alternative part to contain both text and HTML
            alt_part = MIMEMultipart('alternative')
            alt_part.attach(text_part)
            alt_part.attach(html_part)
            
            message.attach(alt_part)
        else:
            # If no HTML content, just attach the text part
            message.attach(text_part)

        # Add attachments if any
        if attachments:
            for attachment in attachments:
                try:
                    part = MIMEBase(*attachment['mime_type'].split('/'))
                    part.set_payload(attachment['content'])
                    
                    # Encode the payload using base64
                    encoders.encode_base64(part)
                    
                    # Set headers
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=attachment['filename']
                    )
                    
                    message.attach(part)
                except Exception as e:
                    logging.error(f"Error adding attachment {attachment['filename']}: {e}")
                    return {
                        "status": "error",
                        "message": f"Error adding attachment {attachment['filename']}: {str(e)}"
                    }

        # Encode the message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        try:
            # Send the email
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            return {
                "status": "success",
                "message": "Email sent successfully",
                "email_id": sent_message['id']
            }

        except Exception as e:
            logging.error(f"Error sending email: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to send email: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in send_email: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error sending email: {str(e)}"
        }

def delete_email(
    email_id: str,
    permanent: bool = False
) -> dict:
    """
    Delete an email. By default moves to trash, can permanently delete if specified.

    Args:
        email_id (str): The ID of the email to delete
        permanent (bool): If True, permanently deletes the email instead of moving to trash

    Returns:
        dict: Status of the delete operation
    """
    try:
        logging.info(f"Deleting email ID: {email_id} (permanent: {permanent})")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        try:
            if permanent:
                # Permanently delete the message
                service.users().messages().delete(
                    userId='me',
                    id=email_id
                ).execute()
                message = "Email permanently deleted"
            else:
                # Move the message to trash
                service.users().messages().trash(
                    userId='me',
                    id=email_id
                ).execute()
                message = "Email moved to trash"

            return {
                "status": "success",
                "message": message,
                "email_id": email_id
            }

        except Exception as e:
            logging.error(f"Error deleting email: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to delete email: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in delete_email: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error deleting email: {str(e)}"
        }

def reply_to_email(
    email_id: str,
    body: str,
    reply_all: bool = False,
) -> dict:
    """
    Reply to an email.

    Args:
        email_id (str): The ID of the email to reply to
        body (str): Reply message content
        reply_all (bool): If True, replies to all recipients (default: False)

    Returns:
        dict: Status of the reply operation
    """
    try:
        logging.info(f"Replying to email ID: {email_id} (reply_all: {reply_all})")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        try:
            # Get the original message to extract headers
            original = service.users().messages().get(
                userId='me',
                id=email_id,
                format='metadata',
                metadataHeaders=['subject', 'from', 'to', 'cc', 'message-id', 'references', 'in-reply-to']
            ).execute()

            # Extract headers
            headers = original['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            original_to = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
            original_cc = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
            message_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), '')
            references = next((h['value'] for h in headers if h['name'].lower() == 'references'), '')

            # Create message container
            message = MIMEMultipart()
            
            # Extract the email address from the From field
            from_match = re.search(r'<(.+?)>|(.+)', from_email)
            if from_match:
                reply_to = from_match.group(1) or from_match.group(2)
            else:
                reply_to = from_email

            # Set recipients
            message['to'] = reply_to

            # Handle reply-all
            if reply_all:
                # Add original CC recipients, excluding our own email
                cc_list = []
                if original_cc:
                    cc_list.extend([cc.strip() for cc in original_cc.split(',')])
                # Add original To recipients, excluding the person we're replying to
                if original_to:
                    cc_list.extend([to.strip() for to in original_to.split(',')])
                # Remove duplicates and our own email
                cc_list = list(set(cc_list))
                if reply_to in cc_list:
                    cc_list.remove(reply_to)
                if cc_list:
                    message['cc'] = ', '.join(cc_list)

            # Set subject (add Re: if not already present)
            if not subject.lower().startswith('re:'):
                subject = f"Re: {subject}"
            message['subject'] = subject

            # Set reference headers for proper threading
            if message_id:
                message['In-Reply-To'] = message_id
                new_references = f"{references} {message_id}" if references else message_id
                message['References'] = new_references

            # Create the body
            msg = MIMEText(body)
            message.attach(msg)

            # Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Send the reply
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            return {
                "status": "success",
                "message": "Reply sent successfully",
                "email_id": sent_message['id']
            }

        except Exception as e:
            logging.error(f"Error sending reply: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to send reply: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in reply_to_email: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error sending reply: {str(e)}"
        }

def search_emails(
    query_params: str = "",
    sort_by: str = "date",
    sort_order: str = "desc",
    max_results: int = 50,
) -> dict:
    """
    Search emails using various Gmail search parameters and sorting options.

    Args:
        query_params (str): JSON string containing search parameters. Supported parameters:
            - from_email (str): Sender's email address
            - to_email (str): Recipient's email address
            - subject (str): Subject line text
            - has_attachment (bool): Whether email has attachments
            - label (str): Gmail label
            - after_date (str): Date in YYYY-MM-DD format
            - before_date (str): Date in YYYY-MM-DD format
            - is_unread (bool): Whether email is unread
            - in_folder (str): Folder/category (inbox, sent, draft, spam, trash)
            - exact_phrase (str): Exact phrase to search in email content
            - exclude_words (list): List of words to exclude
        sort_by (str): Field to sort by ('date', 'subject', 'from')
        sort_order (str): Sort direction ('asc' or 'desc')
        max_results (int): Maximum number of emails to return (default: 50)

    Returns:
        dict: Search results and status
    """
    try:
        # Parse query_params from JSON string if provided
        params = json.loads(query_params) if query_params else {}
        logging.info(f"Searching emails with parameters: {params}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "emails": [],
            }

        # Build Gmail search query
        query_parts = []
        if params:
            if 'from_email' in params:
                query_parts.append(f"from:{params['from_email']}")
            if 'to_email' in params:
                query_parts.append(f"to:{params['to_email']}")
            if 'subject' in params:
                query_parts.append(f"subject:{params['subject']}")
            if 'has_attachment' in params and params['has_attachment']:
                query_parts.append("has:attachment")
            if 'label' in params:
                query_parts.append(f"label:{params['label']}")
            if 'after_date' in params:
                after_dt = parse_date(params['after_date'])
                if after_dt:
                    query_parts.append(f"after:{after_dt.strftime('%Y/%m/%d')}")
            if 'before_date' in params:
                before_dt = parse_date(params['before_date'])
                if before_dt:
                    query_parts.append(f"before:{before_dt.strftime('%Y/%m/%d')}")
            if 'is_unread' in params:
                query_parts.append("is:unread" if params['is_unread'] else "is:read")
            if 'in_folder' in params:
                query_parts.append(f"in:{params['in_folder']}")
            if 'exact_phrase' in params:
                query_parts.append(f'"{params["exact_phrase"]}"')
            if 'exclude_words' in params and params['exclude_words']:
                for word in params['exclude_words']:
                    query_parts.append(f"-{word}")

        query = " ".join(query_parts)
        logging.info(f"Gmail API Query: {query}")

        # Call the Gmail API
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        
        if not messages:
            logging.info("No messages found matching the query")
            return {
                "status": "success",
                "message": "No emails found matching the search criteria.",
                "emails": [],
            }

        # Get metadata for each email
        emails = []
        for message in messages:
            msg = service.users().messages().get(
                userId='me',
                id=message['id'],
                format='metadata',
                metadataHeaders=['subject', 'from', 'to', 'date', 'labels']
            ).execute()

            # Extract headers
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown Recipient')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')

            email_data = {
                'id': msg['id'],
                'threadId': msg['threadId'],
                'subject': subject,
                'from': from_email,
                'to': to_email,
                'date': date,
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', [])
            }
            emails.append(email_data)

        # Sort results
        if sort_by == 'date':
            emails.sort(key=lambda x: x['date'], reverse=(sort_order == 'desc'))
        elif sort_by == 'subject':
            emails.sort(key=lambda x: x['subject'].lower(), reverse=(sort_order == 'desc'))
        elif sort_by == 'from':
            emails.sort(key=lambda x: x['from'].lower(), reverse=(sort_order == 'desc'))

        return {
            "status": "success",
            "message": f"Found {len(emails)} email(s).",
            "emails": emails,
        }

    except Exception as e:
        logging.error(f"Error searching emails: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error searching emails: {str(e)}",
            "emails": [],
        }

def list_labels() -> dict:
    """
    List all available Gmail labels.

    Returns:
        dict: List of Gmail labels with their details
    """
    try:
        logging.info("Fetching Gmail labels")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "labels": [],
            }

        # Get all labels
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])

        if not labels:
            return {
                "status": "success",
                "message": "No labels found.",
                "labels": [],
            }

        # Format label information
        label_list = []
        for label in labels:
            label_info = {
                'id': label['id'],
                'name': label['name'],
                'type': label['type'],  # 'system' or 'user'
                'messageListVisibility': label.get('messageListVisibility', 'show'),
                'labelListVisibility': label.get('labelListVisibility', 'labelShow'),
                'messagesTotal': label.get('messagesTotal', 0),
                'messagesUnread': label.get('messagesUnread', 0),
                'color': label.get('color', None)
            }
            label_list.append(label_info)

        return {
            "status": "success",
            "message": f"Found {len(label_list)} labels.",
            "labels": label_list,
        }

    except Exception as e:
        logging.error(f"Error fetching labels: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error fetching labels: {str(e)}",
            "labels": [],
        }

def modify_labels(
    email_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None
) -> dict:
    """
    Add or remove labels from an email.

    Args:
        email_id (str): The ID of the email to modify
        add_labels (list, optional): List of label IDs to add
        remove_labels (list, optional): List of label IDs to remove

    Returns:
        dict: Status of the label modification operation
    """
    try:
        logging.info(f"Modifying labels for email ID: {email_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Prepare the label modification request
        body = {}
        if add_labels:
            body['addLabelIds'] = add_labels
        if remove_labels:
            body['removeLabelIds'] = remove_labels

        if not body:
            return {
                "status": "error",
                "message": "No label modifications specified.",
            }

        # Modify the labels
        result = service.users().messages().modify(
            userId='me',
            id=email_id,
            body=body
        ).execute()

        return {
            "status": "success",
            "message": "Labels modified successfully.",
            "email_id": result['id'],
            "labels": result.get('labelIds', [])
        }

    except Exception as e:
        logging.error(f"Error modifying labels: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error modifying labels: {str(e)}"
        }

def create_label(
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
    background_color: str = "",
    text_color: str = "",
) -> dict:
    """
    Create a new Gmail label.

    Args:
        name (str): Name of the label
        label_list_visibility (str): Label's visibility in the label list
        message_list_visibility (str): Label's visibility in the message list
        background_color (str, optional): Background color in hex format
        text_color (str, optional): Text color in hex format

    Returns:
        dict: Status of the label creation operation
    """
    try:
        logging.info(f"Creating new label: {name}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Prepare the label creation request
        label_data = {
            'name': name,
            'labelListVisibility': label_list_visibility,
            'messageListVisibility': message_list_visibility
        }

        # Add color information if provided
        if background_color or text_color:
            label_data['color'] = {}
            if background_color:
                label_data['color']['backgroundColor'] = background_color
            if text_color:
                label_data['color']['textColor'] = text_color

        # Create the label
        result = service.users().labels().create(
            userId='me',
            body=label_data
        ).execute()

        return {
            "status": "success",
            "message": "Label created successfully.",
            "label": {
                'id': result['id'],
                'name': result['name'],
                'type': result['type'],
                'messageListVisibility': result.get('messageListVisibility', 'show'),
                'labelListVisibility': result.get('labelListVisibility', 'labelShow'),
                'color': result.get('color', None)
            }
        }

    except Exception as e:
        logging.error(f"Error creating label: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error creating label: {str(e)}"
        }

def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    html_content: str = "",
    attachments: Optional[List[Dict[str, Union[str, bytes]]]] = None,
) -> dict:
    """
    Create an email draft.

    Args:
        to (str): Recipient email address(es), comma-separated
        subject (str): Email subject
        body (str): Plain text email body content
        cc (str, optional): CC email address(es), comma-separated
        bcc (str, optional): BCC email address(es), comma-separated
        html_content (str, optional): HTML version of the email body
        attachments (list, optional): List of attachment objects with structure:
            [
                {
                    'filename': str,  # Name of the file
                    'content': bytes,  # File content as bytes
                    'mime_type': str,  # MIME type of the file
                }
            ]

    Returns:
        dict: Status of the draft creation operation
    """
    try:
        logging.info(f"Creating draft email to: {to}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Create message container
        message = MIMEMultipart('mixed' if attachments else 'alternative')
        message['to'] = to
        message['subject'] = subject

        # Add CC and BCC if provided
        if cc:
            message['cc'] = cc
        if bcc:
            message['bcc'] = bcc

        # Create the plain text part
        text_part = MIMEText(body, 'plain')
        
        if html_content:
            # Create the HTML part
            html_part = MIMEText(html_content, 'html')
            
            # Create alternative part to contain both text and HTML
            alt_part = MIMEMultipart('alternative')
            alt_part.attach(text_part)
            alt_part.attach(html_part)
            
            message.attach(alt_part)
        else:
            # If no HTML content, just attach the text part
            message.attach(text_part)

        # Add attachments if any
        if attachments:
            for attachment in attachments:
                try:
                    part = MIMEBase(*attachment['mime_type'].split('/'))
                    part.set_payload(attachment['content'])
                    
                    # Encode the payload using base64
                    encoders.encode_base64(part)
                    
                    # Set headers
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=attachment['filename']
                    )
                    
                    message.attach(part)
                except Exception as e:
                    logging.error(f"Error adding attachment {attachment['filename']}: {e}")
                    return {
                        "status": "error",
                        "message": f"Error adding attachment {attachment['filename']}: {str(e)}"
                    }

        # Encode the message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        try:
            # Create the draft
            draft = service.users().drafts().create(
                userId='me',
                body={
                    'message': {
                        'raw': raw_message
                    }
                }
            ).execute()

            return {
                "status": "success",
                "message": "Draft created successfully",
                "draft_id": draft['id']
            }

        except Exception as e:
            logging.error(f"Error creating draft: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to create draft: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in create_draft: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error creating draft: {str(e)}"
        }

def list_drafts(max_results: int = 50) -> dict:
    """
    List email drafts.

    Args:
        max_results (int): Maximum number of drafts to return (default: 50)

    Returns:
        dict: List of draft emails
    """
    try:
        logging.info("Fetching email drafts")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "drafts": [],
            }

        # List drafts
        results = service.users().drafts().list(
            userId='me',
            maxResults=max_results
        ).execute()

        drafts = results.get('drafts', [])
        
        if not drafts:
            return {
                "status": "success",
                "message": "No drafts found.",
                "drafts": [],
            }

        # Get detailed information for each draft
        draft_list = []
        for draft in drafts:
            draft_data = service.users().drafts().get(
                userId='me',
                id=draft['id'],
                format='metadata'
            ).execute()

            message = draft_data['message']
            headers = message['payload']['headers']
            
            # Extract headers
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            to = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')

            draft_info = {
                'id': draft['id'],
                'message_id': message['id'],
                'thread_id': message['threadId'],
                'subject': subject,
                'to': to,
                'from': from_email,
                'snippet': message.get('snippet', '')
            }
            draft_list.append(draft_info)

        return {
            "status": "success",
            "message": f"Found {len(draft_list)} draft(s).",
            "drafts": draft_list,
        }

    except Exception as e:
        logging.error(f"Error fetching drafts: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error fetching drafts: {str(e)}",
            "drafts": [],
        }

def update_draft(
    draft_id: str,
    to: str = "",
    subject: str = "",
    body: str = "",
    cc: str = "",
    bcc: str = "",
    html_content: str = "",
    attachments: Optional[List[Dict[str, Union[str, bytes]]]] = None,
) -> dict:
    """
    Update an existing draft.

    Args:
        draft_id (str): ID of the draft to update
        to (str, optional): New recipient email address(es)
        subject (str, optional): New subject
        body (str, optional): New plain text body
        cc (str, optional): New CC recipients
        bcc (str, optional): New BCC recipients
        html_content (str, optional): New HTML content
        attachments (list, optional): New attachments list

    Returns:
        dict: Status of the draft update operation
    """
    try:
        logging.info(f"Updating draft ID: {draft_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Get the existing draft
        try:
            existing_draft = service.users().drafts().get(
                userId='me',
                id=draft_id,
                format='full'
            ).execute()
        except Exception as e:
            return {
                "status": "error",
                "message": f"Draft not found: {str(e)}"
            }

        # Extract existing message details
        existing_message = existing_draft['message']
        headers = existing_message['payload']['headers']
        
        # Create new message with existing or updated content
        message = MIMEMultipart('mixed' if attachments else 'alternative')
        
        # Update or keep existing headers
        message['to'] = to or next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
        message['subject'] = subject or next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        
        if cc is not None:
            message['cc'] = cc
        elif next((h['value'] for h in headers if h['name'].lower() == 'cc'), None):
            message['cc'] = next(h['value'] for h in headers if h['name'].lower() == 'cc')
            
        if bcc is not None:
            message['bcc'] = bcc
        elif next((h['value'] for h in headers if h['name'].lower() == 'bcc'), None):
            message['bcc'] = next(h['value'] for h in headers if h['name'].lower() == 'bcc')

        # Get existing body content if not provided
        if body is None or html_content is None:
            existing_content = get_email_body(service, 'me', existing_message)
            body = body or existing_content['text']
            html_content = html_content or existing_content['html']

        # Create message parts
        text_part = MIMEText(body, 'plain')
        
        if html_content:
            html_part = MIMEText(html_content, 'html')
            alt_part = MIMEMultipart('alternative')
            alt_part.attach(text_part)
            alt_part.attach(html_part)
            message.attach(alt_part)
        else:
            message.attach(text_part)

        # Handle attachments
        if attachments:
            for attachment in attachments:
                try:
                    part = MIMEBase(*attachment['mime_type'].split('/'))
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=attachment['filename']
                    )
                    message.attach(part)
                except Exception as e:
                    logging.error(f"Error adding attachment {attachment['filename']}: {e}")
                    return {
                        "status": "error",
                        "message": f"Error adding attachment {attachment['filename']}: {str(e)}"
                    }

        # Encode the updated message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        try:
            # Update the draft
            updated_draft = service.users().drafts().update(
                userId='me',
                id=draft_id,
                body={
                    'message': {
                        'raw': raw_message
                    }
                }
            ).execute()

            return {
                "status": "success",
                "message": "Draft updated successfully",
                "draft_id": updated_draft['id']
            }

        except Exception as e:
            logging.error(f"Error updating draft: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to update draft: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in update_draft: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error updating draft: {str(e)}"
        }

def delete_draft(draft_id: str) -> dict:
    """
    Delete a draft email.

    Args:
        draft_id (str): ID of the draft to delete

    Returns:
        dict: Status of the delete operation
    """
    try:
        logging.info(f"Deleting draft ID: {draft_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        try:
            # Delete the draft
            service.users().drafts().delete(
                userId='me',
                id=draft_id
            ).execute()

            return {
                "status": "success",
                "message": "Draft deleted successfully",
                "draft_id": draft_id
            }

        except Exception as e:
            logging.error(f"Error deleting draft: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to delete draft: {str(e)}"
            }

    except Exception as e:
        logging.error(f"Error in delete_draft: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error deleting draft: {str(e)}"
        }

def list_threads(
    query_params: Optional[Dict[str, Union[str, bool]]] = None,
    max_results: int = 50
) -> dict:
    """
    List email threads with optional filtering.

    Args:
        query_params (dict): Dictionary of search parameters (same as search_emails)
        max_results (int): Maximum number of threads to return (default: 50)

    Returns:
        dict: List of email threads
    """
    try:
        logging.info(f"Listing threads with parameters: {query_params}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "threads": [],
            }

        # Build Gmail search query
        query_parts = []
        if query_params:
            if 'from_email' in query_params:
                query_parts.append(f"from:{query_params['from_email']}")
            if 'to_email' in query_params:
                query_parts.append(f"to:{query_params['to_email']}")
            if 'subject' in query_params:
                query_parts.append(f"subject:{query_params['subject']}")
            if 'has_attachment' in query_params and query_params['has_attachment']:
                query_parts.append("has:attachment")
            if 'label' in query_params:
                query_parts.append(f"label:{query_params['label']}")
            if 'after_date' in query_params:
                after_dt = parse_date(query_params['after_date'])
                if after_dt:
                    query_parts.append(f"after:{after_dt.strftime('%Y/%m/%d')}")
            if 'before_date' in query_params:
                before_dt = parse_date(query_params['before_date'])
                if before_dt:
                    query_parts.append(f"before:{before_dt.strftime('%Y/%m/%d')}")
            if 'is_unread' in query_params:
                query_parts.append("is:unread" if query_params['is_unread'] else "is:read")
            if 'in_folder' in query_params:
                query_parts.append(f"in:{query_params['in_folder']}")

        query = " ".join(query_parts)
        logging.info(f"Gmail API Query: {query}")

        # List threads
        results = service.users().threads().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        threads = results.get('threads', [])
        
        if not threads:
            return {
                "status": "success",
                "message": "No threads found.",
                "threads": [],
            }

        # Get summary information for each thread
        thread_list = []
        for thread in threads:
            thread_data = service.users().threads().get(
                userId='me',
                id=thread['id'],
                format='metadata'
            ).execute()

            # Get the most recent message in the thread
            latest_message = thread_data['messages'][-1]
            headers = latest_message['payload']['headers']
            
            # Extract headers
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

            thread_info = {
                'id': thread['id'],
                'subject': subject,
                'latest_from': from_email,
                'latest_date': date,
                'message_count': len(thread_data['messages']),
                'snippet': latest_message.get('snippet', ''),
                'unread': 'UNREAD' in latest_message.get('labelIds', [])
            }
            thread_list.append(thread_info)

        return {
            "status": "success",
            "message": f"Found {len(thread_list)} thread(s).",
            "threads": thread_list,
        }

    except Exception as e:
        logging.error(f"Error listing threads: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error listing threads: {str(e)}",
            "threads": [],
        }

def get_thread_content(thread_id: str) -> dict:
    """
    Get all emails in a thread.

    Args:
        thread_id (str): ID of the thread to fetch

    Returns:
        dict: Full thread content with all messages
    """
    try:
        logging.info(f"Fetching thread content for ID: {thread_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "thread": None,
            }

        # Get the full thread content
        thread = service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()

        # Process all messages in the thread
        messages = []
        for msg in thread['messages']:
            # Extract headers
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
            cc = next((h['value'] for h in headers if h['name'].lower() == 'cc'), '')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

            # Get message body with all content types
            body_content = get_email_body(service, 'me', msg)
            
            message_data = {
                'id': msg['id'],
                'subject': subject,
                'from': from_email,
                'to': to_email,
                'cc': cc,
                'date': date,
                'snippet': msg.get('snippet', ''),
                'body': {
                    'text': body_content['text'],
                    'html': body_content['html']
                },
                'labels': msg.get('labelIds', []),
                'attachments': body_content['attachments']
            }
            messages.append(message_data)

        thread_data = {
            'id': thread['id'],
            'message_count': len(messages),
            'messages': messages,
            'snippet': thread.get('snippet', '')
        }

        return {
            "status": "success",
            "message": f"Thread retrieved successfully with {len(messages)} message(s).",
            "thread": thread_data,
        }

    except Exception as e:
        logging.error(f"Error fetching thread content: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error fetching thread content: {str(e)}",
            "thread": None,
        }

def modify_thread(
    thread_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None
) -> dict:
    """
    Modify labels for all messages in a thread.

    Args:
        thread_id (str): ID of the thread to modify
        add_labels (list, optional): List of label IDs to add
        remove_labels (list, optional): List of label IDs to remove

    Returns:
        dict: Status of the thread modification operation
    """
    try:
        logging.info(f"Modifying thread ID: {thread_id}")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        # Prepare the modification request
        body = {}
        if add_labels:
            body['addLabelIds'] = add_labels
        if remove_labels:
            body['removeLabelIds'] = remove_labels

        if not body:
            return {
                "status": "error",
                "message": "No modifications specified.",
            }

        # Modify the thread
        result = service.users().threads().modify(
            userId='me',
            id=thread_id,
            body=body
        ).execute()

        return {
            "status": "success",
            "message": "Thread modified successfully.",
            "thread_id": result['id']
        }

    except Exception as e:
        logging.error(f"Error modifying thread: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error modifying thread: {str(e)}"
        }

def batch_modify_emails(
    email_ids: List[str],
    operation: str,
    params: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Perform batch operations on multiple emails.

    Args:
        email_ids (list): List of email IDs to operate on
        operation (str): Operation to perform ('delete', 'trash', 'modify_labels', 'mark_read', 'mark_unread')
        params (dict, optional): Additional parameters for the operation:
            - For 'modify_labels': {'add_labels': [...], 'remove_labels': [...]}

    Returns:
        dict: Status of the batch operation
    """
    try:
        logging.info(f"Performing batch {operation} on {len(email_ids)} emails")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
            }

        results = {
            'successful': [],
            'failed': []
        }

        if operation == 'delete':
            # Permanently delete messages
            for email_id in email_ids:
                try:
                    service.users().messages().delete(
                        userId='me',
                        id=email_id
                    ).execute()
                    results['successful'].append(email_id)
                except Exception as e:
                    logging.error(f"Error deleting email {email_id}: {e}")
                    results['failed'].append({
                        'id': email_id,
                        'error': str(e)
                    })

        elif operation == 'trash':
            # Move messages to trash
            for email_id in email_ids:
                try:
                    service.users().messages().trash(
                        userId='me',
                        id=email_id
                    ).execute()
                    results['successful'].append(email_id)
                except Exception as e:
                    logging.error(f"Error moving email {email_id} to trash: {e}")
                    results['failed'].append({
                        'id': email_id,
                        'error': str(e)
                    })

        elif operation == 'modify_labels':
            if not params or ('add_labels' not in params and 'remove_labels' not in params):
                return {
                    "status": "error",
                    "message": "Label modification requires 'add_labels' and/or 'remove_labels' parameters.",
                }

            # Prepare the modification request
            body = {}
            if 'add_labels' in params:
                body['addLabelIds'] = params['add_labels']
            if 'remove_labels' in params:
                body['removeLabelIds'] = params['remove_labels']

            # Modify labels for each message
            for email_id in email_ids:
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=email_id,
                        body=body
                    ).execute()
                    results['successful'].append(email_id)
                except Exception as e:
                    logging.error(f"Error modifying labels for email {email_id}: {e}")
                    results['failed'].append({
                        'id': email_id,
                        'error': str(e)
                    })

        elif operation in ['mark_read', 'mark_unread']:
            # Prepare label modifications
            body = {
                'removeLabelIds' if operation == 'mark_read' else 'addLabelIds': ['UNREAD']
            }

            # Modify read status for each message
            for email_id in email_ids:
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=email_id,
                        body=body
                    ).execute()
                    results['successful'].append(email_id)
                except Exception as e:
                    logging.error(f"Error marking email {email_id} as {operation}: {e}")
                    results['failed'].append({
                        'id': email_id,
                        'error': str(e)
                    })

        else:
            return {
                "status": "error",
                "message": f"Unsupported operation: {operation}",
            }

        return {
            "status": "success",
            "message": f"Batch {operation} completed. {len(results['successful'])} successful, {len(results['failed'])} failed.",
            "results": results
        }

    except Exception as e:
        logging.error(f"Error in batch operation: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error in batch operation: {str(e)}"
        }

def batch_get_emails(
    email_ids: List[str],
    format: str = 'metadata',
    metadata_headers: Optional[List[str]] = None
) -> dict:
    """
    Get multiple emails in a single batch request.

    Args:
        email_ids (list): List of email IDs to fetch
        format (str): Format to return ('minimal', 'metadata', 'full')
        metadata_headers (list, optional): List of header names to include when format is 'metadata'

    Returns:
        dict: Batch of email data
    """
    try:
        logging.info(f"Fetching {len(email_ids)} emails in batch")
        
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            return {
                "status": "error",
                "message": "Failed to authenticate with Gmail. Please check credentials.",
                "emails": [],
            }

        if not metadata_headers and format == 'metadata':
            metadata_headers = ['subject', 'from', 'to', 'date']

        # Fetch emails
        emails = []
        failed = []
        
        for email_id in email_ids:
            try:
                msg = service.users().messages().get(
                    userId='me',
                    id=email_id,
                    format=format,
                    metadataHeaders=metadata_headers if format == 'metadata' else None
                ).execute()

                # Extract headers
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                to_email = next((h['value'] for h in headers if h['name'].lower() == 'to'), '')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

                email_data = {
                    'id': msg['id'],
                    'threadId': msg['threadId'],
                    'subject': subject,
                    'from': from_email,
                    'to': to_email,
                    'date': date,
                    'snippet': msg.get('snippet', ''),
                    'labels': msg.get('labelIds', [])
                }

                # Add body content for full format
                if format == 'full':
                    body_content = get_email_body(service, 'me', msg)
                    email_data['body'] = {
                        'text': body_content['text'],
                        'html': body_content['html']
                    }
                    email_data['attachments'] = body_content['attachments']

                emails.append(email_data)

            except Exception as e:
                logging.error(f"Error fetching email {email_id}: {e}")
                failed.append({
                    'id': email_id,
                    'error': str(e)
                })

        return {
            "status": "success",
            "message": f"Batch fetch completed. {len(emails)} successful, {len(failed)} failed.",
            "emails": emails,
            "failed": failed
        }

    except Exception as e:
        logging.error(f"Error in batch get: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error in batch get: {str(e)}",
            "emails": [],
            "failed": []
        }

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for Gmail...")
app = Server("gmail-mcp-server")

# Wrap Gmail utility functions as ADK FunctionTools
ADK_GMAIL_TOOLS = {
    "list_emails": FunctionTool(func=list_emails),
    "search_emails": FunctionTool(func=search_emails),
    "get_email_content": FunctionTool(func=get_email_content),
    "send_email": FunctionTool(func=send_email),
    "delete_email": FunctionTool(func=delete_email),
    "reply_to_email": FunctionTool(func=reply_to_email),
    # "list_labels": FunctionTool(func=list_labels),
    # "modify_labels": FunctionTool(func=modify_labels),
    # "create_label": FunctionTool(func=create_label),
    "create_draft": FunctionTool(func=create_draft),
    "list_drafts": FunctionTool(func=list_drafts),
    "update_draft": FunctionTool(func=update_draft),
    "delete_draft": FunctionTool(func=delete_draft),
    # "list_threads": FunctionTool(func=list_threads),
    # "get_thread_content": FunctionTool(func=get_thread_content),
    # "modify_thread": FunctionTool(func=modify_thread),
    # "batch_modify_emails": FunctionTool(func=batch_modify_emails),
    # "batch_get_emails": FunctionTool(func=batch_get_emails),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_GMAIL_TOOLS.items():
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

    if name in ADK_GMAIL_TOOLS:
        adk_tool_instance = ADK_GMAIL_TOOLS[name]
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
    logging.info("Launching Gmail MCP Server via stdio...")
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