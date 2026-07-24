// 整体布局容器：顶栏 + 左侧对话 + 中央画布 + 右侧面板，面板可折叠
// Overall layout container: top bar + left chat + center canvas + right panel, panels are collapsible
import { AnimatePresence, motion } from 'framer-motion'
import { PanelLeftOpen, PanelRightOpen } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchScene } from '../../api/client'
import { useScene } from '../../store/useScene'
import { useWebSocket } from '../../hooks/useWebSocket'
import { ChatPanel } from '../chat/ChatPanel'
import { EditorCanvas } from '../canvas/EditorCanvas'
import { RightPanel } from '../sidebar/RightPanel'
import { TopToolbar } from '../toolbar/TopToolbar'

export function AppShell() {
  // 自动建立 WebSocket 连接
  // Automatically establish WebSocket connection
  const { sessionId } = useWebSocket()
  const setScene = useScene((s) => s.setScene)

  const [chatOpen, setChatOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)

  // 启动时加载当前会话已有的场景
  // Load the existing scene of the current session on startup
  useEffect(() => {
    fetchScene(sessionId)
      .then((s) => setScene(s))
      .catch(() => {
        /* 后端未就绪时静默，等待 WS 推送 */
        /* Stay silent when the backend is not ready, wait for WS push */
      })
  }, [sessionId, setScene])

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg-base text-fg-primary">
      <TopToolbar onToggleChat={() => setChatOpen((v) => !v)} />

      <div className="flex flex-1 min-h-0">
        {/* 左侧对话面板 */}
        {/* Left chat panel */}
        <AnimatePresence initial={false}>
          {chatOpen ? (
            <motion.div
              key="chat"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 380, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <ChatPanel onCollapse={() => setChatOpen(false)} />
            </motion.div>
          ) : (
            <motion.button
              key="chat-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => setChatOpen(true)}
              aria-label="展开对话面板"
              className="shrink-0 flex flex-col items-center gap-2 w-11 border-r border-border bg-bg-panel text-fg-muted hover:text-fg-primary pt-3"
            >
              <PanelLeftOpen size={16} />
              <span className="text-[10px] [writing-mode:vertical-rl]">对话</span>
            </motion.button>
          )}
        </AnimatePresence>

        {/* 中央 3D 画布 */}
        {/* Center 3D canvas */}
        <main className="relative flex-1 min-w-0 bg-bg-base">
          <EditorCanvas />
          {/* 画布左下角水印 */}
          {/* Watermark at the bottom-left of the canvas */}
          <div className="pointer-events-none absolute bottom-3 left-3 text-[10px] font-mono text-fg-muted/60">
            Trigen Editor · 拖拽旋转 · 滚轮缩放 · 点击选中
          </div>
        </main>

        {/* 右侧面板 */}
        {/* Right panel */}
        <AnimatePresence initial={false}>
          {rightOpen ? (
            <motion.div
              key="right"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 280, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <RightPanel onCollapse={() => setRightOpen(false)} />
            </motion.div>
          ) : (
            <motion.button
              key="right-rail"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 44, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: 'easeInOut' }}
              onClick={() => setRightOpen(true)}
              aria-label="展开右侧面板"
              className="shrink-0 flex flex-col items-center gap-2 w-11 border-l border-border bg-bg-panel text-fg-muted hover:text-fg-primary pt-3"
            >
              <PanelRightOpen size={16} />
              <span className="text-[10px]">面板</span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
