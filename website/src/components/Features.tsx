import { motion } from "framer-motion";
import { useLanguage, useTranslation } from "@/store/useLanguage";
import SectionHeading from "./SectionHeading";

export default function Features() {
  const t = useTranslation();
  const { lang } = useLanguage();

  return (
    <section
      id="features"
      className="relative w-full overflow-hidden bg-void py-24 md:py-32"
    >
      <div className="pointer-events-none absolute inset-0 noise-overlay" />

      <div className="relative mx-auto max-w-7xl px-6 md:px-10">
        <SectionHeading
          label={t.features.label}
          title={
            <>
              {t.features.titleL1}
              <br />
              <span className="text-gradient-amber">{t.features.titleL2}</span>
            </>
          }
          desc={t.features.desc}
        />

        <div key={lang} className="mt-16 grid gap-px border border-white/10 bg-white/[0.02] sm:grid-cols-2 lg:grid-cols-3">
          {t.features.items.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <motion.article
                key={feature.index}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.1 }}
                className="group relative overflow-hidden bg-void p-8 transition-all duration-500 hover:bg-white/[0.03]"
              >
                <div className="pointer-events-none absolute -right-20 -top-20 h-40 w-40 rounded-full bg-cyber/0 blur-[60px] transition-all duration-500 group-hover:bg-cyber/10" />

                <div className="relative flex items-start justify-between">
                  <div className="flex h-12 w-12 items-center justify-center border border-white/10 text-snow transition-all duration-500 group-hover:border-cyber group-hover:text-cyber">
                    <Icon size={20} />
                  </div>
                  <span className="font-mono text-[10px] tracking-mega text-ash">
                    {feature.index}
                  </span>
                </div>

                <h3 className="relative mt-6 font-display text-xl font-semibold leading-tightish tracking-tightish text-snow">
                  {feature.title}
                </h3>

                <p className="relative mt-3 font-sans text-[15px] leading-copy text-ash">
                  {feature.desc}
                </p>

                <div className="relative mt-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-mega text-ash opacity-0 transition-all duration-500 group-hover:opacity-100">
                  <span className="h-px w-6 bg-cyber" />
                  {t.features.active}
                </div>
              </motion.article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
