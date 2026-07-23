import {
  MessageSquare,
  Boxes,
  Sparkles,
  Globe,
  FileOutput,
  Layers,
  Gamepad2,
  Printer,
  Palette,
  GraduationCap,
  Orbit,
  type LucideIcon,
} from "lucide-react";

export type Lang = "en" | "zh";

export interface InnovationItem {
  index: string;
  title: string;
  desc: string;
  keyword: string;
}

export interface FeatureItem {
  index: string;
  icon: LucideIcon;
  title: string;
  desc: string;
}

export interface UseCaseItem {
  icon: LucideIcon;
  title: string;
  desc: string;
  tag: string;
}

export interface NavLink {
  label: string;
  href: string;
}

export interface StatItem {
  value: string;
  label: string;
}

export interface Translation {
  nav: NavLink[];
  hero: {
    tagline: string;
    subtitle: string;
    primaryCta: string;
    ghostCta: string;
    scroll: string;
  };
  stats: StatItem[];
  innovation: {
    label: string;
    titleL1: string;
    titleL2: string;
    desc: string;
    items: InnovationItem[];
    tri: { label: string; en: string; color: string }[];
  };
  features: {
    label: string;
    titleL1: string;
    titleL2: string;
    desc: string;
    active: string;
    items: FeatureItem[];
  };
  useCases: {
    label: string;
    titleL1: string;
    titleL2: string;
    desc: string;
    enter: string;
    more: string;
    items: UseCaseItem[];
  };
  cta: {
    label: string;
    titleL1: string;
    titleL2: string;
    desc: string;
    placeholder: string;
    submit: string;
    submitted: string;
    submittedNote: string;
  };
  footer: {
    tagline: string;
    cols: { title: string; links: NavLink[] }[];
  };
  langToggle: {
    to: string;
  };
}

const featureIcons = [MessageSquare, Boxes, Sparkles, Globe, FileOutput, Layers];
const useCaseIcons = [Gamepad2, Printer, Palette, GraduationCap, Orbit];

