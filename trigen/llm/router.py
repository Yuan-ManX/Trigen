"""Trigen Model Router.

Unified routing layer that dispatches requests to diverse LLM providers
based on the model identifier. Supports OpenAI-protocol services, Anthropic,
DeepSeek, Qwen, Ollama, and multimodal backends. Each provider is described
by a ModelProvider entry; the router resolves the right client and endpoint
at call time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trigen.llm.router")


class ProviderType(str, Enum):
    """Supported provider categories."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    ZHIPU = "zhipu"
    MOONSHOT = "moonshot"
    BAICHUAN = "baichuan"
    MINIMAX = "minimax"
    SPARK = "spark"
    GROQ = "groq"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    LOCAL = "local"


class Modality(str, Enum):
    """Input/output modalities a model can handle."""

    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE_GEN = "image_gen"
    THREE_D = "3d"
    ANIMATION = "animation"
    VOICE = "voice"


@dataclass
class ModelEntry:
    """A single model in the catalog."""

    id: str
    label: str
    provider: ProviderType
    base_url: str
    api_key_env: str
    description: str
    modalities: List[Modality] = field(default_factory=lambda: [Modality.TEXT])
    max_tokens: int = 4096
    context_window: int = 8192
    openai_compatible: bool = True
    is_open_source: bool = False
    is_local: bool = False


