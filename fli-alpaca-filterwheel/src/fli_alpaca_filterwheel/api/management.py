"""Alpaca Management API endpoints.

Served at /management/... (no /api/v1 prefix, per the Alpaca specification).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from fli_alpaca_filterwheel import __version__
from fli_alpaca_filterwheel.models import (
    ConfiguredDevice,
    ConfiguredDevicesResponse,
    IntArrayValueResponse,
    ServerDescription,
    ServerDescriptionResponse,
)

router = APIRouter(tags=["Management"])


@router.get("/management/apiversions", response_model=IntArrayValueResponse)
def get_api_versions(
    request: Request,
    ClientTransactionID: int = Query(0),
) -> IntArrayValueResponse:
    """Return the list of supported Alpaca API version numbers."""
    return IntArrayValueResponse(
        Value=[1],
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=request.app.state.counter.next(),
    )


@router.get("/management/v1/description", response_model=ServerDescriptionResponse)
def get_server_description(
    request: Request,
    ClientTransactionID: int = Query(0),
) -> ServerDescriptionResponse:
    """Return a description of this Alpaca server."""
    config = request.app.state.config
    return ServerDescriptionResponse(
        Value=ServerDescription(
            ServerName=config.driver_name,
            Manufacturer="FLI Alpaca Driver",
            ManufacturerVersion=__version__,
            Location="",
        ),
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=request.app.state.counter.next(),
    )


@router.get("/management/v1/configureddevices", response_model=ConfiguredDevicesResponse)
def get_configured_devices(
    request: Request,
    ClientTransactionID: int = Query(0),
) -> ConfiguredDevicesResponse:
    """Return the list of configured devices on this server."""
    config = request.app.state.config
    return ConfiguredDevicesResponse(
        Value=[
            ConfiguredDevice(
                DeviceName=config.driver_name,
                DeviceType="FilterWheel",
                DeviceNumber=config.device_number,
                UniqueID=config.unique_id,
            )
        ],
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=request.app.state.counter.next(),
    )
