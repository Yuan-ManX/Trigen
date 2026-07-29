"""Runtime API key store.

Allows the frontend to configure provider API keys at runtime without
restarting the backend or editing the .env file. Keys are kept in an
in-memory dict and persisted to a JSON file under the Trigen workspace
so they survive process restarts.

Resolution order for a given env name (e.g. OPENAI_API_KEY):
  1. Runtime key store (set via the UI)
  2. Process environment variable (set in .env or shell)

Only the env-name -> key mapping is stored; keys are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("trigen.llm.key_store")


@dataclass
class KeyStatus:
    """Public-facing status of a single API key slot."""

    env_name: str
    configured: bool
    preview: str = ""  # masked preview, e.g. "sk-…AB12"
    source: str = ""  # "runtime", "env", or ""


class APIKeyStore:
    """Thread-safe runtime API key store with file persistence."""

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._keys: Dict[str, str] = {}
        self._persist_path = persist_path
        if persist_path:
            self._load()

    def _load(self) -> None:
        """Load persisted keys from disk."""
        if not self._persist_path:
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._keys = {str(k): str(v) for k, v in data.items() if v}
        except FileNotFoundError:
            pass  # First run — no persisted keys yet
        except Exception as exc:
            logger.warning("Failed to load API key store: %s", exc)

    def _persist(self) -> None:
        """Persist current keys to disk."""
        if not self._persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(self._keys, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to persist API key store: %s", exc)

    def set_key(self, env_name: str, api_key: str) -> None:
        """Set or update a runtime API key."""
        env_name = env_name.strip()
        api_key = api_key.strip() if isinstance(api_key, str) else ""
        with self._lock:
            if api_key:
                self._keys[env_name] = api_key
            else:
                self._keys.pop(env_name, None)
            self._persist()
        logger.info("API key slot '%s' updated (configured=%s)", env_name, bool(api_key))

    def get_key(self, env_name: str) -> str:
        """Resolve a key: runtime store first, then process env."""
        env_name = env_name.strip()
        with self._lock:
            if env_name in self._keys and self._keys[env_name]:
                return self._keys[env_name]
        return os.environ.get(env_name, "")

    def delete_key(self, env_name: str) -> bool:
        """Remove a runtime key. Returns True if a key was removed."""
        env_name = env_name.strip()
        with self._lock:
            existed = env_name in self._keys
            self._keys.pop(env_name, None)
            self._persist()
            return existed

    def has_runtime_key(self, env_name: str) -> bool:
        """Check whether a runtime key (not env) is set."""
        env_name = env_name.strip()
        with self._lock:
            return bool(self._keys.get(env_name))

    def list_runtime_keys(self) -> Dict[str, str]:
        """Return a copy of all runtime keys (full values)."""
        with self._lock:
            return dict(self._keys)

    def status(self, env_name: str) -> KeyStatus:
        """Return the public status of a key slot (masked)."""
        env_name = env_name.strip()
        with self._lock:
            if env_name in self._keys and self._keys[env_name]:
                return KeyStatus(
                    env_name=env_name,
                    configured=True,
                    preview=self._mask(self._keys[env_name]),
                    source="runtime",
                )
        env_val = os.environ.get(env_name, "")
        if env_val:
            return KeyStatus(
                env_name=env_name,
                configured=True,
                preview=self._mask(env_val),
                source="env",
            )
        return KeyStatus(env_name=env_name, configured=False)

    def status_many(self, env_names: List[str]) -> List[KeyStatus]:
        """Return the status of multiple key slots."""
        return [self.status(name) for name in env_names]

    def clear_all(self) -> int:
        """Remove all runtime keys. Returns the number removed."""
        with self._lock:
            count = len(self._keys)
            self._keys.clear()
            self._persist()
            return count

    @staticmethod
    def _mask(key: str) -> str:
        """Mask a key, showing only the first 3 and last 4 characters."""
        if not key:
            return ""
        if len(key) <= 8:
            return "•" * len(key)
        return f"{key[:3]}…{key[-4:]}"


# Global store instance — persists under the workspace directory
def _default_persist_path() -> str:
    workspace = os.environ.get(
        "TRIGEN_WORKSPACE",
        os.path.join(os.getcwd(), ".trigen", "workspace"),
    )
    return os.path.join(workspace, "api_keys.json")


store = APIKeyStore(persist_path=_default_persist_path())
