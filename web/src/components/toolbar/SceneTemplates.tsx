// Scene templates browser: modal dialog showing available scene templates
import { AnimatePresence, motion } from 'framer-motion'
import {
  Atom,
  Box,
  Building2,
  Cog,
  Columns,
  Construction,
  Dna,
  FlaskConical,
  Flower,
  Gem,
  Globe2,
  Lightbulb,
  Mountain,
  Orbit,
  Package,
  Snowflake,
  Sparkles,
  TrendingUp,
  TreeDeciduous,
  X,
} from 'lucide-react'

export interface TemplateCard {
  id: string
  name: string
  description: string
  icon: typeof Box
  color: string
  prompt: string
  objects: string
  /** Optional skill tag — when present, the template invokes a registered skill. */
  skill?: string
}

export const TEMPLATES: TemplateCard[] = [
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
  // ----- Skill-aligned templates (each maps to a registered creative skill) -----
  {
    id: 'spiral_staircase',
    name: 'Spiral Staircase',
    description: 'Central pillar with steps spiraling upward, stone material',
    icon: TrendingUp,
    color: 'text-amber-300',
    prompt: 'Use the spiral_staircase skill to build a spiral staircase with 16 steps',
    objects: '17 objects',
    skill: 'spiral_staircase',
  },
  {
    id: 'colonnade',
    name: 'Colonnade',
    description: 'Row of marble columns on a plinth, classical architecture',
    icon: Columns,
    color: 'text-stone-300',
    prompt: 'Use the colonnade skill to build a row of 8 marble columns',
    objects: '9 objects',
    skill: 'colonnade',
  },
  {
    id: 'forest',
    name: 'Forest',
    description: 'Scattered trees with trunks and leafy crowns on a ground plane',
    icon: TreeDeciduous,
    color: 'text-emerald-400',
    prompt: 'Use the forest skill to grow a forest of 12 trees',
    objects: '24+ objects',
    skill: 'forest',
  },
  {
    id: 'crystal_garden',
    name: 'Crystal Garden',
    description: 'Cluster of glowing polyhedra on a reflective floor',
    icon: Flower,
    color: 'text-fuchsia-400',
    prompt: 'Use the crystal_garden skill to scatter a garden of 10 glowing crystals',
    objects: '10+ objects',
    skill: 'crystal_garden',
  },
  {
    id: 'dna_helix',
    name: 'DNA Helix',
    description: 'Double helix of spheres connected by rungs, rotating',
    icon: Dna,
    color: 'text-cyan-300',
    prompt: 'Use the dna_helix skill to construct a DNA double helix with 24 base pairs',
    objects: '50+ objects',
    skill: 'dna_helix',
  },
  {
    id: 'spiral_galaxy',
    name: 'Spiral Galaxy',
    description: 'Central bulge with two spiral arms of stars, dark sky',
    icon: Orbit,
    color: 'text-indigo-300',
    prompt: 'Use the spiral_galaxy skill to generate a spiral galaxy with 2 arms',
    objects: '120+ stars',
    skill: 'spiral_galaxy',
  },
  {
    id: 'studio_lighting_skill',
    name: 'Studio Lighting Rig',
    description: 'Three-point key/fill/rim light rig with a display platform',
    icon: Lightbulb,
    color: 'text-yellow-300',
    prompt: 'Use the studio_lighting skill to set up a three-point lighting rig',
    objects: '4 lights + platform',
    skill: 'studio_lighting',
  },
  {
    id: 'atom',
    name: 'Atom Model',
    description: 'Glowing nucleus with three electron orbits and shells',
    icon: Atom,
    color: 'text-sky-300',
    prompt: 'Build an atom model: a glowing nucleus with three electron orbits at different angles, each with electrons on them',
    objects: '7 objects',
    skill: 'atom',
  },
  {
    id: 'gear_assembly',
    name: 'Gear Assembly',
    description: 'Row of interlocking metal gears with radial teeth that visually mesh',
    icon: Cog,
    color: 'text-zinc-300',
    prompt: 'Use the gear_assembly skill to build a row of 3 interlocking gears with 12 teeth each',
    objects: '3 gears + teeth + axles',
    skill: 'gear_assembly',
  },
  {
    id: 'molecule',
    name: 'Molecule',
    description: 'Ball-and-stick molecule: central atom with satellites and bond cylinders',
    icon: FlaskConical,
    color: 'text-rose-300',
    prompt: 'Use the molecule skill to build a ball-and-stick molecule with 4 satellite atoms and bonds',
    objects: '1 center + 4 satellites + 4 bonds',
    skill: 'molecule',
  },
  {
    id: 'snowman',
    name: 'Snowman',
    description: 'Three stacked snow spheres with carrot nose, coal eyes, stick arms, and top hat',
    icon: Snowflake,
    color: 'text-sky-200',
    prompt: 'Use the snowman skill to build a snowman with a carrot nose, coal eyes, stick arms, and a top hat',
    objects: '3 spheres + nose + eyes + arms + hat',
    skill: 'snowman',
  },
  {
    id: 'bridge',
    name: 'Suspension Bridge',
    description: 'Deck, piers, towers, main cables, and hangers over a water plane',
    icon: Construction,
    color: 'text-amber-500',
    prompt: 'Use the bridge skill to build a suspension bridge with deck, towers, cables, and hangers over water',
    objects: 'Deck + 2 towers + cables + hangers + water',
    skill: 'bridge',
  },
  {
    id: 'zen_garden',
    name: 'Zen Garden',
    description: 'Raked sand garden with scattered stones, moss patches, and a muted backdrop',
    icon: Mountain,
    color: 'text-emerald-300',
    prompt: 'Use the zen_garden skill to build a zen garden with raked sand, scattered stones, and moss patches',
    objects: 'Sand plane + 5 stones + 3 moss patches',
    skill: 'zen_garden',
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
                      <div className="space-y-0.5 w-full">
                        <div className="flex items-center justify-between gap-1.5">
                          <h3 className="text-[12px] font-semibold text-fg-primary group-hover:text-accent-cyan transition-colors">
                            {tpl.name}
                          </h3>
                          {tpl.skill && (
                            <span
                              title={`Invokes skill: ${tpl.skill}`}
                              className="shrink-0 text-[8.5px] uppercase tracking-wider font-semibold text-accent-purple/80 border border-accent-purple/30 rounded px-1 py-px bg-accent-purple/5"
                            >
                              skill
                            </span>
                          )}
                        </div>
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
