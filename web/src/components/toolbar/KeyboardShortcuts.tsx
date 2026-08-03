// Keyboard shortcuts overlay: press ? to toggle, shows all available shortcuts
import { AnimatePresence, motion } from 'framer-motion'
import { Keyboard, X } from 'lucide-react'

interface ShortcutGroup {
  title: string
  shortcuts: Array<{ keys: string; description: string }>
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: 'Global',
    shortcuts: [
      { keys: 'Ctrl/Cmd + K', description: 'Open Command Palette' },
      { keys: 'Ctrl/Cmd + Z', description: 'Undo last action' },
      { keys: 'Ctrl/Cmd + Shift + Z', description: 'Redo undone action' },
      { keys: 'Ctrl/Cmd + Y', description: 'Redo (alternative)' },
      { keys: 'Ctrl/Cmd + D', description: 'Duplicate selected object' },
      { keys: 'Delete / Backspace', description: 'Delete selected object' },
      { keys: 'Escape', description: 'Deselect / Close panel' },
      { keys: '?', description: 'Toggle this shortcuts overlay' },
    ],
  },
  {
    title: 'Mode & View',
    shortcuts: [
      { keys: 'Ctrl/Cmd + E', description: 'Toggle Edit / Run mode' },
      { keys: '1', description: 'Switch to Move transform' },
      { keys: '2', description: 'Switch to Rotate transform' },
      { keys: '3', description: 'Switch to Scale transform' },
      { keys: 'F', description: 'Focus camera on selected object' },
      { keys: 'G', description: 'Toggle grid visibility' },
    ],
  },
  {
    title: 'Selection',
    shortcuts: [
      { keys: 'Click', description: 'Select object' },
      { keys: 'Click empty space', description: 'Deselect' },
      { keys: 'Ctrl/Cmd + Click', description: 'Multi-select (coming soon)' },
    ],
  },
  {
    title: 'Chat',
    shortcuts: [
      { keys: 'Enter', description: 'Send message' },
      { keys: 'Shift + Enter', description: 'New line in input' },
    ],
  },
]

interface KeyboardShortcutsProps {
  open: boolean
  onClose: () => void
}

/** Render a single keycap */
function KeyCap({ label }: { label: string }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[24px] h-5 px-1.5 rounded border border-border bg-bg-elevated text-[10px] font-mono font-medium text-fg-secondary shadow-sm">
      {label}
    </kbd>
  )
}

/** Parse a key combo string into individual keycaps */
function parseKeys(keys: string): string[] {
  return keys.split('+').map((k) => k.trim())
}

export function KeyboardShortcuts({ open, onClose }: KeyboardShortcutsProps) {
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
            className="relative w-[640px] max-w-[90vw] max-h-[80vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Keyboard size={16} className="text-accent-cyan" />
                <h2 className="text-sm font-semibold text-fg-primary">
                  Keyboard Shortcuts
                </h2>
              </div>
              <button
                onClick={onClose}
                aria-label="Close shortcuts"
                className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
              >
                <X size={15} />
              </button>
            </header>

            {/* Body: shortcut groups in a 2-column layout */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 p-5 overflow-y-auto max-h-[calc(80vh-48px)]">
              {SHORTCUT_GROUPS.map((group) => (
                <div key={group.title} className="space-y-2">
                  <h3 className="text-[10px] uppercase tracking-wider text-fg-muted font-semibold border-b border-border-subtle pb-1.5">
                    {group.title}
                  </h3>
                  <div className="space-y-1.5">
                    {group.shortcuts.map((s, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between gap-2"
                      >
                        <span className="text-[11px] text-fg-secondary">
                          {s.description}
                        </span>
                        <div className="flex items-center gap-1 shrink-0">
                          {parseKeys(s.keys).map((key, j) => (
                            <div key={j} className="flex items-center gap-1">
                              {j > 0 && (
                                <span className="text-[9px] text-fg-muted">+</span>
                              )}
                              <KeyCap label={key} />
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <footer className="px-5 py-3 border-t border-border-subtle text-center">
              <p className="text-[10px] text-fg-muted">
                Press <KeyCap label="?" /> or <KeyCap label="Esc" /> to close
              </p>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
