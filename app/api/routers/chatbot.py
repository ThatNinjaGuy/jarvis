from fastapi import APIRouter, WebSocket, Query
from starlette.websockets import WebSocketDisconnect
import logging
import asyncio
from app.config.agent_session import start_agent_session, end_agent_session
from app.communication_handlers import (
    handle_agent_to_client_messaging,
    handle_client_to_agent_messaging,
)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Enhanced client websocket endpoint with memory capabilities"""
    try:
        # Wait for client connection
        await websocket.accept()
        logging.info(f"Client #{session_id} connected, audio mode: {is_audio}")

        # Start agent session (will use enhanced session if memory is available)
        session_data = await start_agent_session(
            session_id,
            is_audio == "true",
            use_memory=True,  # Try to use memory if available
        )

        # Create communication handlers with session data for memory tracking
        agent_to_client_task = asyncio.create_task(
            handle_agent_to_client_messaging(
                websocket,
                session_data["live_events"],
                session_data,  # Pass session data for memory tracking
            )
        )
        client_to_agent_task = asyncio.create_task(
            handle_client_to_agent_messaging(
                websocket,
                session_data["live_request_queue"],
                session_data,  # Pass session data for memory tracking
            )
        )

        try:
            await asyncio.gather(agent_to_client_task, client_to_agent_task)
        except WebSocketDisconnect:
            logging.info(f"Client #{session_id} disconnected normally")
        except Exception as e:
            logging.error(
                f"Error in WebSocket connection for client #{session_id}: {str(e)}",
                exc_info=True,
            )
        finally:
            # Clean up tasks
            agent_to_client_task.cancel()
            client_to_agent_task.cancel()
            try:
                await agent_to_client_task
                await client_to_agent_task
            except asyncio.CancelledError:
                pass

            # End session (will capture memory if available)
            await end_agent_session(session_id)

    except Exception as e:
        logging.error(
            f"Error setting up WebSocket for client #{session_id}: {str(e)}",
            exc_info=True,
        )
        raise
