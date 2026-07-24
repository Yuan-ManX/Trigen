// 顶部工具栏：Logo + 标语，右侧导出 / 重置 / 连接状态
// Top toolbar: Logo + tagline, with export / reset / connection status on the right
import { motion } from 'framer-motion'
import {
  Download,
  Loader2,
  RotateCcw,
  Triangle,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchHealth, resetScene } from '../../api/client'
import { useChat } from '../../store/useChat'
import { useScene } from '../../store/useScene'
import type { HealthResponse } from '../../types'

interface TopToolbarProps {
  onToggleChat: () => void
}

/** 连接状态映射 */
/** Connection status mapping */
function statusInfo(status: string): { label: string; color: string } {
  switch (status) {
    case 'connected':
      return { label: '已连接', color: 'bg-emerald-400' }
    case 'connecting':
      return { label: '连接中', color: 'bg-accent-gold' }
    case 'error':
      return { label: '连接错误', color: 'bg-rose-400' }
    default:
      return { label: '未连接', color: 'bg-fg-muted' }
  }
}

export function TopToolbar({ onToggleChat }: TopToolbarProps) {
  const status = useChat((s) => s.status)
  const sessionId = useChat((s) => s.sessionId)
  const scene = useScene((s) => s.scene)
  const clearScene = useScene((s) => s.clear)

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [resetting, setResetting] = useState(false)

  // 启动时检查后端健康状态
  // Check backend health status on startup
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  const info = statusInfo(status)

  /** 导出当前场景为 JSON 文件（客户端下载） */
  /** Export the current scene as a JSON file (client-side download) */
  const handleExport = () => {
    const blob = new Blob([JSON.stringify(scene, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trigen-scene-${sessionId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  /** 重置场景：调用后端并清空本地 */
  /** Reset the scene: call the backend and clear the local state */
  const handleReset = async () => {
    if (resetting) return
    const ok = window.confirm('确定要重置当前场景吗？所有对象将被清空。')
    if (!ok) return
    setResetting(true)
    try {
      const fresh = await resetScene(sessionId)
      clearScene()
      useScene.getState().setScene(fresh)
    } catch {
      // 后端不可用时仍清空本地场景
      // Still clear the local scene when the backend is unavailable
      clearScene()
    } finally {
      setResetting(false)
    }
  }

  return (
    <header className="flex items-center justify-between h-12 px-4 border-b border-border bg-bg-panel/90 backdrop-blur z-10">
      {/* 左侧 Logo */}
      {/* Left logo */}
      <div className="flex items-center gap-2.5">
        <motion.div
          initial={{ rotate: -20, opacity: 0 }}
          animate={{ rotate: 0, opacity: 1 }}
          transition={{ duration: 0.4 }}
          className="w-7 h-7 rounded-md bg-gradient-to-br from-accent-cyan to-accent-gold flex items-center justify-center shadow-glow"
        >
          <Triangle size={14} className="text-bg-base" fill="currentColor" />
        </motion.div>
        <div className="flex items-baseline gap-2">
          <span className="font-sans font-bold text-fg-primary text-base tracking-tight">
            Trigen
          </span>
          <span className="text-[11px] text-fg-muted hidden sm:inline">
            AI 原生 3D 创作
          </span>
        </div>
        {health && (
          <span className="ml-2 text-[10px] font-mono text-fg-muted px-1.5 py-0.5 rounded border border-border-subtle">
            v{health.version}
          </span>
        )}
      </div>

      {/* 右侧操作 */}
      {/* Right actions */}
      <div className="flex items-center gap-2">
        {/* 连接状态 */}
        {/* Connection status */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border bg-bg-elevated">
          <span className={`w-1.5 h-1.5 rounded-full ${info.color} ${status === 'connecting' ? 'animate-pulse' : ''}`} />
          <span className="text-[11px] text-fg-secondary font-mono">{info.label}</span>
        </div>

        <button
          onClick={handleExport}
          className="flex items-center gap-1.5 text-xs text-fg-secondary hover:text-fg-primary px-2.5 py-1.5 rounded-md border border-border hover:border-accent-cyan/40 hover:bg-bg-hover transition-colors"
          title="导出场景为 JSON"
        >
          <Download size={13} />
          <span className="hidden sm:inline">导出</span>
        </button>

        <button
          onClick={handleReset}
          disabled={resetting}
          className="flex items-center gap-1.5 text-xs text-fg-secondary hover:text-fg-primary px-2.5 py-1.5 rounded-md border border-border hover:border-rose-400/40 hover:bg-bg-hover transition-colors disabled:opacity-60"
          title="重置场景"
        >
          {resetting ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RotateCcw size={13} />
          )}
          <span className="hidden sm:inline">重置</span>
        </button>

        <button
          onClick={onToggleChat}
          className="lg:hidden flex items-center justify-center w-8 h-8 rounded-md border border-border text-fg-secondary hover:text-fg-primary"
          aria-label="切换对话面板"
        >
          <Triangle size={14} />
        </button>
      </div>
    </header>
  )
}
