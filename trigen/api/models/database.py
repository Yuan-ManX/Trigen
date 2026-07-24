"""SQLAlchemy 异步数据库模型与会话管理。

SQLAlchemy async database models and session management.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Column, DateTime, String, Text, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """ORM 基类 / ORM declarative base."""
    pass


class SessionRecord(Base):
    """会话记录。

    Session record.
    """

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)  # 主键 ID / Primary key ID
    session_id = Column(String(64), index=True, nullable=False)  # 会话 ID / Session ID
    role = Column(String(16), nullable=False)  # user / assistant / 角色: user 或 assistant
    content = Column(Text, nullable=False)  # 消息内容 / Message content
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间 / Created time


class AssetRecord(Base):
    """导出资产记录。

    Exported asset record.
    """

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)  # 主键 ID / Primary key ID
    session_id = Column(String(64), index=True, nullable=False)  # 会话 ID / Session ID
    filename = Column(String(256), nullable=False)  # 文件名 / Filename
    format = Column(String(16), nullable=False)  # 导出格式 / Export format
    path = Column(Text, nullable=False)  # 文件路径 / File path
    size_kb = Column(Integer, default=0)  # 文件大小(KB) / File size in KB
    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间 / Created time


class Database:
    """异步数据库管理器。

    Async database manager.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url  # 数据库连接 URL / Database connection URL
        self._engine = None  # 异步引擎实例 / Async engine instance
        self._session_maker = None  # 会话工厂 / Session maker

    async def init(self) -> None:
        """初始化数据库表。

        Initialize database tables.
        """
        db_dir = os.path.dirname(self.db_url.replace("sqlite+aiosqlite:///", ""))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)  # 创建数据库目录 / Create database directory
        self._engine = create_async_engine(self.db_url, echo=False)
        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # 同步建表 / Create tables synchronously

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()  # 释放引擎资源 / Dispose engine resources

    def session(self) -> AsyncSession:
        if not self._session_maker:
            raise RuntimeError("数据库未初始化，请先调用 init()")  # 数据库未初始化错误 / Database not initialized error
        return self._session_maker()

    async def log_message(self, session_id: str, role: str, content: str) -> None:
        try:
            async with self.session() as s:
                record = SessionRecord(session_id=session_id, role=role, content=content)
                s.add(record)
                await s.commit()
        except Exception:
            pass  # 日志失败不阻断主流程 / Logging failure does not block main flow

    async def log_asset(self, session_id: str, filename: str, fmt: str, path: str, size_kb: int) -> None:
        try:
            async with self.session() as s:
                record = AssetRecord(
                    session_id=session_id,
                    filename=filename,
                    format=fmt,
                    path=path,
                    size_kb=size_kb,
                )
                s.add(record)
                await s.commit()
        except Exception:
            pass  # 资产记录失败不阻断主流程 / Asset logging failure does not block main flow

    async def get_assets(self, session_id: str) -> list:
        try:
            async with self.session() as s:
                from sqlalchemy import select

                result = await s.execute(
                    select(AssetRecord)
                    .where(AssetRecord.session_id == session_id)
                    .order_by(AssetRecord.created_at.desc())  # 按创建时间倒序 / Order by created time descending
                )
                return [
                    {
                        "filename": r.filename,
                        "format": r.format,
                        "size_kb": r.size_kb,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in result.scalars()
                ]
        except Exception:
            return []  # 查询失败返回空列表 / Return empty list on query failure
