import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Menu } from "lucide-react";
import Sidebar from "./Sidebar";
import Particles from "./Particles";

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  return (
    <div className="relative flex h-screen overflow-hidden bg-black font-sans" dir="rtl">
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
        className="pointer-events-none fixed inset-x-0 bottom-0 z-0 h-72 opacity-20 floor-grid"
        style={{
          transform: "perspective(450px) rotateX(68deg) translateY(90px) scale(1.4)",
          transformOrigin: "bottom center",
          maskImage: "linear-gradient(to top, rgba(0,0,0,1), transparent)",
          WebkitMaskImage: "linear-gradient(to top, rgba(0,0,0,1), transparent)",
        }}
      />

      {/* ذرات پس‌زمینه — فقط دسکتاپ (در موبایل غیرفعال می‌شود) */}
      <Particles count={40} />

      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main className="relative z-10 flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-20 flex shrink-0 items-center gap-3 border-b border-white/5 bg-black/80 px-4 py-3 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="icon-btn"
            aria-label="باز کردن منو"
            aria-expanded={sidebarOpen}
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/15 bg-white/5">
              <img
                src="/logo.png"
                alt="مدیریت تکالیف"
                width={28}
                height={28}
                className="h-full w-full rounded-xl object-cover"
              />
            </span>
            <span className="text-sm font-bold text-white">مدیریت تکالیف</span>
          </div>
        </header>

        <motion.div
          key={location.pathname}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.16, ease: "easeOut" }}
          className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto"
        >
          <div className="w-full p-4 md:p-8">
            <Outlet />
          </div>
        </motion.div>
      </main>
    </div>
  );
}
