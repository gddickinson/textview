"""API-key storage with three layers in order:

1. OS keychain via `keyring` (Mac Keychain / Win Credential Manager / Linux
   Secret Service) — preferred when available.
2. Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) — useful
   for CI and shells that already export them.
3. QSettings fallback — encrypted nowhere; only used if the user
   explicitly opts in by saving without keyring installed.

`get_api_key(provider)` walks the layers and returns the first hit.
"""
import os

from PyQt6.QtCore import QSettings


_SERVICE = "TextView"
_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _keyring_module():
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError:
        return None


def get_api_key(provider: str) -> str | None:
    kr = _keyring_module()
    if kr:
        try:
            v = kr.get_password(_SERVICE, f"{provider}_api_key")
            if v:
                return v
        except Exception:
            pass
    env = _ENV_VAR.get(provider)
    if env and os.environ.get(env):
        return os.environ[env]
    v = QSettings().value(f"llm/{provider}_api_key")
    if v:
        return str(v)
    return None


def set_api_key(provider: str, key: str, *, prefer_keyring: bool = True) -> str:
    """Stash a key. Returns the storage layer that was used."""
    if prefer_keyring:
        kr = _keyring_module()
        if kr:
            try:
                kr.set_password(_SERVICE, f"{provider}_api_key", key)
                return "keyring"
            except Exception:
                pass
    QSettings().setValue(f"llm/{provider}_api_key", key)
    return "settings"


def clear_api_key(provider: str):
    kr = _keyring_module()
    if kr:
        try:
            kr.delete_password(_SERVICE, f"{provider}_api_key")
        except Exception:
            pass
    s = QSettings()
    s.remove(f"llm/{provider}_api_key")
