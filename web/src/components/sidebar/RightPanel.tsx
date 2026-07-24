// 右侧面板：Tab 切换图层 / 属性，可折叠
// Right panel: tab switching between layers / properties, collapsible
import { Layers, PanelRightClose, Settings2 } from 'lucide-react'
import { useState } from 'react'
import { useScene } from '../../store/useScene'
import { LayersTab } from './LayersTab'
import { PropertiesTab } from './PropertiesTab'

type Tab = 'layers' | 'properties'

interface RightPanelProps {
  onCollapse: () => void
}

export function RightPanel({ onCollapse }: RightPanelProps) {
  const [tab, setTab] = useState<Tab>('layers')
  const selectedId = useScene((s) => s.selectedId)

  // 选中对象时自动切换到属性面板
  // Auto-switch to the properties panel when an object is selected
  const effectiveTab: Tab = selectedId ? 'properties' : tab

  return (
    <aside className="flex flex-col w-[280px] shrink-0 border-l border-border bg-bg-panel">
      {/* Tab 头部 */}
      {/* Tab header */}
      <header className="flex items-center justify-between h-11 border-b border-border">
        <div className="flex">
          <button
            onClick={() => setTab('layers')}
            className={`flex items-center gap-1.5 h-11 px-3 text-xs font-medium border-b-2 transition-colors ${
              effectiveTab === 'layers'
                ? 'text-fg-primary border-accent-cyan'
                : 'text-fg-muted border-transparent hover:text-fg-secondary'
            }`}
          >
            <Layers size={13} />
            图层
          </button>
          <button
            onClick={() => setTab('properties')}
            className={`flex items-center gap-1.5 h-11 px-3 text-xs font-medium border-b-2 transition-colors ${
              effectiveTab === 'properties'
                ? 'text-fg-primary border-accent-cyan'
                : 'text-fg-muted border-transparent hover:text-fg-secondary'
            }`}
          >
            <Settings2 size={13} />
            属性
          </button>
        </div>
        <button
          onClick={onCollapse}
          aria-label="折叠右侧面板"
          className="mr-3 text-fg-muted hover:text-fg-primary transition-colors"
        >
          <PanelRightClose size={16} />
        </button>
      </header>

      {/* 内容区 */}
      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {effectiveTab === 'layers' ? <LayersTab /> : <PropertiesTab />}
      </div>
    </aside>
  )
}
