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
    GOOGLE = "google"
    XAI = "xai"
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
    MISTRAL = "mistral"
    COHERE = "cohere"
    PERPLEXITY = "perplexity"
    AI21 = "ai21"
    REPLICATE = "replicate"
    HUGGINGFACE = "huggingface"
    STABILITY = "stability"
    RUNWAY = "runway"
    MESHY = "meshy"
    # Multimodal generation providers (added for broad coverage).
    FAL = "fal"
    ELEVENLABS = "elevenlabs"
    TRIPO = "tripo"
    LUMA = "luma"
    IDEOGRAM = "ideogram"
    LEONARDO = "leonardo"
    RECRAFT = "recraft"
    PIKA = "pika"
    KLING = "kling"
    ASSEMBLYAI = "assemblyai"
    SUNO = "suno"
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
    MUSIC = "music"


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
    # Routing hints used by ``ModelRouter.select_best_for_task``. Lower is
    # cheaper / faster. ``cost_tier`` ranges 0 (free/local) to 4 (premium
    # frontier). ``latency_tier`` ranges 0 (instant) to 4 (multi-minute
    # async jobs). ``capabilities`` carries opt-in features such as
    # ``function_calling``, ``reasoning``, ``json_mode``.
    cost_tier: int = 2
    latency_tier: int = 2
    capabilities: List[str] = field(default_factory=list)
    # Optional default blueprint shipped with the model. Runtime overrides
    # set via the API live in ``blueprint.store`` and take precedence.
    # Imported lazily via ``ModelEntry.blueprint`` property-free annotation
    # to avoid a router <-> blueprint import cycle at module load.
    blueprint: Any = None


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
    # === Mistral AI ===
    ModelEntry(
        id="mistral-large-latest",
        label="Mistral Large",
        provider=ProviderType.MISTRAL,
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        description="Mistral AI flagship model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=128000,
        is_open_source=False,
    ),
    ModelEntry(
        id="mistral-small-latest",
        label="Mistral Small",
        provider=ProviderType.MISTRAL,
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        description="Fast and efficient Mistral model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=32000,
        is_open_source=False,
    ),
    ModelEntry(
        id="pixtral-large-latest",
        label="Pixtral Large",
        provider=ProviderType.MISTRAL,
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        description="Mistral vision-language model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=128000,
        is_open_source=True,
    ),
    ModelEntry(
        id="codestral-latest",
        label="Codestral",
        provider=ProviderType.MISTRAL,
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        description="Mistral code generation model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=32000,
        is_open_source=True,
    ),
    # === Cohere ===
    ModelEntry(
        id="command-r-plus",
        label="Command R+",
        provider=ProviderType.COHERE,
        base_url="https://api.cohere.com/v1",
        api_key_env="COHERE_API_KEY",
        description="Cohere enterprise LLM",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=False,
    ),
    ModelEntry(
        id="command-r",
        label="Command R",
        provider=ProviderType.COHERE,
        base_url="https://api.cohere.com/v1",
        api_key_env="COHERE_API_KEY",
        description="Cohere scalable LLM",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=False,
    ),
    ModelEntry(
        id="command-r7b",
        label="Command R7B",
        provider=ProviderType.COHERE,
        base_url="https://api.cohere.com/v1",
        api_key_env="COHERE_API_KEY",
        description="Cohere efficient model",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=True,
    ),
    # === Perplexity ===
    ModelEntry(
        id="perplexity/sonar-pro",
        label="Sonar Pro",
        provider=ProviderType.PERPLEXITY,
        base_url="https://api.perplexity.ai",
        api_key_env="PPLX_API_KEY",
        description="Perplexity online model with web search",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=127000,
        is_open_source=False,
    ),
    ModelEntry(
        id="perplexity/sonar",
        label="Sonar",
        provider=ProviderType.PERPLEXITY,
        base_url="https://api.perplexity.ai",
        api_key_env="PPLX_API_KEY",
        description="Perplexity fast online model",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=127000,
        is_open_source=False,
    ),
    ModelEntry(
        id="perplexity/llama-3.1-sonar-large-128k-online",
        label="Sonar Large Online",
        provider=ProviderType.PERPLEXITY,
        base_url="https://api.perplexity.ai",
        api_key_env="PPLX_API_KEY",
        description="Llama 3.1 with web search via Perplexity",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=127000,
        is_open_source=True,
    ),
    # === AI21 Labs ===
    ModelEntry(
        id="jamba-1.5-large",
        label="Jamba 1.5 Large",
        provider=ProviderType.AI21,
        base_url="https://api.ai21.com/studio/v1",
        api_key_env="AI21_API_KEY",
        description="AI21 SSM-Transformer hybrid model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=256000,
        is_open_source=True,
    ),
    ModelEntry(
        id="jamba-1.5-mini",
        label="Jamba 1.5 Mini",
        provider=ProviderType.AI21,
        base_url="https://api.ai21.com/studio/v1",
        api_key_env="AI21_API_KEY",
        description="AI21 compact efficient model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=256000,
        is_open_source=True,
    ),
    # === Replicate (hosted open-source) ===
    ModelEntry(
        id="meta/llama-3.1-405b-instruct",
        label="Llama 3.1 405B (Replicate)",
        provider=ProviderType.REPLICATE,
        base_url="https://api.replicate.com/v1",
        api_key_env="REPLICATE_API_TOKEN",
        description="Llama 3.1 405B hosted on Replicate",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=True,
    ),
    ModelEntry(
        id="black-forest-labs/flux-schnell",
        label="FLUX Schnell (Replicate)",
        provider=ProviderType.REPLICATE,
        base_url="https://api.replicate.com/v1",
        api_key_env="REPLICATE_API_TOKEN",
        description="FLUX image generation on Replicate",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
        is_open_source=True,
    ),
    # === Hugging Face (Inference API) ===
    ModelEntry(
        id="meta-llama/Llama-3.3-70B-Instruct",
        label="Llama 3.3 70B (HF)",
        provider=ProviderType.HUGGINGFACE,
        base_url="https://api-inference.huggingface.co/v1",
        api_key_env="HF_TOKEN",
        description="Llama 3.3 via Hugging Face Inference API",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=True,
    ),
    ModelEntry(
        id="Qwen/Qwen2.5-72B-Instruct",
        label="Qwen 2.5 72B (HF)",
        provider=ProviderType.HUGGINGFACE,
        base_url="https://api-inference.huggingface.co/v1",
        api_key_env="HF_TOKEN",
        description="Qwen 2.5 72B via Hugging Face",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=32768,
        is_open_source=True,
    ),
    ModelEntry(
        id="microsoft/Phi-3.5-mini-instruct",
        label="Phi 3.5 Mini (HF)",
        provider=ProviderType.HUGGINGFACE,
        base_url="https://api-inference.huggingface.co/v1",
        api_key_env="HF_TOKEN",
        description="Microsoft Phi 3.5 via Hugging Face",
        modalities=[Modality.TEXT],
        max_tokens=4096,
        context_window=128000,
        is_open_source=True,
    ),
    # === Stability AI (image generation) ===
    ModelEntry(
        id="stable-image-core",
        label="Stable Image Core",
        provider=ProviderType.STABILITY,
        base_url="https://api.stability.ai/v1",
        api_key_env="STABILITY_API_KEY",
        description="Stability AI core image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
        is_open_source=True,
    ),
    ModelEntry(
        id="stable-image-ultra",
        label="Stable Image Ultra",
        provider=ProviderType.STABILITY,
        base_url="https://api.stability.ai/v1",
        api_key_env="STABILITY_API_KEY",
        description="Stability AI ultra quality image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1,
        context_window=4000,
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
    # === Google Gemini ===
    ModelEntry(
        id="gemini-2.0-flash",
        label="Gemini 2.0 Flash",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GOOGLE_API_KEY",
        description="Google Gemini 2.0 Flash multimodal",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=1048576,
    ),
    ModelEntry(
        id="gemini-2.0-pro",
        label="Gemini 2.0 Pro",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GOOGLE_API_KEY",
        description="Google Gemini 2.0 Pro flagship",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=2097152,
    ),
    ModelEntry(
        id="gemini-1.5-pro",
        label="Gemini 1.5 Pro",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GOOGLE_API_KEY",
        description="Google Gemini 1.5 Pro with 2M context",
        modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO],
        max_tokens=8192,
        context_window=2097152,
    ),
    ModelEntry(
        id="gemini-1.5-flash",
        label="Gemini 1.5 Flash",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GOOGLE_API_KEY",
        description="Fast and efficient Gemini model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=1048576,
    ),
    # === xAI Grok ===
    ModelEntry(
        id="grok-2-latest",
        label="Grok 2",
        provider=ProviderType.XAI,
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        description="xAI Grok 2 conversational model",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=131072,
    ),
    ModelEntry(
        id="grok-2-vision-latest",
        label="Grok 2 Vision",
        provider=ProviderType.XAI,
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        description="xAI Grok 2 with vision capability",
        modalities=[Modality.TEXT, Modality.VISION],
        max_tokens=8192,
        context_window=32768,
    ),
    ModelEntry(
        id="grok-beta",
        label="Grok Beta",
        provider=ProviderType.XAI,
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        description="xAI Grok beta model",
        modalities=[Modality.TEXT],
        max_tokens=8192,
        context_window=131072,
    ),
    # === Runway video generation ===
    ModelEntry(
        id="runway/gen3-alpha",
        label="Runway Gen-3 Alpha",
        provider=ProviderType.RUNWAY,
        base_url="https://api.runwayml.com/v1",
        api_key_env="RUNWAY_API_KEY",
        description="Runway Gen-3 text-to-video",
        modalities=[Modality.VIDEO],
        max_tokens=1,
        context_window=4000,
    ),
    ModelEntry(
        id="runway/gen3-turbo",
        label="Runway Gen-3 Turbo",
        provider=ProviderType.RUNWAY,
        base_url="https://api.runwayml.com/v1",
        api_key_env="RUNWAY_API_KEY",
        description="Runway Gen-3 Turbo fast video generation",
        modalities=[Modality.VIDEO],
        max_tokens=1,
        context_window=4000,
    ),
    # === Meshy 3D generation (direct API) ===
    ModelEntry(
        id="meshy-direct/text-to-3d",
        label="Meshy Text-to-3D (Direct)",
        provider=ProviderType.MESHY,
        base_url="https://api.meshy.ai/v2",
        api_key_env="MESHY_API_KEY",
        description="Meshy direct text-to-3D mesh generation",
        modalities=[Modality.THREE_D],
        max_tokens=1,
        context_window=4000,
    ),
    ModelEntry(
        id="meshy-direct/image-to-3d",
        label="Meshy Image-to-3D (Direct)",
        provider=ProviderType.MESHY,
        base_url="https://api.meshy.ai/v2",
        api_key_env="MESHY_API_KEY",
        description="Meshy direct image-to-3D reconstruction",
        modalities=[Modality.THREE_D],
        max_tokens=1,
        context_window=4000,
    ),
    # === fal.ai (multimodal generation aggregator) ===
    ModelEntry(
        id="fal-ai/flux-pro",
        label="FLUX Pro (fal)",
        provider=ProviderType.FAL,
        base_url="https://fal.run",
        api_key_env="FAL_API_KEY",
        description="FLUX Pro image generation via fal.ai",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=2,
    ),
    ModelEntry(
        id="fal-ai/flux-dev",
        label="FLUX Dev (fal)",
        provider=ProviderType.FAL,
        base_url="https://fal.run",
        api_key_env="FAL_API_KEY",
        description="FLUX Dev image generation via fal.ai",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=2,
    ),
    ModelEntry(
        id="fal-ai/kling-video",
        label="Kling Video (fal)",
        provider=ProviderType.FAL,
        base_url="https://fal.run",
        api_key_env="FAL_API_KEY",
        description="Kling text-to-video via fal.ai",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    ModelEntry(
        id="fal-ai/tripo-3d",
        label="Tripo 3D (fal)",
        provider=ProviderType.FAL,
        base_url="https://fal.run",
        api_key_env="FAL_API_KEY",
        description="Tripo text-to-3D via fal.ai",
        modalities=[Modality.THREE_D],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    # === ElevenLabs (TTS) ===
    ModelEntry(
        id="eleven-multilingual-v2",
        label="ElevenLabs Multilingual V2",
        provider=ProviderType.ELEVENLABS,
        base_url="https://api.elevenlabs.io/v1",
        api_key_env="ELEVENLABS_API_KEY",
        description="ElevenLabs multilingual text-to-speech",
        modalities=[Modality.VOICE],
        max_tokens=4096, context_window=4096,
        cost_tier=3, latency_tier=1,
    ),
    ModelEntry(
        id="eleven-turbo-v2-5",
        label="ElevenLabs Turbo V2.5",
        provider=ProviderType.ELEVENLABS,
        base_url="https://api.elevenlabs.io/v1",
        api_key_env="ELEVENLABS_API_KEY",
        description="ElevenLabs low-latency TTS",
        modalities=[Modality.VOICE],
        max_tokens=4096, context_window=4096,
        cost_tier=2, latency_tier=0,
    ),
    ModelEntry(
        id="eleven-monolingual-v1",
        label="ElevenLabs Monolingual V1",
        provider=ProviderType.ELEVENLABS,
        base_url="https://api.elevenlabs.io/v1",
        api_key_env="ELEVENLABS_API_KEY",
        description="ElevenLabs English-only TTS",
        modalities=[Modality.VOICE],
        max_tokens=4096, context_window=4096,
        cost_tier=2, latency_tier=1,
    ),
    # === Tripo (direct 3D) ===
    ModelEntry(
        id="tripo-direct/text-to-3d",
        label="Tripo Text-to-3D (Direct)",
        provider=ProviderType.TRIPO,
        base_url="https://api.tripo3d.ai/v2",
        api_key_env="TRIPO_API_KEY",
        description="Tripo direct text-to-3D mesh generation",
        modalities=[Modality.THREE_D],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    ModelEntry(
        id="tripo-direct/image-to-3d",
        label="Tripo Image-to-3D (Direct)",
        provider=ProviderType.TRIPO,
        base_url="https://api.tripo3d.ai/v2",
        api_key_env="TRIPO_API_KEY",
        description="Tripo direct image-to-3D reconstruction",
        modalities=[Modality.THREE_D],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    # === Luma (video) ===
    ModelEntry(
        id="luma/ray2",
        label="Luma Ray 2",
        provider=ProviderType.LUMA,
        base_url="https://api.lumalabs.ai/v1",
        api_key_env="LUMA_API_KEY",
        description="Luma Ray 2 text-to-video",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    ModelEntry(
        id="luma/dream-machine",
        label="Luma Dream Machine",
        provider=ProviderType.LUMA,
        base_url="https://api.lumalabs.ai/v1",
        api_key_env="LUMA_API_KEY",
        description="Luma Dream Machine video generation",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=4,
    ),
    # === Ideogram (image) ===
    ModelEntry(
        id="ideogram-v3",
        label="Ideogram V3",
        provider=ProviderType.IDEOGRAM,
        base_url="https://api.ideogram.ai/v1",
        api_key_env="IDEOGRAM_API_KEY",
        description="Ideogram V3 image generation with strong typography",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=2,
    ),
    ModelEntry(
        id="ideogram-v2-turbo",
        label="Ideogram V2 Turbo",
        provider=ProviderType.IDEOGRAM,
        base_url="https://api.ideogram.ai/v1",
        api_key_env="IDEOGRAM_API_KEY",
        description="Ideogram V2 Turbo fast image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=1, latency_tier=1,
    ),
    # === Leonardo (image) ===
    ModelEntry(
        id="leonardo/phoenix",
        label="Leonardo Phoenix",
        provider=ProviderType.LEONARDO,
        base_url="https://cloud.leonardo.ai/api/rest/v1",
        api_key_env="LEONARDO_API_KEY",
        description="Leonardo Phoenix flagship image model",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=2,
    ),
    ModelEntry(
        id="leonardo/lightning",
        label="Leonardo Lightning",
        provider=ProviderType.LEONARDO,
        base_url="https://cloud.leonardo.ai/api/rest/v1",
        api_key_env="LEONARDO_API_KEY",
        description="Leonardo Lightning fast image generation",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=1, latency_tier=1,
    ),
    # === Recraft (image) ===
    ModelEntry(
        id="recraft-v3",
        label="Recraft V3",
        provider=ProviderType.RECRAFT,
        base_url="https://external.api.recraft.ai/v1",
        api_key_env="RECRAFT_API_KEY",
        description="Recraft V3 image generation with vector output",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=2,
    ),
    ModelEntry(
        id="recraft-20b",
        label="Recraft 20B",
        provider=ProviderType.RECRAFT,
        base_url="https://external.api.recraft.ai/v1",
        api_key_env="RECRAFT_API_KEY",
        description="Recraft 20B high-fidelity image model",
        modalities=[Modality.IMAGE_GEN],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=2,
    ),
    # === Pika (video) ===
    ModelEntry(
        id="pika/pika-2.0",
        label="Pika 2.0",
        provider=ProviderType.PIKA,
        base_url="https://api.pika.art/v1",
        api_key_env="PIKA_API_KEY",
        description="Pika 2.0 text-to-video generation",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=4,
    ),
    ModelEntry(
        id="pika/pika-scenes",
        label="Pika Scenes",
        provider=ProviderType.PIKA,
        base_url="https://api.pika.art/v1",
        api_key_env="PIKA_API_KEY",
        description="Pika Scenes cinematic video generation",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    # === Kling (video, direct) ===
    ModelEntry(
        id="kling/v2-master",
        label="Kling V2 Master",
        provider=ProviderType.KLING,
        base_url="https://api.klingai.com/v1",
        api_key_env="KLING_API_KEY",
        description="Kling V2 Master text-to-video direct API",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=3, latency_tier=4,
    ),
    ModelEntry(
        id="kling/v1-6-pro",
        label="Kling V1.6 Pro",
        provider=ProviderType.KLING,
        base_url="https://api.klingai.com/v1",
        api_key_env="KLING_API_KEY",
        description="Kling V1.6 Pro text-to-video direct API",
        modalities=[Modality.VIDEO],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=4,
    ),
    # === AssemblyAI (transcription) ===
    ModelEntry(
        id="assemblyai/best",
        label="AssemblyAI Best",
        provider=ProviderType.ASSEMBLYAI,
        base_url="https://api.assemblyai.com/v2",
        api_key_env="ASSEMBLYAI_API_KEY",
        description="AssemblyAI Best-NL speech-to-text",
        modalities=[Modality.AUDIO],
        max_tokens=1, context_window=32000,
        cost_tier=2, latency_tier=1,
    ),
    ModelEntry(
        id="assemblyai/nano",
        label="AssemblyAI Nano",
        provider=ProviderType.ASSEMBLYAI,
        base_url="https://api.assemblyai.com/v2",
        api_key_env="ASSEMBLYAI_API_KEY",
        description="AssemblyAI Nano fast streaming transcription",
        modalities=[Modality.AUDIO],
        max_tokens=1, context_window=32000,
        cost_tier=1, latency_tier=0,
    ),
    # === Suno (music) ===
    ModelEntry(
        id="suno/v4.5",
        label="Suno V4.5",
        provider=ProviderType.SUNO,
        base_url="https://api.suno.ai/v1",
        api_key_env="SUNO_API_KEY",
        description="Suno V4.5 music generation",
        modalities=[Modality.MUSIC],
        max_tokens=1, context_window=4000,
        cost_tier=2, latency_tier=4,
    ),
    ModelEntry(
        id="suno/v3.5",
        label="Suno V3.5",
        provider=ProviderType.SUNO,
        base_url="https://api.suno.ai/v1",
        api_key_env="SUNO_API_KEY",
        description="Suno V3.5 music generation",
        modalities=[Modality.MUSIC],
        max_tokens=1, context_window=4000,
        cost_tier=1, latency_tier=3,
    ),
    # === Google Gemini (native API format) ===
    ModelEntry(
        id="gemini-native/gemini-2.5-pro",
        label="Gemini 2.5 Pro (Native)",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GOOGLE_API_KEY",
        description="Gemini 2.5 Pro via native API format",
        modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO],
        max_tokens=8192, context_window=2097152,
        cost_tier=3, latency_tier=2,
        openai_compatible=False,
        capabilities=["function_calling", "json_mode"],
    ),
    ModelEntry(
        id="gemini-native/gemini-2.5-flash",
        label="Gemini 2.5 Flash (Native)",
        provider=ProviderType.GOOGLE,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GOOGLE_API_KEY",
        description="Gemini 2.5 Flash via native API format",
        modalities=[Modality.TEXT, Modality.VISION, Modality.AUDIO],
        max_tokens=8192, context_window=1048576,
        cost_tier=1, latency_tier=1,
        openai_compatible=False,
        capabilities=["function_calling", "json_mode"],
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
            Modality.MUSIC,
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
                "api_key_env": "TRIGEN_LLM_API_KEY",
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
            # Runtime key store first (set via UI), then process env
            try:
                from trigen.llm.key_store import store as _key_store

                api_key = _key_store.get_key(entry.api_key_env)
            except Exception:
                api_key = os.environ.get(entry.api_key_env, "")
        # For local Ollama, allow a dummy key
        if not api_key and entry.is_local and entry.provider == ProviderType.OLLAMA:
            api_key = "ollama"

        return {
            "model": entry.id,
            "base_url": entry.base_url,
            "api_key": api_key,
            "api_key_env": entry.api_key_env,
            "openai_compatible": entry.openai_compatible,
            "provider": entry.provider,
            "modalities": entry.modalities,
        }

    def list_available_chat_models(self) -> List[str]:
        """Return model ids that can power conversational chat right now.

        A model qualifies when it has TEXT or VISION modality, is not a
        generation-only model, and has an API key configured (or is the
        offline default / a local Ollama model).
        """
        result: List[str] = []
        for entry in self._models.values():
            if self.is_generation_model(entry.id):
                continue
            if not any(m in (Modality.TEXT, Modality.VISION) for m in entry.modalities):
                continue
            params = self.resolve(entry.id)
            if params.get("api_key") or entry.id == "trigen-default":
                result.append(entry.id)
        return result

    def build_fallback_chain(
        self,
        primary: Optional[str] = None,
        preferred_modality: Modality = Modality.TEXT,
    ) -> List[str]:
        """Build an ordered fallback chain of model ids.

        The primary model (if any) is tried first. Then available chat
        models are appended in priority order: large cloud models first,
        then open-source hosted models, then local Ollama models, and
        finally the offline default. Duplicates are removed.

        When ``preferred_modality`` is VISION, models that actually declare
        the VISION capability are sorted ahead of text-only models so the
        first attempt can handle image input. Cost and latency tiers act
        as tiebreakers (cheaper and faster first).
        """
        chain: List[str] = []
        seen: set[str] = set()

        def _add(model_id: str) -> None:
            if model_id and model_id not in seen:
                chain.append(model_id)
                seen.add(model_id)

        if primary:
            _add(primary)

        available = self.list_available_chat_models()

        def _priority(mid: str) -> tuple:
            entry = self._models.get(mid)
            if not entry:
                return (99, 99, 99)
            if entry.id == "trigen-default":
                return (90, 0, 0)
            tier = 80 if entry.is_local else (50 if entry.is_open_source else 10)
            # Prefer models that declare the requested modality.
            modality_bonus = 0 if preferred_modality in entry.modalities else 20
            return (tier + modality_bonus, entry.cost_tier, entry.latency_tier)

        for mid in sorted(available, key=_priority):
            _add(mid)

        _add("trigen-default")
        return chain

    def select_best_for_task(
        self,
        modality: Modality,
        preferred: Optional[str] = None,
        max_cost_tier: int = 4,
        max_latency_tier: int = 4,
        require_capability: Optional[str] = None,
    ) -> Optional[str]:
        """Pick the best model for a task given modality + constraints.

        Considers only models that declare ``modality`` and have an API key
        configured (or are the offline default). Filters by cost / latency
        caps and optional capability tag, then picks the (cost, latency,
        tier) minimum. Returns ``None`` when nothing satisfies the filter.

        This is the modality-aware entry point that generation tools use
        when no explicit model id is supplied by the caller.
        """
        if preferred:
            entry = self.get_model(preferred)
            if entry and modality in entry.modalities:
                resolved = self.resolve(preferred)
                if resolved.get("api_key") or entry.id == "trigen-default":
                    if (entry.cost_tier <= max_cost_tier
                            and entry.latency_tier <= max_latency_tier
                            and (not require_capability
                                 or require_capability in entry.capabilities)):
                        return preferred

        candidates: List[tuple] = []
        for entry in self.list_by_modality(modality):
            if entry.cost_tier > max_cost_tier:
                continue
            if entry.latency_tier > max_latency_tier:
                continue
            if require_capability and require_capability not in entry.capabilities:
                continue
            resolved = self.resolve(entry.id)
            if not (resolved.get("api_key") or entry.id == "trigen-default"):
                continue
            candidates.append((entry.cost_tier, entry.latency_tier, entry.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

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
                    "cost_tier": m.cost_tier,
                    "latency_tier": m.latency_tier,
                    "capabilities": list(m.capabilities),
                }
            )
        return result


# Global router instance
router = ModelRouter()
