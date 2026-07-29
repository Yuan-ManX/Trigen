// Rich media renderer for multimodal tool results.
// Displays generated images, videos, audio, and 3D asset download links
// inline within the chat conversation, directly from the tool result payload.
import { Download, ExternalLink, FileBox, Music } from 'lucide-react'

interface MultimodalResultProps {
  toolName: string
  data: Record<string, unknown>
}

/** Extract a string value from the data object */
function str(val: unknown): string {
  return typeof val === 'string' ? val : ''
}

/** Build a data URL from base64 payload and mime type */
function buildDataUrl(base64: string, mime: string): string {
  if (!base64) return ''
  if (base64.startsWith('data:')) return base64
  return `data:${mime || 'application/octet-stream'};base64,${base64}`
}

/** Render an image from base64 or URL */
function ImageResult({ data }: { data: Record<string, unknown> }) {
  const url = str(data.url)
  const b64 = str(data.base64_data)
  const mime = str(data.mime_type) || 'image/png'
  const src = url || buildDataUrl(b64, mime)
  if (!src) return null
  return (
    <div className="mt-2 rounded-md overflow-hidden border border-border-subtle bg-bg-base/60">
      <img
        src={src}
        alt={str(data.prompt) || 'Generated image'}
        className="w-full max-h-72 object-contain bg-black/30"
        loading="lazy"
      />
      {str(data.prompt) && (
        <div className="px-2 py-1 text-[10px] text-fg-muted truncate">
          {str(data.prompt)}
        </div>
      )}
    </div>
  )
}

/** Render a video player from a URL */
function VideoResult({ data }: { data: Record<string, unknown> }) {
  const url = str(data.url)
  if (!url) return null
  return (
    <div className="mt-2 rounded-md overflow-hidden border border-border-subtle bg-bg-base/60">
      <video
        src={url}
        controls
        className="w-full max-h-72 object-contain bg-black/40"
        preload="metadata"
      />
      {str(data.prompt) && (
        <div className="px-2 py-1 text-[10px] text-fg-muted truncate">
          {str(data.prompt)}
        </div>
      )}
    </div>
  )
}

/** Render an audio player from base64 data */
function AudioResult({ data }: { data: Record<string, unknown> }) {
  const b64 = str(data.base64_data)
  const mime = str(data.mime_type) || 'audio/mpeg'
  const src = buildDataUrl(b64, mime)
  if (!src) return null
  return (
    <div className="mt-2 rounded-md border border-border-subtle bg-bg-base/60 px-3 py-2">
      <div className="flex items-center gap-2 mb-1.5">
        <Music size={12} className="text-accent-cyan" />
        <span className="text-[11px] text-fg-secondary">
          {str(data.voice) ? `Voice: ${data.voice}` : 'Synthesized audio'}
        </span>
      </div>
      <audio src={src} controls className="w-full" preload="metadata" />
    </div>
  )
}

/** Render a download link for a 3D asset */
function Asset3DResult({ data }: { data: Record<string, unknown> }) {
  const url = str(data.url)
  const format = str(data.output_format) || 'glb'
  if (!url) return null
  return (
    <div className="mt-2 rounded-md border border-border-subtle bg-bg-base/60 px-3 py-2">
      <div className="flex items-center gap-2">
        <FileBox size={14} className="text-accent-gold" />
        <span className="text-[11px] text-fg-secondary flex-1 truncate">
          3D asset ({format.toUpperCase()})
        </span>
        <a
          href={url}
          download={`trigen-asset.${format}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] text-accent-cyan hover:text-accent-cyan/80 transition-colors"
        >
          <Download size={11} />
          Download
        </a>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] text-fg-muted hover:text-fg-secondary transition-colors"
        >
          <ExternalLink size={11} />
          Open
        </a>
      </div>
      {str(data.prompt) && (
        <div className="mt-1 text-[10px] text-fg-muted truncate">
          {str(data.prompt)}
        </div>
      )}
    </div>
  )
}

/** Render a transcription result */
function TranscriptionResult({ data }: { data: Record<string, unknown> }) {
  const text = str(data.text)
  if (!text) return null
  return (
    <div className="mt-2 rounded-md border border-border-subtle bg-bg-base/60 px-3 py-2">
      <div className="text-[11px] text-fg-secondary leading-relaxed whitespace-pre-wrap">
        {text}
      </div>
    </div>
  )
}

/** Main entry: pick the right renderer based on the tool name */
export function MultimodalResult({ toolName, data }: MultimodalResultProps) {
  switch (toolName) {
    case 'generate_image':
    case 'generate_animation':
      return <ImageResult data={data} />
    case 'generate_video':
      return <VideoResult data={data} />
    case 'synthesize_speech':
      return <AudioResult data={data} />
    case 'generate_3d_asset':
      return <Asset3DResult data={data} />
    case 'transcribe_audio':
      return <TranscriptionResult data={data} />
    default:
      return null
  }
}

/** Check whether a tool name produces multimodal renderable output */
export function hasMultimediaResult(toolName: string): boolean {
  return [
    'generate_image',
    'generate_animation',
    'generate_video',
    'synthesize_speech',
    'generate_3d_asset',
    'transcribe_audio',
  ].includes(toolName)
}
