import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { useLanguage, useTranslation } from "@/store/useLanguage";

export default function CTA() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const t = useTranslation();
  const { lang } = useLanguage();

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setSubmitted(true);
  };

  return (
    <section
      id="cta"
      className="relative w-full overflow-hidden bg-ink py-24 md:py-32"
    >
      <div className="pointer-events-none absolute inset-0 grid-overlay opacity-40" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyber/5 blur-[140px]" />

      <div key={lang} className="relative mx-auto max-w-4xl px-6 text-center md:px-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="section-label mx-auto justify-center"
        >
          <span className="h-px w-8 bg-cyber" />
          {t.cta.label}
        </motion.div>

        <motion.h2
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="mt-6 font-display text-4xl font-semibold leading-tight tracking-tight sm:text-5xl md:text-6xl"
        >
          {t.cta.titleL1}
          <br />
          <span className="text-gradient-cyber">{t.cta.titleL2}</span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="mx-auto mt-6 max-w-xl font-sans text-[15px] leading-copy text-ash sm:text-base"
        >
          {t.cta.desc}
        </motion.p>

        <motion.form
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.3 }}
          onSubmit={onSubmit}
          className="mx-auto mt-10 flex max-w-md flex-col gap-3 sm:flex-row"
        >
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t.cta.placeholder}
            className="flex-1 border border-white/15 bg-white/[0.02] px-5 py-3 font-mono text-sm text-snow placeholder:text-ash/60 focus:border-cyber focus:outline-none focus:ring-1 focus:ring-cyber/30"
          />
          <button type="submit" className="btn-primary group whitespace-nowrap">
            {submitted ? t.cta.submitted : t.cta.submit}
            {submitted ? (
              <CheckCircle2 size={14} />
            ) : (
              <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
            )}
          </button>
        </motion.form>

        {submitted && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-4 font-mono text-xs text-cyber"
          >
            {t.cta.submittedNote}
          </motion.p>
        )}
      </div>
    </section>
  );
}
