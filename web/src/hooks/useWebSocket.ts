// WebSocket lifecycle binding hook
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
 * Automatically manages the WebSocket connection lifecycle.
 * @param autoConnect Whether to auto-connect on mount (default true)
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
    // Do not actively disconnect on component unmount to keep the global session alive; call disconnect() if needed
    // Return an empty cleanup function here to avoid frequent disconnections during hot reload
    return
  }, [autoConnect, connect])

  return { status, sessionId, connect, disconnect }
}
