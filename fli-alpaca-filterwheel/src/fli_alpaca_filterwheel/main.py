"""FastAPI application and entry point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fli_alpaca_filterwheel import __version__
from fli_alpaca_filterwheel.api import common, filterwheel, management
from fli_alpaca_filterwheel.config import Config
from fli_alpaca_filterwheel.device import DeviceError, FLIFilterWheelDevice, TransactionCounter
from fli_alpaca_filterwheel.models import AlpacaResponse


def create_app(config: Config | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = Config.from_env()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    device = FLIFilterWheelDevice(config)
    counter = TransactionCounter()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Optionally connect to the hardware on startup.
        if config.auto_connect:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, device.connect)
                logger.info("Auto-connected to FLI filter wheel")
            except (DeviceError, ImportError, OSError) as exc:
                logger.warning("Auto-connect failed: %s", exc)

        yield

        # Disconnect cleanly on shutdown.
        if device.connected:
            try:
                device.disconnect()
            except Exception as exc:
                logger.warning("Error during shutdown disconnect: %s", exc)

    app = FastAPI(
        lifespan=lifespan,
        title="FLI FilterWheel Alpaca Driver",
        description=(
            "ASCOM Alpaca-compliant driver for Finger Lakes Instrumentation (FLI) "
            "filter wheels.  Implements IFilterWheelV3."
        ),
        version=__version__,
    )

    # Attach shared state.
    app.state.config = config
    app.state.device = device
    app.state.counter = counter

    # CORS — allow any origin so that the ASCOM Remote and browser tools work.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Exception handlers
    # ---------------------------------------------------------------------------

    @app.exception_handler(DeviceError)
    async def device_error_handler(request: Request, exc: DeviceError) -> JSONResponse:
        client_txn = 0
        if "ClientTransactionID" in request.query_params:
            try:
                client_txn = int(request.query_params["ClientTransactionID"])
            except (ValueError, TypeError):
                pass
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=exc.code,
                ErrorMessage=exc.message,
                ClientTransactionID=client_txn,
                ServerTransactionID=counter.next(),
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # Alpaca spec: 400 for invalid device number.
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content=AlpacaResponse(
                ErrorNumber=0x500,
                ErrorMessage=f"Internal server error: {exc}",
                ServerTransactionID=counter.next(),
            ).model_dump(),
        )

    # ---------------------------------------------------------------------------
    # Routers
    # ---------------------------------------------------------------------------

    app.include_router(management.router)
    app.include_router(common.router, prefix="/api/v1")
    app.include_router(filterwheel.router, prefix="/api/v1")

    # ---------------------------------------------------------------------------
    # Informational root endpoint
    # ---------------------------------------------------------------------------

    @app.get("/")
    def root():
        return {
            "driver": "FLI FilterWheel Alpaca Driver",
            "version": __version__,
            "api_docs": "/docs",
            "management": "/management/apiversions",
            "device_api": f"/api/v1/filterwheel/{config.device_number}",
        }

    return app


def run() -> None:
    """Entry point for ``uv run fli-alpaca-filterwheel``."""
    config = Config.from_env_or_file()
    app = create_app(config)

    print(
        f"FLI FilterWheel Alpaca Driver v{__version__} "
        f"listening on http://{config.host}:{config.port}",
        file=sys.stderr,
    )
    print(
        f"  API docs : http://localhost:{config.port}/docs",
        file=sys.stderr,
    )
    print(
        f"  Devices  : http://localhost:{config.port}/management/v1/configureddevices",
        file=sys.stderr,
    )

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    run()
