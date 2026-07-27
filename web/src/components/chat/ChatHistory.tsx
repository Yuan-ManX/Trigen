// Chat history panel: searchable, grouped, pinnable conversation list
import { History, Pin, Plus, Search, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useChat, type Conversation } from '../../store/useChat'

/** Date group label */
type DateGroup = 'pinned' | 'today' | 'yesterday' | 'thisWeek' | 'older'

/** Group a conversation by its updatedAt timestamp */
function getDateGroup(conv: Conversation): DateGroup {
  if (conv.pinned) return 'pinned'
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const yesterday = today - 86400000
  const weekAgo = today - 7 * 86400000
  const dDay = new Date(conv.updatedAt)

  if (dDay.getTime() >= today) return 'today'
  if (dDay.getTime() >= yesterday) return 'yesterday'
  if (dDay.getTime() >= weekAgo) return 'thisWeek'
  return 'older'
}

const GROUP_LABELS: Record<DateGroup, string> = {
  pinned: 'Pinned',
  today: 'Today',
  yesterday: 'Yesterday',
  thisWeek: 'This Week',
  older: 'Older',
}

const GROUP_ORDER: DateGroup[] = ['pinned', 'today', 'yesterday', 'thisWeek', 'older']

/** Format time as HH:MM */
function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Get the last non-empty message preview */
function lastMessagePreview(conv: Conversation): string {
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    const m = conv.messages[i]
    if (m.content && !m.error) {
      const text = m.content.trim()
      if (text) return text.length > 60 ? text.slice(0, 60) + '…' : text
    }
  }
  return ''
}

/** Count user prompts in a conversation */
function promptCount(conv: Conversation): number {
  return conv.messages.filter((m) => m.role === 'user').length
}

interface ConversationCardProps {
  conv: Conversation
  active: boolean
  onLoad: () => void
  onDelete: () => void
  onPin: () => void
  onRename: (title: string) => void
}

