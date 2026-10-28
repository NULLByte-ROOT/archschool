import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";

/**
 * نمایش تصویر سراسری به سبک تلگرام:
 *
 * - هر تصویری در کل اپ (آواتار، تصویر گفتگو، پیوستِ تکلیف) در همین
 *   روکش تمام‌صفحه باز می‌شود؛ دیگر تب جدید یا صفحه‌ی جدید نیست.
 * - گالری: اگر فراخوان فهرست تصاویر همان بافت را بدهد (همه تصاویر
 *   یک اتاق گفتگو یا همه‌ی پیوست‌های تصویری یک تکلیف)، بشود با فلش
 *   کیبورد، دکمه‌های chevron و کشیدن انگشت بین‌شان جابه‌جا شد.
 * - بزرگ‌نمایی: پینچ (موبایل)، چرخ ماوس و دابل‌کلیک (دسکتاپ).
 *   بعد از زوم، کشیدن فقط تصویر را جابه‌جا می‌کند (pan) و از زوم
 *   خارج شدن، همان مکان را برمی‌گرداند.
 * - آدرس تصاویر باید از قبل با resolveMediaUrl حل شده باشد تا روی
 *   HTTPS مشکل mixed-content نداشته باشیم.
 */

export type ViewerImage = {
  src: string;
  alt: string;
};

type ViewerState = {
  images: ViewerImage[];
  index: number;
};

let current: ViewerState | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): ViewerState | null {
  return current;
}

/** باز کردن یک تصویر تنها (کلیک روی آواتار و ...) */
export function openImageViewer(
  src: string | null | undefined,
  alt = "",
  images?: ViewerImage[],
  startIndex = 0
) {
  if (!src) return;
  if (images && images.length > 0) {
    const found = images.findIndex((candidate) => candidate.src === src);
    current = {
      images,
      index: found >= 0 ? found : Math.min(Math.max(startIndex, 0), images.length - 1),
    };
  } else {
    current = { images: [{ src, alt }], index: 0 };
  }
  emit();
}

/** باز کردن گالری کامل: فهرست تصاویر آن بافت + ایندکس تصویر کلیک‌شده */
export function openImageGallery(images: ViewerImage[], startIndex = 0) {
  if (images.length === 0) return;
  current = {
    images,
    index: Math.min(Math.max(startIndex, 0), images.length - 1),
  };
  emit();
}

function closeImageViewer() {
  current = null;
  emit();
}

function fileNameFor(image: ViewerImage): string {
  const alt = image.alt?.trim();
  if (alt) return alt;
  try {
    const path = new URL(image.src, window.location.href).pathname;
    const last = decodeURIComponent(path.split("/").pop() ?? "");
    if (last) return last;
  } catch {
    // ignore malformed URLs and fall through
  }
  return "image";
}

