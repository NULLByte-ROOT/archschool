import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, ClipboardList, Loader2, PenLine, Plus, X } from "lucide-react";
import { createAssignment } from "../api/client";
import Dropdown from "./Dropdown";
import DueDatePicker from "./DueDatePicker";
import Corners from "./Corners";
import {
  CATEGORY_GROUPS,
  SUBJECT_LIST,
  categoryItemLabel,
  defaultDueForSubject,
  subjectName,
} from "../lib/assignments";

export default function AddAssignmentModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  return createPortal(
    <AnimatePresence>{open && <AssignmentForm onClose={onClose} onSaved={onSaved} />}</AnimatePresence>,
    document.body
  );
}

function AssignmentForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [groupId, setGroupId] = useState<string | null>(null);
  const [subtype, setSubtype] = useState<string | null>(null);
  const [subjectId, setSubjectId] = useState<string | null>(null);
  const [due, setDue] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const categoryGroups = useMemo(
    () =>
      CATEGORY_GROUPS.map((g) => ({
        label: g.label,
        options: g.items.map((i) => ({ value: i.id, label: i.label })),
      })),
    []
  );

  const subjectGroups = useMemo(
    () => [
      {
        options: SUBJECT_LIST.map((s) => ({
          value: s.id,
          label: s.name,
          description: `${s.nameEn} · ${s.teacher}`,
        })),
      },
    ],
    []
  );

  const groupLabel = CATEGORY_GROUPS.find((g) => g.id === groupId)?.label;
  const autoTitle =
    subtype && subjectId ? `${categoryItemLabel(subtype)} ${subjectName(subjectId)}` : "";
  const canSubmit = !!groupId && !!subtype && !!subjectId && !saving;

  async function handleSubmit() {
    if (!canSubmit || !subtype || !subjectId || !groupId) return;
    setSaving(true);
    setError(null);
    try {
      await createAssignment({
        title: title.trim() || autoTitle || categoryItemLabel(subtype),
        course: subjectName(subjectId),
        subject_id: subjectId,
        category: groupId,
        subtype,
        due_date: due,
        priority: groupId === "exam" ? 3 : 2,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا در ذخیره‌سازی");
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/75"
      />

      <motion.div
        key="form"
        initial={{ opacity: 0, y: 40, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 30, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 320, damping: 30 }}
        className="panel noise relative z-10 max-h-[94vh] w-full max-w-lg overflow-y-auto rounded-t-[28px] border-white/15 p-5 shadow-2xl shadow-black sm:rounded-3xl sm:p-7"
      >
        <Corners />

        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.06] shadow-inner">
              <Plus size={20} className="text-white" />
            </span>
            <div>
              <h2 className="text-lg font-black text-white">افزودن تکلیف</h2>
              <p className="mono text-[10px] tracking-widest text-fg-500">// NEW ASSIGNMENT</p>
            </div>
          </div>
          <button onClick={onClose} aria-label="بستن" className="icon-btn shrink-0">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mono-label mb-2 block">موضوع</label>
            <Dropdown
              large
              ariaLabel="موضوع"
              icon={<ClipboardList size={17} />}
              groups={categoryGroups}
              value={subtype}
              hint={groupLabel}
              placeholder="موضوع"
              onChange={(v) => {
                const g = CATEGORY_GROUPS.find((gr) => gr.items.some((i) => i.id === v));
                setSubtype(v);
                setGroupId(g?.id ?? null);
              }}
            />
          </div>

          <div>
            <label className="mono-label mb-2 block">درس</label>
            <Dropdown
              large
              ariaLabel="درس"
              icon={<BookOpen size={17} />}
              groups={subjectGroups}
              value={subjectId}
              placeholder="انتخاب درس"
              onChange={(v) => {
                setSubjectId(v);
                setDue(defaultDueForSubject(v)?.toISOString() ?? null);
              }}
            />
          </div>

          <div>
            <label className="mono-label mb-2 block">مهلت تحویل</label>
            <DueDatePicker value={due} onChange={setDue} subjectId={subjectId ?? undefined} />
          </div>

          <div>
            <label className="mono-label mb-2 block">عنوان (اختیاری)</label>
            <div className="relative">
              <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-fg-500">
                <PenLine size={15} />
              </span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder={autoTitle || "مثلاً: حل تمرین‌های فصل ۳"}
                className="input pr-10"
              />
            </div>
          </div>

          {error && (
            <p
              dir="rtl"
              className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12px] text-red-300"
            >
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex items-center gap-3">
          <button onClick={onClose} className="btn-ghost flex-1 justify-center">
            انصراف
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="btn-primary flex-[1.4] justify-center py-3"
          >
            {saving ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                ذخیره…
              </>
            ) : (
              <>
                <Plus size={15} />
                ثبت تکلیف
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
