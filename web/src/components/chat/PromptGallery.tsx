// Prompt gallery: a curated, categorized library of bilingual example
// prompts that speeds up 3D creation. Clicking a card inserts its full
// prompt into the input bar (rather than sending it) so the user can read
// and refine it before the Agent runs. Grouped by creative intent so the
// right starting point is easy to find: full scenes, materials & lighting,
// animation & motion, cinematic storyboards, and procedural generation.
import { Clapperboard, Layers, Lightbulb, Sparkles, Wind } from 'lucide-react'
import { useState } from 'react'

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
    id: 'scenes',
    label: 'Scenes',
    labelZh: '场景',
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
    ],
  },
  {
    id: 'materials',
    label: 'Materials & Light',
    labelZh: '材质与光照',
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
    ],
  },
  {
    id: 'motion',
    label: 'Animation & Motion',
    labelZh: '动画与运动',
    icon: Wind,
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
    ],
  },
  {
    id: 'storyboard',
    label: 'Storyboard',
    labelZh: '分镜',
    icon: Clapperboard,
    accent: 'text-rose-300',
    prompts: [
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
  {
    id: 'procedural',
    label: 'Procedural',
    labelZh: '程序化生成',
    icon: Sparkles,
    accent: 'text-accent-purple',
    prompts: [
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
    ],
  },
]

interface PromptGalleryProps {
  /** Insert a prompt into the input (never sends it directly). */
  onInsert: (prompt: string) => void
  disabled: boolean
}

/** Renders a compact, expandable gallery of categorized example prompts. */
export function PromptGallery({ onInsert, disabled }: PromptGalleryProps) {
  const [open, setOpen] = useState(false)
  const [activeCat, setActiveCat] = useState<string>(CATEGORIES[0].id)

  if (disabled) return null

  const category = CATEGORIES.find((c) => c.id === activeCat) ?? CATEGORIES[0]

  return (
    <div className="mb-2">
      {/* Toggle header */}
      <div className="flex items-center gap-2 mb-1.5">
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
          {CATEGORIES.reduce((n, c) => n + c.prompts.length, 0)} ideas · click to insert
        </span>
      </div>

      {open && (
        <div className="rounded-lg border border-border-subtle bg-bg-base/50 p-2">
          {/* Category chips */}
          <div className="flex items-center gap-1 flex-wrap mb-2">
            {CATEGORIES.map((c) => {
              const Icon = c.icon
              return (
                <button
                  key={c.id}
                  onClick={() => setActiveCat(c.id)}
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[9.5px] transition-colors border ${
                    activeCat === c.id
                      ? 'border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan'
                      : 'border-transparent text-fg-muted hover:text-fg-secondary hover:bg-bg-hover'
                  }`}
                >
                  <Icon size={10} className={c.accent} />
                  {c.label}
                  <span className="text-fg-muted/60">· {c.labelZh}</span>
                </button>
              )
            })}
          </div>

          {/* Prompt cards */}
          <div className="space-y-1.5">
            {category.prompts.map((p) => (
              <button
                key={p.id}
                onClick={() => onInsert(p.prompt)}
                title={p.prompt}
                className="w-full text-left rounded-md border border-border bg-bg-elevated/40 px-2.5 py-1.5 hover:border-accent-cyan/40 hover:bg-accent-cyan/5 transition-colors group"
              >
                <div className="text-[10.5px] font-medium text-fg-primary flex items-center gap-1.5">
                  {p.title}
                  <span className="text-[9px] text-fg-muted/70">{p.titleZh}</span>
                </div>
                <p className="text-[9.5px] text-fg-muted leading-relaxed mt-0.5 line-clamp-2">
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