import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, EyeOff, Loader2, Shield, User, KeyRound } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import AccessCodeInput from "../components/AccessCodeInput";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [otpDigits, setOtpDigits] = useState(["", "", "", "", "", ""]);
  const [showCode, setShowCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = username.trim()
    ? username.trim().charAt(0).toUpperCase() + username.trim().slice(1)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = otpDigits.join("");
    if (loading || code.length !== 6) return;
    setLoading(true);
    setError(null);
    try {
      await register(username.trim(), code);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ثبت‌نام");
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    username.trim().length >= 2 && otpDigits.join("").length === 6 && !loading;

  return (
    <div
      dir="rtl"
      className="relative flex min-h-[100dvh] w-full items-center justify-center overflow-hidden bg-black px-5 py-10 text-white"
      style={{ fontFamily: "'Vazirmatn', system-ui, sans-serif" }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-50"
        style={{
          backgroundSize: "52px 52px",
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.05) 1px, transparent 1px)",
          maskImage: "radial-gradient(circle at 50% 30%, black 10%, transparent 72%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 30%, black 10%, transparent 72%)",
        }}
      />
      <div className="pointer-events-none absolute -top-32 left-1/2 h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-white/[0.06] blur-[120px]" />

      <div className="relative z-10 w-full max-w-[430px]">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img
            src="/logo.png"
            alt="ArchSchool"
            width={64}
            height={64}
            className="h-16 w-16 rounded-2xl border border-white/20 object-cover shadow-[0_0_35px_-8px_rgba(255,255,255,0.6)]"
          />
          <div>
            <h1 className="text-2xl font-black text-white">ساخت حساب</h1>
            <p className="mt-1 text-xs text-zinc-500">با نام کاربری و کد دسترسی ۶ کاراکتری ثبت‌نام کن</p>
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-[#07070a]/95 p-6 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.95)] sm:p-8">
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label className="mono mb-2 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-zinc-300">
                <User className="h-3.5 w-3.5" />
                USERNAME
              </label>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="ali"
                autoComplete="username"
                dir="ltr"
                className="auth-input w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 font-mono text-sm text-white outline-none transition-all placeholder:text-zinc-600 hover:bg-white/[0.05] focus:border-white/60 focus:bg-black/80"
              />
              {preview && (
                <p className="mt-2 text-[11px] text-zinc-500">
                  نام نمایشی:{" "}
                  <span className="font-semibold text-white" dir="ltr">
                    {preview}
                  </span>
                </p>
              )}
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-2">
                <label className="mono flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-zinc-300">
                  <KeyRound className="h-3.5 w-3.5" />
                  ACCESS CODE
                </label>
                <button
                  type="button"
                  onClick={() => setShowCode((value) => !value)}
                  className="mono flex items-center gap-1 text-[11px] text-zinc-400 transition hover:text-white"
                >
                  {showCode ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  {showCode ? "HIDE" : "SHOW"}
                </button>
              </div>
              <AccessCodeInput
                value={otpDigits}
                onChange={setOtpDigits}
                masked={!showCode}
                disabled={loading}
              />
              <p className="mono mt-2 text-center text-[10px] text-zinc-500">
                فقط حروف انگلیسی بزرگ و اعداد، دقیقاً ۶ کاراکتر
              </p>
            </div>

            {error && (
              <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] text-red-300">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="auth-submit flex w-full items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 text-sm font-extrabold text-black shadow-[0_0_30px_-5px_rgba(255,255,255,0.6)] transition-all hover:bg-zinc-100 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
              ثبت‌نام و ورود
            </button>
          </form>

          <div className="mt-6 flex items-center justify-between border-t border-white/10 pt-4 text-[11px]">
            <Link to="/login" className="text-zinc-400 transition hover:text-white">
              حساب داری؟ ورود
            </Link>
            <span className="mono flex items-center gap-1.5 text-[10px] tracking-[0.16em] text-zinc-500">
              <Shield size={12} />
              SECURE
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

