"""Common Alpaca device endpoints (shared by all device types).

All endpoints are under /api/v1/filterwheel/{device_number}/...
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Path, Query, Request
from fastapi.responses import JSONResponse

from fli_alpaca_filterwheel import __version__
from fli_alpaca_filterwheel.device import DeviceError
from fli_alpaca_filterwheel.models import (
    AlpacaResponse,
    BoolResponse,
    DeviceStateResponse,
    StateValue,
    StringArrayResponse,
    StringResponse,
    IntResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_DEVICE_NUMBER = Path(..., ge=0, description="Zero-based device number")


def _validate_device(device_number: int, request: Request) -> None:
    """Return HTTP 400 if the device number is invalid."""
    if device_number != request.app.state.config.device_number:
        raise _http_400(
            f"No FilterWheel with device number {device_number}",
            request,
        )


def _http_400(message: str, request: Request):
    """Raise a 400 response (Alpaca spec requires this for invalid device numbers)."""
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail=message)


def _txn(request: Request) -> int:
    return request.app.state.counter.next()


# ---------------------------------------------------------------------------
# connected
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/connected", response_model=BoolResponse)
def get_connected(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> BoolResponse:
    _validate_device(device_number, request)
    return BoolResponse(
        Value=request.app.state.device.connected,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.put("/filterwheel/{device_number}/connected", response_model=AlpacaResponse)
async def set_connected(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    Connected: str = Form(...),
    ClientID: int = Form(0),
    ClientTransactionID: int = Form(0),
) -> AlpacaResponse | JSONResponse:
    _validate_device(device_number, request)
    connect = Connected.strip().lower() in ("true", "1", "yes")
    device = request.app.state.device

    try:
        loop = asyncio.get_event_loop()
        if connect:
            await loop.run_in_executor(None, device.connect)
        else:
            await loop.run_in_executor(None, device.disconnect)
    except DeviceError as exc:
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=exc.code,
                ErrorMessage=exc.message,
                ClientTransactionID=ClientTransactionID,
                ServerTransactionID=_txn(request),
            ).model_dump(),
        )
    except ImportError as exc:
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=0x500,
                ErrorMessage=f"pyfli is not installed or not compiled: {exc}",
                ClientTransactionID=ClientTransactionID,
                ServerTransactionID=_txn(request),
            ).model_dump(),
        )

    return AlpacaResponse(
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


# ---------------------------------------------------------------------------
# Identification properties (read from config, no hardware I/O)
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/name", response_model=StringResponse)
def get_name(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringResponse:
    _validate_device(device_number, request)
    return StringResponse(
        Value=request.app.state.config.driver_name,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.get("/filterwheel/{device_number}/description", response_model=StringResponse)
def get_description(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringResponse:
    _validate_device(device_number, request)
    return StringResponse(
        Value="FLI FilterWheel Alpaca Driver — controls an FLI filter wheel via the FLI SDK",
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.get("/filterwheel/{device_number}/driverinfo", response_model=StringResponse)
def get_driverinfo(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringResponse:
    _validate_device(device_number, request)
    return StringResponse(
        Value=(
            f"FLI FilterWheel Alpaca Driver v{__version__} — "
            "Finger Lakes Instrumentation filter wheel controller"
        ),
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.get("/filterwheel/{device_number}/driverversion", response_model=StringResponse)
def get_driverversion(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringResponse:
    _validate_device(device_number, request)
    return StringResponse(
        Value=__version__,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.get("/filterwheel/{device_number}/interfaceversion", response_model=IntResponse)
def get_interfaceversion(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> IntResponse:
    _validate_device(device_number, request)
    return IntResponse(
        Value=3,  # IFilterWheelV3
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


@router.get("/filterwheel/{device_number}/supportedactions", response_model=StringArrayResponse)
def get_supportedactions(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringArrayResponse:
    _validate_device(device_number, request)
    return StringArrayResponse(
        Value=[],
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


# ---------------------------------------------------------------------------
# devicestate (Alpaca interface version 3)
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/devicestate", response_model=DeviceStateResponse)
def get_devicestate(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> DeviceStateResponse:
    _validate_device(device_number, request)
    device = request.app.state.device

    state_items: list[StateValue] = [
        StateValue(Name="TimeStamp", Value=datetime.now(tz=timezone.utc).isoformat()),
    ]

    if device.connected:
        try:
            position = device.get_position_sync()
        except DeviceError:
            position = -1
        state_items.append(StateValue(Name="Position", Value=position))

    return DeviceStateResponse(
        Value=state_items,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=_txn(request),
    )


# ---------------------------------------------------------------------------
# Legacy pass-through command endpoints (ActionNotImplemented)
# ---------------------------------------------------------------------------


def _not_implemented_response(
    client_txn_id: int, server_txn_id: int
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=AlpacaResponse(
            ErrorNumber=0x40C,
            ErrorMessage="ActionNotImplementedException: this driver does not support arbitrary commands",
            ClientTransactionID=client_txn_id,
            ServerTransactionID=server_txn_id,
        ).model_dump(),
    )


@router.put("/filterwheel/{device_number}/commandblind", response_model=AlpacaResponse)
def put_commandblind(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    Action: str = Form(...),
    Parameters: str = Form(""),
    ClientID: int = Form(0),
    ClientTransactionID: int = Form(0),
) -> JSONResponse:
    _validate_device(device_number, request)
    return _not_implemented_response(ClientTransactionID, _txn(request))


@router.put("/filterwheel/{device_number}/commandbool", response_model=AlpacaResponse)
def put_commandbool(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    Action: str = Form(...),
    Parameters: str = Form(""),
    ClientID: int = Form(0),
    ClientTransactionID: int = Form(0),
) -> JSONResponse:
    _validate_device(device_number, request)
    return _not_implemented_response(ClientTransactionID, _txn(request))


@router.put("/filterwheel/{device_number}/commandstring", response_model=AlpacaResponse)
def put_commandstring(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    Action: str = Form(...),
    Parameters: str = Form(""),
    ClientID: int = Form(0),
    ClientTransactionID: int = Form(0),
) -> JSONResponse:
    _validate_device(device_number, request)
    return _not_implemented_response(ClientTransactionID, _txn(request))
