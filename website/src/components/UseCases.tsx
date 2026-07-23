import { motion } from "framer-motion";
import { useLanguage, useTranslation } from "@/store/useLanguage";
import SectionHeading from "./SectionHeading";

export default function UseCases() {
  const t = useTranslation();
  const { lang } = useLanguage();

  return (
    <section
      id="use-cases"
      className="relative w-full overflow-hidden bg-void py-24 md:py-32"
    >
      <div className="pointer-events-none absolute inset-0 noise-overlay" />
      <div className="pointer-events-none absolute right-0 top-0 h-80 w-80 rounded-full bg-amber/5 blur-[120px]" />

      <div className="relative mx-auto max-w-7xl px-6 md:px-10">
        <SectionHeading
          label={t.useCases.label}
          title={
            <>
              {t.useCases.titleL1}
              <br />
              <span className="text-gradient-amber">{t.useCases.titleL2}</span>
            </>
          }
          desc={t.useCases.desc}
        />

        <div key={lang} className="mt-16 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {t.useCases.items.map((uc, i) => {
            const Icon = uc.icon;
            return (
              <motion.article
                key={uc.title}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.55, delay: (i % 3) * 0.1 }}
                className="group relative overflow-hidden border border-white/10 bg-white/[0.02] p-8 transition-all duration-500 hover:border-cyber/40 hover:bg-white/[0.04]"
              >
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-cyber/0 to-amber/0 opacity-0 transition-opacity duration-500 group-hover:from-cyber/[0.03] group-hover:to-amber/[0.03] group-hover:opacity-100" />

                <div className="relative flex items-center justify-between">
                  <div className="flex h-12 w-12 items-center justify-center border border-white/10 text-snow transition-all duration-500 group-hover:border-amber group-hover:text-amber">
                    <Icon size={20} />
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-ultra text-ash">
                    {uc.tag}
                  </span>
                </div>

                <h3 className="relative mt-6 font-display text-2xl font-semibold leading-tightish tracking-tightish text-snow">
                  {uc.title}
                </h3>
                <p className="relative mt-3 font-sans text-[15px] leading-copy text-ash">
                  {uc.desc}
                </p>

                <div className="relative mt-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-mega text-ash transition-colors duration-500 group-hover:text-cyber">
                  <span>{t.useCases.enter}</span>
                  <span className="h-px w-0 bg-cyber transition-all duration-500 group-hover:w-8" />
                </div>
              </motion.article>
            );
          })}

          {/* 占位 CTA 卡片 */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.55, delay: 0.3 }}
            className="group relative flex flex-col items-center justify-center overflow-hidden border border-dashed border-white/15 bg-transparent p-8 text-center transition-all duration-500 hover:border-cyber"
          >
            <div className="font-display text-4xl font-semibold text-white/20 transition-colors duration-500 group-hover:text-cyber">
              +
            </div>
            <p className="mt-3 font-mono text-xs uppercase tracking-mega text-ash">
              {t.useCases.more}
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
