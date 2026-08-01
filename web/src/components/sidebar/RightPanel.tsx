// Right panel: tab switching between layers / outliner / timeline / properties /
// scene settings. Uses compact icon-only tabs (with tooltips) so five panels fit
// within the 280px sidebar. Collapsible.
import { Clapperboard, Globe, Layers, ListTree, PanelRightClose, Settings2 } from 'lucide-react'
import { useEditor, type PanelTab } from '../../store/useEditor'
import { useScene } from '../../store/useScene'
import { LayersTab } from './LayersTab'
import { Outliner } from './Outliner'
import { PropertiesTab } from './PropertiesTab'
import { SceneSettingsTab } from './SceneSettingsTab'
import { Timeline } from './Timeline'

interface RightPanelProps {
  onCollapse: () => void
}

export function RightPanel({ onCollapse }: RightPanelProps) {
  const tab = useEditor((s) => s.activePanel)
  const setTab = useEditor((s) => s.setActivePanel)
  const selectedId = useScene((s) => s.selectedId)

  // Auto-switch to properties when an object is selected from a list-style tab
  const effectiveTab: PanelTab =
    selectedId && (tab === 'layers' || tab === 'outliner') ? 'properties' : tab

  const tabs: Array<{ id: PanelTab; icon: typeof Layers; label: string }> = [
    { id: 'layers', icon: Layers, label: 'Layers' },
    { id: 'outliner', icon: ListTree, label: 'Outliner' },
    { id: 'timeline', icon: Clapperboard, label: 'Timeline' },
    { id: 'properties', icon: Settings2, label: 'Properties' },
    { id: 'scene', icon: Globe, label: 'Scene' },
  ]

  return (
    <aside className="flex flex-col w-[280px] shrink-0 border-l border-border bg-bg-panel">
      {/* Tab header — icon-only for compactness across five panels */}
      <header className="flex items-center justify-between h-11 border-b border-border">
        <div className="flex">
          {tabs.map((t) => {
            const Icon = t.icon
            const active = effectiveTab === t.id
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                title={t.label}
                aria-label={t.label}
                className={`flex items-center justify-center w-10 h-11 border-b-2 transition-colors ${
                  active
                    ? 'text-fg-primary border-accent-cyan'
                    : 'text-fg-muted border-transparent hover:text-fg-secondary'
                }`}
              >
                <Icon size={15} />
              </button>
            )
          })}
        </div>
        <button
          onClick={onCollapse}
          aria-label="Collapse right panel"
          className="mr-2.5 text-fg-muted hover:text-fg-primary transition-colors"
        >
          <PanelRightClose size={16} />
        </button>
      </header>

      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {effectiveTab === 'layers' && <LayersTab />}
        {effectiveTab === 'outliner' && <Outliner />}
        {effectiveTab === 'timeline' && <Timeline />}
        {effectiveTab === 'properties' && <PropertiesTab />}
        {effectiveTab === 'scene' && <SceneSettingsTab />}
      </div>
    </aside>
  )
}
