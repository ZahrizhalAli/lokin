"""development runner.

This development runner executes bots and provides the supporting
infrastructure they need - creating Daily rooms and tokens, managing WebRTC
connections, and setting up telephony webhook/WebSocket infrastructure. It
supports multiple transport types with a unified interface.

Install with::

    pip install lokin[runner]

All bots must implement a `bot(runner_args)` async function as the entry point.
The server automatically discovers and executes this function when connections
are established.

Single transport example::

    async def bot(runner_args: RunnerArguments):
        transport = DailyTransport(
            runner_args.room_url,
            runner_args.token,
            "Bot",
            DailyParams(...)
        )
        # Your bot logic here
        await run_pipeline(transport)

    if __name__ == "__main__":
        from pipecat.runner.run import main
        main()

Multiple transport example::

    async def bot(runner_args: RunnerArguments):
        # Type-safe transport detection
        if isinstance(runner_args, DailyRunnerArguments):
            transport = setup_daily_transport(runner_args)  # Your application code
        elif isinstance(runner_args, SmallWebRTCRunnerArguments):
            transport = setup_webrtc_transport(runner_args)  # Your application code
        elif isinstance(runner_args, WebSocketRunnerArguments):
            transport = setup_telephony_transport(runner_args)  # Your application code

        # Your bot implementation
        await run_pipeline(transport)

Supported transports:

- WebRTC - Provides local WebRTC interface with prebuilt UI
- Telephony - Handles webhook and WebSocket connections for Twilio, Telnyx, Plivo, Exotel

To run locally:

- WebRTC: `python bot.py -t webrtc`
- ESP32: `python bot.py -t webrtc --esp32 --host 192.168.1.100`
"""

import argparse
import asyncio
import mimetypes
import os
import sys
import uuid
from contextlib import asynccontextmanager
from http import HTTPMethod
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict, Union

import aiohttp
from fastapi.responses import FileResponse, Response
from loguru import logger

from lokin.runner.types import (
    DailyRunnerArguments,
    RunnerArguments,
    SmallWebRTCRunnerArguments,
    WebSocketRunnerArguments,
)

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse


from dotenv import load_dotenv

load_dotenv(override=True)
os.environ["ENV"] = "local"

TELEPHONY_TRANSPORTS = ["twilio", "telnyx", "plivo", "exotel"]

RUNNER_DOWNLOADS_FOLDER: Optional[str] = None
RUNNER_HOST: str = "localhost"
RUNNER_PORT: int = 7860


def _get_bot_module():
    """Get the bot module from the calling script."""
    import importlib.util

    # Get the main module (the file that was executed)
    main_module = sys.modules["__main__"]

    # Check if it has a bot function
    if hasattr(main_module, "bot"):
        return main_module

    # Try to import 'bot' module from current directory
    try:
        import bot  # type: ignore[import-untyped]

        return bot
    except ImportError:
        pass

    # Look for any .py file in current directory that has a bot function
    # (excluding server.py).
    cwd = os.getcwd()
    for filename in os.listdir(cwd):
        if filename.endswith(".py") and filename != "server.py":
            try:
                module_name = filename[:-3]  # Remove .py extension
                spec = importlib.util.spec_from_file_location(
                    module_name, os.path.join(cwd, filename)
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, "bot"):
                    return module
            except Exception:
                continue

    raise ImportError(
        "Could not find 'bot' function. Make sure your bot file has a 'bot' function."
    )

def _create_server_app(args: argparse.Namespace):
    """Create FastAPI app with transport-specific routes."""
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Set up transport-specific routes
    if args.transport == "webrtc":
        _setup_webrtc_routes(app, args)
    else:
        logger.warning(f"Unknown transport type: {args.transport}")

    return app


