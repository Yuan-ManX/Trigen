"""Models router — exposes the LLM model catalog to the frontend.

Provides the full list of supported models grouped by provider, including
text, multimodal, open-source, and local models. The frontend uses this
to render a categorized model selector. Also exposes a generation endpoint
for multimodal models (image/3D/audio/video) that use dedicated endpoints,
an availability checker, a custom-provider registry, and a pipeline
executor for multi-step generation workflows.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from trigen.llm.router import router as model_router, ProviderType
from trigen.llm.multimodal import dispatcher as multimodal_dispatcher
from trigen.llm.availability import checker as availability_checker
from trigen.llm.ollama_connector import connector as ollama_connector
from trigen.llm.provider_registry import (
    CustomModel,
    CustomProvider,
    registry as provider_registry,
)
from trigen.llm.pipeline import orchestrator as pipeline_orchestrator, parse_pipeline
from trigen.llm.key_store import store as key_store
from trigen.llm.model_discovery import discover_all

logger = logging.getLogger("trigen.api.models")
router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """List all available LLM models in the catalog."""
    catalog = model_router.to_catalog_dict()
    return {"models": catalog, "count": len(catalog)}


@router.get("/models/providers")
async def list_providers() -> Dict[str, Any]:
    """List all supported LLM providers with their models."""
    providers: Dict[str, List[Dict[str, Any]]] = {}
    for entry in model_router.list_models():
        provider = entry.provider.value
        if provider not in providers:
            providers[provider] = []
        providers[provider].append(
            {
                "id": entry.id,
                "label": entry.label,
                "description": entry.description,
                "modalities": [m.value for m in entry.modalities],
                "max_tokens": entry.max_tokens,
                "context_window": entry.context_window,
                "is_open_source": entry.is_open_source,
                "is_local": entry.is_local,
                "api_key_env": entry.api_key_env,
            }
        )
    return {"providers": providers, "count": len(providers)}


@router.get("/models/modalities")
async def list_modalities() -> Dict[str, Any]:
    """List models grouped by modality capability."""
    from trigen.llm.router import Modality

    modalities: Dict[str, List[Dict[str, Any]]] = {}
    for mod in Modality:
        models = model_router.list_by_modality(mod)
        if models:
            modalities[mod.value] = [
                {
                    "id": m.id,
                    "label": m.label,
                    "provider": m.provider.value,
                    "description": m.description,
                }
                for m in models
            ]
    return {"modalities": modalities, "count": len(modalities)}


@router.get("/models/open-source")
async def list_open_source_models() -> Dict[str, Any]:
    """List only open-source models."""
    models = model_router.list_open_source()
    return {
        "models": [
            {
                "id": m.id,
                "label": m.label,
                "provider": m.provider.value,
                "description": m.description,
                "is_local": m.is_local,
            }
            for m in models
        ],
        "count": len(models),
    }


@router.get("/models/local")
async def list_local_models() -> Dict[str, Any]:
    """List only locally-hosted models (Ollama, offline)."""
    models = model_router.list_local()
    return {
        "models": [
            {
                "id": m.id,
                "label": m.label,
                "provider": m.provider.value,
                "description": m.description,
                "base_url": m.base_url,
            }
            for m in models
        ],
        "count": len(models),
    }


class GenerateImageRequest(BaseModel):
    """Request body for image generation."""

    model: str = Field(..., description="Model id, e.g. dall-e-3")
    prompt: str = Field(..., description="Text prompt for the image")
    size: str = Field("1024x1024", description="Image size")
    n: int = Field(1, description="Number of images")


class Generate3DRequest(BaseModel):
    """Request body for 3D asset generation."""

    model: str = Field(..., description="Model id, e.g. meshy/text-to-3d")
    prompt: str = Field(..., description="Text prompt for the 3D asset")
    output_format: str = Field("glb", description="Output format")


class TTSRequest(BaseModel):
    """Request body for text-to-speech."""

    model: str = Field("tts-1", description="TTS model id")
    text: str = Field(..., description="Text to synthesize")
    voice: str = Field("alloy", description="Voice id")


class TranscribeRequest(BaseModel):
    """Request body for audio transcription."""

    model: str = Field("whisper-1", description="Transcription model id")
    audio_base64: str = Field(..., description="Base64-encoded audio")
    mime_type: str = Field("audio/wav", description="Audio MIME type")


@router.post("/models/generate-image")
async def generate_image(req: GenerateImageRequest) -> Dict[str, Any]:
    """Generate an image using a multimodal model."""
    result = await multimodal_dispatcher.generate_image(
        model_id=req.model, prompt=req.prompt, size=req.size, n=req.n
    )
    return {
        "success": result.success,
        "modality": result.modality,
        "model": result.model,
        "url": result.url,
        "base64_data": result.base64_data,
        "mime_type": result.mime_type,
        "error": result.error,
    }


@router.post("/models/generate-3d")
async def generate_3d(req: Generate3DRequest) -> Dict[str, Any]:
    """Generate a 3D asset using a multimodal model."""
    result = await multimodal_dispatcher.generate_3d(
        model_id=req.model, prompt=req.prompt, output_format=req.output_format
    )
    return {
        "success": result.success,
        "modality": result.modality,
        "model": result.model,
        "url": result.url,
        "error": result.error,
        "raw": result.raw,
    }


@router.post("/models/tts")
async def text_to_speech(req: TTSRequest) -> Dict[str, Any]:
    """Synthesize speech from text."""
    result = await multimodal_dispatcher.synthesize_speech(
        model_id=req.model, text=req.text, voice=req.voice
    )
    return {
        "success": result.success,
        "modality": result.modality,
        "model": result.model,
        "base64_data": result.base64_data,
        "mime_type": result.mime_type,
        "error": result.error,
    }


@router.post("/models/transcribe")
async def transcribe_audio(req: TranscribeRequest) -> Dict[str, Any]:
    """Transcribe audio to text."""
    result = await multimodal_dispatcher.transcribe_audio(
        model_id=req.model, audio_base64=req.audio_base64, mime_type=req.mime_type
    )
    return {
        "success": result.success,
        "modality": result.modality,
        "model": result.model,
        "text": result.raw.get("text", ""),
        "error": result.error,
    }


# ===== Availability / status endpoints =====


@router.get("/models/availability")
async def model_availability() -> Dict[str, Any]:
    """Report which models are currently usable (API key set / daemon running)."""
    items = await availability_checker.check_all()
    available = sum(1 for i in items if i.available)
    return {
        "models": [
            {
                "id": i.id,
                "label": i.label,
                "provider": i.provider,
                "available": i.available,
                "reason": i.reason,
                "modalities": i.modalities,
                "is_local": i.is_local,
                "is_open_source": i.is_open_source,
                "is_generation": i.is_generation,
            }
            for i in items
        ],
        "total": len(items),
        "available": available,
    }


@router.get("/models/ollama")
async def list_ollama_models() -> Dict[str, Any]:
    """List models installed in the local Ollama daemon."""
    models = await ollama_connector.list_models(force_refresh=True)
    return {
        "models": [
            {
                "name": m.name,
                "size_bytes": m.size_bytes,
                "digest": m.digest,
                "family": m.family,
                "parameter_size": m.parameter_size,
                "quantization": m.quantization,
            }
            for m in models
        ],
        "count": len(models),
        "reachable": len(models) > 0 or True,  # Daemon reachable if no exception
    }


# ===== Custom provider registry endpoints =====


class RegisterProviderRequest(BaseModel):
    """Request body for registering a custom provider."""

    name: str = Field(..., description="Provider name (unique)")
    base_url: str = Field(..., description="OpenAI-compatible base URL")
    api_key: str = Field("", description="API key for the provider")
    openai_compatible: bool = Field(True, description="Whether the endpoint follows the OpenAI protocol")
    is_local: bool = Field(False, description="Whether this is a local endpoint")
    models: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Model definitions: {id, label, description, modalities, max_tokens, context_window}",
    )


@router.get("/models/providers/custom")
async def list_custom_providers() -> Dict[str, Any]:
    """List all registered custom providers."""
    providers = provider_registry.list_providers()
    return {"providers": providers, "count": len(providers)}


@router.post("/models/providers/custom")
async def register_custom_provider(req: RegisterProviderRequest) -> Dict[str, Any]:
    """Register a new custom provider at runtime."""
    models = [
        CustomModel(
            id=m.get("id", ""),
            label=m.get("label", m.get("id", "")),
            description=m.get("description", ""),
            modalities=m.get("modalities", ["text"]),
            max_tokens=int(m.get("max_tokens", 4096)),
            context_window=int(m.get("context_window", 8192)),
        )
        for m in req.models
    ]
    prov = CustomProvider(
        name=req.name,
        base_url=req.base_url,
        api_key=req.api_key,
        openai_compatible=req.openai_compatible,
        is_local=req.is_local,
        models=models,
    )
    result = await provider_registry.register_provider(prov)
    return result


@router.delete("/models/providers/custom/{name}")
async def remove_custom_provider(name: str) -> Dict[str, Any]:
    """Remove a custom provider by name."""
    removed = await provider_registry.remove_provider(name)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")
    return {"removed": True, "name": name}


# ===== Pipeline execution endpoint =====


class RunPipelineRequest(BaseModel):
    """Request body for executing a multi-step generation pipeline."""

    name: str = Field("untitled", description="Pipeline name")
    nodes: List[Dict[str, Any]] = Field(..., description="Pipeline node definitions")


@router.post("/models/pipeline")
async def run_pipeline(req: RunPipelineRequest) -> Dict[str, Any]:
    """Execute a multi-step generation pipeline (ComfyUI-style DAG)."""
    definition = {"name": req.name, "nodes": req.nodes}
    pipeline = parse_pipeline(definition)
    results = await pipeline_orchestrator.execute(pipeline)
    return {
        "name": pipeline.name,
        "node_count": len(results),
        "results": [
            {
                "node_id": r.node_id,
                "status": r.status.value,
                "outputs": r.outputs,
                "error": r.error,
                "elapsed_ms": r.elapsed_ms,
            }
            for r in results
        ],
    }


# ===== Model connection testing =====


class TestModelRequest(BaseModel):
    """Request body for testing a model connection."""

    model: str = Field(..., description="Model id to test")
    prompt: str = Field("Hello, respond with one word.", description="Test prompt")


@router.post("/models/test")
async def test_model_connection(req: TestModelRequest) -> Dict[str, Any]:
    """Verify that a model can actually respond to a request.

    Sends a minimal completion to the model and reports whether it
    returned a valid response. Useful for validating API key
    configuration and provider connectivity from the frontend.
    """
    import time

    from trigen.config import LLMConfig
    from trigen.llm.client import LLMClient

    resolved = model_router.resolve(req.model)
    if not resolved.get("api_key") and req.model != "trigen-default":
        return {
            "model": req.model,
            "success": False,
            "error": "No API key configured for this model",
            "provider": resolved.get("provider", "").value
            if hasattr(resolved.get("provider", ""), "value")
            else str(resolved.get("provider", "")),
        }

    client = LLMClient(LLMConfig())
    start = time.time()
    try:
        messages = [{"role": "user", "content": req.prompt}]
        text_parts = []
        async for chunk in client.stream(messages=messages, model=req.model):
            if chunk.content:
                text_parts.append(chunk.content)
            if chunk.finish_reason == "error":
                return {
                    "model": req.model,
                    "success": False,
                    "error": chunk.content,
                    "elapsed_ms": int((time.time() - start) * 1000),
                }
        elapsed = int((time.time() - start) * 1000)
        response_text = "".join(text_parts).strip()
        return {
            "model": req.model,
            "success": bool(response_text),
            "response": response_text[:200],
            "elapsed_ms": elapsed,
            "provider": resolved.get("provider", "").value
            if hasattr(resolved.get("provider", ""), "value")
            else str(resolved.get("provider", "")),
        }
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return {
            "model": req.model,
            "success": False,
            "error": str(exc),
            "elapsed_ms": elapsed,
        }


# ===== Pipeline templates =====


PIPELINE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "text-to-image-to-3d",
        "name": "Text → Image → 3D",
        "description": "Generate an image from text, then reconstruct a 3D scene from it",
        "nodes": [
            {
                "id": "img_1",
                "type": "generate_image",
                "inputs": {"model": "dall-e-3", "prompt": "a futuristic city skyline at sunset", "size": "1024x1024"},
            },
            {
                "id": "recon_1",
                "type": "image_to_3d",
                "inputs": {
                    "image_base64": {"from": "img_1", "output": "base64_data"},
                    "prompt": "Reconstruct the city skyline as 3D primitives",
                },
            },
        ],
    },
    {
        "id": "text-to-speech",
        "name": "Text → Speech",
        "description": "Synthesize speech from a text prompt",
        "nodes": [
            {
                "id": "tts_1",
                "type": "tts",
                "inputs": {"model": "tts-1", "text": "Welcome to Trigen, the AI-native 3D creation agent.", "voice": "alloy"},
            },
        ],
    },
    {
        "id": "audio-transcribe",
        "name": "Audio → Text",
        "description": "Transcribe audio input to text",
        "nodes": [
            {
                "id": "transcribe_1",
                "type": "transcribe",
                "inputs": {"model": "whisper-1", "audio_base64": "", "mime_type": "audio/wav"},
            },
        ],
    },
    {
        "id": "llm-then-image",
        "name": "LLM → Image",
        "description": "Use an LLM to craft a detailed prompt, then generate an image",
        "nodes": [
            {
                "id": "llm_1",
                "type": "llm_complete",
                "inputs": {
                    "model": "gpt-4o",
                    "prompt": "Describe a surreal dreamscape with floating islands and waterfalls, in one vivid sentence.",
                },
            },
            {
                "id": "img_1",
                "type": "generate_image",
                "inputs": {
                    "model": "dall-e-3",
                    "prompt": {"from": "llm_1", "output": "content"},
                    "size": "1024x1024",
                },
            },
        ],
    },
]


@router.get("/models/pipeline/templates")
async def list_pipeline_templates() -> Dict[str, Any]:
    """List pre-built pipeline templates for common multimodal workflows."""
    return {"templates": PIPELINE_TEMPLATES, "count": len(PIPELINE_TEMPLATES)}


# ===== Streaming pipeline execution =====


@router.post("/models/pipeline/stream")
async def run_pipeline_stream(req: RunPipelineRequest) -> Dict[str, Any]:
    """Execute a pipeline and return results with per-node timing.

    This endpoint executes the pipeline synchronously but returns detailed
    timing and status for each node, allowing the frontend to display
    progress as nodes complete. For true real-time streaming, use the
    WebSocket chat endpoint with a pipeline-formatted message.
    """
    import time

    from trigen.llm.pipeline import PipelineNode, Pipeline as PipelineDef

    definition = {"name": req.name, "nodes": req.nodes}
    pipeline = parse_pipeline(definition)
    start = time.time()
    results = await pipeline_orchestrator.execute(pipeline)
    total_elapsed = int((time.time() - start) * 1000)

    # Build a summary
    succeeded = sum(1 for r in results if r.status.value == "success")
    failed = sum(1 for r in results if r.status.value == "failed")

    return {
        "name": pipeline.name,
        "total_elapsed_ms": total_elapsed,
        "node_count": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": [
            {
                "node_id": r.node_id,
                "status": r.status.value,
                "outputs": r.outputs,
                "error": r.error,
                "elapsed_ms": r.elapsed_ms,
            }
            for r in results
        ],
    }


@router.post("/models/pipeline/sse")
async def run_pipeline_sse(req: RunPipelineRequest):
    """Execute a pipeline and stream node-by-node progress via Server-Sent Events.

    Each pipeline node emits two events: 'start' when it begins running and
    'result' when it finishes. A final 'done' event carries the summary.

    Event format: data: {json}\\n\\n
    """
    import json
    from fastapi.responses import StreamingResponse

    definition = {"name": req.name, "nodes": req.nodes}
    pipeline = parse_pipeline(definition)

    async def event_stream():
        async for event in pipeline_orchestrator.execute_stream(pipeline):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===== Runtime API key management =====


class SetKeyRequest(BaseModel):
    """Request body for setting a runtime API key."""

    env_name: str = Field(..., description="Environment variable name, e.g. OPENAI_API_KEY")
    api_key: str = Field(..., description="The API key value")


def _collect_key_env_names() -> List[str]:
    """Collect all unique API key env names from the model catalog."""
    seen: List[str] = []
    seen_set: set[str] = set()
    for entry in model_router.list_models():
        if entry.api_key_env and entry.api_key_env not in seen_set:
            seen.append(entry.api_key_env)
            seen_set.add(entry.api_key_env)
    return seen


@router.get("/models/keys")
async def list_api_keys() -> Dict[str, Any]:
    """List all API key slots with their configuration status (masked)."""
    env_names = _collect_key_env_names()
    statuses = key_store.status_many(env_names)
    configured = sum(1 for s in statuses if s.configured)
    return {
        "keys": [
            {
                "env_name": s.env_name,
                "configured": s.configured,
                "preview": s.preview,
                "source": s.source,
            }
            for s in statuses
        ],
        "total": len(statuses),
        "configured": configured,
    }


@router.post("/models/keys")
async def set_api_key(req: SetKeyRequest) -> Dict[str, Any]:
    """Set or update a runtime API key."""
    env_name = req.env_name.strip()
    if not env_name:
        raise HTTPException(status_code=400, detail="env_name is required")
    key_store.set_key(env_name, req.api_key)
    status = key_store.status(env_name)
    # Invalidate availability cache so the frontend sees the new state
    availability_checker._ollama_reachable = None
    return {
        "env_name": env_name,
        "configured": status.configured,
        "preview": status.preview,
        "source": status.source,
    }


@router.delete("/models/keys/{env_name}")
async def delete_api_key(env_name: str) -> Dict[str, Any]:
    """Remove a runtime API key (falls back to env var if present)."""
    removed = key_store.delete_key(env_name)
    availability_checker._ollama_reachable = None
    status = key_store.status(env_name)
    return {
        "env_name": env_name,
        "removed": removed,
        "still_configured_via_env": status.configured and status.source == "env",
        "configured": status.configured,
        "source": status.source,
    }


@router.delete("/models/keys")
async def clear_all_api_keys() -> Dict[str, Any]:
    """Remove all runtime API keys (env-var keys remain untouched)."""
    removed = key_store.clear_all()
    availability_checker._ollama_reachable = None
    return {"removed_count": removed}


@router.post("/models/discover")
async def run_model_discovery() -> Dict[str, Any]:
    """Trigger dynamic model discovery across all configured providers.

    Queries OpenRouter, Ollama, Together, Groq, and Mistral for their live
    model listings and registers any new models in the router catalog.
    Returns per-provider counts of newly discovered models.
    """
    counts = await discover_all(model_router)
    total = sum(counts.values())
    catalog_count = len(model_router.list_models())
    return {
        "discovered": counts,
        "new_count": total,
        "total_catalog": catalog_count,
    }

