import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  ArrowUpDown,
  BookOpen,
  Calendar,
  Check,
  ChevronLeft,
  ClipboardList,
  Filter,
  GraduationCap,
  LayoutGrid,
  List,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  fetchAssignments,
  deleteAssignment,
  toggleAssignmentCompletion,
} from "../api/client";
import type { Assignment } from "../api/client";
import PageHeader from "../components/PageHeader";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import Dropdown from "../components/Dropdown";
import AddAssignmentModal from "../components/AddAssignmentModal";
import { useAuth } from "../contexts/AuthContext";
import { useNow } from "../hooks/useNow";
import { useIsMobileWidth } from "../hooks/useMediaQuery";
import {
  SUBJECT_LIST,
  TONE_BORDER,
  TONE_DOT,
  TONE_GLOW,
  TONE_TEXT,
  canManageAssignment,
  categoryGroup,
  categoryItemLabel,
  deadlineTone,
  formatDue,
  parseDue,
  relativeDue,
  subjectName,
} from "../lib/assignments";

type Status = "all" | "active" | "done";
type View = "grid" | "list";
type Sort = "newest" | "oldest" | "deadline";

const STATUS_FILTERS: { key: Status; label: string }[] = [
  { key: "all", label: "همه" },
  { key: "active", label: "انجام‌نشده" },
  { key: "done", label: "انجام‌شده" },
];

const CATEGORY_OPTIONS = [
  { value: "", label: "همه دسته‌ها" },
  { value: "homework", label: "تکلیف‌ها" },
  { value: "exam", label: "امتحان" },
  { value: "project", label: "پروژه عملی" },
];

const SORT_OPTIONS = [
  { value: "newest", label: "جدیدترین" },
  { value: "oldest", label: "قدیمی‌ترین" },
  { value: "deadline", label: "نزدیک‌ترین مهلت" },
];

const VIEW_BUTTONS: { key: View; label: string; icon: LucideIcon }[] = [
  { key: "grid", label: "نمایش شبکه‌ای", icon: LayoutGrid },
  { key: "list", label: "نمایش لیستی", icon: List },
];

function assignDeadline(a: Assignment) {
  return a.due_date ? parseDue(a.due_date).getTime() : Infinity;
}

const listCache = new Map<string, Assignment[]>();
function cacheKey(status: Status) {
  return `${localStorage.getItem("token") ?? ""}|${status}`;
}

interface ItemProps {
  item: Assignment;
  view: View;
  index: number;
  now: number;
  layoutEnabled: boolean;
  canManage: boolean;
  onOpen: (id: number) => void;
  onToggle: (item: Assignment) => void;
  onDelete: (item: Assignment) => void;
  onEdit: (item: Assignment) => void;
}

const CreatorBadge = memo(function CreatorBadge({
  name,
}: {
  name: string | null;
}) {
  if (!name) return null;
  return (
    <span
      className="badge shrink-0 !py-0.5 !text-[9px]"
      title={`ساخته شده توسط ${name}`}
    >
      <span className="dot" />
      ساخته شده توسط: {name}
    </span>
  );
});

const CompletedStack = memo(function CompletedStack({
  users,
}: {
  users: Assignment["completed_by_users"];
}) {
  if (users.length === 0) return null;
  return (
    <span className="flex shrink-0 items-center" title="انجام‌دهندگان">
      <span className="flex -space-x-2" dir="ltr">
        {users.slice(0, 5).map((u) => (
          <Avatar key={u.id} name={u.username ?? "?"} size="xxs" />
        ))}
      </span>
      {users.length > 5 && (
        <span className="mono ms-1 text-[10px] text-fg-500">
          +{users.length - 5}
        </span>
      )}
    </span>
  );
});

