import { useCallback, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Menu } from "lucide-react";
import Sidebar from "./Sidebar";
import Particles from "./Particles";
import { useUnreadSocket } from "../hooks/useUnreadSocket";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  // One persistent notifications-only WebSocket (room "pulse") that feeds the
  // global unread store for the whole app.
  useUnreadSocket();
  const immersive =
    location.pathname === "/chat" || /^\/assignments\/[^/]+$/.test(location.pathname);

  /**
   * On-screen keyboard (mobile web).
   *
   * `100dvh` only reacts to browser chrome, not to the keyboard: on Android
   * Chrome the layout viewport keeps its full height, so a `h-dvh` chat shell
   * pushes the composer underneath the keyboard. Mirroring `visualViewport`
   * into an explicit pixel height keeps the composer reachable while typing.
   * The pixel height is only applied while the keyboard is actually open
   * (`innerHeight - visualViewport.height > 120`), so nothing changes on
   * desktop or in normal mobile browsing.
   */
  const [keyboardHeight, setKeyboardHeight] = useState<number | null>(null);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const visual = Math.round(vv.height);
        const layout = Math.round(window.innerHeight);
        const covered = layout - visual;
        setKeyboardHeight(visual > 0 && covered > 120 ? visual : null);
      });
    };

    sync();
    vv.addEventListener("resize", sync);
    window.addEventListener("orientationchange", sync);
    return () => {
      cancelAnimationFrame(frame);
      vv.removeEventListener("resize", sync);
      window.removeEventListener("orientationchange", sync);
    };
  }, []);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const openSidebar = useCallback(() => setSidebarOpen(true), []);

  return (
    <div
      className="app-shell relative flex h-dvh overflow-hidden bg-black font-sans"
      dir="rtl"
      style={keyboardHeight ? { height: `${keyboardHeight}px` } : undefined}
    >
      {/* پس‌زمینه شبکه */}
      <div
        className="pointer-events-none fixed inset-0 z-0 grid-bg"
        style={{
          maskImage: "radial-gradient(circle at 50% 0%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 0%, black 20%, transparent 75%)",
        }}
      />

      {/* هاله سفید */}
      <div
        className="pointer-events-none fixed -top-40 left-1/2 z-0 h-[520px] w-[520px] -translate-x-1/2"
        style={{
          background: "radial-gradient(circle, rgba(255,255,255,0.07), transparent 68%)",
        }}
      />

      {/* کف پرسپکتیو */}
      <div
        className="app-floor pointer-events-none fixed inset-x-0 bottom-0 z-0 h-72 opacity-20 floor-grid"
        style={{
          transform: "perspective(450px) rotateX(68deg) translateY(90px) scale(1.4)",
          transformOrigin: "bottom center",
          maskImage: "linear-gradient(to top, rgba(0,0,0,1), transparent)",
          WebkitMaskImage: "linear-gradient(to top, rgba(0,0,0,1), transparent)",
        }}
      />

      {/* ذرات پس‌زمینه — فقط دسکتاپ (در موبایل غیرفعال می‌شود) */}
      <Particles count={40} />

      <Sidebar isOpen={sidebarOpen} onClose={closeSidebar} />

      <main className="relative z-10 flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="app-topbar z-20 flex w-full max-w-full shrink-0 items-center gap-2 overflow-hidden border-b border-white/5 bg-black/80 px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={openSidebar}
            className="icon-btn shrink-0"
            aria-label="باز کردن منو"
            aria-expanded={sidebarOpen}
          >
            <Menu size={18} />
          </button>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/15 bg-white/5">
              <img
                src="/logo.png"
                alt="ArchSchool"
                width={28}
                height={28}
                className="h-full w-full rounded-xl object-cover"
              />
            </span>
            <span className="truncate text-sm font-bold text-white">ArchSchool</span>
          </div>
        </header>

        <motion.div
          key={location.pathname}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto"
        >
          <div className={immersive ? "h-full w-full" : "w-full p-4 md:p-8"}>
            <Outlet />
          </div>
        </motion.div>
      </main>
    </div>
  );
}
