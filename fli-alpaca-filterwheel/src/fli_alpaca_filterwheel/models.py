"""Pydantic response models for the Alpaca API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Base response
# ---------------------------------------------------------------------------


class AlpacaResponse(BaseModel):
    ClientTransactionID: int = 0
    ServerTransactionID: int = 0
    ErrorNumber: int = 0
    ErrorMessage: str = ""


# ---------------------------------------------------------------------------
# Typed value responses
# ---------------------------------------------------------------------------


class BoolResponse(AlpacaResponse):
    Value: bool


class IntResponse(AlpacaResponse):
    Value: int


class StringResponse(AlpacaResponse):
    Value: str


class StringArrayResponse(AlpacaResponse):
    Value: list[str]


class IntArrayResponse(AlpacaResponse):
    Value: list[int]


# ---------------------------------------------------------------------------
# DeviceState (Alpaca interface version 3)
# ---------------------------------------------------------------------------


class StateValue(BaseModel):
    Name: str
    Value: Any


class DeviceStateResponse(AlpacaResponse):
    Value: list[StateValue]


# ---------------------------------------------------------------------------
# Management API models
# ---------------------------------------------------------------------------


class ConfiguredDevice(BaseModel):
    DeviceName: str
    DeviceType: str
    DeviceNumber: int
    UniqueID: str


class ConfiguredDevicesResponse(AlpacaResponse):
    Value: list[ConfiguredDevice]


class ServerDescription(BaseModel):
    ServerName: str
    Manufacturer: str
    ManufacturerVersion: str
    Location: str


class ServerDescriptionResponse(AlpacaResponse):
    Value: ServerDescription


class IntArrayValueResponse(AlpacaResponse):
    Value: list[int]
