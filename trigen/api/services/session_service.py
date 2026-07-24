"""会话服务层，管理会话状态与消息持久化。

Session service layer, managing session state and message persistence.
"""

from __future__ import annotations

import uuid
from typing import Optional

from trigen.api.models.database import Database


class SessionService:
    """会话管理服务。

    Session management service.
    """

    _instance: Optional["SessionService"] = None  # 单例实例 / Singleton instance

    @classmethod
    def get(cls) -> "SessionService":
        if cls._instance is None:
            cls._instance = cls()  # 懒加载创建单例 / Lazily create singleton
        return cls._instance

    def __init__(self):
        self._db: Optional[Database] = None  # 数据库实例 / Database instance

    def bind_db(self, db: Database) -> None:
        self._db = db  # 绑定数据库实例 / Bind database instance

    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("数据库未绑定")  # 数据库未绑定错误 / Database not bound error
        return self._db

    @staticmethod
    def generate_session_id() -> str:
        # 生成唯一会话 ID / Generate a unique session ID
        return f"sess_{uuid.uuid4().hex[:12]}"

    async def log_user_message(self, session_id: str, content: str) -> None:
        # 记录用户消息 / Log user message
        await self.db.log_message(session_id, "user", content)

    async def log_assistant_message(self, session_id: str, content: str) -> None:
        # 记录助手消息 / Log assistant message
        await self.db.log_message(session_id, "assistant", content)

    async def log_asset(self, session_id: str, filename: str, fmt: str, path: str, size_kb: int) -> None:
        # 记录导出资产 / Log exported asset
        await self.db.log_asset(session_id, filename, fmt, path, size_kb)

    async def get_assets(self, session_id: str) -> list:
        # 获取指定会话的资产列表 / Get the asset list of the specified session
        return await self.db.get_assets(session_id)
