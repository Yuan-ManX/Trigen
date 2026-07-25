// Right panel: tab switching between layers / properties / scene settings, collapsible
import { Globe, Layers, PanelRightClose, Settings2 } from 'lucide-react'
import { useState } from 'react'
import { useScene } from '../../store/useScene'
import { LayersTab } from './LayersTab'
import { PropertiesTab } from './PropertiesTab'
import { SceneSettingsTab } from './SceneSettingsTab'

type Tab = 'layers' | 'properties' | 'scene'

interface RightPanelProps {
  onCollapse: () => void
}

export function RightPanel({ onCollapse }: RightPanelProps) {
  const [tab, setTab] = useState<Tab>('layers')
  const selectedId = useScene((s) => s.selectedId)

  // Auto-switch to properties when an object is selected (only from layers tab)
  const effectiveTab: Tab = selectedId && tab === 'layers' ? 'properties' : tab

  const tabs: Array<{ id: Tab; icon: typeof Layers; label: string }> = [
    { id: 'layers', icon: Layers, label: 'Layers' },
    { id: 'properties', icon: Settings2, label: 'Props' },
    { id: 'scene', icon: Globe, label: 'Scene' },
  ]

  return (
    <aside className="flex flex-col w-[280px] shrink-0 border-l border-border bg-bg-panel">
      {/* Tab header */}
      <header className="flex items-center justify-between h-11 border-b border-border">
        <div className="flex">
          {tabs.map((t) => {
            const Icon = t.icon
            const active = effectiveTab === t.id
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 h-11 px-3 text-xs font-medium border-b-2 transition-colors ${
                  active
                    ? 'text-fg-primary border-accent-cyan'
                    : 'text-fg-muted border-transparent hover:text-fg-secondary'
                }`}
              >
                <Icon size={13} />
                <span>{t.label}</span>
              </button>
            )
          })}
        </div>
        <button
          onClick={onCollapse}
          aria-label="Collapse right panel"
          className="mr-3 text-fg-muted hover:text-fg-primary transition-colors"
        >
          <PanelRightClose size={16} />
        </button>
      </header>

      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {effectiveTab === 'layers' && <LayersTab />}
        {effectiveTab === 'properties' && <PropertiesTab />}
        {effectiveTab === 'scene' && <SceneSettingsTab />}
      </div>
    </aside>
  )
}
