import { useEffect, useState } from "react";

/** خواندن یک مدیاکوئری به‌صورت واکنشی */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** موبایل یا صفحه‌نمایش لمسی: غیرفعال‌سازی افکت‌های سنگین */
export const MOBILE_QUERY = "(max-width: 768px), (pointer: coarse)";

/** آیا دستگاه فعلی موبایل/لمسی است؟ */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY);
}

/** فقط بر اساس عرض صفحه‌نمایش (برای انتخاب چیدمان) */
export const MOBILE_WIDTH_QUERY = "(max-width: 768px)";

/** آیا عرض صفحه‌نمایش در محدوده‌ی موبایل است؟ */
export function useIsMobileWidth(): boolean {
  return useMediaQuery(MOBILE_WIDTH_QUERY);
}
