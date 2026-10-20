import { Moon, Sun } from "lucide-react";
import { useTheme } from "../contexts/ThemeContext";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`icon-btn shrink-0 ${className}`}
      aria-label={isDark ? "روشن کردن تم" : "تاریک کردن تم"}
      title={isDark ? "حالت روشن" : "حالت تاریک"}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
