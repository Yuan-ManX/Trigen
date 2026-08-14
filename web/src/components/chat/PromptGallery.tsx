// Prompt gallery: a curated, categorized library of bilingual example
// prompts that speeds up 3D creation. Clicking a card inserts its full
// prompt into the input bar (rather than sending it) so the user can read
// and refine it before the Agent runs.
//
// The gallery is paired with a SceneContextPanel above it, which suggests
// next-best actions based on the current live scene and exposes a template
// quick-start strip driven by the Agent's creative skill catalog.
//
// Prompts are grouped by creative intent so the right starting point is
// easy to find: creation (full scenes and procedural generation), lighting
// & mood, post-processing (cinematic looks), composition (multi-object
// arrangements), and animation & motion (including camera storyboards).
import { Aperture, Boxes, Clapperboard, Layers, Lightbulb, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { SceneContextPanel } from './SceneContextPanel'

interface GalleryPrompt {
  id: string
  title: string
  titleZh: string
  prompt: string
}

interface GalleryCategory {
  id: string
  label: string
  labelZh: string
  icon: typeof Sparkles
  accent: string
  prompts: GalleryPrompt[]
}

const CATEGORIES: GalleryCategory[] = [
  {
    id: 'creation',
    label: 'Creation',
    labelZh: '创建',
    icon: Layers,
    accent: 'text-accent-cyan',
    prompts: [
      {
        id: 'island',
        title: 'Low-poly isle',
        titleZh: '低多边形小岛',
        prompt: 'Compose a low-poly island: a sandy disc with a few palm trees, surrounded by a calm blue sea plane, warm sunlit palette.',
      },
      {
        id: 'cyberpunk',
        title: 'Cyberpunk alley',
        titleZh: '赛博朋克小巷',
        prompt: 'Build a night cyberpunk street: a row of glossy dark buildings with neon cyan and magenta signs, wet reflective ground plane, cinematic fog.',
      },
      {
        id: 'showroom',
        title: 'Product showcase',
        titleZh: '产品展示台',
        prompt: 'Create a minimalist product showcase: a glossy colored sphere on a white pedestal, soft studio three-point lighting, subtle gradient background.',
      },
      {
        id: 'terrain',
        title: 'Rolling terrain',
        titleZh: '起伏地形',
        prompt: 'Generate rolling terrain with a few hills, then add an L-system tree on the tallest hill.',
      },
      {
        id: 'crystal',
        title: 'Crystal cluster',
        titleZh: '水晶簇',
        prompt: 'Run the crystal garden composition to scatter a cluster of translucent colored crystals across the ground.',
      },
      {
        id: 'noise-deform',
        title: 'Noise deformation',
        titleZh: '噪声变形',
        prompt: 'Add noise deformation to all spheres',
      },
    ],
  },
  {
    id: 'lighting',
    label: 'Lighting & Mood',
    labelZh: '光照与氛围',
    icon: Lightbulb,
    accent: 'text-accent-gold',
    prompts: [
      {
        id: 'rimlight',
        title: 'Rim-lit hero',
        titleZh: '轮廓光主角',
        prompt: 'Style the scene with drama: dim the ambient light, add a warm key light from the front and a cool cyan rim light behind the main object.',
      },
      {
        id: 'glass-metal',
        title: 'Glass & metal',
        titleZh: '玻璃与金属',
        prompt: 'Apply a glass preset to the sphere and a polished metal preset to the torus, then add a ground plane with a soft reflection-like sheen.',
      },
      {
        id: 'sunset',
        title: 'Warm sunset',
        titleZh: '温暖日落',
        prompt: 'Set the background to a warm sunset gradient, switch the lights to a low warm sun and a cool fill, and add a light amber fog.',
      },
      {
        id: 'cozy-mood',
        title: 'Cozy mood',
        titleZh: '温馨氛围',
        prompt: 'Create a cozy lighting mood',
      },
    ],
  },
  {
    id: 'postprocessing',
    label: 'Post-Processing',
    labelZh: '后期处理',
    icon: Aperture,
    accent: 'text-rose-300',
    prompts: [
      {
        id: 'cinematic-bloom',
        title: 'Cinematic bloom',
        titleZh: '电影感辉光',
        prompt: 'Add cinematic bloom with color grading',
      },
      {
        id: 'noir',
        title: 'Noir look',
        titleZh: '黑色电影',
        prompt: 'Make it look noir',
      },
    ],
  },
  {
    id: 'composition',
    label: 'Composition',
    labelZh: '组合构图',
    icon: Boxes,
    accent: 'text-accent-purple',
    prompts: [
      {
        id: 'spiral-staircase',
        title: 'Spiral staircase',
        titleZh: '螺旋楼梯',
        prompt: 'Create a spiral staircase with 12 marble steps',
      },
      {
        id: 'scatter-spheres',
        title: 'Scatter spheres',
        titleZh: '散布球体',
        prompt: 'Scatter 15 spheres randomly around the origin',
      },
      {
        id: 'bridge',
        title: 'Arched bridge',
        titleZh: '拱桥',
        prompt: 'Build a bridge with an arch',
      },
    ],
  },
  {
    id: 'animation',
    label: 'Animation',
    labelZh: '动画',
    icon: Clapperboard,
    accent: 'text-accent-emerald',
    prompts: [
      {
        id: 'orbitcam',
        title: 'Orbit camera',
        titleZh: '环绕相机',
        prompt: 'Animate the camera in a slow orbit around the main object at a height of 2, radius 6, looping smoothly.',
      },
      {
        id: 'bounce',
        title: 'Bouncing sphere',
        titleZh: '弹跳球体',
        prompt: 'Add a bounce animation to the sphere so it rises and falls near the ground, then pause the scene animation.',
      },
      {
        id: 'wave',
        title: 'Wave field',
        titleZh: '波浪阵列',
        prompt: 'Create a 5x5 grid of small cubes on the ground and add a wave animation to them so they ripple outward in sequence.',
      },
      {
        id: 'director',
        title: 'Cinematic tour',
        titleZh: '电影环绕',
        prompt: 'Compose a cinematic storyboard with three shots: a wide establishing shot, a close-up on the main object, and a slow orbit ending back at the wide view.',
      },
      {
        id: 'reveal',
        title: 'Hero reveal',
        titleZh: '主角亮相',
        prompt: 'Compose a storyboard titled "Hero reveal" that starts low and pulls back to frame the whole scene, then play it.',
      },
    ],
  },
]

interface PromptGalleryProps {
  /** Insert a prompt into the input (never sends it directly). */
  onInsert: (prompt: string) => void
  disabled: boolean
}

/** Renders a compact, expandable gallery of categorized example prompts
 *  along with the scene-aware suggestion panel above it. */
export function PromptGallery({ onInsert, disabled }: PromptGalleryProps) {
  const [open, setOpen] = useState(false)
  const [activeCat, setActiveCat] = useState<string>(CATEGORIES[0].id)

  if (disabled) return null

  const category = CATEGORIES.find((c) => c.id === activeCat) ?? CATEGORIES[0]

  return (
    <div className="mb-1.5">
      {/* Scene-aware suggestion panel — reacts to the live scene and
          recommends the next best action. Shown above the prompt gallery
          so it is the first thing the user sees before browsing templates. */}
      <SceneContextPanel onInsert={onInsert} disabled={disabled} />

      {/* Toggle header */}
      <div className="flex items-center gap-2 mb-0.5">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-medium text-accent-cyan hover:text-accent-cyan/80 transition-colors"
        >
          <Sparkles size={11} />
          <span>Prompt gallery / 示例提示</span>
          <span className={`text-fg-muted transition-transform ${open ? 'rotate-0' : ''}`}>
            {open ? '▾' : '▸'}
          </span>
        </button>
        <span className="text-[9px] text-fg-muted/60">
          {CATEGORIES.reduce((n, c) => n + c.prompts.length, 0)} ideas
        </span>
      </div>

      {open && (
        <div className="rounded-lg border border-border-subtle bg-bg-base/50 px-2 py-1.5">
          {/* Category chips */}
          <div className="flex items-center gap-1 flex-wrap mb-1.5">
            {CATEGORIES.map((c) => {
              const Icon = c.icon
              return (
                <button
                  key={c.id}
                  onClick={() => setActiveCat(c.id)}
                  className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] transition-colors border ${
                    activeCat === c.id
                      ? 'border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan'
                      : 'border-transparent text-fg-muted hover:text-fg-secondary hover:bg-bg-hover'
                  }`}
                >
                  <Icon size={9} className={c.accent} />
                  {c.label}
                  <span className="text-fg-muted/60">· {c.labelZh}</span>
                </button>
              )
            })}
          </div>

          {/* Prompt cards */}
          <div className="space-y-1">
            {category.prompts.map((p) => (
              <button
                key={p.id}
                onClick={() => onInsert(p.prompt)}
                title={p.prompt}
                className="w-full text-left rounded-md border border-border bg-bg-elevated/40 px-2 py-1 hover:border-accent-cyan/40 hover:bg-accent-cyan/5 transition-colors group"
              >
                <div className="text-[10px] font-medium text-fg-primary flex items-center gap-1">
                  {p.title}
                  <span className="text-[8.5px] text-fg-muted/70">{p.titleZh}</span>
                </div>
                <p className="text-[9px] text-fg-muted leading-relaxed mt-0.5 line-clamp-2">
                  {p.prompt}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}