"""Trigen 后端 API 主入口。

Trigen Backend API Main Entry.

FastAPI 应用初始化、中间件注册、路由挂载、生命周期管理。
端口：7100

FastAPI application initialization, middleware registration, router mounting,
and lifecycle management. Port: 7100.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trigen.api.config import config
from trigen.api.models.database import Database
from trigen.api.routers import assets, chat, health, scene, tools
from trigen.api.services.agent_service import AgentService
from trigen.api.services.session_service import SessionService

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trigen.api")  # API 模块日志器 / API module logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库与 Agent，关闭时释放资源。

    Application lifecycle: initialize the database and Agent on startup,
    and release resources on shutdown.
    """
    os.makedirs(config.exports_dir, exist_ok=True)  # 创建导出目录 / Create exports directory

    db = Database(config.db_url)
    await db.init()
    SessionService.get().bind_db(db)
    logger.info("数据库已初始化: %s", config.db_url)  # 数据库初始化完成日志 / Database initialization done log

    # 预初始化 Agent（触发 workspace 创建） / Pre-initialize Agent (triggers workspace creation)
    _ = AgentService.get().orchestrator
    logger.info("Trigen Agent 就绪 | LLM 配置: %s | 端口: %d", AgentService.get().llm_configured, config.port)

    yield

    await db.close()
    logger.info("Trigen API 已关闭")  # API 关闭日志 / API shutdown log


def create_app() -> FastAPI:
    """构建 FastAPI 应用实例。

    Build the FastAPI application instance.
    """
    app = FastAPI(
        title="Trigen API",
        description="AI-Native 3D Creation Agent Platform — Backend API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS / Cross-origin resource sharing middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由 / Routers
    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(chat.router, prefix=api_prefix)
    app.include_router(scene.router, prefix=api_prefix)
    app.include_router(assets.router, prefix=api_prefix)
    app.include_router(tools.router, prefix=api_prefix)

    # 根路由 / Root route
    @app.get("/")
    async def root():
        return {
            "name": "Trigen API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return app


app = create_app()  # 全局 FastAPI 应用实例 / Global FastAPI application instance


if __name__ == "__main__":
    uvicorn.run(
        "trigen.api.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="debug" if config.debug else "info",
    )
