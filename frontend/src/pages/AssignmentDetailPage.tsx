import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Download,
  FileText,
  GraduationCap,
  Loader2,
  MessageSquare,
  Paperclip,
  Trash2,
  UploadCloud,
  User,
  Users,
  X,
} from "lucide-react";
import {
  deleteAssignment,
  deleteAttachment,
  fetchAssignment,
  fetchAttachments,
  fetchTeamStatus,
  resolveMediaUrl,
  toggleAssignmentCompletion,
  uploadAssignmentFile,
} from "../api/client";
import type { Assignment, Attachment, TeamMember } from "../api/client";
import Avatar from "../components/Avatar";
import ChatRoom from "../components/ChatRoom";
import Corners from "../components/Corners";
import { useAuth } from "../contexts/AuthContext";
import { useNow } from "../hooks/useNow";
import { useBellSchedule } from "../hooks/useBellSchedule";
import {
  SUBJECT_BY_ID,
  TONE_TEXT,
  canManageAssignment,
  categoryGroup,
  categoryItemLabel,
  formatDue,
  parseDue,
  subjectName,
} from "../lib/assignments";
import { countdownTone, dueCountdown } from "../lib/bell";
import { openImageGallery } from "../components/ImageViewer";

function fileIcon(name: string) {
  if (/\.(png|jpe?g|jfif|gif|webp|avif|bmp)$/i.test(name)) return "image";
  if (/\.(zip|rar|7z)$/i.test(name)) return "archive";
  return "file";
}

const IMAGE_FILE_RE = /\.(png|jpe?g|jfif|gif|webp|avif|bmp)(\?|$)/i;

/** نام فایل + آپلودکننده + تاریخ — مشترک بین حالت تصویر و فایل */
function AttachmentMeta({
  attachment,
  uploaderName,
}: {
  attachment: Attachment;
  uploaderName: string;
}) {
  return (
    <span className="min-w-0 flex-1">
      <span
        className="block truncate text-[11px] font-semibold text-fg-100"
        dir="ltr"
      >
        {attachment.file_name}
      </span>
      <span className="mt-1 flex items-center gap-1.5 text-[9px] text-fg-500">
        <Avatar name={uploaderName} size="xxs" />
        <span className="truncate" dir="ltr">
          {uploaderName}
        </span>
        <span>·</span>
        <span>
          {parseDue(attachment.created_at).toLocaleDateString("fa-IR")}
        </span>
      </span>
    </span>
  );
}

export default function AssignmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const assignmentId = Number(id);

  if (!assignmentId) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
        <ClipboardList size={30} className="text-fg-500" />
        <p className="text-sm text-fg-500">تکلیف پیدا نشد</p>
      </div>
    );
  }

  return <AssignmentView key={assignmentId} assignmentId={assignmentId} />;
}