def _setup_webrtc_routes(app: FastAPI, args: argparse.Namespace):
    """Set up WebRTC-specific routes."""
    try:
        from webui.client import SmallWebRTCPrebuiltUI

        from lokin.transports.smallwebrtc.connection import SmallWebRTCConnection
        from lokin.transports.smallwebrtc.request_handler import (
            IceCandidate,
            SmallWebRTCPatchRequest,
            SmallWebRTCRequest,
            SmallWebRTCRequestHandler,
        )
    except ImportError as e:
        logger.error(f"WebRTC transport dependencies not installed: {e}")
        return

    class IceServer(TypedDict, total=False):
        urls: Union[str, List[str]]

    class IceConfig(TypedDict):
        iceServers: List[IceServer]

    class StartBotResult(TypedDict, total=False):
        sessionId: str
        iceConfig: Optional[IceConfig]

    # In-memory store of active sessions: session_id -> session info
    active_sessions: Dict[str, Dict[str, Any]] = {}

    # Mount the frontend
    app.mount("/client", SmallWebRTCPrebuiltUI)

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        """Redirect root requests to client interface."""
        return RedirectResponse(url="/client/")

    @app.get("/files/{filename:path}")
    async def download_file(filename: str):
        """Handle file downloads."""
        if not args.folder:
            logger.warning(f"Attempting to dowload {filename}, but downloads folder not setup.")
            return

        file_path = Path(args.folder) / filename
        if not os.path.exists(file_path):
            raise HTTPException(404)

        media_type, _ = mimetypes.guess_type(file_path)

        return FileResponse(path=file_path, media_type=media_type, filename=filename)

    # Initialize the SmallWebRTC request handler
    small_webrtc_handler: SmallWebRTCRequestHandler = SmallWebRTCRequestHandler(
        esp32_mode=args.esp32, host=args.host
    )

    @app.post("/api/offer")
    async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
        """Handle WebRTC offer requests via SmallWebRTCRequestHandler."""

        # Prepare runner arguments with the callback to run your bot
        async def webrtc_connection_callback(connection: SmallWebRTCConnection):
            bot_module = _get_bot_module()

            runner_args = SmallWebRTCRunnerArguments(
                webrtc_connection=connection, body=request.request_data
            )
            runner_args.cli_args = args
            background_tasks.add_task(bot_module.bot, runner_args)

        # Delegate handling to SmallWebRTCRequestHandler
        answer = await small_webrtc_handler.handle_web_request(
            request=request,
            webrtc_connection_callback=webrtc_connection_callback,
        )
        return answer

    @app.patch("/api/offer")
    async def ice_candidate(request: SmallWebRTCPatchRequest):
        """Handle WebRTC new ice candidate requests."""
        logger.debug(f"Received patch request: {request}")
        await small_webrtc_handler.handle_patch_request(request)
        return {"status": "success"}

    @app.post("/start")
    async def rtvi_start(request: Request):
        """Mimic Pipecat Cloud's /start endpoint."""
        # Parse the request body
        try:
            request_data = await request.json()
            logger.debug(f"Received request: {request_data}")
        except Exception as e:
            logger.error(f"Failed to parse request body: {e}")
            request_data = {}

        # Store session info immediately in memory, replicate the behavior expected on Pipecat Cloud
        session_id = str(uuid.uuid4())
        active_sessions[session_id] = request_data.get("body", {})

        result: StartBotResult = {"sessionId": session_id}
        if request_data.get("enableDefaultIceServers"):
            result["iceConfig"] = IceConfig(
                iceServers=[IceServer(urls=["stun:stun.l.google.com:19302"])]
            )

        return result

    @app.api_route(
        "/sessions/{session_id}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def proxy_request(
        session_id: str, path: str, request: Request, background_tasks: BackgroundTasks
    ):
        """Mimic Pipecat Cloud's proxy."""
        active_session = active_sessions.get(session_id)
        if active_session is None:
            return Response(content="Invalid or not-yet-ready session_id", status_code=404)

        if path.endswith("api/offer"):
            # Parse the request body and convert to SmallWebRTCRequest
            try:
                request_data = await request.json()
                if request.method == HTTPMethod.POST.value:
                    webrtc_request = SmallWebRTCRequest(
                        sdp=request_data["sdp"],
                        type=request_data["type"],
                        pc_id=request_data.get("pc_id"),
                        restart_pc=request_data.get("restart_pc"),
                        request_data=request_data.get("request_data")
                        or request_data.get("requestData")
                        or active_session,
                    )
                    return await offer(webrtc_request, background_tasks)
                elif request.method == HTTPMethod.PATCH.value:
                    patch_request = SmallWebRTCPatchRequest(
                        pc_id=request_data["pc_id"],
                        candidates=[IceCandidate(**c) for c in request_data.get("candidates", [])],
                    )
                    return await ice_candidate(patch_request)
            except Exception as e:
                logger.error(f"Failed to parse WebRTC request: {e}")
                return Response(content="Invalid WebRTC request", status_code=400)

        logger.info(f"Received request for path: {path}")
        return Response(status_code=200)

    @asynccontextmanager
    async def smallwebrtc_lifespan(app: FastAPI):
        """Manage FastAPI application lifecycle and cleanup connections."""
        yield
        await small_webrtc_handler.close()

    # Add the SmallWebRTC lifespan to the app
    _add_lifespan_to_app(app, smallwebrtc_lifespan)


def _add_lifespan_to_app(app: FastAPI, new_lifespan):
    """Add a new lifespan context manager to the app, combining with existing if present.

    Args:
        app: The FastAPI application instance
        new_lifespan: The new lifespan context manager to add
    """
    if hasattr(app.router, "lifespan_context") and app.router.lifespan_context is not None:
        # If there's already a lifespan context, combine them
        existing_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def combined_lifespan(app: FastAPI):
            async with existing_lifespan(app):
                async with new_lifespan(app):
                    yield

        app.router.lifespan_context = combined_lifespan
    else:
        # No existing lifespan, use the new one
        app.router.lifespan_context = new_lifespan

