"""Tests for the FLI FilterWheel Alpaca driver.

These tests use a mock pyfli module so they run without hardware and without
the compiled Cython extension.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Build a minimal pyfli mock before importing the driver
# ---------------------------------------------------------------------------

_mock_pyfli = ModuleType("pyfli")
_mock_pyfli.FLIList = MagicMock(return_value=[["/dev/fliusb0", "FLI CFW-1-8"]])
_mock_pyfli.FLIOpen = MagicMock(return_value=42)
_mock_pyfli.FLIClose = MagicMock()
_mock_pyfli.getFilterCount = MagicMock(return_value=5)
_mock_pyfli.getFilterName = MagicMock(side_effect=lambda dev, i: f"Filter {i}")
_mock_pyfli.getFilterPos = MagicMock(return_value=0)
_mock_pyfli.setFilterPos = MagicMock()
_mock_pyfli.getDeviceStatus = MagicMock(return_value=0)  # idle
_mock_pyfli.getModel = MagicMock(return_value="CFW-1-8")
_mock_pyfli.getSerialString = MagicMock(return_value="SN12345")
_mock_pyfli.getHWRevision = MagicMock(return_value=1)
_mock_pyfli.getFWRevision = MagicMock(return_value=2)

sys.modules["pyfli"] = _mock_pyfli

# ---------------------------------------------------------------------------
# Now import the driver
# ---------------------------------------------------------------------------

from fli_alpaca_filterwheel.config import Config
from fli_alpaca_filterwheel.main import create_app


@pytest.fixture()
def client():
    config = Config(
        device_path="/dev/fliusb0",
        filter_names=["L", "R", "G", "B", "Ha"],
        focus_offsets=[0, -50, -50, -50, 200],
        device_number=0,
        driver_name="Test FLI FilterWheel",
        unique_id="test-fli-fw-0",
        auto_connect=False,
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Management API
# ---------------------------------------------------------------------------


def test_management_apiversions(client):
    r = client.get("/management/apiversions")
    assert r.status_code == 200
    data = r.json()
    assert data["Value"] == [1]
    assert data["ErrorNumber"] == 0


def test_management_description(client):
    r = client.get("/management/v1/description")
    assert r.status_code == 200
    data = r.json()
    assert "ServerName" in data["Value"]
    assert data["Value"]["ServerName"] == "Test FLI FilterWheel"


def test_management_configureddevices(client):
    r = client.get("/management/v1/configureddevices")
    assert r.status_code == 200
    devices = r.json()["Value"]
    assert len(devices) == 1
    assert devices[0]["DeviceType"] == "FilterWheel"
    assert devices[0]["DeviceNumber"] == 0


# ---------------------------------------------------------------------------
# Common endpoints (not connected)
# ---------------------------------------------------------------------------


def test_invalid_device_number(client):
    r = client.get("/api/v1/filterwheel/99/connected")
    assert r.status_code == 400


def test_get_connected_initially_false(client):
    r = client.get("/api/v1/filterwheel/0/connected")
    assert r.status_code == 200
    assert r.json()["Value"] is False


def test_get_name(client):
    r = client.get("/api/v1/filterwheel/0/name")
    assert r.status_code == 200
    assert "FLI" in r.json()["Value"]


def test_get_interfaceversion(client):
    r = client.get("/api/v1/filterwheel/0/interfaceversion")
    assert r.status_code == 200
    assert r.json()["Value"] == 3


def test_get_driverversion(client):
    r = client.get("/api/v1/filterwheel/0/driverversion")
    assert r.status_code == 200
    assert r.json()["Value"]  # non-empty string


def test_get_supportedactions(client):
    r = client.get("/api/v1/filterwheel/0/supportedactions")
    assert r.status_code == 200
    assert r.json()["Value"] == []


# ---------------------------------------------------------------------------
# Connect / disconnect
# ---------------------------------------------------------------------------


def test_connect(client):
    r = client.put(
        "/api/v1/filterwheel/0/connected",
        data={"Connected": "True", "ClientID": "1", "ClientTransactionID": "1"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0

    r2 = client.get("/api/v1/filterwheel/0/connected")
    assert r2.json()["Value"] is True


def test_disconnect(client):
    client.put(
        "/api/v1/filterwheel/0/connected",
        data={"Connected": "True", "ClientID": "1", "ClientTransactionID": "1"},
    )
    r = client.put(
        "/api/v1/filterwheel/0/connected",
        data={"Connected": "False", "ClientID": "1", "ClientTransactionID": "2"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0

    r2 = client.get("/api/v1/filterwheel/0/connected")
    assert r2.json()["Value"] is False


# ---------------------------------------------------------------------------
# FilterWheel endpoints (require connection)
# ---------------------------------------------------------------------------


def _connect(client):
    client.put(
        "/api/v1/filterwheel/0/connected",
        data={"Connected": "True", "ClientID": "1", "ClientTransactionID": "1"},
    )


def test_get_names_not_connected_returns_error(client):
    r = client.get("/api/v1/filterwheel/0/names")
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0x407


def test_get_names(client):
    _connect(client)
    r = client.get("/api/v1/filterwheel/0/names")
    assert r.status_code == 200
    data = r.json()
    assert data["ErrorNumber"] == 0
    assert data["Value"] == ["L", "R", "G", "B", "Ha"]


def test_get_focusoffsets(client):
    _connect(client)
    r = client.get("/api/v1/filterwheel/0/focusoffsets")
    assert r.status_code == 200
    data = r.json()
    assert data["ErrorNumber"] == 0
    assert data["Value"] == [0, -50, -50, -50, 200]


def test_get_position(client):
    _connect(client)
    _mock_pyfli.getFilterPos.return_value = 2
    _mock_pyfli.getDeviceStatus.return_value = 0

    r = client.get("/api/v1/filterwheel/0/position")
    assert r.status_code == 200
    data = r.json()
    assert data["ErrorNumber"] == 0
    assert data["Value"] == 2


def test_get_position_while_moving_returns_minus_one(client):
    _connect(client)
    _mock_pyfli.getDeviceStatus.return_value = 0x01  # MOVING_CCW

    r = client.get("/api/v1/filterwheel/0/position")
    assert r.status_code == 200
    assert r.json()["Value"] == -1

    # Reset
    _mock_pyfli.getDeviceStatus.return_value = 0


def test_set_position(client):
    _connect(client)
    _mock_pyfli.setFilterPos.reset_mock()

    r = client.put(
        "/api/v1/filterwheel/0/position",
        data={"Position": "3", "ClientID": "1", "ClientTransactionID": "5"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0
    _mock_pyfli.setFilterPos.assert_called_once_with(42, 3)


def test_set_position_out_of_range(client):
    _connect(client)

    r = client.put(
        "/api/v1/filterwheel/0/position",
        data={"Position": "99", "ClientID": "1", "ClientTransactionID": "6"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0x401  # InvalidValue


def test_set_position_not_connected(client):
    r = client.put(
        "/api/v1/filterwheel/0/position",
        data={"Position": "1", "ClientID": "1", "ClientTransactionID": "7"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0x407  # NotConnected


def test_devicestate(client):
    _connect(client)
    _mock_pyfli.getFilterPos.return_value = 1
    _mock_pyfli.getDeviceStatus.return_value = 0

    r = client.get("/api/v1/filterwheel/0/devicestate")
    assert r.status_code == 200
    data = r.json()
    assert data["ErrorNumber"] == 0
    names = {item["Name"] for item in data["Value"]}
    assert "Position" in names
    assert "TimeStamp" in names


def test_commandblind_not_implemented(client):
    r = client.put(
        "/api/v1/filterwheel/0/commandblind",
        data={"Action": "test", "Parameters": "", "ClientTransactionID": "1"},
    )
    assert r.status_code == 200
    assert r.json()["ErrorNumber"] == 0x40C


def test_transaction_ids_increment(client):
    r1 = client.get("/api/v1/filterwheel/0/connected")
    r2 = client.get("/api/v1/filterwheel/0/connected")
    assert r2.json()["ServerTransactionID"] > r1.json()["ServerTransactionID"]


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------


def test_config_from_file(tmp_path: Path):
    from fli_alpaca_filterwheel.config import Config

    yaml_content = textwrap.dedent("""\
        device_path: /dev/fliusb0
        interface: usb
        host: "127.0.0.1"
        port: 11112
        device_number: 0
        driver_name: "My Wheel"
        unique_id: "test-uid"
        auto_connect: false
        log_level: DEBUG
        filters:
          - name: L
            focus_offset: 0
          - name: R
            focus_offset: -50
          - name: Ha
            focus_offset: 200
    """)

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml_content)

    cfg = Config.from_file(cfg_file)

    assert cfg.device_path == "/dev/fliusb0"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 11112
    assert cfg.driver_name == "My Wheel"
    assert cfg.filter_names == ["L", "R", "Ha"]
    assert cfg.focus_offsets == [0, -50, 200]
    assert cfg.log_level == "DEBUG"


def test_config_from_file_empty_filters(tmp_path: Path):
    from fli_alpaca_filterwheel.config import Config

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("port: 9999\n")

    cfg = Config.from_file(cfg_file)
    assert cfg.port == 9999
    assert cfg.filter_names == []
    assert cfg.focus_offsets == []


def test_config_from_file_bad_offset(tmp_path: Path):
    from fli_alpaca_filterwheel.config import Config

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("filters:\n  - name: L\n    focus_offset: notanumber\n")

    with pytest.raises(ValueError, match="focus_offset"):
        Config.from_file(cfg_file)


def test_config_env_overrides_file(tmp_path: Path, monkeypatch):
    from fli_alpaca_filterwheel.config import Config

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "port: 9000\nfilters:\n  - name: L\n    focus_offset: 0\n"
    )
    monkeypatch.setenv("FLI_CONFIG", str(cfg_file))
    monkeypatch.setenv("FLI_ALPACA_PORT", "11111")
    monkeypatch.setenv("FLI_FILTER_NAMES", "Ha,OIII")
    monkeypatch.setenv("FLI_FOCUS_OFFSETS", "200,200")

    cfg = Config.from_env_or_file()

    # Env var should win over file value
    assert cfg.port == 11111
    # Env var filter names/offsets should replace file values
    assert cfg.filter_names == ["Ha", "OIII"]
    assert cfg.focus_offsets == [200, 200]


def test_config_env_or_file_uses_defaults_when_no_file(monkeypatch):
    from fli_alpaca_filterwheel.config import Config

    monkeypatch.setenv("FLI_CONFIG", "/nonexistent/path/config.yaml")
    # Clear any other relevant env vars
    for key in ("FLI_ALPACA_PORT", "FLI_FILTER_NAMES", "FLI_FOCUS_OFFSETS"):
        monkeypatch.delenv(key, raising=False)

    cfg = Config.from_env_or_file()
    assert cfg.port == 11111
    assert cfg.filter_names == []

