import { useRef } from "react";
import type { ClipboardEvent, KeyboardEvent } from "react";

const CODE_LENGTH = 6;

interface AccessCodeInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  masked: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
}

function sanitize(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export default function AccessCodeInput({
  value,
  onChange,
  masked,
  disabled = false,
  autoFocus = false,
}: AccessCodeInputProps) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const applyDigits = (start: number, digits: string) => {
    const next = [...value];
    digits.split("").forEach((char, offset) => {
      const index = start + offset;
      if (index < CODE_LENGTH) next[index] = char;
    });
    onChange(next);
    const lastFilled = Math.min(start + digits.length - 1, CODE_LENGTH - 1);
    refs.current[lastFilled]?.focus();
  };

  const handleChange = (index: number, raw: string) => {
    const clean = sanitize(raw);

    if (clean.length > 1) {
      applyDigits(index, clean.slice(0, CODE_LENGTH - index));
      return;
    }

    const next = [...value];
    next[index] = clean;
    onChange(next);

    if (clean && index < CODE_LENGTH - 1) {
      refs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Backspace") {
      event.preventDefault();
      const next = [...value];

      if (next[index]) {
        next[index] = "";
        onChange(next);
        return;
      }

      if (index > 0) {
        next[index - 1] = "";
        onChange(next);
        refs.current[index - 1]?.focus();
      }
      return;
    }

    if (event.key === "Delete") {
      event.preventDefault();
      const next = [...value];
      next[index] = "";
      onChange(next);
      return;
    }

    if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      refs.current[index - 1]?.focus();
    }

    if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) {
      event.preventDefault();
      refs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (
    index: number,
    event: ClipboardEvent<HTMLInputElement>
  ) => {
    event.preventDefault();
    const pasted = sanitize(event.clipboardData.getData("text"));
    if (!pasted) return;
    applyDigits(index, pasted.slice(0, CODE_LENGTH - index));
  };

  return (
    <div dir="ltr" className="grid grid-cols-6 gap-1.5 sm:gap-2">
      {value.map((digit, index) => (
        <input
          key={index}
          ref={(el) => {
            refs.current[index] = el;
          }}
          type={masked ? "password" : "text"}
          inputMode="text"
          pattern="[A-Za-z0-9]*"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          maxLength={1}
          value={digit}
          disabled={disabled}
          autoFocus={autoFocus && index === 0}
          aria-label={`Access code character ${index + 1}`}
          onChange={(event) =>
            handleChange(index, event.target.value.toUpperCase())
          }
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={(event) => handlePaste(index, event)}
          onFocus={(event) => event.currentTarget.select()}
          placeholder="•"
          className="auth-input h-11 w-full min-w-0 rounded-xl border border-white/10 bg-white/[0.03] px-0 text-center font-mono text-base font-bold text-white outline-none transition-all placeholder:text-zinc-700 hover:bg-white/[0.06] focus:-translate-y-0.5 focus:scale-105 focus:border-white focus:bg-black sm:h-12"
        />
      ))}
    </div>
  );
}