const AssignmentItem = memo(function AssignmentItem({
  item,
  view,
  index,
  now,
  layoutEnabled,
  canManage,
  onOpen,
  onToggle,
  onDelete,
  onEdit,
}: ItemProps) {
  const tone = deadlineTone(item.due_date, now);
  const group = categoryGroup(item.category);
  const GroupIcon = group?.id === "exam" ? GraduationCap : ClipboardList;
  const done = item.is_completed_by_me;

  const motionProps = {
    layout: layoutEnabled,
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, scale: 0.96 },
    transition: {
      duration: 0.22,
      ease: [0.16, 1, 0.3, 1] as const,
      delay: Math.min(index * 0.015, 0.12),
    },
    onClick: () => onOpen(item.id),
  };

  const toggle = (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onToggle(item);
      }}
      title={done ? "من انجام دادم" : "انجام دادم"}
      className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition ${
        done
          ? "border-success/30 bg-success/10 text-success"
          : "border-white/12 text-fg-300 hover:border-white/30 hover:text-white"
      }`}
    >
      <Check size={12} strokeWidth={3} />
      {done ? "برگرداندن" : "انجام دادم"}
    </button>
  );

  const editBtn = canManage ? (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onEdit(item);
      }}
      className="icon-btn hover:border-white/40 hover:text-white"
      title="ویرایش"
      aria-label="ویرایش تکلیف"
    >
      <Pencil size={14} />
    </button>
  ) : null;

  const removeBtn = canManage ? (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onDelete(item);
      }}
      className="icon-btn ml-auto hover:border-danger/40 hover:text-danger"
      title="حذف"
    >
      <Trash2 size={14} />
    </button>
  ) : null;

  if (view === "list") {
    return (
      <motion.div
        {...motionProps}
        className={`panel panel-hover group relative flex cursor-pointer items-center gap-4 overflow-hidden rounded-2xl border-2 py-3.5 pr-4 pl-3 ${TONE_BORDER[tone]} ${TONE_GLOW[tone]}`}
      >
        <Corners />
        <span className={`absolute top-3 right-0 bottom-3 w-1 rounded-full ${TONE_DOT[tone]}`} />

        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
          <GroupIcon size={18} className="text-white" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3
              className={`truncate text-[14px] font-bold ${
                done ? "text-fg-500 line-through" : "text-white"
              }`}
            >
              {item.title}
            </h3>
            <CreatorBadge name={item.creator_username} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <span className="text-fg-500">
              {group?.label ?? "بدون دسته"}
              {item.subtype && <span> · {categoryItemLabel(item.subtype)}</span>}
            </span>
            {item.subject_id && (
              <span className="flex items-center gap-1.5 text-fg-300">
                <BookOpen size={11} className="shrink-0 text-fg-500" />
                <span className="truncate">{subjectName(item.subject_id, item.course)}</span>
              </span>
            )}
            <span className={`flex items-center gap-1.5 ${TONE_TEXT[tone]}`}>
              <Calendar size={11} className="shrink-0 opacity-70" />
              <span className="truncate">{formatDue(item.due_date)}</span>
              <span className="shrink-0 opacity-70">· {relativeDue(item.due_date, now)}</span>
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <CompletedStack users={item.completed_by_users} />
          {toggle}
          {editBtn}
          {removeBtn}
          <span className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-500 transition group-hover:bg-white/[0.06] group-hover:text-white">
            <ChevronLeft size={16} />
          </span>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      {...motionProps}
      className={`panel panel-hover group relative cursor-pointer overflow-hidden rounded-2xl border-2 p-4 ${TONE_BORDER[tone]} ${TONE_GLOW[tone]}`}
    >
      <Corners />
      <span className={`absolute top-4 right-0 h-[calc(100%-2rem)] w-1 rounded-full ${TONE_DOT[tone]}`} />

      <div className="mb-3 flex items-center gap-2 pr-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
          <GroupIcon size={15} className="text-white" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-semibold text-fg-300">
            {group?.label ?? "بدون دسته"}
            {item.subtype && <span className="text-fg-500"> · {categoryItemLabel(item.subtype)}</span>}
          </p>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 pr-2">
        <h3
          className={`line-clamp-2 text-[15px] leading-6 font-bold ${
            done ? "text-fg-500 line-through" : "text-white"
          }`}
        >
          {item.title}
        </h3>
        <CreatorBadge name={item.creator_username} />
      </div>

      <div className="mb-3 space-y-1.5 pr-2 text-[12px]">
        {item.subject_id && (
          <p className="flex items-center gap-1.5 text-fg-300">
            <BookOpen size={12} className="shrink-0 text-fg-500" />
            <span className="truncate">{subjectName(item.subject_id, item.course)}</span>
          </p>
        )}
        <p className={`flex items-center gap-1.5 ${TONE_TEXT[tone]}`}>
          <Calendar size={12} className="shrink-0 opacity-70" />
          <span className="truncate">{formatDue(item.due_date)}</span>
          <span className="shrink-0 opacity-70">· {relativeDue(item.due_date, now)}</span>
        </p>
      </div>

      <div className="flex items-center gap-2 border-t border-white/8 pt-3 pr-2">
        <CompletedStack users={item.completed_by_users} />
        {toggle}
        {editBtn}
        {removeBtn}
        <span className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-500 transition group-hover:bg-white/[0.06] group-hover:text-white">
          <ChevronLeft size={16} />
        </span>
      </div>
    </motion.div>
  );
});

export default function AssignmentsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const now = useNow(30_000);
  const isMobileWidth = useIsMobileWidth();
  const [items, setItems] = useState<Assignment[]>(() => listCache.get(cacheKey("all")) ?? []);
  const [status, setStatus] = useState<Status>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [sort, setSort] = useState<Sort>("newest");
  const [view, setView] = useState<View>("grid");
  const [loading, setLoading] = useState(() => !listCache.has(cacheKey("all")));
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Assignment | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setRefreshKey((k) => k + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = status === "all" ? undefined : { completed: status === "done" };
    fetchAssignments(params, controller.signal)
      .then((data) => {
        listCache.set(cacheKey(status), data);
        setItems(data);
        setError(null);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : "خطا در بارگذاری داده‌ها");
        setLoading(false);
      });
    return () => controller.abort();
  }, [status, refreshKey]);

  const categoryGroups = useMemo(() => [{ options: CATEGORY_OPTIONS }], []);
  const subjectGroups = useMemo(
    () => [
      {
        options: [
          { value: "", label: "همه درس‌ها" },
          ...SUBJECT_LIST.map((s) => ({ value: s.id, label: s.name, description: s.teacher })),
        ],
      },
    ],
    []
  );
  const sortGroups = useMemo(
    () => [
      {
        options: SORT_OPTIONS.map((o) => {
          const labels: Record<string, string> = {
            newest: "جدیدترین ابتدا",
            oldest: "قدیمی‌ترین ابتدا",
            deadline: "نزدیک‌ترین ددلاین",
          };
          return { ...o, label: labels[o.value] ?? o.label };
        }),
      },
    ],
    []
  );

  const displayed = useMemo(() => {
    let list = items;
    if (categoryFilter === "project") list = list.filter((a) => a.subtype === "practical");
    else if (categoryFilter) list = list.filter((a) => a.category === categoryFilter);
    if (subjectFilter) list = list.filter((a) => a.subject_id === subjectFilter);

    const sorted = [...list];
    sorted.sort((a, b) => {
      if (sort === "newest") return parseDue(b.created_at).getTime() - parseDue(a.created_at).getTime();
      if (sort === "oldest") return parseDue(a.created_at).getTime() - parseDue(b.created_at).getTime();
      return (
        assignDeadline(a) - assignDeadline(b) ||
        parseDue(b.created_at).getTime() - parseDue(a.created_at).getTime()
      );
    });
    return sorted;
  }, [items, categoryFilter, subjectFilter, sort]);

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((item: Assignment) => {
    setEditing(item);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditing(null);
  }, []);

  const handleOpen = useCallback((id: number) => navigate(`/assignments/${id}`), [navigate]);
  const handleToggle = useCallback(
    (item: Assignment) => toggleAssignmentCompletion(item.id).then(reload),
    [reload]
  );
  const handleDelete = useCallback((item: Assignment) => deleteAssignment(item.id).then(reload), [reload]);

  return (
    <div>
      <PageHeader
        kicker="assignments"
        title="تکالیف و پروژه‌ها"
        subtitle="مدیریت، زمان‌بندی و پیگیری تکالیف درسی"
        action={
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={openCreate}
            className="group relative flex items-center gap-2.5 overflow-hidden rounded-2xl border border-white/70 bg-white px-5 py-3 text-sm font-black text-black shadow-[0_0_35px_-8px_rgba(255,255,255,0.85)] transition-colors hover:bg-white/90"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-black text-white">
              <Plus size={15} strokeWidth={3} />
            </span>
            افزودن تکالیف
          </motion.button>
        }
      />

      {/* نوار ابزار */}
      <div className="panel relative mb-5 flex flex-col gap-3 p-3">
        <Corners />
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1.5 rounded-2xl border border-white/10 bg-white/[0.02] p-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => {
                  if (f.key === status) return;
                  const cached = listCache.get(cacheKey(f.key));
                  if (cached) {
                    setItems(cached);
                    setError(null);
                    setLoading(false);
                  } else {
                    setLoading(true);
                  }
                  setStatus(f.key);
                }}
                className={`relative rounded-xl px-4 py-2 text-xs font-semibold transition ${
                  status === f.key ? "text-black" : "text-fg-500 hover:text-white"
                }`}
              >
                {status === f.key && (
                  <motion.span
                    layoutId="assign-filter"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    className="absolute inset-0 rounded-xl bg-white"
                  />
                )}
                <span className="relative z-10">{f.label}</span>
              </button>
            ))}
          </div>

          <span className="badge ms-auto">
            <span className="dot" />
            {displayed.length} ITEMS
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Dropdown
            ariaLabel="فیلتر دسته‌بندی"
            groups={categoryGroups}
            value={categoryFilter}
            onChange={setCategoryFilter}
            placeholder="همه دسته‌ها"
            icon={<Filter size={16} />}
            className="w-[calc(50%-0.25rem)] sm:w-[190px]"
          />
          <Dropdown
            ariaLabel="فیلتر درس"
            groups={subjectGroups}
            value={subjectFilter}
            onChange={setSubjectFilter}
            placeholder="همه درس‌ها"
            icon={<BookOpen size={16} />}
            className="w-[calc(50%-0.25rem)] sm:w-[190px]"
          />
          <Dropdown
            ariaLabel="ترتیب نمایش"
            groups={sortGroups}
            value={sort}
            onChange={(v) => setSort(v as Sort)}
            placeholder="جدیدترین"
            icon={<ArrowUpDown size={16} />}
            className="w-[calc(50%-0.25rem)] sm:w-[214px]"
          />

          <div className="flex gap-1 rounded-2xl border border-white/10 bg-white/[0.02] p-1 ms-auto">
            {VIEW_BUTTONS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key)}
                aria-label={label}
                aria-pressed={view === key}
                title={label}
                className={`relative flex h-9 w-9 items-center justify-center rounded-xl transition-colors ${
                  view === key ? "text-black" : "text-fg-500 hover:text-white"
                }`}
              >
                {view === key && (
                  <motion.span
                    layoutId="assign-view"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    className="absolute inset-0 rounded-xl bg-white"
                  />
                )}
                <Icon size={16} className="relative z-10" />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* لیست */}
      {loading ? (
        <div
          className={
            view === "grid" ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-3" : "flex flex-col gap-3"
          }
          aria-busy="true"
          aria-live="polite"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className={`panel relative animate-pulse overflow-hidden rounded-2xl border-2 border-white/8 ${
                view === "grid" ? "h-48" : "h-[76px]"
              }`}
              style={{ animationDelay: `${i * 90}ms` }}
            >
              <span className="absolute top-4 right-0 h-[calc(100%-2rem)] w-1 rounded-full bg-white/15" />
              <span className="absolute top-6 right-6 h-4 w-2/5 rounded-md bg-white/10" />
              <span className="absolute top-14 right-6 h-3 w-3/5 rounded-md bg-white/8" />
              <span className="absolute bottom-5 right-6 h-3 w-1/4 rounded-md bg-white/8" />
            </div>
          ))}
        </div>
      ) : error ? (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel relative flex flex-col items-center justify-center gap-3 p-16 text-center"
        >
          <Corners />
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-danger/30 bg-danger/10">
            <RefreshCw size={20} className="text-danger" />
          </span>
          <p className="text-sm font-semibold text-white">بارگذاری داده‌ها ناموفق بود</p>
          <p className="max-w-xs text-[12px] text-fg-500">{error}</p>
          <button onClick={reload} className="btn-primary mt-1">
            <RefreshCw size={14} />
            تلاش دوباره
          </button>
        </motion.div>
      ) : displayed.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel relative flex flex-col items-center justify-center gap-3 p-16 text-center"
        >
          <Corners />
          <ClipboardList size={30} className="text-fg-500" />
          <p className="text-sm text-fg-500">
            {items.length === 0 ? "هنوز تکلیفی ثبت نشده" : "تکلیفی با این فیلترها پیدا نشد"}
          </p>
          {items.length === 0 && (
            <button onClick={openCreate} className="btn-ghost mt-1">
              <Plus size={14} />
              افزودن اولین تکلیف
            </button>
          )}
        </motion.div>
      ) : (
        <motion.div
          layout
          transition={{ type: "spring", stiffness: 320, damping: 34 }}
          className={
            view === "grid" ? "grid gap-4 sm:grid-cols-2 xl:grid-cols-3" : "flex flex-col gap-3"
          }
        >
          <AnimatePresence mode="popLayout" initial={false}>
            {displayed.map((item, i) => (
              <AssignmentItem
                key={item.id}
                item={item}
                view={view}
                index={i}
                now={now}
                layoutEnabled={!isMobileWidth}
                canManage={canManageAssignment(item, user)}
                onOpen={handleOpen}
                onToggle={handleToggle}
                onDelete={handleDelete}
                onEdit={openEdit}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      <AddAssignmentModal
        open={modalOpen}
        onClose={closeModal}
        onSaved={reload}
        assignment={editing}
      />
    </div>
  );
}
