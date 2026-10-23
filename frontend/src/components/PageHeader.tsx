import { memo } from "react";
import type { ReactNode } from "react";

/**
 * Memoised: pages re-render on their own clocks and state, and the header is
 * pure text — there is no reason to reconcile it again when nothing changed.
 */
function PageHeader({
  kicker,
  title,
  subtitle,
  action,
}: {
  kicker?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4 sm:mb-8">
      <div className="min-w-0">
        {kicker && (
          <div className="badge mb-3">
            <span className="dot animate-pulse" />
            {kicker}
          </div>
        )}
        <h1 className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 text-sm text-fg-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export default memo(PageHeader);
