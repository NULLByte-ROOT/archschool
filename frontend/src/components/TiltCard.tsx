import { useRef } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import type { ReactNode } from "react";
import type { HTMLMotionProps } from "framer-motion";

interface TiltCardProps extends HTMLMotionProps<"div"> {
  children: ReactNode;
  intensity?: number;
  glare?: boolean;
  className?: string;
}

export default function TiltCard({
  children,
  intensity = 10,
  glare = true,
  className = "",
  ...rest
}: TiltCardProps) {
  const ref = useRef<HTMLDivElement>(null);

  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.5);

  const springCfg = { stiffness: 200, damping: 25, mass: 0.5 };
  const sx = useSpring(mx, springCfg);
  const sy = useSpring(my, springCfg);

  const rotateY = useTransform(sx, [0, 1], [-intensity, intensity]);
  const rotateX = useTransform(sy, [0, 1], [intensity, -intensity]);

  // درخشش موس
  const glareX = useTransform(sx, [0, 1], ["0%", "100%"]);
  const glareY = useTransform(sy, [0, 1], ["0%", "100%"]);

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    mx.set((e.clientX - rect.left) / rect.width);
    my.set((e.clientY - rect.top) / rect.height);
  }

  function handleLeave() {
    mx.set(0.5);
    my.set(0.5);
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      style={{
        rotateX,
        rotateY,
        transformStyle: "preserve-3d",
        perspective: 1200,
      }}
      whileHover={{ scale: 1.015 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      className={`relative ${className}`}
      {...rest}
    >
      {children}

      {glare && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{
            background: `radial-gradient(circle at ${glareX.get()} ${glareY.get()}, rgba(255,255,255,0.08), transparent 60%)`,
            backgroundPositionX: glareX,
            backgroundPositionY: glareY,
          }}
        />
      )}
    </motion.div>
  );
}