/** Save the image with a real download; falls back to opening it directly when CORS blocks the blob. */
async function downloadImage(image: ViewerImage) {
  const fileName = fileNameFor(image);
  try {
    const response = await fetch(image.src);
    if (!response.ok) throw new Error(String(response.status));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  } catch {
    const link = document.createElement("a");
    link.href = image.src;
    link.download = fileName;
    link.target = "_blank";
    link.rel = "noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;
const SWIPE_THRESHOLD = 60;

function clampZoom(value: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
}

function touchDistance(
  a: { x: number; y: number },
  b: { x: number; y: number }
): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export default function ImageViewer() {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const overlayRef = useRef<HTMLDivElement | null>(null);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const pinchBaseRef = useRef<{ dist: number; zoom: number } | null>(null);
  const dragLastRef = useRef<{ x: number; y: number } | null>(null);
  const swipeStartRef = useRef<{ x: number; y: number } | null>(null);
  // آیا بین pointerdown و up جابه‌جایی واقعی داشتیم؟ (تمایز کلیک و سوایپ/درگ)
  const movedRef = useRef(false);

  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const total = state?.images.length ?? 0;
  const safeIndex = state
    ? Math.min(Math.max(index, 0), total - 1)
    : 0;
  const image = state?.images[safeIndex] ?? null;

  // همگام‌سازی با استور سراسری: هر باز/جابه‌جایی جدید از پایه شروع شود
  useEffect(() => {
    if (!state) return;
    setIndex(state.index);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setDir(0);
  }, [state]);

  function step(delta: number) {
    if (!state || total < 2) return;
    setDir(delta);
    setIndex((prev) => (prev + delta + total) % total);
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  // قفل اسکرول + میان‌برهای کیبورد
  useEffect(() => {
    if (!image) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeImageViewer();
      } else if (event.key === "ArrowLeft") {
        // چینش راست‌به‌چپ: فلش چپ = تصویر بعدی
        step(1);
      } else if (event.key === "ArrowRight") {
        step(-1);
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [image, state, total]);

  // چرخ ماوس برای زوم (listener دستی تا preventDefault کار کند)
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !image) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      setZoom((prev) => {
        const next = clampZoom(prev * (event.deltaY < 0 ? 1.2 : 1 / 1.2));
        return next;
      });
    };
    overlay.addEventListener("wheel", onWheel, { passive: false });
    return () => overlay.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [image]);

  // وقتی زوم به ۱ برمی‌گردد، جابه‌جایی صفر می‌شود
  useEffect(() => {
    if (zoom === MIN_ZOOM) setPan({ x: 0, y: 0 });
  }, [zoom]);

  // پیش‌بارگذاری تصویر قبلی/بعدی برای تعویض روان
  useEffect(() => {
    if (!state || total < 2) return;
    for (const offset of [-1, 1]) {
      const neighbor = state.images[(safeIndex + offset + total) % total];
      if (!neighbor) continue;
      const loader = new Image();
      loader.decoding = "async";
      loader.src = neighbor.src;
    }
  }, [state, safeIndex, total]);

  if (!state || !image) return null;

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const pointers = pointersRef.current;
    movedRef.current = false;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    overlayRef.current?.setPointerCapture(event.pointerId);

    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinchBaseRef.current = { dist: touchDistance(a, b), zoom };
      dragLastRef.current = null;
      swipeStartRef.current = null;
    } else if (pointers.size === 1) {
      if (zoom > MIN_ZOOM) {
        dragLastRef.current = { x: event.clientX, y: event.clientY };
        swipeStartRef.current = null;
      } else {
        swipeStartRef.current = { x: event.clientX, y: event.clientY };
        dragLastRef.current = null;
      }
    }
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const pointers = pointersRef.current;
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    const pinch = pinchBaseRef.current;
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const ratio = touchDistance(a, b) / Math.max(1, pinch.dist);
      setZoom(clampZoom(pinch.zoom * ratio));
      return;
    }

    const drag = dragLastRef.current;
    if (zoom > MIN_ZOOM && drag) {
      setPan((prev) => ({
        x: prev.x + (event.clientX - drag.x),
        y: prev.y + (event.clientY - drag.y),
      }));
      dragLastRef.current = { x: event.clientX, y: event.clientY };
      movedRef.current = true;
      return;
    }

    // نوک حرکت وقتی زوم ۱ است (سوایپ بالقوه) — برای تمایز کلیک بی‌جابه‌جایی
    if (zoom === MIN_ZOOM && swipeStartRef.current) {
      if (
        touchDistance(
          { x: event.clientX, y: event.clientY },
          swipeStartRef.current
        ) > 10
      ) {
        movedRef.current = true;
      }
    }
  }

  function handlePointerCancel(event: ReactPointerEvent<HTMLDivElement>) {
    pointersRef.current.delete(event.pointerId);
    pinchBaseRef.current = null;
    dragLastRef.current = null;
    swipeStartRef.current = null;
  }

  function handleGestureEnd(event: ReactPointerEvent<HTMLDivElement>) {
    pointersRef.current.delete(event.pointerId);
    if (pointersRef.current.size < 2) pinchBaseRef.current = null;
    dragLastRef.current = null;
    const start = swipeStartRef.current;
    swipeStartRef.current = null;

    if (!start || zoom > MIN_ZOOM || total < 2) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
      step(dx < 0 ? 1 : -1);
    }
  }

  return createPortal(
    <AnimatePresence>
      <motion.div
        key="image-viewer"
        ref={overlayRef}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
        onClick={() => closeImageViewer()}
        role="dialog"
        aria-modal="true"
        aria-label={image.alt ? `تصویر ${image.alt}` : "نمایش تصویر"}
        style={{ touchAction: "none" }}
        className="fixed inset-0 z-[9999] bg-black/95"
      >
        {/* لایه‌ی تعامل: پن، پینچ، سوایپ، پس‌زمینه */}
        <div
          className="absolute inset-0"
          onClick={(event) => {
            // کلیک بعد از درگ/سوایپ بسته نشود
            if (movedRef.current) {
              movedRef.current = false;
              return;
            }
            // کلیک روی خود تصویر نمی‌بندد؛ فقط پس‌زمینه می‌بندد
            if ((event.target as HTMLElement).closest("[data-viewer-image]")) {
              return;
            }
            closeImageViewer();
          }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handleGestureEnd}
          onPointerCancel={handlePointerCancel}
          onDoubleClick={(event) => {
            event.stopPropagation();
            setZoom((prev) => (prev > MIN_ZOOM + 0.01 ? MIN_ZOOM : 2.5));
          }}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={image.src}
              className="absolute inset-0 flex items-center justify-center p-4 sm:p-10"
              initial={{ opacity: 0, x: dir * 60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -dir * 60 }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            >
              <img
                src={image.src}
                alt={image.alt}
                draggable={false}
                data-viewer-image
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                  transformOrigin: "center",
                  cursor: zoom > MIN_ZOOM ? "grab" : "zoom-in",
                }}
                className="max-h-full max-w-full select-none object-contain shadow-2xl shadow-black will-change-transform"
              />
            </motion.div>
          </AnimatePresence>
        </div>

        {/* بستن */}
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            closeImageViewer();
          }}
          aria-label="بستن تصویر"
          className="absolute top-[max(1rem,env(safe-area-inset-top))] right-[max(1rem,env(safe-area-inset-right))] z-10 flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white transition hover:bg-white/20"
        >
          <X size={20} />
        </button>

        {/* دانلود */}
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            void downloadImage(image);
          }}
          aria-label="دانلود تصویر"
          title="دانلود تصویر"
          className="absolute top-[max(1rem,env(safe-area-inset-top))] left-[max(1rem,env(safe-area-inset-left))] z-10 flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white transition hover:bg-white/20"
        >
          <Download size={20} />
        </button>

        {/* شمارنده */}
        {total > 1 && (
          <span
            onClick={(event) => event.stopPropagation()}
            className="mono absolute top-[max(1.35rem,env(safe-area-inset-top))] left-1/2 z-10 -translate-x-1/2 rounded-full border border-white/15 bg-black/60 px-3 py-1 text-[11px] font-bold tabular-nums text-white/90"
          >
            {safeIndex + 1} / {total}
          </span>
        )}

        {/* ناوبری چپ/راست */}
        {total > 1 && (
          <>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                step(-1);
              }}
              aria-label="تصویر قبلی"
              className="absolute top-1/2 right-[max(0.5rem,env(safe-area-inset-right))] z-10 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-black/50 text-white/90 transition hover:bg-black/80 hover:text-white md:h-14 md:w-14"
            >
              <ChevronRight size={24} />
            </button>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                step(1);
              }}
              aria-label="تصویر بعدی"
              className="absolute top-1/2 left-[max(0.5rem,env(safe-area-inset-left))] z-10 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-black/50 text-white/90 transition hover:bg-black/80 hover:text-white md:h-14 md:w-14"
            >
              <ChevronLeft size={24} />
            </button>
          </>
        )}

        {/* کپشن */}
        {image.alt && (
          <p
            onClick={(event) => event.stopPropagation()}
            className="pointer-events-none absolute bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-10 max-w-[80vw] -translate-x-1/2 truncate rounded-full bg-black/60 px-4 py-1.5 text-center text-xs font-semibold text-white/80"
          >
            {image.alt}
          </p>
        )}
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
