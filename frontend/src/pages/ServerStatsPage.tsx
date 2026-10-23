import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Cpu, HardDrive, MemoryStick, RefreshCw, ServerCog } from "lucide-react";
import { fetchServerStats } from "../api/client";
import type { ServerStats } from "../api/client";
import PageHeader from "../components/PageHeader";
import Corners from "../components/Corners";

/**
 * داشبورد زندهٔ وضعیت سرور — فقط Owner.
 * هر ۲ ثانیه یک GET سبک زده می‌شود؛ بدون WebSocket تا مسیر چتِ در حال کار
 * دست‌نخورده بماند. حلقه‌ها و میله‌ها با transition نرم حرکت می‌کنند.
 */

const POLL_MS = 2000;

const fa = new Intl.NumberFormat("en-US");

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "۰";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${fa.format(Math.round(value * 10) / 10)} ${units[unit]}`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d) parts.push(`${fa.format(d)} روز`);
  if (h) parts.push(`${fa.format(h)} ساعت`);
  parts.push(`${fa.format(m)} دقیقه`);
  return parts.join(" و ");
}

function tone(percent: number): string {
  if (percent >= 90) return "#f87171";
  if (percent >= 70) return "#fbbf24";
  return "#4ade80";
}

/** حلقهٔ درصدی با دستهٔ SVG؛ نرم‌شدن با transition انجام می‌شود. */
function Gauge({
  percent,
  label,
  sublabel,
  icon,
}: {
  percent: number;
  label: string;
  sublabel: string;
  icon: React.ReactNode;
}) {
  const clamped = Math.max(0, Math.min(100, percent));
  const R = 44;
  const C = 2 * Math.PI * R;
  const color = tone(clamped);
  return (
    <div className="panel relative flex flex-col items-center gap-2 p-4 sm:p-5">
      <Corners />
      <div className="flex items-center gap-2 self-start">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-fg-300">
          {icon}
        </span>
        <span className="mono-label">{label}</span>
      </div>
      <div className="relative">
        <svg width="112" height="112" viewBox="0 0 112 112">
          <circle
            cx="56"
            cy="56"
            r={R}
            fill="none"
            stroke="rgba(255,255,255,0.07)"
            strokeWidth="9"
          />
          <circle
            cx="56"
            cy="56"
            r={R}
            fill="none"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - clamped / 100)}
            transform="rotate(-90 56 56)"
            style={{
              transition: "stroke-dashoffset 1.2s ease, stroke 0.6s ease",
              filter: `drop-shadow(0 0 6px ${color}66)`,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-extrabold text-white tabular-nums">
            {fa.format(Math.round(clamped))}٪
          </span>
        </div>
      </div>
      <p className="mono text-center text-[11px] leading-5 text-fg-500" dir="auto">
        {sublabel}
      </p>
    </div>
  );
}

/** میلهٔ افقی (برای هسته‌های CPU). */
function CoreBar({ percent }: { percent: number }) {
  const clamped = Math.max(0, Math.min(100, percent));
  const color = tone(clamped);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
        {/*
          scaleX به‌جای width: انیمیشن width هر فریم layout کل ردیف را دوباره
          حساب می‌کرد (با ۲۴ هسته، هر ۲ ثانیه یک موج layout). scaleX فقط
          کامپوزیت است و از سمت راست رشد می‌کند تا در RTL همان ظاهر را بدهد.
        */}
        <div
          className="h-full w-full rounded-full will-change-transform"
          style={{
            background: color,
            transform: `scaleX(${clamped / 100})`,
            transformOrigin: "right",
            transition: "transform 1.2s ease, background 0.6s ease",
          }}
        />
      </div>
      <span
        className="mono w-10 shrink-0 text-left text-[10px] tabular-nums text-fg-500"
        dir="ltr"
      >
        {Math.round(clamped)}%
      </span>
    </div>
  );
}

export default function ServerStatsPage() {
  const [stats, setStats] = useState<ServerStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function poll() {
      try {
        const data = await fetchServerStats(controller.signal);
        if (!active) return;
        setStats(data);
        setError(null);
      } catch (e) {
        if (controller.signal.aborted) return;
        // خطای موقتی شبکه نباید صفحه را بخواباند؛ نشان می‌دهیم و ادامه می‌دهیم.
        if (active) {
          setError(e instanceof Error ? e.message : "خطا در دریافت آمار");
        }
      }
    }

    poll();
    timer.current = window.setInterval(poll, POLL_MS);
    return () => {
      active = false;
      controller.abort();
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [tick]);

  return (
    <div>
      <PageHeader
        kicker="owner"
        title="آمار زندهٔ سرور"
        subtitle="CPU، رم و دیسک — به‌روزرسانی هر ۲ ثانیه"
        action={
          <button
            onClick={() => setTick((t) => t + 1)}
            className="btn-primary"
            title="بروزرسانی فوری"
          >
            <RefreshCw size={14} />
            بروزرسانی
          </button>
        }
      />

      {error && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mb-4 rounded-xl border border-warning/25 bg-warning/10 px-3 py-2 text-xs text-warning"
        >
          {error} — تلاش مجدد خودکار…
        </motion.p>
      )}

      {!stats ? (
        <div className="panel flex items-center justify-center gap-2 p-12 text-sm text-fg-500">
          <RefreshCw size={16} className="animate-spin" />
          در حال اتصال به سرور…
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Gauge
              percent={stats.cpu.percent}
              label="CPU"
              icon={<Cpu size={14} />}
              sublabel={`بار ۱ دقیقه: ${stats.cpu.load_1.toFixed(2)} · ${fa.format(stats.cpu.core_count)} هسته`}
            />
            <Gauge
              percent={stats.memory.percent}
              label="RAM"
              icon={<MemoryStick size={14} />}
              sublabel={`${formatBytes(stats.memory.used)} از ${formatBytes(stats.memory.total)}`}
            />
            <Gauge
              percent={stats.disk.percent}
              label="دیسک"
              icon={<HardDrive size={14} />}
              sublabel={`${formatBytes(stats.disk.used)} از ${formatBytes(stats.disk.total)}`}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="panel relative p-4 sm:p-5">
              <Corners />
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-fg-300">
                  <Cpu size={13} />
                </span>
                <span className="mono-label">هسته‌های CPU</span>
              </div>
              <div className="space-y-2.5">
                {stats.cpu.per_core.map((p, i) => (
                  <CoreBar key={i} percent={p} />
                ))}
              </div>
            </div>

            <div className="panel relative p-4 sm:p-5">
              <Corners />
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-fg-300">
                  <ServerCog size={13} />
                </span>
                <span className="mono-label">وضعیت سیستم</span>
              </div>
              <dl className="space-y-2.5 text-[13px]">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-500">آپ‌تایم</dt>
                  <dd className="font-semibold text-white">
                    {formatUptime(stats.uptime_seconds)}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-500">بار سیستم (۱/۵/۱۵)</dt>
                  <dd className="mono text-white tabular-nums" dir="ltr">
                    {stats.cpu.load_1.toFixed(2)} / {stats.cpu.load_5.toFixed(2)} /{" "}
                    {stats.cpu.load_15.toFixed(2)}
                  </dd>
                </div>
                {stats.swap.total > 0 && (
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-fg-500">Swap</dt>
                    <dd className="font-semibold text-white">
                      {fa.format(Math.round(stats.swap.percent))}٪ —{" "}
                      {formatBytes(stats.swap.used)}
                    </dd>
                  </div>
                )}
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-fg-500">RAM در حال استفاده</dt>
                  <dd className="font-semibold text-white">
                    {formatBytes(stats.memory.used)}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
