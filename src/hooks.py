"""User scripting hooks.

Each `*.py` file in `~/.config/TextView/hooks/` is imported once at app
startup. Any of these top-level callables fire on the matching event:

    on_file_opened(window, path: str)
    on_file_saved(window, path: str)
    on_run_finished(window, exit_code: int, status: int)
    on_chat_response(window, text: str)

Hooks have direct access to MainWindow and all controllers (edit, run,
web, exp, bookmarks, recent, images, project_panel, chat_panel, …) — by
design. This is the user's own script directory; if a hook misbehaves
the user can delete or fix it. Errors in a hook surface as a status-bar
message and are logged once; they do not block the event source.

To keep startup honest, hook loading is best-effort: a single bad file
doesn't prevent the rest from loading.
"""
import importlib.util
import sys
from pathlib import Path
from typing import Callable


HOOKS_DIR = Path.home() / ".config" / "TextView" / "hooks"


class HookRegistry:
    EVENTS = ("on_file_opened", "on_file_saved",
              "on_run_finished", "on_chat_response")

    def __init__(self, window):
        self.window = window
        self.handlers: dict[str, list[Callable]] = {e: [] for e in self.EVENTS}
        self.modules: list = []

    def load_all(self):
        if not HOOKS_DIR.exists():
            return
        for f in sorted(HOOKS_DIR.glob("*.py")):
            try:
                self._load_one(f)
            except Exception as e:
                self.window.statusBar().showMessage(
                    f"Hook {f.name} failed to load: {e}", 4000,
                )

    def _load_one(self, path: Path):
        spec = importlib.util.spec_from_file_location(
            f"textview_hook_{path.stem}", str(path),
        )
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.modules.append(mod)
        for event in self.EVENTS:
            fn = getattr(mod, event, None)
            if callable(fn):
                self.handlers[event].append(fn)

    def fire(self, event: str, *args):
        api = getattr(self.window, "api", None)
        for h in self.handlers.get(event, []):
            try:
                # Hooks can accept an optional `api=` kwarg. Try it first;
                # fall back to the legacy `(window, *args)` signature so
                # existing user scripts keep working.
                import inspect
                sig = inspect.signature(h)
                if "api" in sig.parameters:
                    h(self.window, *args, api=api)
                else:
                    h(self.window, *args)
            except Exception as e:
                self.window.statusBar().showMessage(
                    f"Hook {event} error: {e}", 3000,
                )

    def subscribe(self, event: str, callback):
        if event not in self.handlers:
            return
        self.handlers[event].append(callback)

    def unsubscribe(self, event: str, callback):
        if event in self.handlers and callback in self.handlers[event]:
            self.handlers[event].remove(callback)

    def reload(self):
        """Drop and re-import everything. Bound to a menu item."""
        for mod in self.modules:
            sys.modules.pop(getattr(mod, "__name__", ""), None)
        self.handlers = {e: [] for e in self.EVENTS}
        self.modules = []
        self.load_all()
        n = sum(len(h) for h in self.handlers.values())
        self.window.statusBar().showMessage(
            f"Reloaded hooks ({n} handlers).", 4000,
        )


def write_example(window):
    """Drop a small example hook into the hooks dir on demand."""
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    example = HOOKS_DIR / "example.py"
    if not example.exists():
        example.write_text(
            '"""Example TextView hook — rename or delete to disable."""\n'
            "\n"
            "def on_file_opened(window, path: str):\n"
            "    window.statusBar().showMessage(f'(hook) opened {path}', 2000)\n"
            "\n"
            "def on_run_finished(window, exit_code: int, status: int):\n"
            "    window.statusBar().showMessage(\n"
            "        f'(hook) run finished exit={exit_code}', 2000\n"
            "    )\n"
        )
    window.statusBar().showMessage(f"Hooks dir: {HOOKS_DIR}", 5000)