function ConversationCard({
  conv,
  active,
  onLoad,
  onDelete,
  onPin,
  onRename,
}: ConversationCardProps) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(conv.title)

  const handleStartEdit = () => {
    setEditValue(conv.title)
    setEditing(true)
  }

  const handleCommitEdit = () => {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== conv.title) {
      onRename(trimmed)
    }
    setEditing(false)
  }

  const preview = lastMessagePreview(conv)
  const count = promptCount(conv)

  return (
    <div
      onClick={() => !editing && onLoad()}
      onDoubleClick={handleStartEdit}
      className={`group cursor-pointer rounded-lg border px-3 py-2.5 transition-all ${
        active
          ? 'border-accent-cyan/40 bg-accent-cyan/10 shadow-glow'
          : 'border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-cyan/20'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-1.5">
            {conv.pinned && (
              <Pin
                size={10}
                className="shrink-0 text-accent-gold fill-accent-gold"
              />
            )}
            {editing ? (
              <input
                autoFocus
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onFocus={(e) => e.target.select()}
                onBlur={handleCommitEdit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCommitEdit()
                  if (e.key === 'Escape') setEditing(false)
                }}
                className="flex-1 bg-bg-base border border-accent-cyan/40 rounded px-1.5 py-0.5 text-[11px] text-fg-primary outline-none"
              />
            ) : (
              <p
                className={`text-[11px] font-semibold truncate flex-1 ${
                  active ? 'text-accent-cyan' : 'text-fg-primary'
                }`}
              >
                {conv.title}
              </p>
            )}
          </div>

          {/* Preview text */}
          {preview && (
            <p className="text-[10px] text-fg-muted mt-1 line-clamp-2 leading-relaxed">
              {preview}
            </p>
          )}

          {/* Metadata row */}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[9px] text-fg-muted font-mono">
              {formatTime(conv.updatedAt)}
            </span>
            <span className="text-[9px] text-fg-muted">·</span>
            <span className="text-[9px] text-fg-muted">
              {count} {count === 1 ? 'prompt' : 'prompts'}
            </span>
          </div>
        </div>

        {/* Action buttons */}
        {!editing && (
          <div className="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => {
                e.stopPropagation()
                onPin()
              }}
              aria-label={conv.pinned ? 'Unpin' : 'Pin'}
              title={conv.pinned ? 'Unpin' : 'Pin'}
              className={`flex items-center justify-center w-5 h-5 rounded transition-colors ${
                conv.pinned
                  ? 'text-accent-gold'
                  : 'text-fg-muted hover:text-accent-gold hover:bg-accent-gold/10'
              }`}
            >
              <Pin size={10} className={conv.pinned ? 'fill-current' : ''} />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
              }}
              aria-label="Delete"
              title="Delete"
              className="flex items-center justify-center w-5 h-5 rounded text-fg-muted hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              <Trash2 size={10} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export function ChatHistory() {
  const conversations = useChat((s) => s.conversations)
  const activeId = useChat((s) => s.activeConversationId)
  const loadConversation = useChat((s) => s.loadConversation)
  const deleteConversation = useChat((s) => s.deleteConversation)
  const togglePin = useChat((s) => s.togglePin)
  const renameConversation = useChat((s) => s.renameConversation)
  const startNewConversation = useChat((s) => s.startNewConversation)
  const setHistoryVisible = useChat((s) => s.setHistoryVisible)

  const [query, setQuery] = useState('')

  // Filter conversations by search query
  const filtered = useMemo(() => {
    if (!query.trim()) return conversations
    const q = query.toLowerCase()
    return conversations.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.messages.some((m) => m.content.toLowerCase().includes(q)),
    )
  }, [conversations, query])

  // Group conversations by date
  const grouped = useMemo(() => {
    const groups: Record<DateGroup, Conversation[]> = {
      pinned: [],
      today: [],
      yesterday: [],
      thisWeek: [],
      older: [],
    }
    for (const conv of filtered) {
      groups[getDateGroup(conv)].push(conv)
    }
    // Sort each group by updatedAt descending
    for (const key of Object.keys(groups) as DateGroup[]) {
      groups[key].sort((a, b) => b.updatedAt - a.updatedAt)
    }
    return groups
  }, [filtered])

  const totalCount = conversations.length
  const filteredCount = filtered.length

  return (
    <div className="flex flex-col h-full bg-bg-panel">
      {/* Header */}
      <div className="flex items-center justify-between h-11 px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <History size={13} className="text-accent-cyan" />
          <span className="text-xs font-semibold text-fg-primary tracking-wide">
            History
          </span>
          <span className="text-[10px] text-fg-muted">
            ({filteredCount}{filteredCount !== totalCount ? `/${totalCount}` : ''})
          </span>
        </div>
        <button
          onClick={() => setHistoryVisible(false)}
          aria-label="Close history"
          className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      {/* New conversation + Search */}
      <div className="px-3 pt-3 pb-2 space-y-2">
        <button
          onClick={startNewConversation}
          className="w-full flex items-center justify-center gap-1.5 rounded-md border border-accent-cyan/30 bg-accent-cyan/10 hover:bg-accent-cyan/20 text-accent-cyan transition-colors px-3 py-2 text-xs font-medium"
        >
          <Plus size={13} />
          <span>New Conversation</span>
        </button>

        {/* Search bar */}
        <div className="relative">
          <Search
            size={12}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-muted pointer-events-none"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations…"
            className="w-full bg-bg-elevated border border-border rounded-md pl-8 pr-7 py-1.5 text-[11px] text-fg-primary placeholder:text-fg-muted outline-none focus:border-accent-cyan/40 transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-muted hover:text-fg-primary transition-colors"
            >
              <X size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {filteredCount === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center px-4">
            <History size={20} className="text-fg-muted/40 mb-2" />
            <p className="text-[11px] text-fg-muted">
              {query
                ? 'No conversations match your search.'
                : 'No conversations yet.\nStart chatting to save history.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {GROUP_ORDER.map((group) => {
              const items = grouped[group]
              if (items.length === 0) return null
              return (
                <div key={group} className="space-y-1">
                  {/* Group label */}
                  <div className="flex items-center gap-2 px-1 pt-1">
                    <span className="text-[9px] uppercase tracking-wider text-fg-muted font-semibold">
                      {GROUP_LABELS[group]}
                    </span>
                    <span className="text-[9px] text-fg-muted/60">
                      {items.length}
                    </span>
                    <div className="flex-1 h-px bg-border-subtle" />
                  </div>
                  {/* Conversation cards */}
                  {items.map((conv) => (
                    <ConversationCard
                      key={conv.id}
                      conv={conv}
                      active={conv.id === activeId}
                      onLoad={() => loadConversation(conv.id)}
                      onDelete={() => deleteConversation(conv.id)}
                      onPin={() => togglePin(conv.id)}
                      onRename={(title) => renameConversation(conv.id, title)}
                    />
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Footer hint */}
      {filteredCount > 0 && (
        <div className="px-3 py-2 border-t border-border-subtle text-center">
          <p className="text-[9px] text-fg-muted">
            Double-click to rename · Hover to pin/delete
          </p>
        </div>
      )}
    </div>
  )
}
