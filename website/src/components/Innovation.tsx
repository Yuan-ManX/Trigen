import { motion } from "framer-motion";
import { useLanguage, useTranslation } from "@/store/useLanguage";
import SectionHeading from "./SectionHeading";

export default function Innovation() {
  const t = useTranslation();
  const { lang } = useLanguage();

  return (
    <section
      id="innovation"
      className="relative w-full overflow-hidden bg-ink py-24 md:py-32"
    >
      <div className="pointer-events-none absolute inset-0 grid-overlay opacity-30" />
      <div className="pointer-events-none absolute -left-40 top-1/2 h-96 w-96 -translate-y-1/2 rounded-full bg-cyber/5 blur-[120px]" />
      <div className="pointer-events-none absolute -right-40 top-1/4 h-96 w-96 rounded-full bg-amber/5 blur-[120px]" />

      <div className="relative mx-auto max-w-7xl px-6 md:px-10">
        <SectionHeading
          label={t.innovation.label}
          title={
            <>
              {t.innovation.titleL1}
              <br />
              <span className="text-gradient-cyber">{t.innovation.titleL2}</span>
            </>
          }
          desc={t.innovation.desc}
        />

        <div key={lang} className="mt-16 grid gap-px border border-white/10 bg-white/[0.02] md:grid-cols-3">
          {t.innovation.items.map((item, i) => (
            <motion.article
              key={item.index}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, delay: i * 0.12 }}
              className="group relative overflow-hidden bg-ink p-8 transition-colors duration-500 hover:bg-white/[0.02] md:p-10"
            >
              <div className="pointer-events-none absolute -right-4 -top-8 font-display text-[120px] font-bold leading-none text-white/[0.03] transition-all duration-500 group-hover:text-cyber/[0.08]">
                {item.index}
              </div>

              <div className="relative">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs uppercase tracking-ultra text-cyber">
                    {item.keyword}
                  </span>
                  <span className="font-mono text-[10px] tracking-mega text-ash">
                    /{item.index}
                  </span>
                </div>

                <h3 className="mt-6 font-display text-2xl font-semibold leading-tightish tracking-tightish text-snow md:text-3xl">
                  {item.title}
                </h3>

                <div className="mt-4 h-px w-12 bg-white/20 transition-all duration-500 group-hover:w-24 group-hover:bg-cyber" />

                <p className="mt-5 font-sans text-[15px] leading-copy text-ash">
                  {item.desc}
                </p>
              </div>

              <div className="absolute bottom-0 left-0 h-px w-0 bg-gradient-to-r from-cyber to-transparent transition-all duration-500 group-hover:w-full" />
            </motion.article>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="mt-16 flex flex-col items-center justify-center gap-6 border border-white/10 bg-white/[0.02] p-10 md:flex-row md:gap-12"
        >
          {t.innovation.tri.map((el, i) => (
            <div key={el.en} className="flex items-center gap-6 md:gap-12">
              <div className="text-center">
                <div className={`font-display text-3xl font-semibold ${el.color} md:text-4xl`}>
                  {el.label}
                </div>
                <div className="mt-2 font-mono text-[10px] uppercase tracking-ultra text-ash">
                  {el.en}
                </div>
              </div>
              {i < 2 && (
                <div className="font-mono text-xl text-ash">⊕</div>
              )}
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
