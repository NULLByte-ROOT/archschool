import { useEffect, useRef } from "react";
import { useIsMobile } from "../hooks/useMediaQuery";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
}

export default function Particles({ count = 40 }: { count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse = useRef({ x: -1000, y: -1000 });
  const isMobile = useIsMobile();
  const isNarrow = typeof window !== "undefined" && window.innerWidth < 768;
  const disabled = isMobile || isNarrow;

  useEffect(() => {
    if (disabled) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = (canvas.width = window.innerWidth);
    let h = (canvas.height = window.innerHeight);
    let raf = 0;
    let lastFrame = 0;

    const particles: Particle[] = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.5 + 0.5,
    }));

    function handleResize() {
      if (!canvas) return;
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }

    function handleMouse(e: MouseEvent) {
      mouse.current = { x: e.clientX, y: e.clientY };
    }

    function handleLeave() {
      mouse.current = { x: -1000, y: -1000 };
    }

    const LINK_DIST = 120;
    const LINK_DIST_SQ = LINK_DIST * LINK_DIST;
    const MOUSE_DIST = 200;
    const MOUSE_DIST_SQ = MOUSE_DIST * MOUSE_DIST;

    function draw(time: number) {
      if (!ctx) return;
      // Cap the ambient background at ~60fps even on 120Hz+ displays: it is
      // decorative and should never compete with UI animations for frames.
      raf = requestAnimationFrame(draw);
      // A hidden tab paints nothing: stopping here saves a full-screen clear +
      // ~40 arcs + link strokes per frame while the app is in the background.
      if (document.visibilityState !== "visible") return;
      if (time - lastFrame < 15) return;
      lastFrame = time;

      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // حرکت
        p.x += p.vx;
        p.y += p.vy;

        // برگشت از لبه‌ها
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;

        // دفع از موس (بدون جذر تا وقتی نزدیک نیست)
        const dx = p.x - mouse.current.x;
        const dy = p.y - mouse.current.y;
        const dist2 = dx * dx + dy * dy;
        if (dist2 < 150 * 150) {
          const dist = Math.sqrt(dist2) || 1;
          const force = (150 - dist) / 150;
          p.vx += (dx / dist) * force * 0.05;
          p.vy += (dy / dist) * force * 0.05;
        }

        // محدود کردن سرعت
        const speedSq = p.vx * p.vx + p.vy * p.vy;
        if (speedSq > 1) {
          const speed = Math.sqrt(speedSq);
          p.vx = (p.vx / speed) * 1;
          p.vy = (p.vy / speed) * 1;
        }

        // رسم ذره
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(147, 197, 253, 0.4)";
        ctx.fill();

        // خطوط
        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j];
          const ddx = p.x - q.x;
          const ddy = p.y - q.y;
          const d2 = ddx * ddx + ddy * ddy;
          if (d2 < LINK_DIST_SQ) {
            const d = Math.sqrt(d2);
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.strokeStyle = `rgba(147, 197, 253, ${0.15 * (1 - d / LINK_DIST)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }

        // خط به موس
        if (dist2 < MOUSE_DIST_SQ) {
          const dist = Math.sqrt(dist2);
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(mouse.current.x, mouse.current.y);
          ctx.strokeStyle = `rgba(59, 130, 246, ${0.3 * (1 - dist / MOUSE_DIST)})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }

    handleResize();
    window.addEventListener("resize", handleResize);
    window.addEventListener("mousemove", handleMouse);
    window.addEventListener("mouseleave", handleLeave);
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouse);
      window.removeEventListener("mouseleave", handleLeave);
    };
  }, [count, disabled]);

  if (disabled) return null;

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0"
      style={{ opacity: 0.7 }}
    />
  );
}