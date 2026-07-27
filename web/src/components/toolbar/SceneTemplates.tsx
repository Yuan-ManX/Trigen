// Scene templates browser: modal dialog showing available scene templates
import { AnimatePresence, motion } from 'framer-motion'
import {
  Box,
  Building2,
  Gem,
  Globe2,
  Package,
  Sparkles,
  X,
} from 'lucide-react'

interface TemplateCard {
  id: string
  name: string
  description: string
  icon: typeof Box
  color: string
  prompt: string
  objects: string
}

const TEMPLATES: TemplateCard[] = [
  {
    id: 'solar_system',
    name: 'Solar System',
    description: 'Glowing sun with 8 orbiting planets and rings',
    icon: Globe2,
    color: 'text-amber-400',
    prompt: 'Create a solar system scene',
    objects: '17 objects',
  },
  {
    id: 'city_block',
    name: 'City Block',
    description: 'Grid of varied buildings on a ground plane',
    icon: Building2,
    color: 'text-cyan-400',
    prompt: 'Create a city block scene',
    objects: '12+ objects',
  },
  {
    id: 'studio',
    name: 'Studio Lighting',
    description: '3-point lighting setup with platform and subject',
    icon: Box,
    color: 'text-purple-400',
    prompt: 'Create a studio lighting setup',
    objects: '8 objects',
  },
  {
    id: 'crystal_cluster',
    name: 'Crystal Cluster',
    description: 'Random glowing crystals in a dark environment',
    icon: Gem,
    color: 'text-pink-400',
    prompt: 'Create a crystal cluster scene',
    objects: '10+ objects',
  },
  {
    id: 'product_showcase',
    name: 'Product Showcase',
    description: 'Pedestal with product under dramatic spotlight',
    icon: Package,
    color: 'text-emerald-400',
    prompt: 'Create a product showcase scene',
    objects: '6 objects',
  },
  {
    id: 'clear',
    name: 'Empty Scene',
    description: 'Clear the current scene and start fresh',
    icon: Sparkles,
    color: 'text-fg-muted',
    prompt: 'Clear the scene',
    objects: '0 objects',
  },
]

interface SceneTemplatesProps {
  open: boolean
  onClose: () => void
  onSelect: (prompt: string) => void
}

export function SceneTemplates({ open, onClose, onSelect }: SceneTemplatesProps) {
  const handleSelect = (template: TemplateCard) => {
    onSelect(template.prompt)
    onClose()
  }

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
            className="relative w-[680px] max-w-[90vw] max-h-[80vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-accent-cyan" />
                <h2 className="text-sm font-semibold text-fg-primary">
                  Scene Templates
                </h2>
                <span className="text-[10px] text-fg-muted">
                  {TEMPLATES.length} templates
                </span>
              </div>
              <button
                onClick={onClose}
                aria-label="Close templates"
                className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
              >
                <X size={15} />
              </button>
            </header>

            {/* Body: template grid */}
            <div className="p-5 overflow-y-auto max-h-[calc(80vh-48px)]">
              <div className="grid grid-cols-3 gap-3">
                {TEMPLATES.map((tpl, i) => {
                  const Icon = tpl.icon
                  return (
                    <motion.button
                      key={tpl.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, delay: i * 0.04 }}
                      onClick={() => handleSelect(tpl)}
                      className="group flex flex-col items-start gap-2 rounded-lg border border-border bg-bg-elevated/40 hover:bg-bg-hover hover:border-accent-cyan/40 transition-all p-3 text-left"
                    >
                      {/* Icon with glow */}
                      <div className="relative">
                        <div className="absolute inset-0 bg-accent-cyan/10 blur-lg rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="relative w-10 h-10 rounded-lg bg-bg-elevated border border-border flex items-center justify-center group-hover:border-accent-cyan/30 transition-colors">
                          <Icon
                            size={20}
                            className={`${tpl.color} group-hover:scale-110 transition-transform`}
                          />
                        </div>
                      </div>

                      {/* Text content */}
                      <div className="space-y-0.5">
                        <h3 className="text-[12px] font-semibold text-fg-primary group-hover:text-accent-cyan transition-colors">
                          {tpl.name}
                        </h3>
                        <p className="text-[10px] text-fg-muted leading-relaxed line-clamp-2">
                          {tpl.description}
                        </p>
                      </div>

                      {/* Object count badge */}
                      <span className="text-[9px] text-fg-muted/70 font-mono mt-auto">
                        {tpl.objects}
                      </span>
                    </motion.button>
                  )
                })}
              </div>

              {/* Hint */}
              <p className="text-center text-[10px] text-fg-muted mt-4">
                Click a template to generate it with the AI Agent
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
