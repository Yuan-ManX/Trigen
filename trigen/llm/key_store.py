"""Runtime API key store with multi-key rotation.

Allows the frontend to configure provider API keys at runtime without
restarting the backend or editing the .env file. Keys are kept in an
in-memory dict and persisted to a JSON file under the Trigen workspace
so they survive process restarts.

Resolution order for a given env name (e.g. OPENAI_API_KEY):
  1. Runtime key store (set via the UI)
  2. Process environment variable (set in .env or shell)

Only the env-name -> key mapping is stored; keys are never logged.

Multi-key support
-----------------
A single logical credential may have more than one physical API key
(e.g. multiple OpenAI orgs). Indexed slots are addressed by suffixing
the base env name with ``_1``, ``_2`` … ``_N``. ``get_keys(base)``
returns every available key for ``base`` plus ``base_1..N``;
``get_next_key(base)`` returns the least-recently-used healthy key,
round-robin skipping keys in cooldown.

Per-key health (``KeySlot``) tracks consecutive failures and a cooldown
deadline. ``mark_failed`` puts a key in cooldown (60s for rate-limit,
300s for auth failures); ``mark_success`` resets the slot. The LLM
client consults this state before retrying a failing key.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("trigen.llm.key_store")

# Cooldown seconds by error type. Auth failures cool longer because the
# key is likely invalid for a while; rate-limit failures are transient.
_COOLDOWN_SECONDS: Dict[str, int] = {
    "rate_limit": 60,
    "auth": 300,
}
# How many consecutive failures on a single key before it is force-cooled
# even for non rate-limit/auth error types.
_MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class KeyStatus:
    """Public-facing status of a single API key slot."""

    env_name: str
    configured: bool
    preview: str = ""  # masked preview, e.g. "sk-…AB12"
    source: str = ""  # "runtime", "env", or ""


@dataclass
class KeySlot:
    """Health state for a single physical API key.

    Tracked per (base_env_name, key_value) so two indexed keys for the
    same provider cool down independently.
    """

    consecutive_failures: int = 0
    cooled_until: float = 0.0  # monotonic deadline; 0 means no cooldown
    last_used: float = 0.0

    def is_available(self, now: float) -> bool:
        return now >= self.cooled_until

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.cooled_until = 0.0


class APIKeyStore:
    """Thread-safe runtime API key store with multi-key rotation."""

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._keys: Dict[str, str] = {}
        self._persist_path = persist_path
        # Per (base_env_name, key_value) health tracking
        self._slots: Dict[tuple, KeySlot] = {}
        # Round-robin cursor per base env name
        self._rr_index: Dict[str, int] = {}
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

    # ------------------------------------------------------------------
    # Single-key API (backward compatible)
    # ------------------------------------------------------------------

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
        """Resolve a single key: runtime store first, then process env.

        Returns the first available key for ``env_name``. For multi-key
        rotation prefer ``get_next_key`` which considers health state.
        """
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
            self._slots.clear()
            self._rr_index.clear()
            self._persist()
            return count

    # ------------------------------------------------------------------
    # Multi-key rotation API
    # ------------------------------------------------------------------

    def get_keys(self, base_env_name: str) -> List[str]:
        """Return every available key for a base env name.

        Collects ``base_env_name`` plus ``base_env_name_1`` …
        ``base_env_name_N`` (for N up to a sane cap). Each slot is
        resolved through the runtime store first, then the process
        environment. Empty/duplicate values are removed while preserving
        discovery order.
        """
        base = base_env_name.strip()
        keys: List[str] = []
        seen: set = set()
        with self._lock:
            candidates = [base] + [f"{base}_{i}" for i in range(1, 32)]
            for name in candidates:
                value = self._keys.get(name, "")
                if not value:
                    value = os.environ.get(name, "")
                if value and value not in seen:
                    keys.append(value)
                    seen.add(value)
        return keys

    def get_next_key(self, base_env_name: str) -> str:
        """Return the least-recently-used healthy key for a base env name.

        Iterates the available keys in round-robin order starting from the
        stored cursor, skipping any key currently in cooldown. If every key
        is cooling down, returns the one whose cooldown expires soonest
        (so the caller can either wait or surface a clear error). Returns
        an empty string when no key is configured at all.
        """
        base = base_env_name.strip()
        keys = self.get_keys(base)
        if not keys:
            return ""
        now = time.monotonic()
        with self._lock:
            start_idx = self._rr_index.get(base, 0) % len(keys)
            ordered = keys[start_idx:] + keys[:start_idx]
            for key in ordered:
                slot = self._slot_for(base, key)
                if slot.is_available(now):
                    slot.last_used = now
                    # Advance the cursor past the chosen key so the next
                    # call picks a different one (true round-robin).
                    chosen_index = keys.index(key)
                    self._rr_index[base] = (chosen_index + 1) % len(keys)
                    return key
            # All keys cooling — return the one that recovers soonest
            soonest = min(
                keys,
                key=lambda k: self._slot_for(base, k).cooled_until,
            )
            return soonest

    def mark_failed(self, base_env_name: str, key: str, error_type: str) -> None:
        """Record a failure on a key and put it in cooldown if appropriate.

        ``error_type`` follows the LLM client classification: ``auth``,
        ``rate_limit``, ``server``, ``timeout``, ``client``, ``unknown``.
        Auth and rate-limit failures cool the key immediately; other types
        only cool after ``_MAX_CONSECUTIVE_FAILURES`` consecutive failures.
        """
        base = base_env_name.strip()
        if not key:
            return
        with self._lock:
            slot = self._slot_for(base, key)
            slot.consecutive_failures += 1
            cooldown = _COOLDOWN_SECONDS.get(error_type, 0)
            if cooldown > 0:
                slot.cooled_until = time.monotonic() + cooldown
                logger.info(
                    "Key for %s entering %ds cooldown (error_type=%s, failures=%d)",
                    base, cooldown, error_type, slot.consecutive_failures,
                )
            elif slot.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                slot.cooled_until = time.monotonic() + 60
                logger.warning(
                    "Key for %s force-cooled after %d consecutive failures",
                    base, slot.consecutive_failures,
                )

    def mark_success(self, base_env_name: str, key: str) -> None:
        """Reset the health state for a key after a successful call."""
        base = base_env_name.strip()
        if not key:
            return
        with self._lock:
            slot = self._slot_for(base, key)
            slot.reset()

    def slot_state(self, base_env_name: str, key: str) -> KeySlot:
        """Return a copy of the health state for a key (for inspection)."""
        with self._lock:
            slot = self._slot_for(base_env_name, key)
            return KeySlot(
                consecutive_failures=slot.consecutive_failures,
                cooled_until=slot.cooled_until,
                last_used=slot.last_used,
            )

    def _slot_for(self, base_env_name: str, key: str) -> KeySlot:
        """Get or create the health slot for (base_env_name, key)."""
        slot_key = (base_env_name, key)
        slot = self._slots.get(slot_key)
        if slot is None:
            slot = KeySlot()
            self._slots[slot_key] = slot
        return slot

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
