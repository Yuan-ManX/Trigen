// Model settings panel: runtime API key configuration for all providers
// Allows users to set, edit, and clear API keys without restarting the backend
import { AnimatePresence, motion } from 'framer-motion'
import {
  Check,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Save,
  Trash2,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  clearAllAPIKeys,
  deleteAPIKey,
  fetchAPIKeys,
  fetchModels,
  setAPIKey,
  testModelConnection,
  type APIKeyStatus,
  type ModelEntry,
  type ModelTestResult,
} from '../../api/client'

/** Human-readable label for each API key environment variable */
const KEY_LABELS: Record<string, string> = {
  OPENAI_API_KEY: 'OpenAI',
  ANTHROPIC_API_KEY: 'Anthropic',
  DEEPSEEK_API_KEY: 'DeepSeek',
  DASHSCOPE_API_KEY: 'Alibaba Qwen (DashScope)',
  ZHIPU_API_KEY: 'Zhipu GLM',
  MOONSHOT_API_KEY: 'Moonshot Kimi',
  BAICHUAN_API_KEY: 'Baichuan',
  MINIMAX_API_KEY: 'MiniMax',
  SPARK_API_KEY: 'iFlytek Spark',
  GROQ_API_KEY: 'Groq',
  TOGETHER_API_KEY: 'Together AI',
  FIREWORKS_API_KEY: 'Fireworks AI',
  MISTRAL_API_KEY: 'Mistral AI',
  COHERE_API_KEY: 'Cohere',
  PPLX_API_KEY: 'Perplexity',
  AI21_API_KEY: 'AI21 Labs',
  REPLICATE_API_TOKEN: 'Replicate',
  HF_TOKEN: 'Hugging Face',
  STABILITY_API_KEY: 'Stability AI',
  OPENROUTER_API_KEY: 'OpenRouter',
  OLLAMA_API_KEY: 'Ollama',
}

/** Suggested documentation URL for obtaining a key */
const KEY_HELP_URLS: Record<string, string> = {
  OPENAI_API_KEY: 'https://platform.openai.com/api-keys',
  ANTHROPIC_API_KEY: 'https://console.anthropic.com/settings/keys',
  DEEPSEEK_API_KEY: 'https://platform.deepseek.com/api_keys',
  DASHSCOPE_API_KEY: 'https://dashscope.console.aliyun.com/apiKey',
  ZHIPU_API_KEY: 'https://open.bigmodel.cn/usercenter/apikeys',
  MOONSHOT_API_KEY: 'https://platform.moonshot.cn/console/api-keys',
  GROQ_API_KEY: 'https://console.groq.com/keys',
  TOGETHER_API_KEY: 'https://api.together.xyz/settings/api-keys',
  FIREWORKS_API_KEY: 'https://fireworks.ai/account/api-keys',
  MISTRAL_API_KEY: 'https://console.mistral.ai/api-keys',
  COHERE_API_KEY: 'https://dashboard.cohere.com/api-keys',
  PPLX_API_KEY: 'https://www.perplexity.ai/settings/api',
  AI21_API_KEY: 'https://studio.ai21.com/account/api-key',
  REPLICATE_API_TOKEN: 'https://replicate.com/account/api-tokens',
  HF_TOKEN: 'https://huggingface.co/settings/tokens',
  STABILITY_API_KEY: 'https://platform.stability.ai/account/keys',
  OPENROUTER_API_KEY: 'https://openrouter.ai/keys',
}

interface ModelSettingsPanelProps {
  open: boolean
  onClose: () => void
}