export const translations: Record<Lang, Translation> = {
  en: {
    nav: [
      { label: "Innovation", href: "#innovation" },
      { label: "Capabilities", href: "#features" },
      { label: "Use Cases", href: "#use-cases" },
    ],
    hero: {
      tagline: "From Three, AI Generates Everything",
      subtitle: "An AI-Native 3D Creation Agent Platform, Exploring the Creation of 3D Content!",
      primaryCta: "Start Creating",
      ghostCta: "Explore Innovation",
      scroll: "Scroll",
    },
    stats: [
      { value: "1st", label: "Conversational 3D Agent Worldwide" },
      { value: "4", label: "Native Formats FBX/OBJ/GLB/STL" },
      { value: "0", label: "3D Experience Required" },
      { value: "∞", label: "3D Forms to Generate" },
    ],
    innovation: {
      label: "Innovation / Original",
      titleL1: "Three Elements,",
      titleL2: "One Genesis Logic",
      desc: "Trigen orchestrates geometry, material and lighting — the three core pillars of 3D graphics — as a unified triple driven by a single autonomous agent. One coherent flow replaces fragmented manual pipelines. This is the 3D generation paradigm born for the conversational era.",
      items: [
        {
          index: "01",
          title: "Conversational 3D Generation",
          keyword: "Dialogue",
          desc: "The first agent that materializes 3D assets from natural dialogue. Speak, upload a photo, or drop a sketch — Trigen reasons, plans and builds the model.",
        },
        {
          index: "02",
          title: "Tri-Element Agent Orchestration",
          keyword: "Tri-Element",
          desc: "Geometry, material and lighting are orchestrated as a unified triple by a single autonomous agent, replacing fragmented manual pipelines with one coherent flow.",
        },
        {
          index: "03",
          title: "Zero-Barrier Creation",
          keyword: "Zero-Barrier",
          desc: "No 3D expertise needed. Mesh topology, UV layout and shading graphs are abstracted behind plain language. Everyone becomes a creator.",
        },
      ],
      tri: [
        { label: "Geometry", en: "Geometry", color: "text-snow" },
        { label: "Material", en: "Material", color: "text-cyber" },
        { label: "Lighting", en: "Lighting", color: "text-amber" },
      ],
    },
    features: {
      label: "Capabilities / Power",
      titleL1: "Six-Dimensional",
      titleL2: "Matrix of Power",
      desc: "Multi-modal input, built-in AI models, agent-driven editing, browser preview, multi-format export, cross-platform integration — every link forged for conversational 3D creation.",
      active: "ACTIVE",
      items: [
        { index: "01", icon: featureIcons[0], title: "Multi-Modal Input", desc: "Text prompts, photos and sketches all drive 3D generation. Dialogue is creation." },
        { index: "02", icon: featureIcons[1], title: "Built-in AI 3D Models", desc: "A curated set of 3D generation models wired into the agent runtime, ready to use." },
        { index: "03", icon: featureIcons[2], title: "Agent-Driven Editing", desc: "Iterate on generated or uploaded 3D content through dialogue: reshape, retexture, relight, animate." },
        { index: "04", icon: featureIcons[3], title: "Real-Time Browser Preview", desc: "Instant visual feedback in a web-native workspace. No software to install." },
        { index: "05", icon: featureIcons[4], title: "Multi-Format Export", desc: "One-click output to FBX, OBJ, GLB and STL, covering print and production pipelines." },
        { index: "06", icon: featureIcons[5], title: "Cross-Platform Integration", desc: "Drop assets straight into Blender, Unity, Unreal Engine and other tools." },
      ],
    },
    useCases: {
      label: "Use Cases / Scenarios",
      titleL1: "Dialogue is the Entry,",
      titleL2: "Anything Can Be Born",
      desc: "From games and film to 3D printing, from digital art to education — Trigen lets anyone create 3D content in any scenario.",
      enter: "Enter Scenario",
      more: "More scenarios generating",
      items: [
        { icon: useCaseIcons[0], title: "Games & Film", desc: "Rapidly prototype characters, props and environments for Unity or Unreal.", tag: "Game / Film" },
        { icon: useCaseIcons[1], title: "3D Printing", desc: "Turn ideas into STL-ready printable models in minutes.", tag: "Printable" },
        { icon: useCaseIcons[2], title: "Digital Art & Design", desc: "Generate sculptures, scenes and visual assets from a single sentence.", tag: "Art" },
        { icon: useCaseIcons[3], title: "Education & Exploration", desc: "Let anyone experience 3D creation without a learning curve.", tag: "Learn" },
        { icon: useCaseIcons[4], title: "Virtual Scenes", desc: "Build interactive browser-native 3D worlds on demand.", tag: "Virtual" },
      ],
    },
    cta: {
      label: "Early Access / Preview",
      titleL1: "Become One of the First",
      titleL2: "Conversational Creators",
      desc: "Leave your email to be among the first to access Trigen. No 3D experience needed — just a sentence, and start creating.",
      placeholder: "your@email.com",
      submit: "Request Access",
      submitted: "Joined",
      submittedNote: "✓ Application received. We'll reach out soon.",
    },
    footer: {
      tagline: "Trigen is the World's First Open-Source Conversational AI agent for 3D creation. From a single thought, three elements spawn infinite 3D forms.",
      cols: [
        {
          title: "Project",
          links: [
            { label: "Innovation", href: "#innovation" },
            { label: "Capabilities", href: "#features" },
            { label: "Use Cases", href: "#use-cases" },
          ],
        },
        {
          title: "Resources",
          links: [
            { label: "Early Access", href: "#cta" },
            { label: "GitHub", href: "https://github.com/Yuan-ManX/Trigen" },
            { label: "Website", href: "#top" },
          ],
        },
      ],
    },
    langToggle: { to: "中文" },
  },
  zh: {
    nav: [
      { label: "创新", href: "#innovation" },
      { label: "能力", href: "#features" },
      { label: "场景", href: "#use-cases" },
    ],
    hero: {
      tagline: "三生构维，智衍万物",
      subtitle: "AI-Native 的 3D 创作 Agent 平台，探索 3D 内容创作！",
      primaryCta: "开启创作",
      ghostCta: "探索创新",
      scroll: "向下",
    },
    stats: [
      { value: "1st", label: "全球首个对话式 3D 智能体" },
      { value: "4", label: "原生导出格式 FBX/OBJ/GLB/STL" },
      { value: "0", label: "所需 3D 经验门槛" },
      { value: "∞", label: "可生成的 3D 形态" },
    ],
    innovation: {
      label: "Innovation / 原创",
      titleL1: "以三元结构",
      titleL2: "演绎造物之理",
      desc: "Trigen 将几何、材质、光照三大三维基础要素作为核心三元，由单一自主 Agent 统一编排，以一条连贯流程替代碎片化的手工管线——这是属于对话时代的 3D 生成范式。",
      items: [
        {
          index: "01",
          title: "对话式 3D 生成",
          keyword: "Dialogue",
          desc: "全球首个以自然对话驱动 3D 资产生成的智能体。说话、传照片、投草图，Trigen 自主推理、规划并构建模型。",
        },
        {
          index: "02",
          title: "三元要素 Agent 编排",
          keyword: "Tri-Element",
          desc: "几何、材质、光照由单一自主 Agent 统一编排为三元结构，以一条连贯流程替代碎片化的手工管线。",
        },
        {
          index: "03",
          title: "零门槛创作",
          keyword: "Zero-Barrier",
          desc: "无需 3D 专业背景。网格拓扑、UV 展开、着色器图等细节被自然语言所封装，人人皆为造物者。",
        },
      ],
      tri: [
        { label: "几何", en: "Geometry", color: "text-snow" },
        { label: "材质", en: "Material", color: "text-cyber" },
        { label: "光照", en: "Lighting", color: "text-amber" },
      ],
    },
    features: {
      label: "Capabilities / 能力",
      titleL1: "六维能力矩阵",
      titleL2: "从对话到资产",
      desc: "多模态输入、内置 AI 模型、Agent 编辑、浏览器预览、多格式导出、跨平台集成——每一环都为对话式 3D 创作而生。",
      active: "激活",
      items: [
        { index: "01", icon: featureIcons[0], title: "多模态输入", desc: "文本提示词、照片、草图均可驱动 3D 生成，对话即创作。" },
        { index: "02", icon: featureIcons[1], title: "内置 AI 3D 模型", desc: "一组精选 3D 生成模型已接入 Agent 运行时，开箱即用。" },
        { index: "03", icon: featureIcons[2], title: "Agent 驱动编辑", desc: "通过对话对生成或上传的 3D 内容迭代：塑形、换贴图、调光、加动画。" },
        { index: "04", icon: featureIcons[3], title: "浏览器实时预览", desc: "网页原生工作空间中获得即时视觉反馈，无需安装任何软件。" },
        { index: "05", icon: featureIcons[4], title: "多格式导出", desc: "一键输出 FBX、OBJ、GLB、STL，覆盖打印与生产全链路。" },
        { index: "06", icon: featureIcons[5], title: "跨平台集成", desc: "资产可直接置入 Blender、Unity、Unreal Engine 等工具平台。" },
      ],
    },
    useCases: {
      label: "Use Cases / 场景",
      titleL1: "对话即入口",
      titleL2: "万物皆可生",
      desc: "从游戏影视到 3D 打印，从数字艺术到教育探索，Trigen 让任何人在任何场景下都能创造 3D 内容。",
      enter: "进入场景",
      more: "更多场景持续生成",
      items: [
        { icon: useCaseIcons[0], title: "游戏与影视", desc: "为 Unity 或 Unreal 快速原型化角色、道具与场景。", tag: "游戏/影视" },
        { icon: useCaseIcons[1], title: "3D 打印", desc: "数分钟内将创意转化为 STL 可打印模型。", tag: "可打印" },
        { icon: useCaseIcons[2], title: "数字艺术与设计", desc: "一句话生成雕塑、场景与视觉资产。", tag: "艺术" },
        { icon: useCaseIcons[3], title: "教育与探索", desc: "让任何人无需学习曲线即可体验 3D 创作。", tag: "学习" },
        { icon: useCaseIcons[4], title: "虚拟场景", desc: "按需构建可交互的浏览器原生 3D 世界。", tag: "虚拟" },
      ],
    },
    cta: {
      label: "Early Access / 早期体验",
      titleL1: "成为第一批",
      titleL2: "对话式造物者",
      desc: "留下邮箱，第一时间获取 Trigen 早期体验资格。无需 3D 经验，只需一句话，开始造物。",
      placeholder: "your@email.com",
      submit: "申请体验",
      submitted: "已加入",
      submittedNote: "✓ 已收到你的申请，我们将很快与你联系。",
    },
    footer: {
      tagline: "Trigen 是全球首个开源的对话式 AI 智能体，面向 3D 创作。一念起，三元衍生万千 3D 形态。",
      cols: [
        {
          title: "项目",
          links: [
            { label: "创新", href: "#innovation" },
            { label: "能力", href: "#features" },
            { label: "场景", href: "#use-cases" },
          ],
        },
        {
          title: "资源",
          links: [
            { label: "早期体验", href: "#cta" },
            { label: "GitHub", href: "https://github.com/Yuan-ManX/Trigen" },
            { label: "官方网站", href: "#top" },
          ],
        },
      ],
    },
    langToggle: { to: "EN" },
  },
};
