from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from llm_client import get_settings, save_settings, unified_chat


class SmartHomeManager:
    def __init__(self):
        self._load()

    def _load(self) -> None:
        settings = get_settings()
        self.home_assistant = settings.get("home_assistant", {}) or {}
        self.devices = settings.get("smart_devices", []) or []

    def _save(self) -> None:
        settings = get_settings()
        settings["home_assistant"] = self.home_assistant
        settings["smart_devices"] = self.devices
        save_settings(settings)

    def configure_home_assistant(self, url: str, token: str) -> None:
        self.home_assistant = {"url": url.strip().rstrip("/"), "token": token.strip()}
        self._save()

    def add_device(self, friendly_name: str, entity_id: str, device_type: str = "switch") -> None:
        self.devices = [d for d in self.devices if d.get("entity_id") != entity_id]
        self.devices.append({
            "friendly_name": friendly_name.strip(),
            "entity_id": entity_id.strip(),
            "device_type": device_type.strip(),
        })
        self._save()

    def remove_device(self, entity_id: str) -> None:
        self.devices = [d for d in self.devices if d.get("entity_id") != entity_id]
        self._save()

    def list_devices(self) -> list[dict[str, str]]:
        return list(self.devices)

    def set_ha_config(self, url: str, token: str) -> None:
        self.configure_home_assistant(url, token)

    def _validate_config(self) -> None:
        if not self.home_assistant.get("url") or not self.home_assistant.get("token"):
            raise RuntimeError("Home Assistant URL and access token are not configured.")

    def _build_parser_prompt(self, command: str) -> str:
        description = "\n".join(
            f"- {d['friendly_name']} ({d['entity_id']})" for d in self.devices
        ) or "No devices configured."
        return (
            "You are a Home Assistant command parser.\n"
            "Translate the user's natural language command into a strict JSON object.\n"
            "Available devices:\n"
            f"{description}\n\n"
            "Return only one JSON object with keys: entity_id, action, service, service_data.\n"
            "Do not include any explanatory text.\n"
            "action must be one of: turn_on, turn_off, toggle, set_brightness, set_temperature, set_color, lock, unlock, open, close, set_scene, set_volume.\n"
            "service should be the Home Assistant service name such as light.turn_on, switch.turn_off, climate.set_temperature, lock.lock, cover.open_cover.\n"
            "service_data should be a JSON object with any required parameters, or {} if none.\n"
            f"User command: {command.strip()}"
        )

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Could not parse command JSON from model response.")
        payload = match.group(0)
        return json.loads(payload)

    def interpret_command(self, command: str) -> dict[str, Any]:
        if not self.devices:
            raise RuntimeError("No smart home devices have been added yet.")
        prompt = self._build_parser_prompt(command)
        response = unified_chat(
            system_prompt=prompt,
            user_prompt="",
        )
        parsed = self._parse_json_response(response)
        if "entity_id" not in parsed or "service" not in parsed:
            raise RuntimeError("Parsed command is missing entity_id or service.")
        parsed.setdefault("service_data", {})
        return parsed

    def send_command(self, command: str) -> str:
        self._validate_config()
        parsed = self.interpret_command(command)
        url = f"{self.home_assistant['url']}/api/services/{parsed['service']}"
        headers = {
            "Authorization": f"Bearer {self.home_assistant['token']}",
            "Content-Type": "application/json",
        }
        body = {"entity_id": parsed["entity_id"]}
        body.update(parsed.get("service_data", {}))
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Home Assistant request failed: {resp.status_code} {resp.text}")
        return f"Sent {parsed['service']} to {parsed['entity_id']}."
