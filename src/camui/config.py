"""
config.py — Paths, constants, and configuration helpers.

All path resolution is done here so every other module can import
from this single source of truth rather than computing paths itself.

Runtime data (captured images, camera profiles, last-used config) is
written to a user-configurable directory resolved in this order:

  1. CAMUI_DATA_DIR environment variable (explicit override)
  2. Current working directory (convenient for local development)

Static read-only databases (camera_controls_db.json, camera-module-info.json,
gpio_map.json) ship inside the package under src/camui/data/ and are
loaded via importlib.resources so they work whether the package is
installed from a wheel or run directly from the source tree.
"""

import importlib.resources as pkg_resources
import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Package version / metadata
# ---------------------------------------------------------------------------
from camui import __version__, __title__

version: str = __version__
project_title: str = __title__
firmware_control: bool = False

# ---------------------------------------------------------------------------
# Runtime data directory  (read-write: gallery, profiles, last-config)
# ---------------------------------------------------------------------------


def get_data_dir() -> Path:
    """Return the runtime data directory, creating it if necessary."""
    env = os.environ.get("CAMUI_DATA_DIR")
    if env:
        data_dir = Path(env)
    else:
        data_dir = Path.cwd()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_gallery_dir() -> Path:
    d = get_data_dir() / "gallery"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_profiles_dir() -> Path:
    d = get_data_dir() / "camera_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_last_config_path() -> Path:
    return get_data_dir() / "camera-last-config.json"


# Items per page in the gallery
ITEMS_PER_PAGE: int = 12

# Minimum camera-last-config structure
MINIMUM_LAST_CONFIG: dict[str, Any] = {"cameras": []}

# ---------------------------------------------------------------------------
# Static package data  (read-only databases shipped with the package)
# ---------------------------------------------------------------------------


def _load_package_json(filename: str) -> dict[str, Any]:
    """Load a JSON file bundled inside camui/data/."""
    # importlib.resources works for both installed wheels and editable installs
    try:
        # Python 3.9+ preferred API
        ref = pkg_resources.files("camui") / "data" / filename
        with ref.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except AttributeError:
        # Fallback for Python 3.8 (not expected, but defensive)
        with pkg_resources.open_text("camui.data", filename) as fh:
            return json.load(fh)


def load_camera_module_info() -> dict[str, Any]:
    return _load_package_json("camera-module-info.json")


def load_camera_controls_db() -> dict[str, Any]:
    return _load_package_json("camera_controls_db.json")


def load_gpio_map() -> dict[str, Any]:
    return _load_package_json("gpio_map.json")


# ---------------------------------------------------------------------------
# Dynamic config helpers
# ---------------------------------------------------------------------------


def load_or_initialize_config(file_path: Path, default_config: dict[str, Any]) -> dict[str, Any]:
    """Load JSON config from *file_path*, creating it from *default_config* if absent/invalid."""
    if file_path.exists():
        try:
            with open(file_path, "r") as fh:
                config = json.load(fh)
            if not config:
                raise ValueError("Empty configuration file")
            return config
        except (json.JSONDecodeError, ValueError):
            pass
    # Create / overwrite with default
    with open(file_path, "w") as fh:
        json.dump(default_config, fh, indent=4)
    return dict(default_config)


def list_profiles() -> list[dict[str, str]]:
    """Return a list of {filename, model} dicts for every .json profile saved."""
    profiles: list[dict[str, str]] = []
    profiles_dir = get_profiles_dir()
    for filename in profiles_dir.iterdir():
        if filename.suffix == ".json":
            try:
                with open(filename, "r") as fh:
                    data = json.load(fh)
                profiles.append({
                    "filename": filename.name,
                    "model": data.get("model", "Unknown"),
                })
            except Exception as exc:
                print(f"Error loading profile {filename.name}: {exc}")
    return profiles


def get_camera_info(camera_model: str, camera_module_info: dict[str, Any]) -> dict[str, Any]:
    """Return the module spec for *camera_model*, falling back to 'Unknown'."""
    modules: list[dict[str, Any]] = camera_module_info.get("camera_modules", [])
    return next(
        (m for m in modules if m["sensor_model"] == camera_model),
        next((m for m in modules if m["sensor_model"] == "Unknown"), {}),
    )
