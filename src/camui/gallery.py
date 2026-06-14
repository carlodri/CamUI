"""
gallery.py — ImageGallery class for managing captured photos.

Handles listing, paginating, deleting, and editing images stored
in the runtime gallery directory (resolved via camui.config).
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from camui.config import get_gallery_dir, ITEMS_PER_PAGE


class ImageGallery:
    """Manages the on-disk gallery of captured JPEG (and optional DNG) images."""

    def __init__(self, upload_folder: Path | None = None, items_per_page: int = ITEMS_PER_PAGE) -> None:
        self.upload_folder = Path(upload_folder) if upload_folder else get_gallery_dir()
        self.items_per_page = items_per_page

    # ------------------------------------------------------------------
    # Listing & pagination
    # ------------------------------------------------------------------

    def get_image_files(self) -> list[dict[str, Any]]:
        """Return a list of image metadata dicts, sorted newest-first."""
        try:
            image_files = [f for f in os.listdir(self.upload_folder) if f.endswith(".jpg")]
            files_and_timestamps: list[dict[str, Any]] = []

            for image_file in image_files:
                try:
                    unix_timestamp = int(image_file.split("_")[-1].split(".")[0])
                    timestamp = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    logging.warning(f"Skipping {image_file}: incorrect timestamp format")
                    continue

                dng_file = os.path.splitext(image_file)[0] + ".dng"
                has_dng = os.path.exists(self.upload_folder / dng_file)

                img_path = self.upload_folder / image_file
                with Image.open(img_path) as pil_img:
                    width, height = pil_img.size

                files_and_timestamps.append({
                    "filename": image_file,
                    "timestamp": timestamp,
                    "has_dng": has_dng,
                    "dng_file": dng_file,
                    "width": width,
                    "height": height,
                })

            files_and_timestamps.sort(key=lambda x: x["timestamp"], reverse=True)
            return files_and_timestamps

        except Exception as exc:
            logging.error(f"Error loading image files: {exc}")
            return []

    def paginate_images(self, page: int) -> tuple[list[dict[str, Any]], int]:
        """Return (images_on_page, total_pages) for the requested *page* (1-indexed)."""
        all_images = self.get_image_files()
        total_pages = max((len(all_images) + self.items_per_page - 1) // self.items_per_page, 1)
        page = min(page, total_pages)
        start = (page - 1) * self.items_per_page
        return all_images[start : start + self.items_per_page], total_pages

    def find_last_image_taken(self) -> str | None:
        """Return the filename of the most recently captured image, or None."""
        all_images = self.get_image_files()
        if all_images:
            return all_images[0]["filename"]
        return None

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def delete_image(self, filename: str) -> tuple[bool, str]:
        """Delete *filename* (and its paired .dng if present). Returns (success, message)."""
        image_path = self.upload_folder / filename
        if not image_path.exists():
            return False, "Image not found"
        try:
            os.remove(image_path)
            logging.info(f"Deleted image: {filename}")
            dng_file = os.path.splitext(filename)[0] + ".dng"
            dng_path = self.upload_folder / dng_file
            if dng_path.exists():
                os.remove(dng_path)
            return True, f"Image '{filename}' deleted successfully."
        except Exception as exc:
            logging.error(f"Error deleting image {filename}: {exc}")
            return False, "Failed to delete image"

    def save_edit(self, filename: str, edits: dict[str, Any], save_option: str, new_filename: str | None = None) -> tuple[bool, str]:
        """Apply *edits* (brightness, contrast, rotation) to *filename* and save."""
        image_path = self.upload_folder / filename
        if not image_path.exists():
            return False, "Original image not found."
        try:
            with Image.open(image_path) as pil_img:
                pil_img = pil_img.convert("RGB")
                img = ImageOps.exif_transpose(pil_img) or pil_img

                if "brightness" in edits:
                    factor = max(0.1, float(edits["brightness"]) / 100)
                    img = ImageEnhance.Brightness(img).enhance(factor)

                if "contrast" in edits:
                    factor = max(0.1, float(edits["contrast"]) / 100)
                    img = ImageEnhance.Contrast(img).enhance(factor)

                if "rotation" in edits:
                    angle = -(int(edits["rotation"]) % 360)
                    img = img.rotate(angle, expand=True)

                if save_option == "replace":
                    save_path = image_path
                elif save_option == "new_file" and new_filename:
                    save_path = self.upload_folder / new_filename
                else:
                    return False, "Invalid save option."

                img.save(save_path)
                return True, "Image saved successfully."

        except Exception as exc:
            logging.error(f"Error editing image {filename}: {exc}")
            return False, "Failed to edit image."
