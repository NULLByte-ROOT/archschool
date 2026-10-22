import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, Copy, Check, Power, Loader2, ShieldCheck, KeyRound } from "lucide-react";
import {
  fetchUsers,
  createUser,
  updateUser,
  updateUserCode,
  deleteUser,
} from "../api/client";
import type { Role, User } from "../api/client";
import PageHeader from "../components/PageHeader";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import Dropdown from "../components/Dropdown";
import { useAuth } from "../contexts/AuthContext";
import { parseDue } from "../lib/assignments";

const ROLE_OPTIONS: { value: Role; label: string; description: string }[] = [
  {
    value: "owner",
    label: "Owner (مالک)",
    description: "دسترسی کامل + آمار سرور + تغییر کدها",
  },
  { value: "admin", label: "مدیر (Admin)", description: "مدیریت تکالیف و کاربران" },
  { value: "friend", label: "دوست (Friend)", description: "گفتگو و کامنت، بدون مدیریت تکلیف" },
  { value: "member", label: "عضو (Member)", description: "فقط مشاهده، اعلام انجام و کامنت تکلیف" },
];

const ADMIN_SELECTABLE: { value: Role; label: string; description: string }[] =
  ROLE_OPTIONS.filter((o) => o.value !== "owner");

const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  friend: "Friend",
  member: "Member",
};

