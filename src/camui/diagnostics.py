"""
diagnostics.py — Standalone camera diagnostics utility.

Usage:
    python -m camui.diagnostics
    pixi run diagnostics
"""

import json
import logging
from typing import Any

from picamera2 import Picamera2


def print_section(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def inspect_camera(camera: Any) -> None:
    """Print full diagnostics for one connected camera."""
    Picamera2.set_logging(logging.DEBUG)
    picam2 = Picamera2(camera["Num"])
    try:
        print_section("Camera Info")
        print(f"Model: {picam2.camera_properties.get('Model')}")
        print(f"Camera Properties: {picam2.camera_properties}")

        print_section("Supported Sensor Modes")
        try:
            for i, mode in enumerate(picam2.sensor_modes):
                print(f"[{i}] {mode}")
        except Exception as exc:
            print(f"⚠️  Could not get sensor modes: {exc}")

        print_section("Camera Controls (Defaults)")
        controls: dict[str, Any] = {}
        try:
            controls = picam2.camera_controls
            for control, data in controls.items():
                print(f"{control}: {data}")
        except Exception as exc:
            print(f"Error reading camera controls: {exc}")

        print_section("Capture Configurations")
        try:
            print("Preview:", picam2.create_preview_configuration())
            print("Still:  ", picam2.create_still_configuration())
            print("Video:  ", picam2.create_video_configuration())
        except Exception as exc:
            print(f"Error creating configs: {exc}")

        print_section("Control Defaults Dump (JSON)")
        try:
            print(json.dumps(controls, indent=2))
        except Exception as exc:
            print(f"Error serialising controls: {exc}")
    finally:
        picam2.close()


def main() -> None:
    Picamera2.set_logging(logging.WARNING)
    global_cameras = Picamera2.global_camera_info()
    if not global_cameras:
        print("No cameras detected.")
        return
    for cam in global_cameras:
        inspect_camera(cam)


if __name__ == "__main__":
    main()
