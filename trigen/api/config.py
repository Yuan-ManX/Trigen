"""Trigen API 配置 / Trigen API Configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env(key: str, default: str = "") -> str:
    # 读取环境变量，未设置时返回默认值 / Read environment variable, return default if unset
    return os.environ.get(key, default) or default


@dataclass
class APIConfig:
    """后端 API 服务配置。

    Backend API service configuration.
    """

    host: str = field(default_factory=lambda: _env("TRIGEN_API_HOST", "0.0.0.0"))  # 监听地址 / Listen host
    port: int = field(default_factory=lambda: int(_env("TRIGEN_API_PORT", "7100")))  # 监听端口 / Listen port
    cors_origins: list = field(  # CORS 允许来源列表 / CORS allowed origins list
        default_factory=lambda: [
            o.strip()
            for o in _env("TRIGEN_CORS_ORIGINS", "http://localhost:4100,http://localhost:5100,http://127.0.0.1:4100").split(
                ","
            )
            if o.strip()
        ]
    )
    db_url: str = field(  # 数据库连接 URL / Database connection URL
        default_factory=lambda: _env(
            "TRIGEN_DB_URL", f"sqlite+aiosqlite:///{os.path.join(os.getcwd(), '.trigen', 'trigen.db')}"
        )
    )
    exports_dir: str = field(  # 导出文件目录 / Exports directory
        default_factory=lambda: _env(
            "TRIGEN_EXPORTS_DIR", os.path.join(os.getcwd(), ".trigen", "workspace", "exports")
        )
    )
    debug: bool = field(default_factory=lambda: _env("TRIGEN_DEBUG", "0") == "1")  # 调试模式 / Debug mode


config = APIConfig()  # 全局配置实例 / Global config instance
