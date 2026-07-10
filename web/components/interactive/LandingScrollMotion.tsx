"use client";

import { useRef, type ReactNode } from "react";
import clsx from "clsx";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";

type RevealVariant = "rise" | "fold" | "slide";

const hiddenByVariant: Record<RevealVariant, { opacity: number; y?: number; x?: number; rotateX?: number; scale?: number }> = {
  rise: { opacity: 0, y: 34 },
  fold: { opacity: 0, y: 42, rotateX: 10, scale: 0.98 },
  slide: { opacity: 0, x: 28 },
};

export function RevealOnScroll({
  children,
  className,
  delay = 0,
  amount = 0.28,
  variant = "rise",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  amount?: number;
  variant?: RevealVariant;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={reduceMotion ? false : hiddenByVariant[variant]}
      whileInView={{ opacity: 1, x: 0, y: 0, rotateX: 0, scale: 1 }}
      viewport={{ once: true, amount }}
      transition={{
        delay: reduceMotion ? 0 : delay,
        duration: reduceMotion ? 0 : 0.68,
        ease: [0.16, 1, 0.3, 1],
      }}
    >
      {children}
    </motion.div>
  );
}

export function LandingScrollRail() {
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const scaleY = useSpring(scrollYProgress, { stiffness: 120, damping: 28, mass: 0.24 });
  const beadY = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

  if (reduceMotion) return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed bottom-10 right-6 top-24 z-20 hidden w-8 items-start justify-center xl:flex"
    >
      <div className="relative h-full w-px overflow-hidden rounded-full bg-[color-mix(in_srgb,var(--wf-text)_12%,transparent)]">
        <motion.div
          className="absolute inset-x-0 top-0 origin-top rounded-full bg-[var(--wf-brand-coral)]"
          style={{ scaleY, height: "100%" }}
        />
      </div>
      <motion.div
        className="absolute top-0 h-8 w-8 -translate-y-1/2 rounded-full border border-[color-mix(in_srgb,var(--wf-brand-coral)_42%,transparent)] bg-[color-mix(in_srgb,var(--wf-canvas)_82%,transparent)] shadow-[0_12px_30px_rgba(182,92,58,.22)] backdrop-blur"
        style={{ y: beadY }}
      >
        <span className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--wf-brand-coral)]" />
      </motion.div>
    </div>
  );
}

export function ScrollKineticPanel({
  children,
  className,
  intensity = 1,
}: {
  children: ReactNode;
  className?: string;
  intensity?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 0.5, 1], [18 * intensity, 0, -12 * intensity]);

  return (
    <motion.div
      ref={ref}
      className={clsx("will-change-transform", className)}
      style={reduceMotion ? undefined : { y }}
    >
      {children}
    </motion.div>
  );
}
