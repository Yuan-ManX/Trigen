import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Github, Menu, X, Languages } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage, useTranslation } from "@/store/useLanguage";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const t = useTranslation();
  const { lang, toggle } = useLanguage();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    document.title =
      lang === "zh"
        ? "Trigen · 全球首个开源对话式 3D 智能体"
        : "Trigen · World's First Open-Source Conversational 3D Agent";
  }, [lang]);

  return (
    <motion.header
      initial={{ y: -40, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-500",
        scrolled
          ? "bg-ink/80 backdrop-blur-xl border-b border-white/5"
          : "bg-transparent"
      )}
    >
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 md:px-10">
        {/* Logo */}
        <a href="#top" className="group flex items-center gap-2.5">
          <span className="relative flex h-6 w-6 items-center justify-center">
            <span className="absolute inset-0 rotate-45 border border-cyber/60 transition-transform duration-500 group-hover:rotate-[135deg]" />
            <span className="absolute inset-1.5 rotate-45 bg-snow transition-colors duration-300 group-hover:bg-cyber" />
          </span>
          <span className="font-display text-base font-semibold tracking-tightish text-snow">
            Trigen
          </span>
        </a>

        {/* Center nav */}
        <div className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-10 md:flex">
          {t.nav.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="group relative font-mono text-2xs uppercase tracking-mega text-ash transition-colors hover:text-snow"
            >
              {link.label}
              <span className="absolute -bottom-1.5 left-0 h-px w-0 bg-cyber transition-all duration-300 group-hover:w-full" />
            </a>
          ))}
        </div>

        {/* Right cluster */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={toggle}
            className="flex h-9 items-center gap-1.5 border border-white/10 px-3 font-mono text-2xs uppercase tracking-mega text-ash transition-all hover:border-cyber hover:text-cyber"
            aria-label="Switch language"
          >
            <Languages size={13} />
            <span>{t.langToggle.to}</span>
          </button>
          <a
            href="https://github.com/Yuan-ManX/Trigen"
            target="_blank"
            rel="noreferrer"
            className="hidden h-9 w-9 items-center justify-center border border-white/10 text-ash transition-all hover:border-cyber hover:text-cyber sm:flex"
            aria-label="GitHub"
          >
            <Github size={14} />
          </a>
          <a href="#cta" className="hidden btn-primary !px-4 !py-2 text-2xs lg:inline-flex">
            {lang === "zh" ? "早期体验" : "Early Access"}
          </a>
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center border border-white/10 text-snow md:hidden"
            aria-label="Menu"
          >
            {open ? <X size={15} /> : <Menu size={15} />}
          </button>
        </div>
      </nav>

      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="overflow-hidden border-t border-white/5 bg-ink/95 backdrop-blur-xl md:hidden"
        >
          <div className="flex flex-col gap-1 px-6 py-4">
            {t.nav.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="border-l border-white/10 px-4 py-3 font-mono text-2xs uppercase tracking-mega text-ash hover:border-cyber hover:text-snow"
              >
                {link.label}
              </a>
            ))}
            <a
              href="#cta"
              onClick={() => setOpen(false)}
              className="btn-primary mt-2"
            >
              {lang === "zh" ? "早期体验" : "Early Access"}
            </a>
          </div>
        </motion.div>
      )}
    </motion.header>
  );
}