/** A single API key row with input, status, save, and clear actions */
function KeyRow({
  envName,
  status,
  testModel,
}: {
  envName: string
  status: APIKeyStatus
  testModel?: string
}) {
  const [value, setValue] = useState('')
  const [visible, setVisible] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null)
  const [saved, setSaved] = useState(false)

  const label = KEY_LABELS[envName] ?? envName
  const helpUrl = KEY_HELP_URLS[envName]
  const hasKey = status.configured
  const isRuntime = status.source === 'runtime'
  const isDirty = value.length > 0

  const handleSave = async () => {
    if (!isDirty || saving) return
    setSaving(true)
    setSaved(false)
    try {
      await setAPIKey(envName, value)
      setValue('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save key:', e)
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    if (testing) return
    setSaving(true)
    try {
      await deleteAPIKey(envName)
      setTestResult(null)
    } catch (e) {
      console.error('Failed to clear key:', e)
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    if (!testModel || testing) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testModelConnection(testModel)
      setTestResult(result)
    } catch (e) {
      setTestResult({
        model: testModel,
        success: false,
        error: e instanceof Error ? e.message : String(e),
        elapsed_ms: 0,
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-bg-elevated/40 p-3">
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <KeyRound
            size={13}
            className={hasKey ? 'text-emerald-400' : 'text-fg-muted'}
          />
          <span className="text-xs font-medium text-fg-primary truncate">{label}</span>
          <code className="text-[9px] text-fg-muted bg-bg-base px-1.5 py-0.5 rounded">
            {envName}
          </code>
        </div>
        {/* Status badge */}
        <div className="flex items-center gap-1.5 shrink-0">
          {hasKey ? (
            <>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                {isRuntime ? 'Runtime' : 'Env'}
              </span>
              {status.preview && (
                <code className="text-[9px] text-fg-muted font-mono">{status.preview}</code>
              )}
            </>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-fg-muted">
              <span className="w-1.5 h-1.5 rounded-full bg-fg-muted/40" />
              Not set
            </span>
          )}
        </div>
      </div>

      {/* Input row */}
      <div className="flex items-center gap-1.5">
        <div className="relative flex-1">
          <input
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={hasKey ? '•••••••• (enter new key to replace)' : 'Paste your API key here…'}
            className="w-full pr-8 px-2.5 py-1.5 rounded-md border border-border bg-bg-base text-xs text-fg-primary placeholder:text-fg-muted outline-none focus:border-accent-cyan/50 transition-colors"
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? 'Hide key' : 'Show key'}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-fg-muted hover:text-fg-primary transition-colors"
          >
            {visible ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
        </div>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={!isDirty || saving}
          aria-label="Save API key"
          title="Save key"
          className="flex items-center justify-center w-7 h-7 rounded-md bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : saved ? <Check size={12} /> : <Save size={12} />}
        </button>

        {/* Clear button (only for runtime keys) */}
        {isRuntime && (
          <button
            onClick={handleClear}
            disabled={saving}
            aria-label="Clear runtime key"
            title="Clear runtime key (env var remains)"
            className="flex items-center justify-center w-7 h-7 rounded-md text-rose-400 hover:bg-rose-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>

      {/* Test + help row */}
      <div className="flex items-center justify-between mt-2">
        {testModel ? (
          <button
            onClick={handleTest}
            disabled={!hasKey || testing}
            className="text-[10px] text-accent-cyan hover:text-accent-cyan/80 disabled:text-fg-muted disabled:cursor-not-allowed transition-colors"
          >
            {testing ? 'Testing…' : `Test ${testModel}`}
          </button>
        ) : (
          <span className="text-[10px] text-fg-muted">No chat model in this provider</span>
        )}
        {helpUrl && (
          <a
            href={helpUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-fg-muted hover:text-accent-cyan transition-colors"
          >
            Get key →
          </a>
        )}
      </div>

      {/* Test result */}
      {testResult && (
        <div
          className={`mt-2 px-2 py-1.5 rounded text-[10px] ${
            testResult.success
              ? 'bg-emerald-500/10 text-emerald-400'
              : 'bg-rose-500/10 text-rose-400'
          }`}
        >
          {testResult.success ? (
            <span>
              ✓ {testResult.response || 'OK'} · {testResult.elapsed_ms}ms
            </span>
          ) : (
            <span>✕ {testResult.error || 'Connection failed'}</span>
          )}
        </div>
      )}
    </div>
  )
}

export function ModelSettingsPanel({ open, onClose }: ModelSettingsPanelProps) {
  const [keys, setKeys] = useState<APIKeyStatus[]>([])
  const [models, setModels] = useState<ModelEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState(false)

  const refresh = async () => {
    setLoading(true)
    try {
      const [keyData, modelData] = await Promise.all([fetchAPIKeys(), fetchModels()])
      setKeys(keyData.keys)
      setModels(modelData)
    } catch (e) {
      console.error('Failed to load key status:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) refresh()
  }, [open])

  // Refresh key status every 5 seconds while open (picks up external changes)
  useEffect(() => {
    if (!open) return
    const id = setInterval(() => {
      fetchAPIKeys()
        .then((data) => setKeys(data.keys))
        .catch(() => {})
    }, 5000)
    return () => clearInterval(id)
  }, [open])

  /** Map env_name → first chat-capable model id (for the test button) */
  const testModelForEnv = (envName: string): string | undefined => {
    const chatModel = models.find(
      (m) => m.api_key_env === envName && (m.modalities.includes('text') || m.modalities.includes('vision')),
    )
    return chatModel?.id
  }

  const configuredCount = keys.filter((k) => k.configured).length
  const runtimeCount = keys.filter((k) => k.source === 'runtime').length

  const handleClearAll = async () => {
    if (clearing) return
    const ok = window.confirm('Remove all runtime API keys? Environment-variable keys will remain.')
    if (!ok) return
    setClearing(true)
    try {
      await clearAllAPIKeys()
      await refresh()
    } catch (e) {
      console.error('Failed to clear keys:', e)
    } finally {
      setClearing(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-[640px] max-w-[92vw] max-h-[85vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl flex flex-col"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-5 border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                <KeyRound size={16} className="text-accent-cyan" />
                <h2 className="text-sm font-semibold text-fg-primary">Model Settings</h2>
                <span className="text-[10px] text-fg-muted">
                  {configuredCount}/{keys.length} keys configured
                </span>
              </div>
              <div className="flex items-center gap-1">
                {runtimeCount > 0 && (
                  <button
                    onClick={handleClearAll}
                    disabled={clearing}
                    className="text-[10px] text-rose-400 hover:text-rose-300 px-2 py-1 rounded hover:bg-rose-500/10 transition-colors disabled:opacity-50"
                  >
                    {clearing ? 'Clearing…' : 'Clear runtime keys'}
                  </button>
                )}
                <button
                  onClick={onClose}
                  aria-label="Close model settings"
                  className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </header>

            {/* Summary banner */}
            <div className="px-5 py-2.5 border-b border-border-subtle bg-bg-elevated/30 shrink-0">
              <p className="text-[11px] text-fg-muted leading-relaxed">
                Configure API keys for each model provider. Keys entered here are stored
                locally in the Trigen workspace and take precedence over environment variables.
                They never leave your machine.
              </p>
              {!loading && configuredCount === 0 && (
                <p className="text-[11px] text-accent-gold mt-1">
                  No API keys configured — the Agent will run in offline mode. Add at least one key to enable LLM-driven creation.
                </p>
              )}
            </div>

            {/* Body: key list */}
            <div className="flex-1 overflow-y-auto p-5 space-y-2.5">
              {loading ? (
                <div className="flex items-center justify-center py-12 text-fg-muted">
                  <Loader2 size={20} className="animate-spin mr-2" />
                  <span className="text-xs">Loading key status…</span>
                </div>
              ) : keys.length === 0 ? (
                <div className="text-center py-12 text-fg-muted text-xs">
                  No API key slots found in the model catalog.
                </div>
              ) : (
                keys.map((status) => (
                  <KeyRow
                    key={status.env_name}
                    envName={status.env_name}
                    status={status}
                    testModel={testModelForEnv(status.env_name)}
                  />
                ))
              )}
            </div>

            {/* Footer */}
            <footer className="flex items-center justify-between px-5 py-2.5 border-t border-border bg-bg-elevated/30 shrink-0">
              <span className="text-[10px] text-fg-muted">
                Runtime: {runtimeCount} · Env: {configuredCount - runtimeCount} · Total: {configuredCount}/{keys.length}
              </span>
              <button
                onClick={refresh}
                className="text-[10px] text-accent-cyan hover:text-accent-cyan/80 transition-colors"
              >
                Refresh
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
