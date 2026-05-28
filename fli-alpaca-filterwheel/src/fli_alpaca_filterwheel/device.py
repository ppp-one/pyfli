"""Thread-safe FLI FilterWheel device manager.

All public methods that call into pyfli are safe to run from asyncio via
``asyncio.get_event_loop().run_in_executor(None, ...)``.  The internal
``_lock`` serialises access to the FLI handle and protects the connection
state; pyfli's own ``@withDeviceLocked`` decorator provides the FLI-level
device lock.

The ``_moving`` flag is set *before* the blocking ``setFilterPos`` call and
cleared in a ``finally`` block, so any concurrent ``get_position_sync`` call
sees ``-1`` (per the ASCOM Alpaca spec) for the duration of the move.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fli_alpaca_filterwheel.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ASCOM / Alpaca error codes
# ---------------------------------------------------------------------------
ERR_NOT_IMPLEMENTED = 0x400
ERR_INVALID_VALUE = 0x401
ERR_NOT_CONNECTED = 0x407
ERR_INVALID_OPERATION = 0x40B
ERR_ACTION_NOT_IMPLEMENTED = 0x40C
ERR_DRIVER = 0x500

# FLI status bits (from libfli.h)
_MOVING_CCW = 0x01
_MOVING_CW = 0x02
_HOMING = 0x04
_MOVING_MASK = _MOVING_CCW | _MOVING_CW | _HOMING


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DeviceError(Exception):
    """Raised for Alpaca-reportable errors."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Atomic transaction-ID counter (shared across the application)
# ---------------------------------------------------------------------------


class TransactionCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value


# ---------------------------------------------------------------------------
# FLI FilterWheel device
# ---------------------------------------------------------------------------


class FLIFilterWheelDevice:
    """Manages a single FLI filter wheel via pyfli."""

    def __init__(self, config: "Config") -> None:
        self._config = config
        self._lock = threading.Lock()
        self._dev: int | None = None
        self._connected = False
        self._moving = False
        self._filter_count = 0
        self._filter_names: list[str] = []
        self._focus_offsets: list[int] = []

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the FLI device and cache its properties."""
        import pyfli  # Imported here so a missing pyfli gives a clear error.

        with self._lock:
            if self._connected:
                return

            path = self._config.device_path
            if path is None:
                devices = pyfli.FLIList(self._config.interface, "filterwheel")
                if not devices:
                    raise DeviceError(
                        ERR_NOT_CONNECTED,
                        "No FLI filter wheels found on the "
                        f"'{self._config.interface}' interface",
                    )
                path = devices[0][0]
                logger.info("Auto-detected FLI filter wheel at %s (%s)", path, devices[0][1])

            self._dev = pyfli.FLIOpen(path, self._config.interface, "filterwheel")
            logger.info("Opened FLI filter wheel (handle=%d)", self._dev)

            try:
                self._filter_count = pyfli.getFilterCount(self._dev)
                logger.info("Filter count: %d", self._filter_count)
                self._filter_names = self._load_filter_names(pyfli)
                self._focus_offsets = self._load_focus_offsets()
            except OSError as exc:
                # Close the device if initialisation fails.
                try:
                    pyfli.FLIClose(self._dev)
                except OSError:
                    pass
                self._dev = None
                raise DeviceError(ERR_DRIVER, f"FLI initialisation error: {exc}") from exc

            self._connected = True

    def disconnect(self) -> None:
        """Close the FLI device."""
        import pyfli

        with self._lock:
            if not self._connected or self._dev is None:
                return
            try:
                pyfli.FLIClose(self._dev)
                logger.info("Closed FLI filter wheel")
            except OSError as exc:
                logger.warning("Error closing FLI device: %s", exc)
            finally:
                self._dev = None
                self._connected = False
                self._moving = False

    def _load_filter_names(self, pyfli_mod) -> list[str]:
        names: list[str] = []

        if self._config.filter_names:
            names = list(self._config.filter_names)
        else:
            # Try to read names stored on the device.
            for i in range(self._filter_count):
                try:
                    name = pyfli_mod.getFilterName(self._dev, i)
                    names.append(name.strip() or f"Filter {i}")
                except OSError:
                    names.append(f"Filter {i}")

        # Ensure the list is exactly filter_count elements long.
        while len(names) < self._filter_count:
            names.append(f"Filter {len(names)}")
        return names[: self._filter_count]

    def _load_focus_offsets(self) -> list[int]:
        offsets = list(self._config.focus_offsets)
        while len(offsets) < self._filter_count:
            offsets.append(0)
        return offsets[: self._filter_count]

    # ------------------------------------------------------------------
    # Read-only properties (safe to call from any thread without FLI I/O)
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def filter_count(self) -> int:
        with self._lock:
            return self._filter_count

    @property
    def filter_names(self) -> list[str]:
        with self._lock:
            return list(self._filter_names)

    @property
    def focus_offsets(self) -> list[int]:
        with self._lock:
            return list(self._focus_offsets)

    # ------------------------------------------------------------------
    # Device operations (blocking; run via run_in_executor from async code)
    # ------------------------------------------------------------------

    def get_position_sync(self) -> int:
        """Return the current filter position, or -1 if moving/unknown."""
        import pyfli

        with self._lock:
            if not self._connected:
                raise DeviceError(ERR_NOT_CONNECTED, "Filter wheel is not connected")
            if self._moving:
                return -1
            dev = self._dev

        try:
            status = pyfli.getDeviceStatus(dev)
            if status & _MOVING_MASK:
                return -1
            return pyfli.getFilterPos(dev)
        except OSError as exc:
            raise DeviceError(ERR_DRIVER, f"FLI error reading position: {exc}") from exc

    def set_position_sync(self, position: int) -> None:
        """Move to *position*.  Blocks until the wheel reaches the target.

        Raises ``DeviceError`` if:
        - not connected
        - the wheel is already moving
        - position is out of range
        """
        import pyfli

        with self._lock:
            if not self._connected:
                raise DeviceError(ERR_NOT_CONNECTED, "Filter wheel is not connected")
            if self._moving:
                raise DeviceError(ERR_INVALID_OPERATION, "Filter wheel is already moving")
            if not (0 <= position < self._filter_count):
                raise DeviceError(
                    ERR_INVALID_VALUE,
                    f"Position {position} is out of range "
                    f"(valid: 0–{self._filter_count - 1})",
                )
            self._moving = True
            dev = self._dev

        try:
            logger.info("Moving filter wheel to position %d", position)
            pyfli.setFilterPos(dev, position)
            logger.info("Filter wheel reached position %d", position)
        except OSError as exc:
            raise DeviceError(ERR_DRIVER, f"FLI move error: {exc}") from exc
        finally:
            with self._lock:
                self._moving = False

    def get_model_info_sync(self) -> dict[str, str]:
        """Return hardware identification strings (model, serial, revisions)."""
        import pyfli

        with self._lock:
            if not self._connected:
                return {}
            dev = self._dev

        try:
            return {
                "model": pyfli.getModel(dev),
                "serial": pyfli.getSerialString(dev),
                "hw_revision": str(pyfli.getHWRevision(dev)),
                "fw_revision": str(pyfli.getFWRevision(dev)),
            }
        except OSError as exc:
            logger.warning("Could not read model info: %s", exc)
            return {}
