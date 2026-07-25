"""Session service layer, managing session state and message persistence."""

from __future__ import annotations

import uuid
from typing import Optional

from trigen.api.models.database import Database


class SessionService:
    """Session management service."""

    _instance: Optional["SessionService"] = None  # Singleton instance

    @classmethod
    def get(cls) -> "SessionService":
        if cls._instance is None:
            cls._instance = cls()  # Lazily create singleton
        return cls._instance

    def __init__(self):
        self._db: Optional[Database] = None  # Database instance

    def bind_db(self, db: Database) -> None:
        self._db = db  # Bind database instance

    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("Database not bound")  # Database not bound error
        return self._db

    @staticmethod
    def generate_session_id() -> str:
        # Generate a unique session ID
        return f"sess_{uuid.uuid4().hex[:12]}"

    async def log_user_message(self, session_id: str, content: str) -> None:
        # Log user message
        await self.db.log_message(session_id, "user", content)

    async def log_assistant_message(self, session_id: str, content: str) -> None:
        # Log assistant message
        await self.db.log_message(session_id, "assistant", content)

    async def log_asset(self, session_id: str, filename: str, fmt: str, path: str, size_kb: int) -> None:
        # Log exported asset
        await self.db.log_asset(session_id, filename, fmt, path, size_kb)

    async def get_assets(self, session_id: str) -> list:
        # Get the asset list of the specified session
        return await self.db.get_assets(session_id)
