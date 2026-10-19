import { createPortal } from "react-dom";
import { NavLink, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard,
  CheckSquare,
  Settings,
  X,
  Users,
  LogOut,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

const navItemClass = ({ isActive }: { isActive: boolean }) =>
  `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-300 ${
    isActive
      ? "border border-white/20 bg-white/[0.06] text-white shadow-[0_0_24px_-10px_rgba(255,255,255,0.6)]"
      : "border border-transparent text-fg-700 hover:bg-white/[0.04] hover:text-white"
  }`;

const activePill = (
  <motion.span
    layoutId="active-pill"
    className="absolute right-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.9)]"
    transition={{ type: "spring", stiffness: 300, damping: 30 }}
  />
);

function LinkList({
  links,
  onClose,
  delayBase = 0,
}: {
  links: { to: string; label: string; icon: typeof Users }[];
  onClose?: () => void;
  delayBase?: number;
}) {
  return (
    <>
      {links.map((link, i) => {
        const Icon = link.icon;
        return (
          <motion.div
            key={link.to}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: delayBase + i * 0.05, duration: 0.3 }}
          >
            <NavLink to={link.to} end={link.to === "/"} onClick={onClose} className={navItemClass}>
              {({ isActive }) => (
                <>
                  {isActive && activePill}
                  <Icon
                    size={18}
                    className={`shrink-0 transition-transform duration-300 ${isActive ? "" : "group-hover:scale-110"}`}
                  />
                  <span>{link.label}</span>
                </>
              )}
            </NavLink>
          </motion.div>
        );
      })}
    </>
  );
}

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const links = [
    { to: "/", label: "داشبورد", icon: LayoutDashboard },
    { to: "/assignments", label: "تکالیف و پروژه‌ها", icon: CheckSquare },
    { to: "/settings", label: "تنظیمات", icon: Settings },
  ];

  const adminLinks = [{ to: "/rootvoid", label: "کاربران", icon: Users }];

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <>
      {/* هدر */}
      <div className="relative flex shrink-0 items-center justify-between border-b border-white/5 px-5 py-5">
        <div className="flex items-center gap-3">
          <motion.div
            whileHover={{ rotate: 8, scale: 1.05 }}
            transition={{ type: "spring", stiffness: 300, damping: 15 }}
            className="relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/30 bg-white/5 shadow-[0_0_20px_-6px_rgba(255,255,255,0.6)]"
          >
            <img
              src="/logo.png"
              alt="مدیریت تکالیف"
              width={40}
              height={40}
              className="h-full w-full rounded-xl object-cover"
            />
          </motion.div>
          <div>
            <h1 className="text-sm font-bold text-white">مدیریت تکالیف</h1>
            <p className="mono text-[10px] tracking-widest text-fg-500">V0.1.0</p>
          </div>
        </div>

        {onClose && (
          <button onClick={onClose} className="icon-btn md:hidden">
            <X size={18} />
          </button>
        )}
      </div>

      {/* منو */}
      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
        <p className="mono-label px-3 py-2">// MENU</p>

        <LinkList links={links} onClose={onClose} />

        {isAdmin && (
          <>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3, duration: 0.3 }}
              className="mono-label mt-4 px-3 py-2"
            >
              // ADMIN
            </motion.p>
            <LinkList links={adminLinks} onClose={onClose} delayBase={(links.length) * 0.05 + 0.1} />
          </>
        )}
      </nav>

      {/* پایین */}
      <div className="mt-auto shrink-0 border-t border-white/5 p-4">
        <div className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.03] p-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/25 bg-white/10 text-sm font-semibold text-white shadow-[0_0_15px_-4px_rgba(255,255,255,0.6)]">
            {user?.username.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-white" dir="ltr">
              {user?.username}
            </p>
            <p className="mono text-[10px] uppercase tracking-wider text-fg-500">
              {user?.is_admin ? "admin" : "online"}
            </p>
          </div>
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={handleLogout}
            className="rounded-md p-1.5 text-fg-500 transition hover:bg-danger/10 hover:text-danger"
            title="خروج"
          >
            <LogOut size={15} />
          </motion.button>
        </div>
      </div>
    </>
  );
}

export default function Sidebar({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  return (
    <>
      {/* سایدبار دسکتاپ */}
      <aside className="hidden h-screen w-64 shrink-0 flex-col overflow-hidden border-l border-white/5 bg-black/70 md:flex">
        <SidebarContent />
      </aside>

      {/* Drawer موبایل — از راست باز می‌شود (rtl) */}
      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <div className="fixed inset-0 z-[120] md:hidden" dir="rtl">
              {/* پرده تاریک پشت منو */}
              <motion.div
                key="backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                onClick={onClose}
                aria-hidden
                className="absolute inset-0 bg-black/80"
              />

              <motion.aside
                key="drawer"
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ type: "spring", damping: 30, stiffness: 300 }}
                className="absolute right-0 top-0 flex h-full w-72 max-w-[85vw] flex-col overflow-hidden border-l border-white/10 bg-black/95"
                style={{ willChange: "transform" }}
              >
                <SidebarContent onClose={onClose} />
              </motion.aside>
            </div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
}