# Full model catalog — text, multimodal, open-source, and local models
MODEL_CATALOG: List[ModelEntry] = [
    # === OpenAI ===
    ModelEntry(
        id="gpt-4o",
        label="GPT-4o",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI flagship multimodal model",
        modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO],
        max_tokens=4096,
        context_window=128000,
    ),
    ModelEntry(
        id="gpt-4o-mini",
        label="GPT-4o Mini",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="Fast and efficient multimodal model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=16384,
        context_window=128000,
    ),
    ModelEntry(
        id="gpt-4-turbo",
        label="GPT-4 Turbo",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="GPT-4 with vision and 128k context",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=128000,
    ),
    ModelEntry(
        id="o1-preview",
        label="o1 Preview",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="Reasoning model for complex tasks",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=32768,
        context_window=128000,
    ),
    ModelEntry(
        id="o1-mini",
        label="o1 Mini",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="Compact reasoning model",
        modalities=[Modality.TEXT],
        max_tokens=65536,
        context_window=128000,
    ),
    # === Anthropic ===
    ModelEntry(
        id="claude-3-5-sonnet-20241022",
        label="Claude 3.5 Sonnet",
        provider=ProviderType.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        description="Anthropic flagship reasoning model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=200000,
        openai_compatible=False,
    ),
    ModelEntry(
        id="claude-3-5-haiku-20241022",
        label="Claude 3.5 Haiku",
        provider=ProviderType.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        description="Fast and lightweight Claude model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=200000,
        openai_compatible=False,
    ),
    ModelEntry(
        id="claude-3-opus-20240229",
        label="Claude 3 Opus",
        provider=ProviderType.ANTHROPIC,
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        description="Most capable Claude 3 model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=200000,
        openai_compatible=False,
    ),
    # === DeepSeek ===
    ModelEntry(
        id="deepseek-chat",
        label="DeepSeek V3",
        provider=ProviderType.DEEPSEEK,
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        description="Open-source MoE chat model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=64000,
        is_open_source=True,
    ),
    ModelEntry(
        id="deepseek-reasoner",
        label="DeepSeek R1",
        provider=ProviderType.DEEPSEEK,
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        description="Open-source reasoning model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=64000,
        is_open_source=True,
    ),
    # === Qwen (Alibaba) ===
    ModelEntry(
        id="qwen-plus",
        label="Qwen Plus",
        provider=ProviderType.QWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        description="Alibaba Cloud Qwen Plus",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=131072,
    ),
    ModelEntry(
        id="qwen-max",
        label="Qwen Max",
        provider=ProviderType.QWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        description="Most capable Qwen model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=32768,
    ),
    ModelEntry(
        id="qwen-vl-max",
        label="Qwen VL Max",
        provider=ProviderType.QWEN,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        description="Qwen vision-language model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=32768,
    ),
    # === Zhipu (GLM) ===
    ModelEntry(
        id="glm-4-plus",
        label="GLM-4 Plus",
        provider=ProviderType.ZHIPU,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        description="Zhipu GLM-4 Plus",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=128000,
    ),
    ModelEntry(
        id="glm-4v",
        label="GLM-4V",
        provider=ProviderType.ZHIPU,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        description="Zhipu vision-language model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=8192,
    ),
    # === Moonshot (Kimi) ===
    ModelEntry(
        id="moonshot-v1-128k",
        label="Kimi (128k)",
        provider=ProviderType.MOONSHOT,
        base_url="https://api.moonshot.cn/v1",
        api_key_env="MOONSHOT_API_KEY",
        description="Moonshot Kimi with 128k context",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=131072,
    ),
    # === Baichuan ===
    ModelEntry(
        id="baichuan4-turbo",
        label="Baichuan4 Turbo",
        provider=ProviderType.BAICHUAN,
        base_url="https://api.baichuan-ai.com/v1",
        api_key_env="BAICHUAN_API_KEY",
        description="Baichuan AI turbo model",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=32768,
    ),
    # === MiniMax ===
    ModelEntry(
        id="abab6.5s-chat",
        label="MiniMax abab6.5s",
        provider=ProviderType.MINIMAX,
        base_url="https://api.minimax.chat/v1",
        api_key_env="MINIMAX_API_KEY",
        description="MiniMax chat model",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=245760,
    ),
    # === Spark (iFlytek) ===
    ModelEntry(
        id="spark-v3.5",
        label="Spark 3.5",
        provider=ProviderType.SPARK,
        base_url="https://spark-api-open.xf-yun.com/v1",
        api_key_env="SPARK_API_KEY",
        description="iFlytek Spark 3.5",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=8192,
    ),
    # === Groq (fast inference) ===
    ModelEntry(
        id="llama-3.3-70b-versatile",
        label="Llama 3.3 70B (Groq)",
        provider=ProviderType.GROQ,
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        description="Llama 3.3 on Groq ultra-fast inference",
        modalities=[Modality.TEXT],
        max_tokens=32768,
        context_window=131072,
        is_open_source=True,
    ),
    ModelEntry(
        id="llama-3.1-8b-instant",
        label="Llama 3.1 8B (Groq)",
        provider=ProviderType.GROQ,
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        description="Llama 3.1 8B instant on Groq",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=131072,
        is_open_source=True,
    ),
    # === Together AI ===
    ModelEntry(
        id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        label="Llama 3.3 70B (Together)",
        provider=ProviderType.TOGETHER,
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        description="Llama 3.3 70B on Together AI",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=131072,
        is_open_source=True,
    ),
    ModelEntry(
        id="Qwen/Qwen2.5-72B-Instruct-Turbo",
        label="Qwen 2.5 72B (Together)",
        provider=ProviderType.TOGETHER,
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        description="Qwen 2.5 72B on Together AI",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=32768,
        is_open_source=True,
    ),
    # === Fireworks AI ===
    ModelEntry(
        id="accounts/fireworks/models/llama-v3p3-70b-instruct",
        label="Llama 3.3 70B (Fireworks)",
        provider=ProviderType.FIREWORKS,
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        description="Llama 3.3 70B on Fireworks AI",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=131072,
        is_open_source=True,
    ),
    # === OpenRouter (aggregator) ===
    ModelEntry(
        id="openrouter/auto",
        label="OpenRouter Auto",
        provider=ProviderType.OPENROUTER,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        description="Auto-route to best model via OpenRouter",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=131072,
    ),
    # === Ollama (local) ===
    ModelEntry(
        id="ollama/llama3.3",
        label="Llama 3.3 (Ollama)",
        provider=ProviderType.OLLAMA,
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        description="Llama 3.3 via local Ollama runtime",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=32768,
        is_open_source=True,
        is_local=True,
    ),
    ModelEntry(
        id="ollama/qwen2.5",
        label="Qwen 2.5 (Ollama)",
        provider=ProviderType.OLLAMA,
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        description="Qwen 2.5 via local Ollama runtime",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=32768,
        is_open_source=True,
        is_local=True,
    ),
    ModelEntry(
        id="ollama/llava",
        label="LLaVA (Ollama)",
        provider=ProviderType.OLLAMA,
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        description="LLaVA vision model via Ollama",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=4096,
        context_window=8192,
        is_open_source=True,
        is_local=True,
    ),
    ModelEntry(
        id="ollama/deepseek-r1",
        label="DeepSeek R1 (Ollama)",
        provider=ProviderType.OLLAMA,
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        description="DeepSeek R1 reasoning model via Ollama",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=65536,
        is_open_source=True,
        is_local=True,
    ),
    # === Trigen offline default ===
    ModelEntry(
        id="trigen-default",
        label="Trigen Default",
        provider=ProviderType.LOCAL,
        base_url="",
        api_key_env="",
        description="Built-in offline rule engine",
        modalities=[Modality.TEXT],
        max_tokens=2048,
        context_window=4096,
        is_local=True,
    ),
    # === Image generation models ===
    ModelEntry(
        id="dall-e-3",
        label="DALL·E 3",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI image generation model",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
    ),
    ModelEntry(
        id="dall-e-2",
        label="DALL·E 2",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI lightweight image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
    ),
    ModelEntry(
        id="stability/stable-diffusion-xl",
        label="Stable Diffusion XL",
        provider=ProviderType.TOGETHER,
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        description="Open-source image generation on Together",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
        is_open_source=True,
    ),
    ModelEntry(
        id="black-forest-labs/FLUX.1-schnell",
        label="FLUX.1 Schnell",
        provider=ProviderType.FIREWORKS,
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        description="FLUX.1 fast image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
        is_open_source=True,
    ),
    # === 3D generation models ===
    ModelEntry(
        id="meshy/text-to-3d",
        label="Meshy Text-to-3D",
        provider=ProviderType.OPENROUTER,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        description="Text-to-3D mesh generation via Meshy",
        modalities=[Modality.THREE_D],
        max_tokens=1,
        context_window=4000,
    ),
    ModelEntry(
        id="tripo/text-to-3d",
        label="Tripo Text-to-3D",
        provider=ProviderType.OPENROUTER,
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        description="Text-to-3D model generation via Tripo",
        modalities=[Modality.THREE_D],
        max_tokens=1,
        context_window=4000,
    ),
    # === Audio / Voice models ===
    ModelEntry(
        id="tts-1",
        label="OpenAI TTS",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI text-to-speech",
        modalities=[Modality.VOICE],
        max_tokens=4096,
        context_window=4096,
    ),
    ModelEntry(
        id="whisper-1",
        label="Whisper",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI speech-to-text transcription",
        modalities=[Modality.AUDIO],
        max_tokens=4096,
        context_window=4096,
    ),
    # === Video generation models ===
    ModelEntry(
        id="sora-1",
        label="Sora",
        provider=ProviderType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        description="OpenAI text-to-video generation",
        modalities=[Modality.VIDEO],
        max_tokens=1,
        context_window=4000,
    ),
    # === Animation models ===
    ModelEntry(
        id="deepseek-ai/anim-v1",
        label="Anim V1",
        provider=ProviderType.TOGETHER,
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        description="Animation sequence generation",
        modalities=[Modality.ANIMATION],
        max_tokens=1,
        context_window=4000,
        is_open_source=True,
    ),
]


