// Material library: visual presets browser for quick material application
import { AnimatePresence, motion } from 'framer-motion'
import {
  Diamond,
  Gem,
  GlassWater,
  Leaf,
  Lightbulb,
  Paintbrush,
  PaintBucket,
  Sparkles,
  TreePine,
  X,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import { useScene } from '../../store/useScene'
import type { Material } from '../../types'

/** Material preset definition */
interface MaterialPreset {
  id: string
  name: string
  description: string
  icon: typeof Diamond
  swatch: string // CSS gradient for the visual preview
  material: Material
}

/** Available material presets */
const PRESETS: MaterialPreset[] = [
  {
    id: 'wood',
    name: 'Wood',
    description: 'Warm brown with low metalness',
    icon: TreePine,
    swatch: 'linear-gradient(135deg, #8B4513 0%, #A0522D 50%, #D2691E 100%)',
    material: {
      color: '#A0522D',
      metalness: 0.0,
      roughness: 0.85,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'metal',
    name: 'Polished Metal',
    description: 'High metalness, low roughness',
    icon: Diamond,
    swatch: 'linear-gradient(135deg, #C0C0C0 0%, #E8E8E8 50%, #A9A9A9 100%)',
    material: {
      color: '#C0C0C0',
      metalness: 1.0,
      roughness: 0.15,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'gold',
    name: 'Gold',
    description: 'Warm metallic gold finish',
    icon: Gem,
    swatch: 'linear-gradient(135deg, #B8860B 0%, #FFD700 50%, #DAA520 100%)',
    material: {
      color: '#FFD700',
      metalness: 1.0,
      roughness: 0.2,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'glass',
    name: 'Glass',
    description: 'Transparent with high roughness',
    icon: GlassWater,
    swatch: 'linear-gradient(135deg, rgba(200,230,255,0.3) 0%, rgba(150,200,255,0.5) 50%, rgba(180,220,255,0.3) 100%)',
    material: {
      color: '#AACCFF',
      metalness: 0.0,
      roughness: 0.05,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 0.3,
      wireframe: false,
    },
  },
  {
    id: 'plastic',
    name: 'Plastic',
    description: 'Smooth non-metallic surface',
    icon: PaintBucket,
    swatch: 'linear-gradient(135deg, #FF6B6B 0%, #EE5A5A 50%, #FF8787 100%)',
    material: {
      color: '#EE5A5A',
      metalness: 0.0,
      roughness: 0.4,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'neon-cyan',
    name: 'Neon Cyan',
    description: 'Emissive glowing cyan',
    icon: Zap,
    swatch: 'linear-gradient(135deg, #00F0FF 0%, #00C4D8 50%, #00FFFF 100%)',
    material: {
      color: '#00F0FF',
      metalness: 0.3,
      roughness: 0.2,
      emissive: '#00F0FF',
      emissive_intensity: 1.5,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'neon-pink',
    name: 'Neon Pink',
    description: 'Emissive glowing pink',
    icon: Sparkles,
    swatch: 'linear-gradient(135deg, #FF00FF 0%, #FF1493 50%, #FF69B4 100%)',
    material: {
      color: '#FF1493',
      metalness: 0.3,
      roughness: 0.2,
      emissive: '#FF1493',
      emissive_intensity: 1.5,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'emerald',
    name: 'Emerald',
    description: 'Rich green gemstone',
    icon: Leaf,
    swatch: 'linear-gradient(135deg, #006400 0%, #008B8B 50%, #00FF00 100%)',
    material: {
      color: '#008B8B',
      metalness: 0.5,
      roughness: 0.1,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'obsidian',
    name: 'Obsidian',
    description: 'Dark volcanic glass',
    icon: Gem,
    swatch: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0f1e 100%)',
    material: {
      color: '#1a1a2e',
      metalness: 0.4,
      roughness: 0.05,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
    },
  },
  {
    id: 'luminous',
    name: 'Luminous White',
    description: 'Self-illuminating white',
    icon: Lightbulb,
    swatch: 'linear-gradient(135deg, #FFFFFF 0%, #F0F0F0 50%, #E0E0E0 100%)',
    material: {
      color: '#FFFFFF',
      metalness: 0.0,
      roughness: 0.3,
      emissive: '#FFFFFF',
      emissive_intensity: 0.8,
      opacity: 1,
      wireframe: false,
    },
  },
  // Extended-PBR presets leveraging clearcoat / transmission / iridescence /
  // sheen. These require MeshPhysicalMaterial, now used by SceneMesh.
  {
    id: 'carpaint',
    name: 'Car Paint',
    description: 'Clearcoat lacquer over metallic base',
    icon: Paintbrush,
    swatch: 'linear-gradient(135deg, #4a0808 0%, #7a0d0d 50%, #c16666 100%)',
    material: {
      color: '#7a0d0d',
      metalness: 0.85,
      roughness: 0.3,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
      clearcoat: 1.0,
      clearcoat_roughness: 0.08,
    },
  },
  {
    id: 'crystal',
    name: 'Crystal',
    description: 'High-IOR transmissive solid',
    icon: Gem,
    swatch: 'linear-gradient(135deg, #bfe9ff 0%, #e6f5ff 50%, #8fd3ff 100%)',
    material: {
      color: '#bfe9ff',
      metalness: 0.0,
      roughness: 0.02,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
      transmission: 0.95,
      thickness: 0.6,
      ior: 2.0,
      attenuation_distance: 1.2,
    },
  },
  {
    id: 'bubble',
    name: 'Soap Bubble',
    description: 'Iridescent thin-film surface',
    icon: Sparkles,
    swatch: 'linear-gradient(135deg, #ffd6f5 0%, #d6fffb 50%, #ffffd6 100%)',
    material: {
      color: '#ffffff',
      metalness: 0.0,
      roughness: 0.0,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 0.5,
      wireframe: false,
      transmission: 0.6,
      iridescence: 1.0,
      iridescence_ior: 1.33,
      ior: 1.25,
    },
  },
  {
    id: 'velvet',
    name: 'Velvet',
    description: 'Sheen-lit fabric surface',
    icon: PaintBucket,
    swatch: 'linear-gradient(135deg, #3a0f44 0%, #5b1a66 50%, #c486d6 100%)',
    material: {
      color: '#5b1a66',
      metalness: 0.0,
      roughness: 0.9,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
      sheen: 1.0,
      sheen_color: '#c486d6',
      sheen_roughness: 0.3,
    },
  },
  {
    id: 'diamond',
    name: 'Diamond',
    description: 'Brilliant cut, IOR 2.42',
    icon: Diamond,
    swatch: 'linear-gradient(135deg, #ffffff 0%, #f0f8ff 50%, #c8e6ff 100%)',
    material: {
      color: '#ffffff',
      metalness: 0.0,
      roughness: 0.0,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
      transmission: 1.0,
      ior: 2.42,
      thickness: 0.5,
    },
  },
  {
    id: 'oilsllick',
    name: 'Oil Slick',
    description: 'Iridescent dark film layer',
    icon: Zap,
    swatch: 'linear-gradient(135deg, #0a0a0a 0%, #1a0a2a 30%, #2a5a8a 60%, #6a2a8a 100%)',
    material: {
      color: '#101010',
      metalness: 0.4,
      roughness: 0.3,
      emissive: '#000000',
      emissive_intensity: 0,
      opacity: 1,
      wireframe: false,
      iridescence: 1.0,
      iridescence_ior: 1.5,
      iridescence_thickness_min: 200,
      iridescence_thickness_max: 700,
    },
  },
]

interface MaterialLibraryProps {
  open: boolean
  onClose: () => void
}

export function MaterialLibrary({ open, onClose }: MaterialLibraryProps) {
  const selected = useScene((s) => s.selected())
  const updateMaterial = useScene((s) => s.updateMaterial)
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const handleApply = (preset: MaterialPreset) => {
    if (!selected) return
    updateMaterial(selected.id, preset.material)
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
            className="relative w-[580px] max-w-[90vw] max-h-[80vh] overflow-hidden rounded-xl border border-border bg-bg-panel shadow-2xl"
          >
            {/* Header */}
            <header className="flex items-center justify-between h-12 px-5 border-b border-border">
              <div className="flex items-center gap-2">
                <Paintbrush size={16} className="text-accent-cyan" />
                <h2 className="text-sm font-semibold text-fg-primary">
                  Material Library
                </h2>
                <span className="text-[10px] text-fg-muted">
                  {PRESETS.length} presets
                </span>
              </div>
              <button
                onClick={onClose}
                aria-label="Close material library"
                className="flex items-center justify-center w-7 h-7 rounded text-fg-muted hover:text-fg-primary hover:bg-bg-hover transition-colors"
              >
                <X size={15} />
              </button>
            </header>

            {/* Selection warning */}
            {!selected && (
              <div className="px-5 py-2 bg-accent-gold/10 border-b border-accent-gold/20">
                <p className="text-[11px] text-accent-gold">
                  Select an object first to apply a material preset.
                </p>
              </div>
            )}

            {/* Body: material grid */}
            <div className="p-5 overflow-y-auto max-h-[calc(80vh-48px)]">
              <div className="grid grid-cols-3 gap-3">
                {PRESETS.map((preset, i) => {
                  const Icon = preset.icon
                  const isHovered = hoveredId === preset.id
                  return (
                    <motion.button
                      key={preset.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, delay: i * 0.03 }}
                      onMouseEnter={() => setHoveredId(preset.id)}
                      onMouseLeave={() => setHoveredId(null)}
                      onClick={() => handleApply(preset)}
                      disabled={!selected}
                      className="group flex flex-col overflow-hidden rounded-lg border border-border bg-bg-elevated/40 hover:border-accent-cyan/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {/* Swatch preview */}
                      <div
                        className="h-16 w-full relative overflow-hidden"
                        style={{ background: preset.swatch }}
                      >
                        <div className="absolute inset-0 flex items-center justify-center">
                          <Icon
                            size={24}
                            className={`text-white/80 drop-shadow-lg transition-transform ${
                              isHovered ? 'scale-125' : 'scale-100'
                            }`}
                          />
                        </div>
                        {/* Shine effect on hover */}
                        <div className="absolute inset-0 bg-gradient-to-t from-black/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>

                      {/* Info */}
                      <div className="px-2.5 py-2 text-left">
                        <h3 className="text-[11px] font-semibold text-fg-primary group-hover:text-accent-cyan transition-colors">
                          {preset.name}
                        </h3>
                        <p className="text-[9px] text-fg-muted leading-relaxed mt-0.5 line-clamp-1">
                          {preset.description}
                        </p>
                      </div>
                    </motion.button>
                  )
                })}
              </div>

              {/* Hint */}
              <p className="text-center text-[10px] text-fg-muted mt-4">
                {selected
                  ? `Click a preset to apply it to "${selected.name}"`
                  : 'Select an object in the scene to apply materials'}
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
