import { useRef } from "react";
import type { ClipboardEvent, KeyboardEvent } from "react";

interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  masked?: boolean;
}

const LENGTH = 6;

export default function CodeInput({ value, onChange, masked = false }: CodeInputProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const setDigits = (next: string, focusIndex?: number) => {
    onChange(next.slice(0, LENGTH));
    if (focusIndex !== undefined) {
      refs.current[Math.min(focusIndex, LENGTH - 1)]?.focus();
    }
  };

  const handleChange = (index: number, raw: string) => {
    const clean = raw.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();

    if (!clean) {
      const next = Array.from({ length: LENGTH }, (_, i) => value[i] ?? "");
      next[index] = "";
      setDigits(next.join(""));
      return;
    }

    const digits = Array.from({ length: LENGTH }, (_, i) => value[i] ?? "");
    clean.split("").forEach((char, offset) => {
      if (index + offset < LENGTH) digits[index + offset] = char;
    });
    setDigits(digits.join(""), index + clean.length);
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace" && !value[index] && index > 0) {
      event.preventDefault();
      const next = Array.from({ length: LENGTH }, (_, i) => value[i] ?? "");
      next[index - 1] = "";
      setDigits(next.join(""), index - 1);
    }
    if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      refs.current[index - 1]?.focus();
    }
    if (event.key === "ArrowRight" && index < LENGTH - 1) {
      event.preventDefault();
      refs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    const pasted = event.clipboardData
      .getData("text")
      .replace(/[^a-zA-Z0-9]/g, "")
      .toUpperCase()
      .slice(0, LENGTH);
    if (!pasted) return;
    setDigits(pasted, pasted.length);
  };

  return (
    <div dir="ltr" className="grid w-full grid-cols-6 gap-1.5 sm:gap-2" onPaste={handlePaste}>
      {Array.from({ length: LENGTH }, (_, index) => (
        <input
          key={index}
          ref={(el) => {
            refs.current[index] = el;
          }}
          type={masked ? "password" : "text"}
          inputMode="text"
          autoCapitalize="characters"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          autoCorrect="off"
          spellCheck={false}
          maxLength={1}
          value={value[index] ?? ""}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onFocus={(event) => event.currentTarget.select()}
          aria-label={`کاراکتر ${index + 1} کد دسترسی`}
          className="auth-input h-11 min-w-0 w-full rounded-xl border border-white/10 bg-white/[0.03] px-0 text-center font-mono text-base font-bold uppercase text-white outline-none transition-colors placeholder:text-zinc-700 hover:bg-white/[0.06] focus:border-white focus:bg-black sm:h-12 sm:text-lg"
        />
      ))}
    </div>
  );
}
