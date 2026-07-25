"""SQLAlchemy async database models and session management."""

from __future__ import annotations

import os
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Column, DateTime, String, Text, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """ORM declarative base."""
    pass


class SessionRecord(Base):
    """Session record."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)  # Primary key ID
    session_id = Column(String(64), index=True, nullable=False)  # Session ID
    role = Column(String(16), nullable=False)  # Role: user or assistant
    content = Column(Text, nullable=False)  # Message content
    created_at = Column(DateTime, default=datetime.utcnow)  # Created time


class AssetRecord(Base):
    """Exported asset record."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)  # Primary key ID
    session_id = Column(String(64), index=True, nullable=False)  # Session ID
    filename = Column(String(256), nullable=False)  # Filename
    format = Column(String(16), nullable=False)  # Export format
    path = Column(Text, nullable=False)  # File path
    size_kb = Column(Integer, default=0)  # File size in KB
    created_at = Column(DateTime, default=datetime.utcnow)  # Created time


class Database:
    """Async database manager."""

    def __init__(self, db_url: str):
        self.db_url = db_url  # Database connection URL
        self._engine = None  # Async engine instance
        self._session_maker = None  # Session maker

    async def init(self) -> None:
        """Initialize database tables."""
        db_dir = os.path.dirname(self.db_url.replace("sqlite+aiosqlite:///", ""))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)  # Create database directory
        self._engine = create_async_engine(self.db_url, echo=False)
        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # Create tables synchronously

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()  # Dispose engine resources

    def session(self) -> AsyncSession:
        if not self._session_maker:
            raise RuntimeError("Database not initialized, please call init() first")  # Database not initialized error
        return self._session_maker()

    async def log_message(self, session_id: str, role: str, content: str) -> None:
        try:
            async with self.session() as s:
                record = SessionRecord(session_id=session_id, role=role, content=content)
                s.add(record)
                await s.commit()
        except Exception:
            pass  # Logging failure does not block main flow

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
            pass  # Asset logging failure does not block main flow

    async def get_assets(self, session_id: str) -> list:
        try:
            async with self.session() as s:
                from sqlalchemy import select

                result = await s.execute(
                    select(AssetRecord)
                    .where(AssetRecord.session_id == session_id)
                    .order_by(AssetRecord.created_at.desc())  # Order by created time descending
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
            return []  # Return empty list on query failure
