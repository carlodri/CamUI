"""
camera.py — CameraObject and StreamingOutput classes.

Extracted from the legacy monolithic app.py during the src/ refactoring.
All path resolution delegates to camui.config.
"""

import io
import json
import os
import threading
import time
from threading import Condition
from typing import Any

from PIL import Image, ImageDraw

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform  # ty: ignore[unresolved-import]

from camui.config import (
    get_gallery_dir,
    get_last_config_path,
    get_profiles_dir,
    get_camera_info,
    load_camera_controls_db,
    load_camera_module_info,
    load_or_initialize_config,
    MINIMUM_LAST_CONFIG,
)


class StreamingOutput(io.BufferedIOBase):
    def __init__(self) -> None:
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf: bytes | bytearray | memoryview) -> int:  # ty: ignore[invalid-method-override]
        self.buffer.seek(0)
        self.buffer.truncate()
        self.buffer.write(buf)
        with self.condition:
            self.condition.notify_all()
        return len(buf)

    def read_frame(self) -> bytes:
        self.buffer.seek(0)
        return self.buffer.read()


class CameraObject:
    def __init__(
        self,
        camera: dict[str, Any],
        camera_module_info: dict[str, Any] | None = None,
    ) -> None:
        self.camera_init = True
        self.camera_info: dict[str, Any] = camera
        self._camera_module_info = camera_module_info or load_camera_module_info()
        self.camera_profile: dict[str, Any] = self.generate_camera_profile()
        self.picam2: Any = Picamera2(camera["Num"])
        self.camera_module_spec: dict[str, Any] | None = self.get_camera_module_spec()
        self.sensor_modes: list[dict[str, Any]] = self.picam2.sensor_modes
        self.camera_resolutions: list[tuple[int, int]] = self.generate_camera_resolutions()
        self.output: StreamingOutput | None = None
        self.sensor_mode_lock = threading.Lock()
        self.init_configure_camera()
        self.live_controls: dict[str, Any] = self.initialize_controls_template(self.picam2.camera_controls)
        self.set_sensor_mode(self.camera_profile.get("sensor_mode", 0))
        self.load_saved_camera_profile()
        self.camera_init = False
        self.capturing_still: bool = False
        self.placeholder_frame: bytes = self.generate_placeholder_frame()
        self.start_streaming()
        self.update_camera_from_metadata()

    # ------------------------------------------------------------------
    # Camera Config
    # ------------------------------------------------------------------

    def init_configure_camera(self) -> None:
        self.still_config: dict[str, Any] = self.picam2.create_still_configuration()
        self.video_config: dict[str, Any] = self.picam2.create_video_configuration()

    def update_camera_config(self) -> None:
        if not self.camera_init:
            self.picam2.stop()
        self.set_orientation()
        self.set_still_config()
        self.set_video_config()
        if not self.camera_init:
            self.picam2.start()

    def configure_camera(self) -> None:
        if not self.camera_init:
            self.capturing_still = True
            self.stop_streaming()
            self.picam2.stop()
            time.sleep(0.1)
        self.set_still_config()
        self.set_video_config()
        if not self.camera_init:
            time.sleep(0.1)
            self.picam2.start()
            self.start_streaming()
            self.capturing_still = False

    def set_still_config(self) -> None:
        self.picam2.configure(self.still_config)

    def set_video_config(self) -> None:
        self.picam2.configure(self.video_config)

    def configure_video_config(self) -> None:
        if not self.camera_init:
            self.capturing_still = True
            self.stop_streaming()
            time.sleep(0.1)
            self.picam2.stop()
            self.picam2.stop()
            time.sleep(0.1)
        self.set_orientation()
        self.picam2.configure(self.video_config)
        if not self.camera_init:
            time.sleep(0.1)
            self.picam2.start()
            self.start_streaming()
            self.capturing_still = False

    def configure_still_config(self) -> None:
        if not self.camera_init:
            self.capturing_still = True
            self.stop_streaming()
            self.picam2.stop()
            time.sleep(0.1)
        self.set_orientation()
        self.picam2.configure(self.still_config)
        if not self.camera_init:
            time.sleep(0.1)
            self.picam2.start()
            self.start_streaming()
            self.capturing_still = False

    def load_saved_camera_profile(self) -> None:
        if self.camera_info.get("Has_Config") and self.camera_info.get("Config_Location"):
            self.load_camera_profile(str(self.camera_info["Config_Location"]))

    def load_camera_profile(self, profile_filename: str) -> bool:
        profile_path = get_profiles_dir() / profile_filename
        if not profile_path.exists():
            print(f"Profile file not found: {profile_path}")
            return False
        try:
            with open(profile_path, "r") as f:
                profile_data = json.load(f)
            self.camera_profile = profile_data
            self.set_sensor_mode(self.camera_profile.get("sensor_mode", 0))
            self.set_orientation()
            self.update_settings("hflip", self.camera_profile["hflip"])
            self.update_settings("vflip", self.camera_profile["vflip"])
            self.update_settings("saveRAW", self.camera_profile["saveRAW"])
            self.apply_profile_controls()
            self.sync_live_controls()
            try:
                last_config_path = get_last_config_path()
                if last_config_path.exists():
                    with open(last_config_path, "r") as f:
                        last_config = json.load(f)
                else:
                    last_config = {"cameras": []}
                camera_num = self.camera_info["Num"]
                updated = False
                for camera in last_config["cameras"]:
                    if camera["Num"] == camera_num:
                        camera["Has_Config"] = True
                        camera["Config_Location"] = profile_filename
                        updated = True
                        break
                if not updated:
                    print(f"Camera {camera_num} not found in camera-last-config.json.")
                with open(last_config_path, "w") as f:
                    json.dump(last_config, f, indent=4)
                print(f"Loaded profile '{profile_filename}' and updated camera-last-config.json.")
            except Exception as e:
                print(f"Error updating camera-last-config.json: {e}")
            return True
        except Exception as e:
            print(f"Error loading camera profile '{profile_filename}': {e}")
            return False

    def generate_camera_profile(self) -> dict[str, Any]:
        config_location = self.camera_info.get("Config_Location", "")
        profile_path = get_profiles_dir() / config_location if config_location else None
        if self.camera_info.get("Has_Config", False) and profile_path and profile_path.exists():
            with open(profile_path, "r") as f:
                self.camera_profile = json.load(f)
        else:
            self.camera_profile = {
                "hflip": 0,
                "vflip": 0,
                "sensor_mode": 0,
                "live_preview": True,
                "model": self.camera_info.get("Model", "Unknown"),
                "resolutions": {"StillCaptureResolution": 0},
                "saveRAW": False,
                "controls": {},
            }
        return self.camera_profile

    def initialize_controls_template(self, picamera2_controls: dict[str, Any]) -> dict[str, Any]:
        camera_json = load_camera_controls_db()
        if "sections" not in camera_json:
            print("Error: 'sections' key not found in camera_json!")
            return camera_json
        self.camera_profile["controls"] = {}
        for section in camera_json["sections"]:
            if "settings" not in section:
                print(f"Warning: Missing 'settings' key in section: {section.get('title', 'Unknown')}")
                continue
            section_enabled = False
            for setting in section["settings"]:
                if not isinstance(setting, dict):
                    print(f"Warning: Unexpected setting format: {setting}")
                    continue
                setting_id = setting.get("id")
                source = setting.get("source", None)
                original_enabled = setting.get("enabled", False)

                if source == "controls":
                    if setting_id in picamera2_controls:
                        min_val, max_val, default_val = picamera2_controls[setting_id]
                        print(f"Updating {setting_id}: Min={min_val}, Max={max_val}, Default={default_val}")
                        setting["min"] = min_val
                        setting["max"] = max_val
                        if default_val is not None:
                            setting["default"] = default_val
                        else:
                            default_val = False if isinstance(min_val, bool) else min_val
                        if setting["enabled"]:
                            self.camera_profile["controls"][setting_id] = default_val
                        setting["enabled"] = original_enabled
                        if original_enabled:
                            section_enabled = True
                    else:
                        print(f"Disabling {setting_id}: Not found in picamera2_controls")
                        setting["enabled"] = False
                elif source == "generatedresolutions":
                    resolution_options: list[dict[str, Any]] = [
                        {"value": i, "label": f"{w} x {h}", "enabled": True}
                        for i, (w, h) in enumerate(self.camera_resolutions)
                    ]
                    setting["options"] = resolution_options
                    section_enabled = True
                    print(f"Updated {setting_id} with generated resolutions")
                else:
                    print(f"Skipping {setting_id}: No source specified, keeping existing values.")
                    section_enabled = True

                if "childsettings" in setting:
                    for child in setting["childsettings"]:
                        child_id = child.get("id")
                        child_source = child.get("source", None)
                        if child_source == "controls" and child_id in picamera2_controls:
                            min_val, max_val, default_val = picamera2_controls[child_id]
                            print(f"Updating Child Setting {child_id}: Min={min_val}, Max={max_val}, Default={default_val}")
                            child["min"] = min_val
                            child["max"] = max_val
                            self.camera_profile["controls"][child_id] = default_val if default_val is not None else min_val
                            if default_val is not None:
                                child["default"] = default_val
                            child["enabled"] = child.get("enabled", False)
                            if child["enabled"]:
                                section_enabled = True
                        else:
                            print(f"Skipping or Disabling Child Setting {child_id}: Not found or no source specified")
            section["enabled"] = section_enabled
        print(f"Initialized camera_profile controls: {self.camera_profile}")
        return camera_json

    def update_settings(self, setting_id: str, setting_value: Any) -> Any:
        if setting_id == "sensor_mode":
            def sensor_mode_task() -> None:
                try:
                    self.set_sensor_mode(int(setting_value))
                    self.camera_profile["sensor_mode"] = int(setting_value)
                    print(f"Sensor mode {setting_value} applied")
                except ValueError as e:
                    print(f"⚠️ Error: {e}")

            thread = threading.Thread(target=sensor_mode_task)
            thread.start()
            thread.join()
        elif setting_id in ["hflip", "vflip"]:
            try:
                self.camera_profile[setting_id] = bool(int(setting_value))
                self.update_camera_config()
                print(f"Applied transform: {setting_id} -> {setting_value} (Camera restarted)")
            except ValueError as e:
                print(f"⚠️ Error: {e}")
        elif setting_id in ["StillCaptureResolution", "LiveFeedResolution"]:
            try:
                self.camera_profile["resolutions"][setting_id] = int(setting_value)
                if setting_id == "StillCaptureResolution":
                    self.still_config = self.picam2.create_video_configuration(
                        main={"size": self.camera_resolutions[int(setting_value)]}
                    )
                    self.update_camera_config()
                    self.camera_profile["resolutions"][setting_id] = int(setting_value)
                if setting_id == "LiveFeedResolution":
                    self.set_live_feed_resolution(setting_value)
                print(f"Applied transform: {setting_id} -> {setting_value} (Camera restarted)")
            except ValueError as e:
                print(f"⚠️ Error: {e}")
        elif setting_id == "saveRAW":
            try:
                self.camera_profile[setting_id] = setting_value
                print(f"Applied transform: {setting_id} -> {setting_value}")
            except ValueError as e:
                print(f"⚠️ Error: {e}")
        else:
            if isinstance(setting_value, str) and "." in setting_value:
                setting_value = float(setting_value)
            else:
                setting_value = int(setting_value)
            self.picam2.set_controls({setting_id: setting_value})
            self.camera_profile.setdefault("controls", {})[setting_id] = setting_value

        updated = False
        for section in self.live_controls.get("sections", []):
            for setting in section.get("settings", []):
                if setting["id"] == setting_id:
                    setting["value"] = setting_value
                    updated = True
                    break
                for child in setting.get("childsettings", []):
                    if child["id"] == setting_id:
                        child["value"] = setting_value
                        updated = True
                        break
            if updated:
                break
        if not updated:
            print(f"⚠️ Warning: Setting {setting_id} not found in live_controls!")
        return setting_value

    def sync_live_controls(self) -> None:
        for section in self.live_controls.get("sections", []):
            for setting in section.get("settings", []):
                setting_id = setting["id"]
                if setting_id in self.camera_profile["controls"]:
                    setting["value"] = self.camera_profile["controls"][setting_id]
                for child in setting.get("childsettings", []):
                    child_id = child["id"]
                    if child_id in self.camera_profile["controls"]:
                        child["value"] = self.camera_profile["controls"][child_id]
        print("✅ Live controls updated to match camera profile.")

    def apply_profile_controls(self) -> None:
        if "controls" in self.camera_profile:
            try:
                for setting_id, setting_value in self.camera_profile["controls"].items():
                    self.picam2.set_controls({setting_id: setting_value})
                    self.update_settings(setting_id, setting_value)
                    print(f"Applied Control: {setting_id} -> {setting_value}")
                print("✅ All profile controls applied successfully")
            except Exception as e:
                print(f"⚠️ Error applying profile controls: {e}")

    def set_orientation(self) -> None:
        transform = Transform()
        transform.hflip = self.camera_profile.get("hflip", False)
        transform.vflip = self.camera_profile.get("vflip", False)
        self.still_config["transform"] = transform
        self.video_config["transform"] = transform
        print("Applied Orientation - hflip:", transform.hflip, "vflip:", transform.vflip)

    def set_sensor_mode(self, mode_index: int) -> None:
        try:
            if mode_index < 0 or mode_index >= len(self.sensor_modes):
                raise ValueError("Invalid sensor mode index")
            mode = self.sensor_modes[mode_index]
            self.camera_profile["sensor_mode"] = mode_index
            print(f"📷 Sensor mode selected for Camera {self.camera_info['Num']}: {mode}")
            self.still_config = self.picam2.create_still_configuration(
                sensor={"output_size": mode["size"], "bit_depth": mode["bit_depth"]}
            )
            self.video_config = self.picam2.create_video_configuration(
                main={"size": mode["size"]},
                sensor={"output_size": mode["size"], "bit_depth": mode["bit_depth"]},
            )
            self.configure_video_config()
        except Exception as e:
            print(f"Error saving profile: {e}")

    def set_live_feed_resolution(self, resolution_index: int) -> None:
        with self.sensor_mode_lock:
            if resolution_index < 0 or resolution_index >= len(self.camera_resolutions):
                raise ValueError("Invalid resolution index")
            resolution = self.camera_resolutions[resolution_index]
            print(f"Setting live feed resolution to: {resolution}")
            self.video_config = self.picam2.create_video_configuration(main={"size": resolution})
            self.configure_video_config()

    def update_camera_from_metadata(self) -> None:
        metadata = self.capture_metadata()
        if not metadata:
            print("Failed to fetch metadata")
            return
        if "sections" not in self.live_controls:
            print("Error: 'sections' key not found in live_controls!")
            return
        enabled_controls: dict[str, bool] = {}
        for section in self.live_controls["sections"]:
            for setting in section.get("settings", []):
                if setting.get("enabled", False) and setting.get("source") == "controls":
                    enabled_controls[setting["id"]] = True
                for child in setting.get("childsettings", []):
                    if child.get("enabled", False) and child.get("source") == "controls":
                        enabled_controls[child["id"]] = True
        for key in enabled_controls:
            if key in metadata:
                self.camera_profile["controls"][key] = metadata[key]
                self.update_settings(key, metadata[key])
                print(f"Updated from metadata - {key}: {metadata[key]}")

    def save_profile(self, filename: str) -> bool:
        try:
            print(self.camera_profile)
            if filename.lower().endswith(".json"):
                filename = filename[:-5]
            profile_path = get_profiles_dir() / f"{filename}.json"
            with open(profile_path, "w") as f:
                json.dump(self.camera_profile, f, indent=4)
            try:
                last_config_path = get_last_config_path()
                if last_config_path.exists():
                    with open(last_config_path, "r") as f:
                        last_config = json.load(f)
                else:
                    last_config = {"cameras": []}
                camera_num = self.camera_info["Num"]
                updated = False
                for camera in last_config["cameras"]:
                    if camera["Num"] == camera_num:
                        camera["Has_Config"] = True
                        camera["Config_Location"] = f"{filename}.json"
                        updated = True
                        break
                if not updated:
                    print(f"Warning: Camera {camera_num} not found in camera-last-config.json.")
                with open(last_config_path, "w") as f:
                    json.dump(last_config, f, indent=4)
                print(f"Updated camera-last-config.json for camera {camera_num} after saving profile.")
            except Exception as e:
                print(f"Error updating camera-last-config.json: {e}")
            return True
        except Exception as e:
            print(f"Error saving profile: {e}")
            return False

    def reset_to_default(self) -> None:
        self.camera_profile = {
            "hflip": 0,
            "vflip": 0,
            "sensor_mode": 0,
            "live_preview": True,
            "model": self.camera_info.get("Model", "Unknown"),
            "resolutions": {"StillCaptureResolution": 0},
            "saveRAW": False,
            "controls": {},
        }
        self.set_sensor_mode(self.camera_profile["sensor_mode"])
        self.set_orientation()
        self.live_controls = self.initialize_controls_template(self.picam2.camera_controls)
        self.update_settings("saveRAW", self.camera_profile["saveRAW"])
        print(self.camera_profile["saveRAW"])
        self.update_camera_from_metadata()
        self.apply_profile_controls()
        print("Camera profile reset to default and settings applied.")

    # ------------------------------------------------------------------
    # Camera Information
    # ------------------------------------------------------------------

    def capture_metadata(self) -> dict[str, Any]:
        self.metadata = self.picam2.capture_metadata()
        print(self.picam2.sensor_resolution)
        return self.metadata

    def get_camera_module_spec(self) -> dict[str, Any] | None:
        return next(
            (
                cam
                for cam in self._camera_module_info.get("camera_modules", [])
                if cam["sensor_model"] == self.camera_info["Model"]
            ),
            None,
        )

    def get_sensor_mode(self) -> int | None:
        current_config = self.picam2.camera_configuration()
        active_mode = current_config.get("sensor", {})
        active_mode_index: int | None = None
        for index, mode in enumerate(self.sensor_modes):
            if mode["size"] == active_mode.get("output_size") and mode["bit_depth"] == active_mode.get("bit_depth"):
                active_mode_index = index
                break
        print(f"Active Sensor Mode: {active_mode_index}")
        return active_mode_index

    def generate_camera_resolutions(self) -> list[tuple[int, int]]:
        if not self.sensor_modes:
            print("⚠️ Warning: No sensor modes available!")
            return []
        resolutions: list[tuple[int, int]] = sorted(
            set(mode["size"] for mode in self.sensor_modes if "size" in mode), reverse=True
        )
        if not resolutions:
            print("⚠️ Warning: No valid resolutions found in sensor modes!")
            return []
        extra_resolutions: list[tuple[int, int]] = []
        for i in range(len(resolutions) - 1):
            w1, h1 = resolutions[i]
            w2, h2 = resolutions[i + 1]
            midpoint = ((w1 + w2) // 2, (h1 + h2) // 2)
            extra_resolutions.append(midpoint)
        last_w, last_h = resolutions[-1]
        half_res = (last_w // 2, last_h // 2)
        inbetween_res = ((last_w + half_res[0]) // 2, (last_h + half_res[1]) // 2)
        resolutions.extend(extra_resolutions)
        resolutions.append(inbetween_res)
        resolutions.append(half_res)
        self.available_resolutions = sorted(set(resolutions), reverse=True)
        return self.available_resolutions

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def generate_stream(self) -> Any:
        last_resolution: tuple[int, int] | None = None
        while True:
            if self.capturing_still:
                frame = self.placeholder_frame
            else:
                if self.output is None:
                    frame = self.placeholder_frame
                    continue
                with self.output.condition:
                    self.output.condition.wait()
                    frame = self.output.read_frame()
                if frame is None:
                    print("🚨 Error: read_frame() returned None! Using placeholder.")
                    frame = self.placeholder_frame
                    continue
                if not isinstance(frame, bytes):
                    print(f"⚠️ Warning: Frame is not bytes! Type: {type(frame)}")
                    frame = self.placeholder_frame
                    continue
                config = self.picam2.stream_configuration("main")
                if config is None:
                    print("🚨 stream_configuration returned None! Skipping frame...")
                    frame = self.placeholder_frame
                    continue
                actual_resolution = config["size"]
                expected_resolution = self.video_config["main"]["size"]
                if last_resolution is None or actual_resolution != expected_resolution:
                    print(f"🔄 Resolution change detected: {last_resolution} → {expected_resolution}")
                    last_resolution = expected_resolution
                    self.picam2.stop()
                    self.picam2.start(show_preview=False)
                    print("✅ Buffer cleared. Restarting stream with new resolution...")
                    continue
                if actual_resolution != expected_resolution:
                    print(f"⚠️ Skipping frame due to resolution mismatch: {actual_resolution} expected: {expected_resolution}")
                    frame = self.placeholder_frame
                    continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )

    def generate_placeholder_frame(self) -> bytes:
        mode_index = self.camera_profile.get("sensor_mode", 0)
        assert isinstance(mode_index, int)
        if mode_index < 0 or mode_index >= len(self.sensor_modes):
            raise ValueError("Invalid sensor mode index")
        mode = self.sensor_modes[mode_index]
        img = Image.new("RGB", mode["size"], (33, 37, 41))  # type: ignore[arg-type]
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def start_streaming(self) -> None:
        self.output = StreamingOutput()
        self.picam2.start_recording(MJPEGEncoder(), output=FileOutput(self.output))
        print("[INFO] Streaming started")
        time.sleep(1)

    def stop_streaming(self) -> None:
        if self.output:
            self.picam2.stop_recording()
            print("[INFO] Streaming stopped")

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def take_still(self, camera_num: int, image_name: str) -> str | None:
        try:
            self.capturing_still = True
            time.sleep(0.5)
            self.stop_streaming()
            filepath = get_gallery_dir() / image_name
            buffers, metadata = self.picam2.switch_mode_and_capture_buffers(
                self.still_config, ["main", "raw"]
            )
            self.picam2.helpers.save(
                self.picam2.helpers.make_image(buffers[0], self.still_config["main"]),
                metadata,
                f"{filepath}.jpg",
            )
            if self.camera_profile.get("saveRAW"):
                self.picam2.helpers.save_dng(
                    buffers[1], metadata, self.still_config["raw"], f"{filepath}.dng"
                )
            print(f"Image captured successfully. Path: {filepath}")
            self.start_streaming()
            print("Applied video config:", self.picam2.camera_configuration())
            self.capturing_still = False
            return f"{filepath}.jpg"
        except Exception as e:
            print(f"Error capturing image: {e}")
            return None

    def take_still_from_feed(self, camera_num: int, image_name: str) -> str | None:
        try:
            filepath = get_gallery_dir() / image_name
            with self.picam2.captured_request() as request:
                request.save("main", f"{filepath}.jpg")
            print(f"Image captured successfully. Path: {filepath}")
            return f"{filepath}.jpg"
        except Exception as e:
            print(f"Error capturing image: {e}")
            return None
