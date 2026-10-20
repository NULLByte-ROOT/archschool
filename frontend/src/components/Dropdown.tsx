import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";

export interface DropdownOption {
  value: string;
  label: string;
  description?: string;
}

export interface DropdownGroup {
  label?: string;
  options: DropdownOption[];
}

interface DropdownProps {
  groups: DropdownGroup[];
  value: string | null;
  onChange: (value: string) => void;
  placeholder: string;
  icon?: ReactNode;
  hint?: string;
  ariaLabel?: string;
  large?: boolean;
  className?: string;
}

const PANEL_ESTIMATE = 300;

interface PanelPos {
  right: number;
  minWidth: number;
  top?: number;
  bottom?: number;
  up: boolean;
}

export default function Dropdown({
  groups,
  value,
  onChange,
  placeholder,
  icon,
  hint,
  ariaLabel,
  large = false,
  className = "",
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<PanelPos | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const flat = groups.flatMap((g) => g.options);
  const selected = flat.find((o) => o.value === value) ?? null;

  const reposition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - r.bottom;
    const up = spaceBelow < PANEL_ESTIMATE && r.top > spaceBelow;
    const compact = window.innerWidth < 640;
    setPos({
      right: compact ? 8 : Math.max(8, window.innerWidth - r.right),
      minWidth: compact ? 0 : r.width,
      up,
      ...(up ? { bottom: window.innerHeight - r.top + 8 } : { top: r.bottom + 8 }),
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onMove() {
      reposition();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onMove);
      window.removeEventListener("scroll", onMove, true);
    };
  }, [open, reposition]);

  function syncActive() {
    const i = flat.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
  }

  function toggle() {
    if (!open) {
      syncActive();
      reposition();
    }
    setOpen((o) => !o);
  }

  function choose(v: string) {
    onChange(v);
    setOpen(false);
  }

  function onTriggerKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        syncActive();
        reposition();
        setOpen(true);
        return;
      }
      setActive((prev) => {
        const next = e.key === "ArrowDown" ? prev + 1 : prev - 1;
        return (next + flat.length) % flat.length;
      });
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (flat[active]) choose(flat[active].value);
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        onKeyDown={onTriggerKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        className={`group flex w-full items-center gap-3 rounded-2xl border text-right transition-[background-color,border-color,box-shadow] duration-300 ${
          large ? "px-4 py-3.5" : "px-3.5 py-3"
        } ${
          open
            ? "border-white/35 bg-black/70 shadow-[0_0_30px_-12px_rgba(255,255,255,0.6)]"
            : "border-white/12 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.05]"
        }`}
      >
        {icon && (
          <span
            className={`flex shrink-0 items-center justify-center rounded-xl border transition-colors ${
              open ? "border-white/30 bg-white/10 text-white" : "border-white/12 bg-white/[0.04] text-fg-500"
            } ${large ? "h-10 w-10" : "h-9 w-9"}`}
          >
            {icon}
          </span>
        )}

        <span className="min-w-0 flex-1">
          {selected ? (
            <>
              {hint && (
                <span className="mono-label mb-0.5 block truncate text-fg-500">{hint}</span>
              )}
              <span
                className={`block truncate font-semibold text-white ${
                  large ? "text-sm" : "text-[13px]"
                }`}
              >
                {selected.label}
              </span>
            </>
          ) : (
            <span className="block truncate text-[13px] text-fg-500">{placeholder}</span>
          )}
        </span>

        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 26 }}
          className="shrink-0 text-fg-500"
        >
          <ChevronDown size={18} />
        </motion.span>
      </button>

      {createPortal(
        <AnimatePresence>
          {open && pos && (
            <motion.div
              ref={panelRef}
              role="listbox"
              aria-label={ariaLabel}
              initial={{ opacity: 0, y: pos.up ? 8 : -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: pos.up ? 8 : -8, scale: 0.98 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              style={{
                position: "fixed",
                right: pos.right,
                minWidth: pos.minWidth,
                top: pos.top,
                bottom: pos.bottom,
                transformOrigin: pos.up ? "bottom" : "top",
              }}
              className="z-[999] max-h-72 w-max max-w-[min(92vw,24rem)] overflow-x-hidden overflow-y-auto rounded-2xl border border-white/15 bg-[#0a0a0c]/98 p-1.5 shadow-2xl shadow-black/80 ring-1 ring-black/50"
            >
              {groups.map((group, gi) => (
                <div key={group.label ?? gi} className="mb-1 last:mb-0">
                  {group.label && <p className="mono-label px-3 pt-2 pb-1.5">{group.label}</p>}
                  {group.options.map((option) => {
                    const isSelected = option.value === value;
                    const isActive = flat[active]?.value === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        onMouseEnter={() => setActive(flat.findIndex((o) => o.value === option.value))}
                        onClick={() => choose(option.value)}
                        className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-3 text-right transition-colors sm:py-2.5 ${
                          isActive ? "bg-white/[0.07]" : ""
                        } ${isSelected ? "text-white" : "text-fg-300 hover:text-white"}`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{option.label}</span>
                          {option.description && (
                            <span className="mt-0.5 block truncate text-[10px] text-fg-500">
                              {option.description}
                            </span>
                          )}
                        </span>
                        {isSelected && <Check size={15} className="shrink-0 text-white" />}
                      </button>
                    );
                  })}
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </div>
  );
}
