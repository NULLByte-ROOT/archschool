import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BookOpen,
  Calendar,
  Check,
  ClipboardList,
  Clock,
  GraduationCap,
  Loader2,
  Trash2,
  User,
} from "lucide-react";
import { fetchAssignment, deleteAssignment, updateAssignment } from "../api/client";
import type { Assignment } from "../api/client";
import Corners from "../components/Corners";
import { useNow } from "../hooks/useNow";
import {
  SUBJECT_BY_ID,
  TONE_BORDER,
  TONE_GLOW,
  TONE_TEXT,
  categoryGroup,
  categoryItemLabel,
  deadlineTone,
  formatDue,
  parseDue,
  relativeDue,
  subjectName,
} from "../lib/assignments";

export default function AssignmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const now = useNow(30_000);
  const [item, setItem] = useState<Assignment | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    let active = true;
    fetchAssignment(Number(id))
      .then((data) => {
        if (active) setItem(data);
      })
      .catch(() => {
        if (active) setNotFound(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  async function toggle() {
    if (!item) return;
    const updated = await updateAssignment(item.id, { completed: !item.completed });
    setItem(updated);
  }

  async function remove() {
    if (!item) return;
    await deleteAssignment(item.id);
    navigate("/assignments");
  }

  return (
    <div className="mx-auto max-w-2xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-2 text-sm text-fg-500 transition hover:text-white"
      >
        <ArrowRight size={16} />
        بازگشت
      </button>

      {loading ? (
        <div className="panel relative flex items-center justify-center gap-2 p-16 text-sm text-fg-500">
          <Corners />
          <Loader2 size={16} className="animate-spin" />
          در حال بارگذاری...
        </div>
      ) : notFound || !item ? (
        <div className="panel relative flex flex-col items-center gap-3 p-16 text-center">
          <Corners />
          <ClipboardList size={28} className="text-fg-500" />
          <p className="text-sm text-fg-500">تکلیف پیدا نشد</p>
        </div>
      ) : (
        (() => {
          const tone = deadlineTone(item.due_date, now);
          const group = categoryGroup(item.category);
          const GroupIcon = group?.id === "exam" ? GraduationCap : ClipboardList;
          const subject = SUBJECT_BY_ID[item.subject_id];
          return (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            >
              <div
                className={`panel noise relative overflow-hidden rounded-3xl border-2 p-6 sm:p-8 ${TONE_BORDER[tone]} ${TONE_GLOW[tone]}`}
              >
                <Corners />

                <div className="mb-5 flex items-center gap-3">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.06]">
                    <GroupIcon size={22} className="text-white" />
                  </span>
                  <div>
                    <span className="badge">{group?.label ?? "بدون دسته"}</span>
                    {item.subtype && (
                      <p className="mono mt-1 text-[11px] tracking-wider text-fg-500">
                        {categoryItemLabel(item.subtype)}
                      </p>
                    )}
                  </div>
                  {item.completed && (
                    <span className="badge ml-auto border-success/30 bg-success/10 text-success">
                      انجام شد
                    </span>
                  )}
                </div>

                <h1
                  className={`text-2xl font-black leading-9 sm:text-3xl ${
                    item.completed ? "text-fg-500 line-through" : "text-white"
                  }`}
                >
                  {item.title}
                </h1>

                <div className="mt-6 grid gap-3 sm:grid-cols-2">
                  <InfoRow
                    icon={<BookOpen size={16} />}
                    label="درس"
                    value={subjectName(item.subject_id, item.course) || "—"}
                    sub={subject?.nameEn}
                  />
                  <InfoRow
                    icon={<User size={16} />}
                    label="دبیر"
                    value={subject?.teacher ?? "—"}
                  />
                  <InfoRow
                    icon={<Calendar size={16} />}
                    label="مهلت تحویل"
                    value={formatDue(item.due_date)}
                    sub={relativeDue(item.due_date, now)}
                    valueClass={TONE_TEXT[tone]}
                  />
                  <InfoRow
                    icon={<Clock size={16} />}
                    label="ثبت‌شده"
                    value={parseDue(item.created_at).toLocaleDateString("fa-IR", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  />
                </div>

                {item.description && (
                  <p className="mt-6 rounded-2xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-7 text-fg-300">
                    {item.description}
                  </p>
                )}
              </div>

              <div className="mt-5 flex gap-3">
                <button
                  onClick={toggle}
                  className={`btn-ghost flex-1 justify-center !py-3 ${
                    item.completed ? "" : "!border-success/40 !text-success hover:!bg-success/10"
                  }`}
                >
                  <Check size={16} strokeWidth={3} />
                  {item.completed ? "برگردان به انجام‌نشده" : "علامت‌گذاری به‌عنوان انجام‌شده"}
                </button>
                <button
                  onClick={remove}
                  className="btn-ghost justify-center !py-3 !border-danger/30 !text-danger hover:!bg-danger/10"
                >
                  <Trash2 size={16} />
                  حذف
                </button>
              </div>
            </motion.div>
          );
        })()
      )}
    </div>
  );
}

function InfoRow({
  icon,
  label,
  value,
  sub,
  valueClass = "text-white",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-3.5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05] text-fg-300">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="mono-label">{label}</p>
        <p className={`truncate text-sm font-semibold ${valueClass}`}>{value}</p>
        {sub && <p className="truncate text-[11px] text-fg-500">{sub}</p>}
      </div>
    </div>
  );
}
