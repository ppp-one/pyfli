# FLI Filter Wheel Alpaca Driver

ASCOM Alpaca driver for FLI filter wheels, built with FastAPI and uv.

## Requirements

- Windows 7?/10/11 with the [FLI USB driver](https://www.flicamera.com/software/index.html) installed
- Python 3.10+
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (C++ workload, for compiling pyfli)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Install and run

From the `fli-alpaca-filterwheel/` directory:

```bat
uv pip install cython numpy setuptools
(cd .. && python setup.py build_ext --inplace)
uv sync
uv run fli-alpaca-filterwheel
```

Listens on `http://0.0.0.0:11111` by default. Interactive API docs at `/docs`.

## Configuration

Copy `fli-filterwheel.example.yaml` to `fli-filterwheel.yaml` and edit. The `filters` list keeps names and focus offsets co-located:

```yaml
device_path: null        # auto-detect; or e.g. /dev/fliusb0
interface: usb
host: "0.0.0.0"
port: 11111
auto_connect: false
log_level: INFO

filters:
  - name: L
    focus_offset: 0
  - name: R
    focus_offset: -50
  - name: Ha
    focus_offset: 200
```

Point to a different file with `FLI_CONFIG=/path/to/config.yaml`. Environment variables override file values; the full list is in `fli-filterwheel.example.yaml`.

## Alpaca endpoints

All device endpoints are under `/api/v1/filterwheel/0/`.

| Method | Path | Description |
|--------|------|-------------|
| GET/PUT | `connected` | Connect / disconnect |
| GET | `names` | Filter names |
| GET | `focusoffsets` | Focus offsets per filter |
| GET/PUT | `position` | Current position; PUT blocks until move completes |
| GET | `devicestate` | Full device state snapshot |

Management endpoints at `/management/apiversions`, `/management/v1/description`, and `/management/v1/configureddevices`.

## Notes

- `GET /position` returns `-1` while the wheel is moving.
- Filter names are read from the device on connection when not set in the config file. FLI devices often return empty names; the driver falls back to `Filter 0`, `Filter 1`, etc.
- Focus offsets are not stored on FLI hardware; configure them in `fli-filterwheel.yaml`.
