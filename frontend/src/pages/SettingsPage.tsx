import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Camera,
  Calendar,
  Check,
  Cpu,
  Fingerprint,
  Loader2,
  LogOut,
  Moon,
  ShieldCheck,
  Sun,
  Trash2,
} from "lucide-react";
import { deleteMyAvatar, updateMe, uploadFile } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import PageHeader from "../components/PageHeader";
import Corners from "../components/Corners";
import Avatar from "../components/Avatar";
import { parseDue } from "../lib/assignments";

export default function SettingsPage() {
  const { user, logout, refreshUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<string | null>(null);

  const [bio, setBio] = useState(user?.bio ?? "");
  const [savingBio, setSavingBio] = useState(false);
  const [bioSaved, setBioSaved] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function clearPreview() {
    if (previewRef.current) {
      URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
    }
    setAvatarPreview(null);
  }

  useEffect(() => {
    return () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
  }, []);

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

  async function handleAvatar(file: File | undefined) {
    if (!file || uploading) return;

    clearPreview();
    const objectUrl = URL.createObjectURL(file);
    previewRef.current = objectUrl;
    setAvatarPreview(objectUrl);

    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadFile(file);
      await updateMe({ avatar_url: uploaded.url });
      await refreshUser();
      clearPreview();
    } catch (e) {
      clearPreview();
      setError(e instanceof Error ? e.message : "آپلود تصویر ناموفق بود");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleRemoveAvatar() {
    if (deleting || uploading) return;
    setDeleting(true);
    setError(null);
    clearPreview();
    try {
      await deleteMyAvatar();
      await refreshUser();
    } catch (e) {
      setError(e instanceof Error ? e.message : "حذف تصویر ناموفق بود");
    } finally {
      setDeleting(false);
    }
  }

  async function saveBio() {
    if (savingBio) return;
    setSavingBio(true);
    setError(null);
    try {
      await updateMe({ bio: bio.trim() });
      await refreshUser();
      setBioSaved(true);
      window.setTimeout(() => setBioSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ذخیره بیو ناموفق بود");
    } finally {
      setSavingBio(false);
    }
  }

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
          <div className="relative shrink-0">
            <Avatar
              name={user?.username ?? "?"}
              src={avatarPreview ?? user?.avatar_url}
              size="xl"
              className="shadow-[0_0_30px_-10px_rgba(255,255,255,0.55)]"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || deleting}
              className="absolute -bottom-1 -left-1 flex h-8 w-8 items-center justify-center rounded-full border border-white/20 bg-black text-white shadow-lg transition hover:bg-white hover:text-black disabled:opacity-60"
              aria-label="تغییر تصویر پروفایل"
              title="تغییر تصویر پروفایل"
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
            </button>
            {(avatarPreview || user?.avatar_url) && (
              <button
                type="button"
                onClick={handleRemoveAvatar}
                disabled={deleting || uploading}
                className="absolute -right-1 -bottom-1 flex h-8 w-8 items-center justify-center rounded-full border border-danger/40 bg-black text-danger shadow-lg transition hover:bg-danger hover:text-white disabled:opacity-60"
                aria-label="حذف عکس پروفایل"
                title="حذف عکس پروفایل"
              >
                {deleting ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Trash2 size={14} />
                )}
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => handleAvatar(event.target.files?.[0])}
            />
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
              <span className="mono text-[10px] text-fg-500">
                {user?.points ?? 0} POINTS
              </span>
            </div>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="bio" className="mono-label">
              BIO
            </label>
            <span className="text-[10px] text-fg-500">{bio.length}/200</span>
          </div>
          <textarea
            id="bio"
            value={bio}
            maxLength={200}
            rows={2}
            onChange={(event) => {
              setBio(event.target.value);
              setBioSaved(false);
            }}
            placeholder="یک بیو کوتاه درباره خودت بنویس…"
            className="input w-full resize-none py-2.5 text-[16px] leading-6 md:text-[12.5px]"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            {error ? (
              <p className="text-[11px] text-danger">{error}</p>
            ) : (
              <span className="text-[11px] text-fg-500">
                {bioSaved ? "ذخیره شد" : "برای نمایش در پروفایل"}
              </span>
            )}
            <button
              type="button"
              onClick={saveBio}
              disabled={savingBio || bio.trim() === (user?.bio ?? "")}
              className="btn-ghost h-9 px-3 text-[11px]"
            >
              {savingBio ? (
                <Loader2 size={13} className="animate-spin" />
              ) : bioSaved ? (
                <Check size={13} />
              ) : null}
              ذخیره بیو
            </button>
          </div>
        </div>

        <div className="mt-5 divide-y divide-white/5 border-t border-white/5">
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

      {/* ظاهر */}
      <div className="panel relative mb-4 p-6">
        <Corners />
        <p className="mono-label mb-1">// APPEARANCE</p>
        <p className="mb-4 text-sm text-fg-500">حالت نمایش را انتخاب کن</p>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setTheme("dark")}
            aria-pressed={theme === "dark"}
            className={`flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-semibold transition ${
              theme === "dark"
                ? "theme-active border-white/60 bg-white text-black"
                : "border-white/10 bg-white/[0.03] text-fg-300 hover:border-white/25"
            }`}
          >
            <Moon size={16} />
            تاریک
          </button>
          <button
            type="button"
            onClick={() => setTheme("light")}
            aria-pressed={theme === "light"}
            className={`flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-semibold transition ${
              theme === "light"
                ? "theme-active border-white/60 bg-white text-black"
                : "border-white/10 bg-white/[0.03] text-fg-300 hover:border-white/25"
            }`}
          >
            <Sun size={16} />
            روشن
          </button>
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
          <span className="mono text-xs text-fg-500">v0.1.1</span>
        </div>
      </div>
    </div>
  );
}
