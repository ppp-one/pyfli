"""Configuration loader.

Priority (highest to lowest):
  1. Environment variables
  2. YAML config file (path from FLI_CONFIG env var, default fli-filterwheel.yaml)
  3. Built-in defaults

Config file format
------------------
The file uses YAML.  The ``filters`` list keeps filter names and focus offsets
together, which is easier to manage than two separate comma-separated strings::

    filters:
      - name: L
        focus_offset: 0
      - name: R
        focus_offset: -50
      - name: Ha
        focus_offset: 200

All other keys mirror the environment variable names (lower-cased, without the
``FLI_`` prefix).  See :func:`from_file` for the full schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Hardware
    device_path: str | None = None
    interface: str = "usb"

    # Filter properties
    filter_names: list[str] = field(default_factory=list)
    focus_offsets: list[int] = field(default_factory=list)

    # Server
    host: str = "0.0.0.0"
    port: int = 11111

    # Alpaca identity
    device_number: int = 0
    driver_name: str = "FLI FilterWheel Alpaca Driver"
    unique_id: str = "fli-filterwheel-0"

    # Behaviour
    auto_connect: bool = False
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """Load configuration from a YAML file.

        The ``filters`` key is a list of mappings with ``name`` and
        ``focus_offset`` fields::

            filters:
              - name: L
                focus_offset: 0
              - name: Ha
                focus_offset: 200

        All other keys are optional and fall back to the same defaults as
        the environment-variable loader.
        """
        import yaml

        with open(path) as fh:
            data: dict = yaml.safe_load(fh) or {}

        filter_names: list[str] = []
        focus_offsets: list[int] = []
        for entry in data.get("filters", []):
            if not isinstance(entry, dict):
                raise ValueError(f"Each 'filters' entry must be a mapping, got: {entry!r}")
            name = str(entry.get("name", ""))
            try:
                offset = int(entry.get("focus_offset", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"focus_offset for filter '{name}' must be an integer"
                ) from exc
            filter_names.append(name)
            focus_offsets.append(offset)

        return cls(
            device_path=data.get("device_path") or None,
            interface=str(data.get("interface", "usb")),
            filter_names=filter_names,
            focus_offsets=focus_offsets,
            host=str(data.get("host", "0.0.0.0")),
            port=int(data.get("port", 11111)),
            device_number=int(data.get("device_number", 0)),
            driver_name=str(data.get("driver_name", "FLI FilterWheel Alpaca Driver")),
            unique_id=str(data.get("unique_id", "fli-filterwheel-0")),
            auto_connect=bool(data.get("auto_connect", False)),
            log_level=str(data.get("log_level", "INFO")).upper(),
        )

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables only."""
        names_str = os.environ.get("FLI_FILTER_NAMES", "")
        filter_names = (
            [n.strip() for n in names_str.split(",") if n.strip()] if names_str else []
        )

        offsets_str = os.environ.get("FLI_FOCUS_OFFSETS", "")
        try:
            focus_offsets = (
                [int(o.strip()) for o in offsets_str.split(",") if o.strip()]
                if offsets_str
                else []
            )
        except ValueError as exc:
            raise ValueError(f"FLI_FOCUS_OFFSETS must be comma-separated integers: {exc}") from exc

        return cls(
            device_path=os.environ.get("FLI_DEVICE_PATH") or None,
            interface=os.environ.get("FLI_INTERFACE", "usb"),
            filter_names=filter_names,
            focus_offsets=focus_offsets,
            host=os.environ.get("FLI_ALPACA_HOST", "0.0.0.0"),
            port=int(os.environ.get("FLI_ALPACA_PORT", "11111")),
            device_number=int(os.environ.get("FLI_DEVICE_NUMBER", "0")),
            driver_name=os.environ.get(
                "FLI_DRIVER_NAME", "FLI FilterWheel Alpaca Driver"
            ),
            unique_id=os.environ.get("FLI_UNIQUE_ID", "fli-filterwheel-0"),
            auto_connect=os.environ.get("FLI_AUTO_CONNECT", "false").lower()
            in ("true", "1", "yes"),
            log_level=os.environ.get("FLI_LOG_LEVEL", "INFO").upper(),
        )

    @classmethod
    def from_env_or_file(cls) -> "Config":
        """Load from a YAML config file then apply env-var overrides.

        The config file path is taken from the ``FLI_CONFIG`` environment
        variable (default: ``fli-filterwheel.yaml`` in the working directory).
        If the file does not exist, built-in defaults are used.

        Environment variables always take precedence over file values.
        """
        config_path = Path(os.environ.get("FLI_CONFIG", "fli-filterwheel.yaml"))
        cfg = cls.from_file(config_path) if config_path.is_file() else cls()

        # Apply env-var overrides only when the variable is explicitly set.
        if os.environ.get("FLI_DEVICE_PATH"):
            cfg.device_path = os.environ["FLI_DEVICE_PATH"]
        if os.environ.get("FLI_INTERFACE"):
            cfg.interface = os.environ["FLI_INTERFACE"]
        if os.environ.get("FLI_ALPACA_HOST"):
            cfg.host = os.environ["FLI_ALPACA_HOST"]
        if os.environ.get("FLI_ALPACA_PORT"):
            cfg.port = int(os.environ["FLI_ALPACA_PORT"])
        if os.environ.get("FLI_DEVICE_NUMBER"):
            cfg.device_number = int(os.environ["FLI_DEVICE_NUMBER"])
        if os.environ.get("FLI_DRIVER_NAME"):
            cfg.driver_name = os.environ["FLI_DRIVER_NAME"]
        if os.environ.get("FLI_UNIQUE_ID"):
            cfg.unique_id = os.environ["FLI_UNIQUE_ID"]
        if os.environ.get("FLI_AUTO_CONNECT"):
            cfg.auto_connect = (
                os.environ["FLI_AUTO_CONNECT"].lower() in ("true", "1", "yes")
            )
        if os.environ.get("FLI_LOG_LEVEL"):
            cfg.log_level = os.environ["FLI_LOG_LEVEL"].upper()

        # Env-var filter names/offsets replace the file values entirely when set.
        names_str = os.environ.get("FLI_FILTER_NAMES", "")
        if names_str:
            cfg.filter_names = [n.strip() for n in names_str.split(",") if n.strip()]

        offsets_str = os.environ.get("FLI_FOCUS_OFFSETS", "")
        if offsets_str:
            try:
                cfg.focus_offsets = [
                    int(o.strip()) for o in offsets_str.split(",") if o.strip()
                ]
            except ValueError as exc:
                raise ValueError(
                    f"FLI_FOCUS_OFFSETS must be comma-separated integers: {exc}"
                ) from exc

        return cfg
