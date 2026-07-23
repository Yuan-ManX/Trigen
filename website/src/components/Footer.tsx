import { useTranslation } from "@/store/useLanguage";

export default function Footer() {
  const t = useTranslation();

  return (
    <footer className="relative w-full overflow-hidden border-t border-white/10 bg-ink">
      <div className="pointer-events-none absolute inset-0 grid-overlay opacity-20" />

      <div className="relative mx-auto max-w-7xl px-6 py-16 md:px-10">
        <div className="grid gap-12 md:grid-cols-4">
          {/* 品牌区 */}
          <div className="md:col-span-2">
            <a href="#top" className="group flex items-center gap-2.5">
              <span className="relative flex h-7 w-7 items-center justify-center">
                <span className="absolute inset-0 rotate-45 border border-cyber/60 transition-transform duration-500 group-hover:rotate-[135deg]" />
                <span className="absolute inset-1.5 rotate-45 bg-snow transition-colors duration-300 group-hover:bg-cyber" />
              </span>
              <span className="font-display text-lg font-semibold tracking-tightish text-snow">
                Trigen
              </span>
            </a>
            <p className="mt-5 max-w-sm font-sans text-[15px] leading-copy text-ash">
              {t.footer.tagline}
            </p>
          </div>

          {/* 导航列 */}
          {t.footer.cols.map((col) => (
            <div key={col.title}>
              <div className="font-mono text-2xs uppercase tracking-ultra text-cyber">
                {col.title}
              </div>
              <ul className="mt-5 space-y-3">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target={link.href.startsWith("http") ? "_blank" : undefined}
                      rel="noreferrer"
                      className="group inline-flex items-center gap-2 font-sans text-[15px] text-ash transition-colors hover:text-snow"
                    >
                      <span className="h-px w-0 bg-cyber transition-all duration-300 group-hover:w-4" />
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 hairline" />

        <div className="mt-6 font-mono text-2xs uppercase tracking-ultra text-ash">
          © {new Date().getFullYear()} Trigen
        </div>
      </div>
    </footer>
  );
}