class ModelRouter:
    """Routes model requests to the appropriate provider.

    Maintains the full model catalog and resolves the correct base_url and
    API key for a given model id. Supports runtime registration of custom
    models for dynamic provider expansion.
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelEntry] = {m.id: m for m in MODEL_CATALOG}

    def get_model(self, model_id: str) -> Optional[ModelEntry]:
        """Look up a model entry by id."""
        return self._models.get(model_id)

    def list_models(self) -> List[ModelEntry]:
        """Return the full model catalog."""
        return list(self._models.values())

    def list_by_provider(self, provider: ProviderType) -> List[ModelEntry]:
        """Filter models by provider type."""
        return [m for m in self._models.values() if m.provider == provider]

    def list_by_modality(self, modality: Modality) -> List[ModelEntry]:
        """Filter models by modality capability."""
        return [m for m in self._models.values() if modality in m.modalities]

    def list_open_source(self) -> List[ModelEntry]:
        """Return only open-source models."""
        return [m for m in self._models.values() if m.is_open_source]

    def list_local(self) -> List[ModelEntry]:
        """Return only locally-hosted models."""
        return [m for m in self._models.values() if m.is_local]

    def is_generation_model(self, model_id: str) -> bool:
        """Return True if the model is a generation model (image/3D/video/etc.)

        Generation models use dedicated API endpoints (e.g. /images/generations)
        rather than /chat/completions, so they cannot be used directly for
        conversational chat. The orchestrator treats them specially.
        """
        entry = self._models.get(model_id)
        if entry is None:
            return False
        generation_modalities = {
            Modality.IMAGE_GEN,
            Modality.THREE_D,
            Modality.VIDEO,
            Modality.ANIMATION,
            Modality.VOICE,
            Modality.AUDIO,
        }
        return any(mod in generation_modalities for mod in entry.modalities) and not any(
            mod in (Modality.TEXT, Modality.VISION) for mod in entry.modalities
        )

    def register(self, entry: ModelEntry) -> None:
        """Register a custom model at runtime."""
        self._models[entry.id] = entry
        logger.info("Registered custom model: %s", entry.id)

    def resolve(self, model_id: str, fallback_key: str = "", fallback_url: str = "") -> Dict[str, Any]:
        """Resolve a model id into connection parameters.

        Returns a dict with: model, base_url, api_key, openai_compatible,
        provider, modalities. Falls back to environment-based defaults
        when the model is unknown. Custom-provider models registered via
        the ProviderRegistry have their API key retrieved from the registry.
        """
        import os

        entry = self._models.get(model_id)
        if entry is None:
            # Unknown model — use fallback values
            return {
                "model": model_id,
                "base_url": fallback_url or os.environ.get("TRIGEN_LLM_BASE_URL", "https://api.openai.com/v1"),
                "api_key": fallback_key or os.environ.get("TRIGEN_LLM_API_KEY", ""),
                "openai_compatible": True,
                "provider": ProviderType.OPENAI,
                "modalities": [Modality.TEXT],
            }

        # Custom providers store the API key directly in the registry
        api_key = ""
        if model_id.startswith("custom/"):
            try:
                from trigen.llm.provider_registry import registry

                registry_key = registry.resolve_api_key(model_id)
                if registry_key:
                    api_key = registry_key
            except Exception:
                pass

        if not api_key and entry.api_key_env:
            api_key = os.environ.get(entry.api_key_env, "")
        # For local Ollama, allow a dummy key
        if not api_key and entry.is_local and entry.provider == ProviderType.OLLAMA:
            api_key = "ollama"

        return {
            "model": entry.id,
            "base_url": entry.base_url,
            "api_key": api_key,
            "openai_compatible": entry.openai_compatible,
            "provider": entry.provider,
            "modalities": entry.modalities,
        }

    def to_catalog_dict(self) -> List[Dict[str, Any]]:
        """Serialize the catalog for the frontend model selector."""
        result: List[Dict[str, Any]] = []
        for m in self._models.values():
            result.append(
                {
                    "id": m.id,
                    "label": m.label,
                    "provider": m.provider.value,
                    "description": m.description,
                    "modalities": [mod.value for mod in m.modalities],
                    "max_tokens": m.max_tokens,
                    "context_window": m.context_window,
                    "is_open_source": m.is_open_source,
                    "is_local": m.is_local,
                    "api_key_env": m.api_key_env,
                }
            )
        return result


# Global router instance
router = ModelRouter()
