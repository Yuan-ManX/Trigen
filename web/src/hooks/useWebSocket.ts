// WebSocket 生命周期绑定 hook
// WebSocket lifecycle binding hook
// 在顶层组件挂载时自动连接，卸载时断开；并暴露连接状态
// Auto-connect on top-level component mount, disconnect on unmount; also exposes connection status
import { useEffect } from 'react'
import { useChat } from '../store/useChat'
import type { SocketStatus } from '../api/client'

interface UseWebSocketResult {
  status: SocketStatus
  sessionId: string
  connect: () => void
  disconnect: () => void
}

/**
 * 自动管理 WebSocket 连接生命周期。
 *
 * Automatically manages the WebSocket connection lifecycle.
 * @param autoConnect 是否在挂载时自动连接（默认 true）
 *                    Whether to auto-connect on mount (default true)
 */
export function useWebSocket(autoConnect = true): UseWebSocketResult {
  const status = useChat((s) => s.status)
  const sessionId = useChat((s) => s.sessionId)
  const connect = useChat((s) => s.connect)
  const disconnect = useChat((s) => s.disconnect)

  useEffect(() => {
    if (autoConnect) {
      connect()
    }
    // 组件卸载时不主动断开，保持全局会话持续；如需断开可调用 disconnect()
    // Do not actively disconnect on component unmount to keep the global session alive; call disconnect() if needed
    // 这里返回空清理函数以避免热重载时频繁断连
    // Return an empty cleanup function here to avoid frequent disconnections during hot reload
    return
  }, [autoConnect, connect])

  return { status, sessionId, connect, disconnect }
}