export default function UsersPage() {
  const { isOwner, user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newCode, setNewCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const [savingRole, setSavingRole] = useState<number | null>(null);
  // «تغییر کد» — فقط Owner
  const [codeTarget, setCodeTarget] = useState<User | null>(null);
  const [newCodeValue, setNewCodeValue] = useState("");
  const [savingCode, setSavingCode] = useState(false);

  async function handleChangeCode() {
    if (!codeTarget) return;
    const code = newCodeValue.trim().toUpperCase();
    if (!/^[A-Z0-9]{6}$/.test(code)) {
      setError("کد دسترسی باید دقیقاً ۶ کاراکتر انگلیسی بزرگ باشد");
      return;
    }
    setSavingCode(true);
    setError(null);
    try {
      const updated = await updateUserCode(codeTarget.id, code);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      setCopied(updated.id);
      setTimeout(() => setCopied(null), 1500);
      setCodeTarget(null);
      setNewCodeValue("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "تغییر کد ناموفق بود");
    } finally {
      setSavingCode(false);
    }
  }

  async function load() {
    setLoading(true);
    try {
      setUsers(await fetchUsers());
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    fetchUsers()
      .then((data) => {
        if (active) setUsers(data);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "خطا");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleCreate() {
    if (!newUsername.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createUser({
        username: newUsername.trim(),
        code: newCode.trim() || undefined,
      });
      setNewUsername("");
      setNewCode("");
      setShowNew(false);
      await load();
      if (created.code) {
        navigator.clipboard.writeText(created.code);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا در ساخت کاربر");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggleActive(user: User) {
    await updateUser(user.id, { is_active: !user.is_active });
    load();
  }

  async function handleRoleChange(user: User, role: string) {
    if (role === user.role) return;
    setSavingRole(user.id);
    setError(null);
    try {
      const updated = await updateUser(user.id, { role: role as Role });
      setUsers((prev) =>
        prev.map((u) => (u.id === updated.id ? updated : u))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "تغییر نقش ناموفق بود");
    } finally {
      setSavingRole(null);
    }
  }

  /** فقط Owner می‌تواند نقش Owner بدهد؛ برای بقیه گزینهٔ Owner حذف می‌شود. */
  const roleGroups = [{ options: isOwner ? ROLE_OPTIONS : ADMIN_SELECTABLE }];

  async function handleDelete(id: number) {
    if (!confirm("مطمئنی؟ این کاربر حذف می‌شه.")) return;
    try {
      await deleteUser(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا در حذف");
    }
  }

  async function handleCopyCode(id: number, code: string) {
    await navigator.clipboard.writeText(code);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div>
      <PageHeader
        kicker="admin"
        title="کاربران"
        subtitle="ساخت و مدیریت کاربران و کدهای ورود"
        action={
          <button onClick={() => setShowNew((v) => !v)} className="btn-primary">
            <Plus size={14} />
            کاربر جدید
          </button>
        }
      />

      <AnimatePresence>
        {showNew && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="mb-6"
          >
            <div className="panel relative p-4">
              <Corners />
              <p className="mono-label mb-3">// NEW USER</p>
              <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                <input
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  placeholder="نام کاربری"
                  dir="ltr"
                  className="input"
                />
                <input
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value.toUpperCase())}
                  placeholder="کد ۶ کاراکتری (خالی = تصادفی)"
                  dir="ltr"
                  maxLength={6}
                  className="input mono tracking-widest"
                />
                <button
                  onClick={handleCreate}
                  disabled={creating || !newUsername.trim()}
                  className="btn-primary"
                >
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                  ساخت
                </button>
              </div>
              <p className="mt-2 text-[11px] text-fg-500">
                اگه کد خالی بذاری، یه کد ۶ کاراکتری ساخته می‌شه و خودکار کپی می‌شه.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-4 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {error}
        </motion.p>
      )}

      {/* تغییر کد دسترسی — فقط Owner */}
      <AnimatePresence>
        {codeTarget && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="mb-6"
          >
            <div className="panel relative p-4">
              <Corners />
              <p className="mono-label mb-3">// CHANGE ACCESS CODE</p>
              <div className="grid gap-3 sm:grid-cols-[auto_1fr_auto]">
                <div className="flex min-w-0 items-center gap-2 self-center">
                  <Avatar name={codeTarget.username} src={codeTarget.avatar_url} size="sm" />
                  <span className="mono truncate text-sm text-white" dir="ltr">
                    {codeTarget.username}
                  </span>
                </div>
                <input
                  value={newCodeValue}
                  onChange={(e) => setNewCodeValue(e.target.value.toUpperCase())}
                  placeholder="کد ۶ کاراکتری"
                  dir="ltr"
                  maxLength={6}
                  className="input mono tracking-widest"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleChangeCode}
                    disabled={savingCode || newCodeValue.trim().length !== 6}
                    className="btn-primary"
                  >
                    {savingCode ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
                    ذخیره
                  </button>
                  <button
                    onClick={() => {
                      setCodeTarget(null);
                      setNewCodeValue("");
                    }}
                    className="btn-ghost"
                  >
                    انصراف
                  </button>
                </div>
              </div>
              <p className="mt-2 text-[11px] text-fg-500">
                کد باید ۶ کاراکتر و فقط حروف انگلیسی بزرگ/اعداد باشد. کد حساب Owner از
                backend/.env کنترل می‌شود.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="panel relative overflow-hidden">
        <Corners />
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-10 text-sm text-fg-500 sm:p-12">
            <Loader2 size={16} className="animate-spin" />
            در حال بارگذاری...
          </div>
        ) : users.length === 0 ? (
          <p className="p-10 text-center text-sm text-fg-500 sm:p-12">هنوز کاربری نیست</p>
        ) : (
          <ul className="divide-y divide-white/5">
            <AnimatePresence initial={false}>
              {users.map((user, i) => {
                const isRowOwner = user.role === "owner";
                const canTouch = isOwner || !isRowOwner;
                return (
                  <motion.li
                    key={user.id}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ delay: i * 0.03, duration: 0.25 }}
                    className="grid gap-2.5 px-4 py-3 transition hover:bg-white/[0.03] sm:grid-cols-[minmax(0,1fr)_168px_auto] sm:items-center sm:gap-3"
                  >
                    {/* هویت: آواتار + نام + نقش */}
                    <div className="flex min-w-0 items-center gap-3">
                      <Avatar name={user.username} src={user.avatar_url} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <p
                            className="mono min-w-0 truncate text-sm font-medium text-white"
                            dir="ltr"
                          >
                            {user.username}
                          </p>
                          <span
                            className={`badge shrink-0 !py-0.5 !text-[9px] ${
                              isRowOwner
                                ? "border-amber-300/50 text-amber-300"
                                : user.role === "admin"
                                  ? "border-white/40 text-white"
                                  : user.role === "friend"
                                    ? "border-sky-300/40 text-sky-300"
                                    : ""
                            }`}
                          >
                            <span className="dot" />
                            {ROLE_LABELS[user.role] ?? user.role}
                            {user.id === me?.id && " (شما)"}
                          </span>
                        </div>
                        <p className="mono text-[11px] text-fg-500">
                          {parseDue(user.created_at).toLocaleDateString("fa-IR-u-nu-latn")}
                        </p>
                      </div>
                    </div>

                    {/* انتخاب نقش — موبایل: تمام‌عرض، بدون برخورد */}
                    <div
                      className={`flex items-center gap-1.5 sm:w-full ${
                        canTouch ? "" : "opacity-50"
                      }`}
                    >
                      <ShieldCheck size={13} className="shrink-0 text-fg-500" />
                      {canTouch ? (
                        <Dropdown
                          ariaLabel={`نقش ${user.username}`}
                          groups={roleGroups}
                          value={user.role}
                          onChange={(role) => handleRoleChange(user, role)}
                          placeholder="نقش"
                          className="w-full"
                        />
                      ) : (
                        <span className="mono flex h-[38px] w-full items-center rounded-xl border border-white/10 bg-white/[0.03] px-3 text-[11px] text-fg-500">
                          Owner — بدون تغییر
                        </span>
                      )}
                      {savingRole === user.id && (
                        <Loader2 size={13} className="shrink-0 animate-spin text-fg-500" />
                      )}
                    </div>

                    {/* کنترل‌ها: وضعیت + کد + دکمه‌ها — موبایل در یک ردیف */}
                    <div className="flex items-center gap-2 overflow-hidden sm:gap-1">
                      {isOwner && (
                        <motion.button
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          onClick={() => {
                            setCodeTarget(user);
                            setNewCodeValue("");
                          }}
                          className="icon-btn hover:border-white/40 hover:text-white"
                          title="تغییر کد دسترسی"
                          aria-label={`تغییر کد دسترسی ${user.username}`}
                        >
                          <KeyRound size={15} />
                        </motion.button>
                      )}

                      <span
                        className={`mono shrink-0 rounded-md border px-2 py-0.5 text-[10px] tracking-wider ${
                          user.is_active
                            ? "border-success/30 bg-success/10 text-success"
                            : "border-white/10 bg-white/5 text-fg-500"
                        }`}
                      >
                        {user.is_active ? "ACTIVE" : "OFF"}
                      </span>

                      {user.code && (
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => handleCopyCode(user.id, user.code!)}
                          className="mono flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-[11px] tracking-widest text-fg-300 transition hover:border-white/40 hover:text-white"
                          dir="ltr"
                          title="کپی کد"
                        >
                          {copied === user.id ? (
                            <>
                              <Check size={11} className="text-success" />
                              COPIED
                            </>
                          ) : (
                            <>
                              <Copy size={11} />
                              {user.code}
                            </>
                          )}
                        </motion.button>
                      )}

                      <div className="flex items-center gap-1">
                        {canTouch && (
                          <>
                            <motion.button
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                              onClick={() => handleToggleActive(user)}
                              className={`icon-btn ${
                                user.is_active
                                  ? "hover:border-warning/40 hover:text-warning"
                                  : "hover:border-success/40 hover:text-success"
                              }`}
                              title={user.is_active ? "غیرفعال کردن" : "فعال کردن"}
                            >
                              <Power size={15} />
                            </motion.button>
                            {user.role !== "admin" && !isRowOwner && (
                              <motion.button
                                whileHover={{ scale: 1.1 }}
                                whileTap={{ scale: 0.9 }}
                                onClick={() => handleDelete(user.id)}
                                className="icon-btn hover:border-danger/40 hover:text-danger"
                                title="حذف"
                              >
                                <Trash2 size={15} />
                              </motion.button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </div>
  );
}
