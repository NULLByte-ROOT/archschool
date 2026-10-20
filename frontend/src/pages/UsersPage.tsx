import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, Copy, Check, Power, Loader2, ShieldCheck } from "lucide-react";
import {
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
} from "../api/client";
import type { Role, User } from "../api/client";
import PageHeader from "../components/PageHeader";
import Corners from "../components/Corners";
import Dropdown from "../components/Dropdown";
import { parseDue } from "../lib/assignments";

const ROLE_OPTIONS: { value: Role; label: string; description: string }[] = [
  { value: "admin", label: "مدیر (Admin)", description: "دسترسی کامل" },
  { value: "editor", label: "ویرایشگر (Editor)", description: "مدیریت همه تکالیف" },
  { value: "member", label: "عضو (Member)", description: "فقط تکالیف خودش" },
];

const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  editor: "Editor",
  member: "Member",
};

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newCode, setNewCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);
  const [savingRole, setSavingRole] = useState<number | null>(null);

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

  const roleGroups = [{ options: ROLE_OPTIONS }];

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
                  placeholder="کد ۶ رقمی (خالی = تصادفی)"
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

      <div className="panel relative overflow-hidden">
        <Corners />
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-12 text-sm text-fg-500">
            <Loader2 size={16} className="animate-spin" />
            در حال بارگذاری...
          </div>
        ) : users.length === 0 ? (
          <p className="p-12 text-center text-sm text-fg-500">هنوز کاربری نیست</p>
        ) : (
          <ul className="divide-y divide-white/5">
            <AnimatePresence initial={false}>
              {users.map((user, i) => (
                <motion.li
                  key={user.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ delay: i * 0.03, duration: 0.25 }}
                  className="flex flex-wrap items-center gap-3 px-4 py-3 transition hover:bg-white/[0.03]"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/20 bg-white/10 text-sm font-semibold text-white">
                    {user.username.charAt(0).toUpperCase()}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="mono truncate text-sm font-medium text-white" dir="ltr">
                        {user.username}
                      </p>
                      <span
                        className={`badge !py-0.5 !text-[9px] ${
                          user.role === "admin"
                            ? "border-white/40 text-white"
                            : user.role === "editor"
                              ? "border-warning/40 text-warning"
                              : ""
                        }`}
                      >
                        <span className="dot" />
                        {ROLE_LABELS[user.role] ?? user.role}
                      </span>
                    </div>
                    <p className="mono text-[11px] text-fg-500">
                      {parseDue(user.created_at).toLocaleDateString("fa-IR")}
                    </p>
                  </div>

                  <div className="flex w-[168px] shrink-0 items-center gap-1.5">
                    <ShieldCheck size={13} className="shrink-0 text-fg-500" />
                    <Dropdown
                      ariaLabel={`نقش ${user.username}`}
                      groups={roleGroups}
                      value={user.role}
                      onChange={(role) => handleRoleChange(user, role)}
                      placeholder="نقش"
                      className="w-full"
                    />
                    {savingRole === user.id && (
                      <Loader2 size={13} className="shrink-0 animate-spin text-fg-500" />
                    )}
                  </div>

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
                      className="mono flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] tracking-widest text-fg-300 transition hover:border-white/40 hover:text-white"
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
                    {user.role !== "admin" && (
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
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </div>
  );
}
