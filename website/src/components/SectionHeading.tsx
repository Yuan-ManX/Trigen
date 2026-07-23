import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface SectionHeadingProps {
  label: string;
  title: ReactNode;
  desc?: string;
  align?: "left" | "center";
}

export default function SectionHeading({
  label,
  title,
  desc,
  align = "left",
}: SectionHeadingProps) {
  const isCenter = align === "center";
  return (
    <div className={isCenter ? "mx-auto max-w-3xl text-center" : "max-w-3xl"}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6 }}
        className={`flex items-center gap-3 ${isCenter ? "justify-center" : ""}`}
      >
        <span className="h-px w-8 bg-cyber" />
        <span className="section-label">{label}</span>
      </motion.div>
      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.7, delay: 0.1 }}
        className="mt-5 font-display text-3xl font-semibold leading-tightish tracking-tightish sm:text-4xl md:text-5xl"
      >
        {title}
      </motion.h2>
      {desc && (
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className={`mt-5 font-sans text-[15px] leading-copy text-ash sm:text-base ${
            isCenter ? "mx-auto" : ""
          }`}
        >
          {desc}
        </motion.p>
      )}
    </div>
  );
}
