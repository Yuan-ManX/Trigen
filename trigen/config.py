"""Trigen Agent 全局配置 / Trigen Agent global configuration.

通过环境变量注入，未配置时使用安全默认值，保证开箱即用。
Configuration is injected via environment variables; safe defaults are used
when unset, ensuring out-of-the-box usability.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


@dataclass
class LLMConfig:
    """LLM 客户端配置，兼容 OpenAI 协议（含本地推理服务）。

    LLM client configuration, compatible with the OpenAI protocol
    (including local inference services).
    """

    api_key: str = field(default_factory=lambda: _env("TRIGEN_LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: _env("TRIGEN_LLM_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: _env("TRIGEN_LLM_MODEL", "gpt-4o-mini"))
    temperature: float = field(default_factory=lambda: float(_env("TRIGEN_LLM_TEMPERATURE", "0.6")))
    max_tokens: int = field(default_factory=lambda: int(_env("TRIGEN_LLM_MAX_TOKENS", "2048")))
    timeout: float = field(default_factory=lambda: float(_env("TRIGEN_LLM_TIMEOUT", "60")))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class AgentConfig:
    """Agent 运行时配置。

    Agent runtime configuration.
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    max_iterations: int = field(default_factory=lambda: int(_env("TRIGEN_AGENT_MAX_ITER", "8")))
    memory_window: int = field(default_factory=lambda: int(_env("TRIGEN_AGENT_MEMORY_WINDOW", "12")))
    workspace_dir: str = field(default_factory=lambda: _env("TRIGEN_WORKSPACE", os.path.join(os.getcwd(), ".trigen", "workspace")))
    enable_streaming: bool = field(default_factory=lambda: _env("TRIGEN_STREAMING", "1") == "1")

    def ensure_workspace(self) -> str:
        os.makedirs(self.workspace_dir, exist_ok=True)  # 创建工作空间目录 / Create workspace directory
        os.makedirs(os.path.join(self.workspace_dir, "exports"), exist_ok=True)  # 创建导出子目录 / Create exports subdirectory
        return self.workspace_dir
