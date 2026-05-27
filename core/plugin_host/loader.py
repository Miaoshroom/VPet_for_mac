"""插件注册入口"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from core.app_paths import config_path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"

Plugin = Any
PluginContext = dict[str, Any]


def setup_plugins(context: PluginContext) -> list[Plugin]:
    plugins = [create_plugin(context) for create_plugin in _load_plugin_creators()]
    app = context["app"]
    for plugin in plugins:
        start = getattr(plugin, "start", None)
        if callable(start):
            start()
        shutdown = getattr(plugin, "shutdown", None)
        if callable(shutdown):
            app.aboutToQuit.connect(shutdown)
    return plugins


def _load_plugin_creators() -> list[type]:
    data = json.loads(config_path("plugin_loader.json").read_text(encoding="utf-8"))
    creators = []
    for plugin_name in data.get("plugins", []):
        name = str(plugin_name)
        module = importlib.import_module(_plugin_module_name(name))
        creators.append(getattr(module, _plugin_class_name(name)))
    return creators


def _plugin_module_name(plugin_name: str) -> str:
    if (PLUGINS / plugin_name / "plugin.py").is_file():
        return f"plugins.{plugin_name}.plugin"
    return f"plugins.{plugin_name}"


def _plugin_class_name(plugin_name: str) -> str:
    return "".join(part.capitalize() for part in plugin_name.split("_")) + "Plugin"
