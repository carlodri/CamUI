"""
gpio.py — GPIO pin configuration loader.

Reads gpio_map.json from the package data directory.
GPIO hardware control is a planned feature and currently unused in the UI.
"""

import json
import logging

from camui.config import load_gpio_map


class GPIO:
    """Loads and exposes GPIO pin configuration from the bundled gpio_map.json."""

    def __init__(self):
        self.gpio_pins = self._load_config()

    def _load_config(self) -> list[dict]:
        try:
            data = load_gpio_map()
            if not isinstance(data, dict) or "gpio_template" not in data:
                raise ValueError("Invalid JSON structure: missing 'gpio_template' key.")
            gpio_template = data["gpio_template"]
            if not isinstance(gpio_template, list) or not all(isinstance(i, dict) for i in gpio_template):
                raise ValueError("gpio_template must be a list of dicts.")
            return gpio_template
        except Exception as exc:
            logging.error(f"Error loading GPIO config: {exc}")
            return []

    def get_gpio_pins(self) -> list[dict]:
        """Return the GPIO pin configuration list."""
        return self.gpio_pins
