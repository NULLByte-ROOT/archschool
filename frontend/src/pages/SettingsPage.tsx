import { useNavigate } from "react-router-dom";
import { LogOut, ShieldCheck, Fingerprint, Calendar, Cpu } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import PageHeader from "../components/PageHeader";
import Corners from "../components/Corners";
import { parseDue } from "../lib/assignments";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const rows = [
    { icon: Fingerprint, label: "USERNAME", value: user?.username ?? "—", mono: true },
    {
      icon: ShieldCheck,
      label: "ROLE",
      value:
        user?.role === "admin"
          ? "ادمین"
          : user?.role === "editor"
            ? "ویرایشگر"
            : "عضو",
      mono: false,
    },
    {
      icon: Cpu,
      label: "STATUS",
      value: user?.is_active ? "فعال" : "غیرفعال",
      mono: false,
    },
    {
      icon: Calendar,
      label: "MEMBER SINCE",
      value: user?.created_at
        ? parseDue(user.created_at).toLocaleDateString("fa-IR")
        : "—",
      mono: false,
    },
  ];

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="max-w-2xl">
      <PageHeader kicker="settings" title="تنظیمات" subtitle="حساب کاربری و اطلاعات سیستم" />

      {/* حساب */}
      <div className="panel relative mb-4 p-6">
        <Corners />
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/25 bg-white/10 text-xl font-bold text-white shadow-[0_0_25px_-8px_rgba(255,255,255,0.7)]">
            {user?.username.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-bold text-white" dir="ltr">
              {user?.username ?? "—"}
            </h2>
            <div className="mt-1.5 flex items-center gap-2">
              <span className="badge">
                <span className="dot" />
                {user?.is_admin ? "admin" : "user"}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-6 divide-y divide-white/5">
          {rows.map((row) => {
            const Icon = row.icon;
            return (
              <div key={row.label} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <Icon size={15} className="text-fg-500" />
                  <span className="mono-label">{row.label}</span>
                </div>
                <span
                  className={`text-sm text-fg-100 ${row.mono ? "mono" : ""}`}
                  dir={row.mono ? "ltr" : undefined}
                >
                  {row.value}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* نشست */}
      <div className="panel relative mb-4 p-6">
        <Corners />
        <p className="mono-label mb-1">// SESSION</p>
        <p className="mb-4 text-sm text-fg-500">از حساب کاربری خارج شو</p>
        <button
          onClick={handleLogout}
          className="btn-ghost border-danger/30 text-danger hover:border-danger/60 hover:bg-danger/10"
        >
          <LogOut size={15} />
          خروج از حساب
        </button>
      </div>

      {/* درباره */}
      <div className="panel relative p-6">
        <Corners />
        <p className="mono-label mb-1">// ABOUT</p>
        <div className="flex items-center justify-between">
          <span className="text-sm text-fg-100">ArchSchool</span>
          <span className="mono text-xs text-fg-500">v0.1.0</span>
        </div>
      </div>
    </div>
  );
}
