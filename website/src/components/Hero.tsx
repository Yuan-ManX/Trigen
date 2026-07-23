import { Suspense, lazy } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { useLanguage, useTranslation } from "@/store/useLanguage";

const GenesisScene = lazy(() => import("@/components/three/GenesisScene"));

const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: "easeOut" } },
};

export default function Hero() {
  const t = useTranslation();
  const { lang } = useLanguage();

  return (
    <section
      id="top"
      className="relative min-h-screen w-full overflow-hidden bg-ink"
    >
      {/* 3D 背景 */}
      <div className="absolute inset-0 z-0">
        <Suspense fallback={null}>
          <GenesisScene />
        </Suspense>
      </div>

      {/* 网格与噪点叠加 */}
      <div className="pointer-events-none absolute inset-0 z-10 grid-overlay opacity-60" />
      <div className="pointer-events-none absolute inset-0 z-10 noise-overlay" />
      <div className="pointer-events-none absolute inset-0 z-10 bg-gradient-to-b from-ink/40 via-transparent to-ink" />

      {/* 扫描线 */}
      <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
        <div className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyber/40 to-transparent animate-scan" />
      </div>

      {/* 主体内容 */}
      <motion.div
        key={lang}
        variants={container}
        initial="hidden"
        animate="show"
        className="relative z-20 mx-auto flex min-h-screen max-w-7xl flex-col items-center justify-center px-6 text-center md:px-10"
      >
        <motion.h1
          variants={item}
          className="font-display text-7xl font-semibold leading-[0.9] tracking-tightish sm:text-8xl md:text-9xl lg:text-[11rem]"
        >
          <span className="block text-gradient-cyber">Trigen</span>
        </motion.h1>

        <motion.p
          variants={item}
          className="mt-6 font-display text-xl font-semibold tracking-tightish text-snow sm:text-2xl md:text-3xl"
        >
          {t.hero.tagline}
        </motion.p>

        <motion.p
          variants={item}
          className="mt-3 max-w-2xl font-sans text-[15px] leading-copy text-ash sm:text-base md:text-lg"
        >
          {t.hero.subtitle}
        </motion.p>

        <motion.div
          variants={item}
          className="mt-10 flex flex-col items-center gap-4 sm:flex-row"
        >
          <a href="#cta" className="btn-primary group">
            {t.hero.primaryCta}
            <ArrowUpRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </a>
          <a href="#innovation" className="btn-ghost">
            {t.hero.ghostCta}
          </a>
        </motion.div>

        {/* 数据条 */}
        <motion.div
          variants={item}
          className="mt-16 grid w-full max-w-3xl grid-cols-2 gap-px border border-white/10 bg-white/[0.02] md:grid-cols-4"
        >
          {t.stats.map((s) => (
            <div key={s.label} className="bg-ink/60 px-4 py-5 text-center backdrop-blur-sm">
              <div className="font-display text-2xl font-semibold text-snow md:text-3xl">
                {s.value}
              </div>
              <div className="mt-2 font-mono text-2xs uppercase tracking-mega text-ash">
                {s.label}
              </div>
            </div>
          ))}
        </motion.div>
      </motion.div>

      {/* 滚动指示器 */}
      <motion.a
        href="#innovation"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4, duration: 0.8 }}
        className="absolute bottom-8 left-1/2 z-20 flex -translate-x-1/2 flex-col items-center gap-2 text-ash transition-colors hover:text-cyber"
      >
        <span className="font-mono text-[10px] uppercase tracking-ultra">{t.hero.scroll}</span>
        <ChevronDown size={16} className="animate-bounce" />
      </motion.a>
    </section>
  );
}
