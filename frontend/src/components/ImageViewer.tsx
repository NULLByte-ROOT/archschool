import { useEffect, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

type ViewerImage = {
  src: string;
  alt: string;
};

let current: ViewerImage | null = null;
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

function getSnapshot() {
  return current;
}

export function openImageViewer(src: string | null | undefined, alt = "") {
  if (!src) return;
  current = { src, alt };
  emit();
}

function closeImageViewer() {
  current = null;
  emit();
}

export default function ImageViewer() {
  const image = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    if (!image) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeImageViewer();
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [image]);

  return createPortal(
    <AnimatePresence>
      {image && (
        <motion.div
          key="image-viewer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          onClick={closeImageViewer}
          role="dialog"
          aria-modal="true"
          aria-label={image.alt ? `تصویر ${image.alt}` : "نمایش تصویر"}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/95 p-4 sm:p-8"
        >
          <motion.img
            key={image.src}
            src={image.src}
            alt={image.alt}
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            onClick={(event) => event.stopPropagation()}
            draggable={false}
            className="max-h-full max-w-full select-none rounded-lg object-contain shadow-2xl shadow-black will-change-transform"
          />

          <button
            type="button"
            onClick={closeImageViewer}
            aria-label="بستن تصویر"
            className="absolute top-[max(1rem,env(safe-area-inset-top))] left-[max(1rem,env(safe-area-inset-left))] flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur-sm transition hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/60"
          >
            <X size={20} />
          </button>

          {image.alt && (
            <p
              onClick={(event) => event.stopPropagation()}
              className="pointer-events-none absolute bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 max-w-[80vw] -translate-x-1/2 truncate text-center text-xs font-semibold text-white/70"
            >
              {image.alt}
            </p>
          )}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
