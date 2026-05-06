"""Hot-loadable user plugins.

A plugin is any `.py` file in `~/.config/TextView/plugins/` (plus any
file shipped under the project's `plugins/` directory) that defines a
top-level `register(ctx)` function. The function is called once at
startup with a `PluginContext` containing:

    ctx.api      — the `AppAPI` instance
    ctx.window   — shortcut to the live `MainWindow`
    ctx.cleanup  — append a callable here; it's invoked when the plugin
                    is unloaded (manually, or before reload).

Plugins can use `api.add_action`, `api.add_dock`, `api.on(event,…)`,
or any of the other methods. Cleanup callables undo whatever the
plugin set up so reload is non-destructive.

Errors during load are caught — one broken plugin doesn't stop the
rest. Errors are surfaced via a status-bar message.

A "Reload plugins" menu action re-walks the directory, runs cleanup
on the previous instances, and re-imports every file.
"""
import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject


# User-managed plugins live here. Always loaded.
USER_PLUGIN_DIR = Path.home() / ".config" / "TextView" / "plugins"
# Project-shipped plugins live next to the source; loaded too so they
# are part of the default install.
PROJECT_PLUGIN_DIR = Path(__file__).parent.parent / "plugins"


class PluginContext:
    def __init__(self, api, name: str):
        self.api = api
        self.window = api.window()
        self.name = name
        self.cleanup: list[Callable] = []

    def add_cleanup(self, fn: Callable):
        self.cleanup.append(fn)


class PluginRegistry(QObject):
    """Discovers, loads, and reloads plugin files."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        # name → {path, module, ctx, error}
        self._plugins: dict[str, dict] = {}

    # -- discovery ---------------------------------------------------------

    @staticmethod
    def _discover() -> list[Path]:
        out: list[Path] = []
        for d in (USER_PLUGIN_DIR, PROJECT_PLUGIN_DIR):
            if d.exists():
                out.extend(sorted(p for p in d.glob("*.py")
                                  if not p.name.startswith("_")))
        # If the user dir is missing, create it so they have a place to
        # drop new files. (PROJECT_PLUGIN_DIR is created by the repo.)
        if not USER_PLUGIN_DIR.exists():
            try:
                USER_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return out

    # -- load / unload -----------------------------------------------------

    def load_all(self):
        for path in self._discover():
            self._load_one(path)

    def _load_one(self, path: Path):
        name = path.stem
        try:
            spec = importlib.util.spec_from_file_location(
                f"textview_plugin_{name}", str(path),
            )
            if spec is None or spec.loader is None:
                return
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
        except Exception as e:
            self._record_error(name, path, f"import failed: {e}")
            return

        register = getattr(mod, "register", None)
        if not callable(register):
            return  # not a plugin

        ctx = PluginContext(self.api, name)
        try:
            register(ctx)
        except Exception as e:
            self._record_error(name, path, f"register() raised: {e}\n"
                               f"{traceback.format_exc(limit=3)}")
            # Roll back any cleanups they did register before crashing.
            for fn in reversed(ctx.cleanup):
                try: fn()
                except Exception: pass
            return

        self._plugins[name] = {
            "path": path, "module": mod, "ctx": ctx, "error": None,
        }

    def _record_error(self, name: str, path: Path, msg: str):
        self._plugins[name] = {
            "path": path, "module": None, "ctx": None, "error": msg,
        }
        self.api.status(f"Plugin '{name}': {msg.splitlines()[0]}", 6000)

    def unload_all(self):
        for name in list(self._plugins.keys()):
            self.unload(name)

    def unload(self, name: str):
        info = self._plugins.pop(name, None)
        if info is None:
            return
        ctx = info.get("ctx")
        if ctx is not None:
            for fn in reversed(ctx.cleanup):
                try: fn()
                except Exception as e:
                    self.api.status(f"Plugin '{name}' cleanup error: {e}",
                                    4000)
        mod = info.get("module")
        if mod is not None:
            sys.modules.pop(getattr(mod, "__name__", ""), None)

    def reload_all(self):
        self.unload_all()
        self.load_all()
        n = len(self._plugins)
        errs = sum(1 for p in self._plugins.values() if p.get("error"))
        msg = f"Plugins reloaded: {n - errs} ok"
        if errs:
            msg += f", {errs} failed"
        self.api.status(msg, 4000)

    # -- introspection -----------------------------------------------------

    def list(self) -> list[dict]:
        return [
            {"name": name,
             "path": str(info["path"]),
             "loaded": info.get("module") is not None,
             "error": info.get("error")}
            for name, info in self._plugins.items()
        ]