function AssignmentView({ assignmentId }: { assignmentId: number }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const now = useNow(30_000);
  const { bells } = useBellSchedule();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [item, setItem] = useState<Assignment | null>(null);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [teamsLoading, setTeamsLoading] = useState(true);
  const [attachmentsLoading, setAttachmentsLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // مهلت منطبق با زنگ‌های مدرسه (پایان روز درسی، نه نیمه‌شب بی‌ربط)
  const countdown = dueCountdown(item?.due_date ?? null, now, bells);
  const tone = countdownTone(countdown);

  // گالری پیوست‌های تصویری همین تکلیف برای نمایشگر تصویر سراسری
  const imageAttachments = useMemo(
    () => attachments.filter((attachment) => IMAGE_FILE_RE.test(attachment.file_url)),
    [attachments]
  );

  const openAttachmentImage = useCallback(
    (attachment: Attachment) => {
      const images = imageAttachments.map((entry) => ({
        src: resolveMediaUrl(entry.file_url),
        alt: entry.file_name || "پیوست تکلیف",
      }));
      const index = imageAttachments.findIndex(
        (entry) => entry.id === attachment.id
      );
      openImageGallery(images, index >= 0 ? index : 0);
    },
    [imageAttachments]
  );

  useEffect(() => {
    let active = true;

    fetchAssignment(assignmentId)
      .then((data) => {
        if (active) setItem(data);
      })
      .catch(() => {
        if (active) setNotFound(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    fetchTeamStatus(assignmentId)
      .then((data) => {
        if (active) setTeam(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setTeamsLoading(false);
      });

    fetchAttachments(assignmentId)
      .then((data) => {
        if (active) setAttachments(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setAttachmentsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [assignmentId]);

  const canManage = !!item && canManageAssignment(item, user);
  const isDoneByMe = !!item?.is_completed_by_me;

  async function toggle() {
    if (!item || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await toggleAssignmentCompletion(item.id);
      setItem(updated);
      setTeam((prev) =>
        prev.map((member) =>
          member.is_self
            ? { ...member, completed: updated.is_completed_by_me }
            : member
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "تغییر وضعیت ناموفق بود");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!item) return;
    if (!confirm("این تکلیف و پیوست‌هایش حذف شوند؟")) return;
    setBusy(true);
    try {
      await deleteAssignment(item.id);
      navigate("/assignments");
    } catch (e) {
      setError(e instanceof Error ? e.message : "حذف ناموفق بود");
      setBusy(false);
    }
  }

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      if (!assignmentId || uploading) return;
      const list = Array.from(files);
      if (list.length === 0) return;
      setUploading(true);
      setError(null);
      try {
        for (const file of list) {
          const attachment = await uploadAssignmentFile(assignmentId, file);
          setAttachments((prev) => [attachment, ...prev]);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "آپلود فایل ناموفق بود");
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [assignmentId, uploading]
  );

  const completedCount = team.filter((member) => member.completed).length;

  async function removeAttachment(attachment: Attachment) {
    if (deletingId !== null) return;
    if (!confirm(`فایل «${attachment.file_name}» حذف شود؟`)) return;
    setDeletingId(attachment.id);
    setError(null);
    try {
      await deleteAttachment(attachment.id);
      setAttachments((prev) => prev.filter((item) => item.id !== attachment.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "حذف فایل ناموفق بود");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="relative min-h-full">
      {/* هدر شیشه‌ای */}
      <header className="glass-top-highlight sticky top-0 z-30 border-b border-white/10 bg-black/55 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-3 py-3 sm:px-5">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="icon-btn shrink-0"
            aria-label="بازگشت"
          >
            <ArrowRight size={17} />
          </button>

          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.06]">
            {item?.category === "exam" ? (
              <GraduationCap size={18} className="text-white" />
            ) : (
              <ClipboardList size={18} className="text-white" />
            )}
          </span>

          <div className="min-w-0 flex-1">
            <h1
              className={`truncate text-sm font-black sm:text-base ${
                item?.is_completed_by_me ? "text-fg-500 line-through" : "text-white"
              }`}
            >
              {item?.title ?? "جزئیات تکلیف"}
            </h1>
            <p className="mono flex items-center gap-2 truncate text-[9px] tracking-[0.16em] text-fg-500 uppercase">
              <span>// ASSIGNMENT</span>
              {item?.subject_id && (
                <span className="hidden sm:inline">
                  · {subjectName(item.subject_id, item.course)}
                </span>
              )}
            </p>
          </div>

          {item && (
            <span
              className={`badge hidden sm:inline-flex ${
                isDoneByMe
                  ? "border-success/30 bg-success/10 text-success"
                  : TONE_TEXT[tone]
              }`}
              title={countdown?.periodNote ?? undefined}
            >
              {isDoneByMe
                ? item?.category === "exam"
                  ? "خوندم"
                  : "انجام دادم"
                : countdown?.label ?? "بدون مهلت"}
            </span>
          )}

          {item && (
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                onClick={toggle}
                disabled={busy}
                title={
                  isDoneByMe
                    ? "لغو"
                    : item?.category === "exam"
                      ? "من خوندم"
                      : "من انجام دادم"
                }
                className={`flex h-10 items-center gap-1.5 rounded-xl border px-2.5 text-[11px] font-semibold transition disabled:opacity-50 sm:h-9 ${
                  isDoneByMe
                    ? "border-white/15 bg-white/[0.04] text-fg-300 hover:text-white"
                    : "border-success/40 bg-success/10 text-success hover:bg-success/15"
                }`}
              >
                {busy ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Check size={13} strokeWidth={3} />
                )}
                <span className="hidden sm:inline">
                  {isDoneByMe
                    ? "برگرداندن"
                    : item?.category === "exam"
                      ? "خوندم"
                      : "انجام دادم"}
                </span>
              </button>
              {canManage && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={busy}
                  className="icon-btn hover:border-danger/40 hover:text-danger disabled:opacity-50"
                  aria-label="حذف تکلیف"
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          )}
        </div>
      </header>

      {loading ? (
        <div className="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-fg-500">
          <Loader2 size={18} className="animate-spin" />
          در حال بارگذاری…
        </div>
      ) : notFound || !item ? (
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-3 p-10 text-center sm:p-16">
          <ClipboardList size={32} className="text-fg-500" />
          <p className="text-sm text-fg-500">تکلیف پیدا نشد</p>
          <button onClick={() => navigate("/assignments")} className="btn-ghost mt-1">
            بازگشت به تکالیف
          </button>
        </div>
      ) : (
        (() => {
          const group = categoryGroup(item.category);
          const subject = SUBJECT_BY_ID[item.subject_id];
          return (
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="mx-auto max-w-6xl px-3 py-5 sm:px-5 sm:py-7"
            >
              {error && (
                <p className="mb-4 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-[12px] text-danger">
                  {error}
                </p>
              )}

              {/* اطلاعات اصلی */}
              <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
                <section className="panel noise relative overflow-hidden rounded-3xl p-5 sm:p-6">
                  <Corners />
                  <div className="mb-4 flex flex-wrap items-center gap-2">
                    <span className="badge">{group?.label ?? "بدون دسته"}</span>
                    {item.subtype && (
                      <span className="font-mono text-[10px] tracking-wider text-fg-500">
                        {categoryItemLabel(item.subtype)}
                      </span>
                    )}
                    {subject && (
                      <span className="badge mr-auto">
                        <BookOpen size={11} />
                        {subject.nameEn}
                      </span>
                    )}
                  </div>

                  <h2 className="text-2xl leading-9 font-black text-white sm:text-3xl">
                    {item.title}
                  </h2>

                  <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
                    <InfoChip
                      icon={<BookOpen size={15} />}
                      label="درس"
                      value={subjectName(item.subject_id, item.course) || "—"}
                      sub={subject?.teacher}
                    />
                    <InfoChip
                      icon={<Calendar size={15} />}
                      label="مهلت"
                      value={formatDue(item.due_date)}
                      sub={countdown?.label ?? "—"}
                      valueClass={TONE_TEXT[tone]}
                    />
                    <InfoChip
                      icon={<User size={15} />}
                      label="سازنده"
                      value={item.creator_username || "نامشخص"}
                    />
                    <InfoChip
                      icon={<Clock size={15} />}
                      label="وضعیت من"
                      value={
                        isDoneByMe
                          ? item.category === "exam"
                            ? "خوندم"
                            : "انجام دادم"
                          : "در انتظار انجام"
                      }
                      valueClass={isDoneByMe ? "text-success" : "text-white"}
                    />
                  </div>

                  {item.description ? (
                    <p className="mt-5 rounded-2xl border border-white/8 bg-white/[0.02] p-4 text-[13px] leading-7 whitespace-pre-wrap text-fg-300">
                      {item.description}
                    </p>
                  ) : (
                    <p className="mt-5 text-[12px] text-fg-500">توضیحی برای این تکلیف ثبت نشده.</p>
                  )}
                </section>

                <div className="flex flex-col gap-4">
                  {/* انجام‌دهندگان */}
                  <section className="panel relative overflow-hidden rounded-3xl p-5">
                    <Corners />
                    <div className="mb-4 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-success/25 bg-success/10">
                          <Check size={16} className="text-success" strokeWidth={3} />
                        </span>
                        <div>
                          <h3 className="text-sm font-bold text-white">
                            انجام داده‌اند
                          </h3>
                          <p className="mono text-[9px] tracking-widest text-fg-500">
                            // COMPLETED BY
                          </p>
                        </div>
                      </div>
                      <span className="badge">{item.completed_by_users.length}</span>
                    </div>

                    {item.completed_by_users.length === 0 ? (
                      <p className="py-3 text-[11px] text-fg-500">
                        هنوز کسی این تکلیف را انجام نداده.
                      </p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {item.completed_by_users.map((completer) => (
                          <span
                            key={completer.id}
                            className="flex items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] py-1.5 pr-2.5 pl-1.5"
                          >
                            <Avatar name={completer.username ?? "?"} size="xs" />
                            <span
                              className="text-[11px] font-medium text-fg-100"
                              dir="ltr"
                            >
                              {completer.username ?? "کاربر"}
                            </span>
                            {completer.id === user?.id && (
                              <span className="rounded-full border border-white/20 bg-white/10 px-1.5 text-[8px] font-semibold text-white">
                                تو
                              </span>
                            )}
                          </span>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* وضعیت تیم */}
                  <section className="panel relative overflow-hidden rounded-3xl p-5">
                    <Corners />
                    <div className="mb-4 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
                          <Users size={16} className="text-white" />
                        </span>
                        <div>
                          <h3 className="text-sm font-bold text-white">وضعیت تیم</h3>
                          <p className="mono text-[9px] tracking-widest text-fg-500">
                            // TEAM STATUS
                          </p>
                        </div>
                      </div>
                      <span className="badge">
                        {completedCount}/{team.length}
                      </span>
                    </div>

                    {teamsLoading ? (
                      <div className="flex items-center gap-2 py-6 text-[11px] text-fg-500">
                        <Loader2 size={13} className="animate-spin" />
                        در حال بارگذاری…
                      </div>
                    ) : team.length === 0 ? (
                      <p className="py-4 text-[11px] text-fg-500">عضوی پیدا نشد.</p>
                    ) : (
                      <div className="flex flex-wrap gap-x-3 gap-y-4">
                        {team.map((member) => (
                          <div
                            key={member.user.id}
                            className="flex w-[58px] flex-col items-center gap-1.5"
                            title={`${member.user.username} · ${member.completed ? "انجام شده" : "انجام نشده"}`}
                          >
                            <span className="relative">
                              <Avatar name={member.user.username} size="md" />
                              <span
                                className={`absolute -bottom-1 -left-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-black ${
                                  member.completed
                                    ? "bg-success text-black"
                                    : "bg-bg-400 text-fg-500"
                                }`}
                              >
                                {member.completed ? (
                                  <Check size={11} strokeWidth={4} />
                                ) : (
                                  <X size={11} strokeWidth={3} />
                                )}
                              </span>
                              {member.is_self && (
                                <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-white shadow-[0_0_8px_#fff]" />
                              )}
                            </span>
                            <span
                              className="w-full truncate text-center text-[10px] text-fg-300"
                              dir="ltr"
                            >
                              {member.user.username}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* پیوست‌ها */}
                  <section className="panel relative overflow-hidden rounded-3xl p-5">
                    <Corners />
                    <div className="mb-4 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
                          <Paperclip size={16} className="text-white" />
                        </span>
                        <div>
                          <h3 className="text-sm font-bold text-white">پیوست‌ها</h3>
                          <p className="mono text-[9px] tracking-widest text-fg-500">
                            // FILES
                          </p>
                        </div>
                      </div>
                      <span className="badge">{attachments.length}</span>
                    </div>

                    <div
                      onDragEnter={(e) => {
                        e.preventDefault();
                        setDragActive(true);
                      }}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragActive(true);
                      }}
                      onDragLeave={(e) => {
                        e.preventDefault();
                        setDragActive(false);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        setDragActive(false);
                        uploadFiles(e.dataTransfer.files);
                      }}
                      onClick={() => fileInputRef.current?.click()}
                      className={`group relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-6 text-center transition ${
                        dragActive
                          ? "border-white/70 bg-white/[0.08]"
                          : "border-white/12 bg-white/[0.02] hover:border-white/30 hover:bg-white/[0.04]"
                      }`}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept="image/*,video/*,application/pdf"
                        className="hidden"
                        onChange={(e) => uploadFiles(e.target.files ?? [])}
                      />
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/12 bg-white/[0.05] text-white">
                        {uploading ? (
                          <Loader2 size={18} className="animate-spin" />
                        ) : (
                          <UploadCloud size={18} />
                        )}
                      </span>
                      <p className="text-[12px] font-semibold text-white">
                        {uploading ? "در حال آپلود…" : "فایل را اینجا رها کن"}
                      </p>
                      <p className="text-[10px] text-fg-500">
                        یا کلیک کن · حداکثر ۲۵ مگابایت
                      </p>
                    </div>

                    <div className="mt-3 space-y-2">
                      {attachmentsLoading ? (
                        <div className="flex items-center gap-2 py-3 text-[11px] text-fg-500">
                          <Loader2 size={13} className="animate-spin" />
                          در حال بارگذاری…
                        </div>
                      ) : attachments.length === 0 ? (
                        <p className="py-2 text-center text-[11px] text-fg-500">
                          هنوز فایلی پیوست نشده.
                        </p>
                      ) : (
                        attachments.map((attachment) => {
                          const kind = fileIcon(attachment.file_name);
                          const uploaderName =
                            attachment.user_username ||
                            attachment.uploader?.username ||
                            "کاربر";
                          const canDelete =
                            attachment.user_id === user?.id || !!user?.is_admin;
                          const mediaUrl = resolveMediaUrl(attachment.file_url);
                          return (
                            <div
                              key={attachment.id}
                              className="group flex items-center gap-2 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 transition hover:border-white/20 hover:bg-white/[0.05]"
                            >
                              {kind === "image" ? (
                                <button
                                  type="button"
                                  onClick={() => openAttachmentImage(attachment)}
                                  className="flex min-w-0 flex-1 cursor-zoom-in items-center gap-2.5"
                                  aria-label="نمایش تصویر"
                                >
                                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-fg-300">
                                    <FileText size={15} />
                                  </span>
                                  <AttachmentMeta
                                    attachment={attachment}
                                    uploaderName={uploaderName}
                                  />
                                </button>
                              ) : (
                                <a
                                  href={mediaUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="flex min-w-0 flex-1 items-center gap-2.5"
                                >
                                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-fg-300">
                                    {kind === "archive" ? (
                                      <Download size={15} />
                                    ) : (
                                      <FileText size={15} />
                                    )}
                                  </span>
                                  <AttachmentMeta
                                    attachment={attachment}
                                    uploaderName={uploaderName}
                                  />
                                </a>
                              )}

                              <a
                                href={mediaUrl}
                                download={attachment.file_name}
                                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-fg-500 transition hover:bg-white/10 hover:text-white sm:h-8 sm:w-8"
                                aria-label="دانلود"
                              >
                                <Download size={14} />
                              </a>

                              {canDelete && (
                                <button
                                  type="button"
                                  onClick={() => removeAttachment(attachment)}
                                  disabled={deletingId === attachment.id}
                                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-fg-500 transition hover:bg-danger/15 hover:text-danger disabled:opacity-50 sm:h-8 sm:w-8"
                                  aria-label="حذف فایل"
                                  title="حذف فایل"
                                >
                                  {deletingId === attachment.id ? (
                                    <Loader2 size={14} className="animate-spin" />
                                  ) : (
                                    <Trash2 size={14} />
                                  )}
                                </button>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  </section>
                </div>
              </div>

              {/* چت تکلیف */}
              <section className="mt-5">
                <div className="mb-3 flex items-center gap-2 px-1">
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03]">
                    <MessageSquare size={14} className="text-white" />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-white">گفتگوی این تکلیف</h3>
                    <p className="mono text-[9px] tracking-widest text-fg-500">
                      // TASK COMMENTS · ONLY THIS ASSIGNMENT
                    </p>
                  </div>
                </div>
                <ChatRoom
                  key={`assignment-${item.id}`}
                  room={`assignment:${item.id}`}
                  assignmentId={item.id}
                  title="گفتگوی تکلیف"
                  subtitle={item.title}
                  compact
                  headerIcon={<MessageSquare size={17} />}
                />
              </section>
            </motion.div>
          );
        })()
      )}
    </div>
  );
}

function InfoChip({
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
    <div className="flex items-center gap-2.5 rounded-xl border border-white/8 bg-white/[0.02] p-2.5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-fg-300">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="mono-label">{label}</p>
        <p className={`truncate text-[12px] font-semibold ${valueClass}`}>{value}</p>
        {sub && <p className="truncate text-[10px] text-fg-500">{sub}</p>}
      </div>
    </div>
  );
}
