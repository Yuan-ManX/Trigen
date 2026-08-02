// Chat panel container: header title + message list + input bar + history view
import { Eraser, History, KeyRound, PanelLeftClose, Plus, Radio, Shield, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { useChat } from '../../store/useChat'
import { ChatHistory } from './ChatHistory'
import { ConfirmDialog } from './ConfirmDialog'
import { InputBar } from './InputBar'
import { MessageList } from './MessageList'
import { ModelSettingsPanel } from './ModelSettingsPanel'

interface ChatPanelProps {
  onCollapse: () => void
}

export function ChatPanel({ onCollapse }: ChatPanelProps) {
  const send = useChat((s) => s.send)
  const isResponding = useChat((s) => s.isResponding)
  const clearMessages = useChat((s) => s.clearMessages)
  const hasMessages = useChat((s) => s.messages.length > 0)
  const showHistory = useChat((s) => s.showHistory)
  const toggleHistory = useChat((s) => s.toggleHistory)
  const startNewConversation = useChat((s) => s.startNewConversation)
  const conversationsCount = useChat((s) => s.conversations.length)
  // Destructive-action confirmation state
  const confirmDestructive = useChat((s) => s.confirmDestructive)
  const setConfirmDestructive = useChat((s) => s.setConfirmDestructive)
  const pendingDestructive = useChat((s) => s.pendingDestructive)
  const confirmPendingDestructive = useChat((s) => s.confirmPendingDestructive)
  const cancelPendingDestructive = useChat((s) => s.cancelPendingDestructive)
  // Token usage from the most recent DONE event
  const lastTokenUsage = useChat((s) => s.lastTokenUsage)
  const [showSettings, setShowSettings] = useState(false)

  return (
    <aside className="flex flex-col w-[400px] h-full shrink-0 border-r border-border bg-bg-panel">
      {/* Header */}
      <header className="flex items-center justify-between h-11 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Radio
            size={13}
            className={
              isResponding
                ? 'text-accent-gold animate-pulse'
                : 'text-accent-cyan'
            }
          />
          <span className="text-xs font-semibold text-fg-primary tracking-wide">
            {showHistory ? 'History' : 'Chat'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* New conversation */}
          <button
            onClick={startNewConversation}
            aria-label="New conversation"
            title="New conversation"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
          >
            <Plus size={14} />
          </button>
          {/* Destructive-action confirmation toggle: when active, the next
              send() is previewed via /api/agent/plan and a modal prompts the
              user before any requires_approval tool runs. */}
          <button
            onClick={() => setConfirmDestructive(!confirmDestructive)}
            aria-label="Toggle destructive-action confirmation"
            aria-pressed={confirmDestructive}
            title={
              confirmDestructive
                ? 'Destructive-action confirmation ON (plan-preview before send)'
                : 'Destructive-action confirmation OFF (send immediately)'
            }
            className={`flex items-center justify-center w-7 h-7 rounded transition-colors ${
              confirmDestructive
                ? 'text-rose-400 bg-rose-500/10'
                : 'text-fg-muted hover:text-fg-primary hover:bg-bg-hover'
            }`}
          >
            {confirmDestructive ? <ShieldAlert size={14} /> : <Shield size={14} />}
          </button>
          {/* Model settings / API keys */}
          <button
            onClick={() => setShowSettings(true)}
            aria-label="Model settings"
            title="Configure model API keys"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-accent-cyan hover:bg-bg-hover transition-colors"
          >
            <KeyRound size={14} />
          </button>
          {/* History toggle */}
          <button
            onClick={toggleHistory}
            aria-label="Toggle chat history"
            title="Chat history"
            className={`flex items-center justify-center w-7 h-7 rounded transition-colors relative ${
              showHistory
                ? 'text-accent-cyan bg-accent-cyan/10'
                : 'text-fg-muted hover:text-fg-primary hover:bg-bg-hover'
            }`}
          >
            <History size={14} />
            {conversationsCount > 0 && !showHistory && (
              <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center w-3.5 h-3.5 rounded-full bg-accent-cyan text-[8px] font-bold text-bg-base">
                {conversationsCount > 9 ? '9+' : conversationsCount}
              </span>
            )}
          </button>
          {/* Clear messages */}
          <button
            onClick={clearMessages}
            disabled={!hasMessages || showHistory}
            aria-label="Clear chat messages"
            title="Clear chat"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Eraser size={14} />
          </button>
          {/* Collapse */}
          <button
            onClick={onCollapse}
            aria-label="Collapse chat panel"
            className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
      </header>

      {/* Body: either history view or chat messages */}
      {showHistory ? (
        <ChatHistory />
      ) : (
        <>
          <MessageList onSuggestion={send} />
          <InputBar />
          {/* Token usage footer: shows the most recent turn's token totals.
              Hidden when null (offline mode never reports usage). */}
          {lastTokenUsage && (
            <div className="flex items-center justify-end gap-2 px-3 py-1 border-t border-border-subtle bg-bg-panel text-[10px] text-fg-muted font-mono">
              {lastTokenUsage.prompt_tokens != null &&
              lastTokenUsage.completion_tokens != null ? (
                <span title="Prompt / completion tokens for the last turn">
                  <span className="text-accent-cyan/80">↑{lastTokenUsage.prompt_tokens}</span>
                  {' '}
                  <span className="text-accent-gold/80">↓{lastTokenUsage.completion_tokens}</span>
                </span>
              ) : (
                <span title="Total tokens for the last turn">
                  {lastTokenUsage.total_tokens ?? 0} tokens
                </span>
              )}
            </div>
          )}
        </>
      )}

      {/* Model settings dialog */}
      <ModelSettingsPanel open={showSettings} onClose={() => setShowSettings(false)} />

      {/* Destructive-action confirmation modal */}
      <ConfirmDialog
        open={pendingDestructive !== null}
        pending={pendingDestructive}
        onConfirm={confirmPendingDestructive}
        onCancel={cancelPendingDestructive}
      />
    </aside>
  )
}