def _validate_and_clean_proxy(proxy: str) -> str:
    """Validate and clean proxy hostname, removing protocol if present."""
    if not proxy:
        return proxy

    original_proxy = proxy

    # Strip common protocols
    if proxy.startswith(("http://", "https://")):
        proxy = proxy.split("://", 1)[1]
        logger.warning(
            f"Removed protocol from proxy URL. Using '{proxy}' instead of '{original_proxy}'. "
            f"The --proxy argument expects only the hostname (e.g., 'mybot.ngrok.io')."
        )

    # Remove trailing slashes
    proxy = proxy.rstrip("/")

    return proxy


def runner_downloads_folder() -> Optional[str]:
    """Returns the folder where files are stored for later download."""
    return RUNNER_DOWNLOADS_FOLDER


def runner_host() -> str:
    """Returns the host name of this runner."""
    return RUNNER_HOST


def runner_port() -> int:
    """Returns the port of this runner."""
    return RUNNER_PORT


def main(parser: Optional[argparse.ArgumentParser] = None):
    """Start the Pipecat development runner.

    Parses command-line arguments and starts a FastAPI server configured
    for the specified transport type.

    The runner discovers and runs any ``bot(runner_args)`` function found in the
    calling module.

    Command-line arguments:
       - --host: Server host address (default: localhost) 879
       - --port: Server port (default: 7860)
       - -t/--transport: Transport type (daily, webrtc, twilio, telnyx, plivo, exotel)
       - -x/--proxy: Public proxy hostname for telephony webhooks
       - -d/--direct: Connect directly to Daily room (automatically sets transport to daily)
       - -f/--folder: Path to downloads folder
       - --dialin: Enable Daily PSTN dial-in webhook handling (requires Daily transport)
       - --esp32: Enable SDP munging for ESP32 compatibility (requires --host with IP address)
       - --whatsapp: Ensure requried WhatsApp environment variables are present
       - -v/--verbose: Increase logging verbosity

    Args:
        parser: Optional custom argument parser. If provided, default runner
            arguments are added to it so bots can define their own CLI
            arguments. Custom arguments should not conflict with the default
            ones. Custom args are accessible via `runner_args.cli_args`.

    """
    global RUNNER_DOWNLOADS_FOLDER, RUNNER_HOST, RUNNER_PORT

    if not parser:
        parser = argparse.ArgumentParser(description="Pipecat Development Runner")
    parser.add_argument("--host", type=str, default=RUNNER_HOST, help="Host address")
    parser.add_argument("--port", type=int, default=RUNNER_PORT, help="Port number")
    parser.add_argument(
        "-t",
        "--transport",
        type=str,
        choices=["daily", "webrtc", *TELEPHONY_TRANSPORTS],
        default="webrtc",
        help="Transport type",
    )
    parser.add_argument("-x", "--proxy", help="Public proxy host name")

    parser.add_argument("-f", "--folder", type=str, help="Path to downloads folder")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase logging verbosity"
    )
    parser.add_argument(
        "--dialin",
        action="store_true",
        default=False,
        help="Enable Daily PSTN dial-in webhook handling (requires Daily transport)",
    )
    parser.add_argument(
        "--esp32",
        action="store_true",
        default=False,
        help="Enable SDP munging for ESP32 compatibility (requires --host with IP address)",
    )


    args = parser.parse_args()

    # Validate and clean proxy hostname
    if args.proxy:
        args.proxy = _validate_and_clean_proxy(args.proxy)

    # Auto-set transport to daily if --direct is used without explicit transport
    if args.transport == "webrtc":  # webrtc is the default
        args.transport = "webrtc"
    elif args.transport != "daily":
        logger.error("--direct flag only works with Daily transport (-t daily)")
        return

    # Validate ESP32 requirements
    if args.esp32 and args.host == "localhost":
        logger.error("For ESP32, you need to specify `--host IP` so we can do SDP munging.")
        return

    # Validate dial-in requirements
    if args.dialin and args.transport != "daily":
        logger.error("--dialin flag only works with Daily transport (-t daily)")
        return

    # Log level
    logger.remove()
    logger.add(sys.stderr, level="TRACE" if args.verbose else "DEBUG")

    # Handle direct Daily connection (no FastAPI server)

    # Print startup message for server-based transports
    if args.transport == "webrtc":
        print()
        if args.esp32:
            print(f"🚀 Bot ready! (ESP32 mode)")
        else:
            print(f"🚀 Bot ready!")
        print(f"   → Open http://{args.host}:{args.port}/client in your browser")
        print()


    RUNNER_DOWNLOADS_FOLDER = args.folder
    RUNNER_HOST = args.host
    RUNNER_PORT = args.port

    # Create the app with transport-specific setup
    app = _create_server_app(args)

    # Run the server
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
