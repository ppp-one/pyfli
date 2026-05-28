"""FilterWheel-specific Alpaca endpoints.

Implements the ASCOM IFilterWheelV3 interface:
  GET  /api/v1/filterwheel/{n}/focusoffsets
  GET  /api/v1/filterwheel/{n}/names
  GET  /api/v1/filterwheel/{n}/position
  PUT  /api/v1/filterwheel/{n}/position
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Form, Path, Query, Request
from fastapi.responses import JSONResponse

from fli_alpaca_filterwheel.device import DeviceError, ERR_NOT_CONNECTED
from fli_alpaca_filterwheel.models import (
    AlpacaResponse,
    IntArrayResponse,
    IntResponse,
    StringArrayResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_DEVICE_NUMBER = Path(..., ge=0, description="Zero-based device number")


def _validate_device(device_number: int, request: Request) -> None:
    if device_number != request.app.state.config.device_number:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"No FilterWheel with device number {device_number}")


def _txn(request: Request) -> int:
    return request.app.state.counter.next()


def _require_connected(device, client_txn_id: int, server_txn_id: int):
    """Return a JSONResponse for not-connected, or None if connected."""
    if not device.connected:
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=ERR_NOT_CONNECTED,
                ErrorMessage="Filter wheel is not connected. "
                             "Send PUT /connected with Connected=True first.",
                ClientTransactionID=client_txn_id,
                ServerTransactionID=server_txn_id,
            ).model_dump(),
        )
    return None


# ---------------------------------------------------------------------------
# GET focusoffsets
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/focusoffsets", response_model=IntArrayResponse)
def get_focusoffsets(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> IntArrayResponse | JSONResponse:
    """Return an array of focus offsets for each filter position.

    Values are in the same units used by the focuser (typically steps or
    micrometres).  Configure them via the FLI_FOCUS_OFFSETS environment
    variable.
    """
    _validate_device(device_number, request)
    device = request.app.state.device
    txn = _txn(request)

    err = _require_connected(device, ClientTransactionID, txn)
    if err:
        return err

    return IntArrayResponse(
        Value=device.focus_offsets,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=txn,
    )


# ---------------------------------------------------------------------------
# GET names
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/names", response_model=StringArrayResponse)
def get_names(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> StringArrayResponse | JSONResponse:
    """Return an array of filter names for each position.

    Names are read from the FLI device on connection, or overridden via
    the FLI_FILTER_NAMES environment variable.
    """
    _validate_device(device_number, request)
    device = request.app.state.device
    txn = _txn(request)

    err = _require_connected(device, ClientTransactionID, txn)
    if err:
        return err

    return StringArrayResponse(
        Value=device.filter_names,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=txn,
    )


# ---------------------------------------------------------------------------
# GET position
# ---------------------------------------------------------------------------


@router.get("/filterwheel/{device_number}/position", response_model=IntResponse)
def get_position(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    ClientTransactionID: int = Query(0),
) -> IntResponse | JSONResponse:
    """Return the current zero-based filter position.

    Returns -1 if the filter wheel is moving or its position is unknown.
    """
    _validate_device(device_number, request)
    device = request.app.state.device
    txn = _txn(request)

    err = _require_connected(device, ClientTransactionID, txn)
    if err:
        return err

    try:
        position = device.get_position_sync()
    except DeviceError as exc:
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=exc.code,
                ErrorMessage=exc.message,
                ClientTransactionID=ClientTransactionID,
                ServerTransactionID=txn,
            ).model_dump(),
        )

    return IntResponse(
        Value=position,
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=txn,
    )


# ---------------------------------------------------------------------------
# PUT position
# ---------------------------------------------------------------------------


@router.put("/filterwheel/{device_number}/position", response_model=AlpacaResponse)
async def set_position(
    request: Request,
    device_number: int = _DEVICE_NUMBER,
    Position: int = Form(...),
    ClientID: int = Form(0),
    ClientTransactionID: int = Form(0),
) -> AlpacaResponse | JSONResponse:
    """Move the filter wheel to the specified position.

    Blocks until the move completes, as required by the ASCOM Alpaca
    FilterWheel specification.  Returns -1 for Position while moving if
    polled concurrently on GET /position.
    """
    _validate_device(device_number, request)
    device = request.app.state.device
    txn = _txn(request)

    err = _require_connected(device, ClientTransactionID, txn)
    if err:
        return err

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, device.set_position_sync, Position)
    except DeviceError as exc:
        logger.warning("set_position failed: %s", exc.message)
        return JSONResponse(
            status_code=200,
            content=AlpacaResponse(
                ErrorNumber=exc.code,
                ErrorMessage=exc.message,
                ClientTransactionID=ClientTransactionID,
                ServerTransactionID=txn,
            ).model_dump(),
        )

    return AlpacaResponse(
        ClientTransactionID=ClientTransactionID,
        ServerTransactionID=txn,
    )
