import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { User, KeyRound, Shield, ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import AccessCodeInput from "../components/AccessCodeInput";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [otpDigits, setOtpDigits] = useState(["", "", "", "", "", ""]);
  const [showCode, setShowCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const previous = {
      overflow: document.body.style.overflow,
      margin: document.body.style.margin,
      height: document.body.style.height,
      width: document.body.style.width,
    };
    document.body.style.overflow = "hidden";
    document.body.style.margin = "0";
    document.body.style.height = "100dvh";
    document.body.style.width = "100%";
    return () => {
      document.body.style.overflow = previous.overflow;
      document.body.style.margin = previous.margin;
      document.body.style.height = previous.height;
      document.body.style.width = previous.width;
    };
  }, []);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const code = otpDigits.join("");
    if (!username.trim() || code.length !== 6 || loading) return;
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), code);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ورود");
    } finally {
      setLoading(false);
    }
  };

  const canSubmit =
    !loading && username.trim().length > 0 && otpDigits.join("").length === 6;

  return (
    <div
      dir="ltr"
      className="relative flex h-[100dvh] w-full max-w-full overflow-hidden bg-black text-white"
      style={{ fontFamily: "'Vazirmatn', system-ui, sans-serif" }}
    >
      <style>{`
        @keyframes loginDrift {
          0%, 100% { transform: translate3d(0, 0, 0); }
          50% { transform: translate3d(0, -14px, 0); }
        }
        .login-drift { animation: loginDrift 7s ease-in-out infinite; }
        .login-drift-slow { animation: loginDrift 11s ease-in-out infinite; }
      `}</style>

      {/* ===== برندینگ دسکتاپ ===== */}
      <aside className="relative hidden h-full w-[54%] shrink-0 flex-col justify-between overflow-hidden border-r border-white/10 bg-[#050507] p-10 md:flex lg:w-[56%] lg:p-14">
        {/* شبکه */}
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundSize: "52px 52px",
            backgroundImage: `
              linear-gradient(to right, rgba(255,255,255,0.055) 1px, transparent 1px),
              linear-gradient(to bottom, rgba(255,255,255,0.055) 1px, transparent 1px)
            `,
            maskImage: "radial-gradient(circle at 30% 30%, black 10%, transparent 72%)",
            WebkitMaskImage: "radial-gradient(circle at 30% 30%, black 10%, transparent 72%)",
          }}
        />

        {/* هاله‌ها */}
        <div className="pointer-events-none absolute -top-32 -left-24 h-[420px] w-[420px] rounded-full bg-white/[0.06] blur-[120px]" />
        <div className="pointer-events-none absolute right-[-10%] bottom-[-15%] h-[380px] w-[380px] rounded-full bg-white/[0.04] blur-[110px]" />

        {/* ذرات تزئینی */}
        <div className="pointer-events-none absolute inset-0">
          {[
            { top: "18%", left: "22%", size: 5, delay: "0s" },
            { top: "32%", left: "68%", size: 3, delay: "1.2s" },
            { top: "58%", left: "38%", size: 4, delay: "2.4s" },
            { top: "72%", left: "78%", size: 3, delay: "0.8s" },
            { top: "44%", left: "12%", size: 3, delay: "3.1s" },
            { top: "84%", left: "50%", size: 4, delay: "1.8s" },
          ].map((dot) => (
            <span
              key={`${dot.top}-${dot.left}`}
              className="login-drift absolute rounded-full bg-white/70 shadow-[0_0_12px_rgba(255,255,255,0.8)]"
              style={{
                top: dot.top,
                left: dot.left,
                width: dot.size,
                height: dot.size,
                animationDelay: dot.delay,
              }}
            />
          ))}
        </div>

        <div className="relative z-10 flex items-center gap-3">
          <img
            src="/logo.png"
            alt="ArchSchool"
            width={52}
            height={52}
            className="h-13 w-13 rounded-2xl border border-white/20 object-cover shadow-[0_0_35px_-8px_rgba(255,255,255,0.65)]"
          />
          <div dir="rtl">
            <p className="text-sm font-bold text-white">ArchSchool</p>
            <p className="mono text-[10px] tracking-[0.25em] text-zinc-500">ARCHSCHOOL</p>
          </div>
        </div>

        <div dir="rtl" className="relative z-10 max-w-xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/[0.04] px-3 py-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white shadow-[0_0_8px_#fff]" />
            <span className="mono text-[10px] tracking-[0.2em] text-zinc-300">
              SMART SCHOOL WORKSPACE
            </span>
          </div>

          <h1 className="mt-6 text-4xl font-black leading-[1.35] tracking-tight lg:text-5xl">
            تکالیفت رو
            <span className="block text-zinc-400">منظم نگه دار.</span>
          </h1>

          <p className="mt-5 max-w-md text-sm leading-7 text-zinc-400">
            همه تکالیف، امتحان‌ها و برنامه هفتگی کلاس در یک‌جا. سریع ببین چه کاری مانده و همیشه
            یک قدم جلوتر باش.
          </p>

          <div className="mt-9 grid max-w-md grid-cols-2 gap-3">
            <div className="login-drift-slow rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <p className="text-2xl font-black text-white">01</p>
              <p className="mt-1 text-xs text-zinc-400">برنامه هفتگی یکجا</p>
            </div>
            <div className="login-drift rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <p className="text-2xl font-black text-white">02</p>
              <p className="mt-1 text-xs text-zinc-400">یادآوری مهلت‌ها</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-zinc-500">
          <Shield size={14} />
          <span className="mono text-[10px] tracking-[0.18em]">DEVELOPED BY SEPEHR</span>
        </div>
      </aside>

      {/* ===== فرم ===== */}
      <main className="relative flex h-full w-full min-w-0 flex-1 items-start justify-center overflow-x-hidden overflow-y-auto px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[max(1.5rem,env(safe-area-inset-bottom))] sm:px-8 md:px-10 lg:px-14">
        <div
          className="pointer-events-none absolute inset-0 hidden md:block"
          style={{
            background:
              "radial-gradient(circle at 50% 0%, rgba(255,255,255,0.06), transparent 60%)",
          }}
        />

        <div className="relative z-10 my-auto w-full min-w-0 max-w-[430px]">
          {/* لوگو و عنوان موبایل */}
          <div className="mb-6 flex flex-col items-center gap-3 text-center md:hidden">
            <img
              src="/logo.png"
              alt="ArchSchool"
              width={64}
              height={64}
              className="h-16 w-16 rounded-2xl border border-white/20 object-cover shadow-[0_0_35px_-8px_rgba(255,255,255,0.6)]"
            />
            <div dir="rtl">
              <h1 className="text-xl font-black text-white">ArchSchool</h1>
              <p className="mt-1 text-xs text-zinc-500">برای ادامه وارد شو</p>
            </div>
          </div>

          <div className="w-full min-w-0 rounded-3xl border border-white/10 bg-[#07070a]/95 p-4 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.95)] sm:p-5 md:p-9">
            <div className="mb-7">
              <div className="mb-4 hidden items-center gap-2.5 md:flex">
                <img
                  src="/logo.png"
                  alt="ArchSchool"
                  width={36}
                  height={36}
                  className="h-9 w-9 rounded-xl border border-white/15 object-cover"
                />
                <span className="mono text-[10px] tracking-[0.2em] text-zinc-400">
                  ARCHSCHOOL
                </span>
              </div>

              <h2 className="text-2xl font-black tracking-tight text-white sm:text-3xl">Welcome</h2>
              <p dir="rtl" className="mt-2 text-xs leading-6 text-zinc-400">
                با نام کاربری و کد دسترسی ۶ کاراکتری وارد شو.
              </p>
            </div>

            <form className="min-w-0 space-y-5" onSubmit={handleSubmit}>
              {/* نام کاربری */}
              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                  <label className="mono flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-zinc-300">
                    <User className="h-3.5 w-3.5 shrink-0 text-white" />
                    <span>USERNAME</span>
                  </label>
                  <span className="mono shrink-0 text-[10px] text-zinc-500">ID // REQUIRED</span>
                </div>

                <div className="relative min-w-0">
                  <input
                    type="text"
                    dir="ltr"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="arsi_dev"
                    autoComplete="username"
                    className="auth-input w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 font-mono text-sm text-white outline-none transition-all placeholder:text-zinc-600 hover:bg-white/[0.05] focus:border-white/60 focus:bg-black/80"
                  />
                  <span className="mono pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-zinc-500">
                    @
                  </span>
                </div>
              </div>

              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                  <label className="mono flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-zinc-300">
                    <KeyRound className="h-3.5 w-3.5 shrink-0 text-white" />
                    <span>ACCESS CODE</span>
                  </label>

                  <button
                    type="button"
                    onClick={() => setShowCode(!showCode)}
                    className="mono flex shrink-0 items-center gap-1 text-[11px] text-zinc-400 transition hover:text-white"
                  >
                    {showCode ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                    <span>{showCode ? "HIDE" : "SHOW"}</span>
                  </button>
                </div>

                <AccessCodeInput
                  value={otpDigits}
                  onChange={setOtpDigits}
                  masked={!showCode}
                  disabled={loading}
                />

                <p className="mono mt-2 break-words text-center text-[10px] text-zinc-500" dir="rtl">
                  در صورت داشتن کد کامل، آن را Paste کنید
                </p>
              </div>

              {error && (
                <p
                  dir="rtl"
                  className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] break-words text-red-300"
                >
                  {error}
                </p>
              )}

              <div className="pt-1">
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className="auth-submit flex w-full min-w-0 cursor-pointer items-center justify-center gap-2 rounded-xl bg-white px-6 py-3.5 text-xs font-extrabold text-black shadow-[0_0_30px_-5px_rgba(255,255,255,0.6)] transition-all hover:bg-zinc-100 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>...</span>
                    </>
                  ) : (
                    <>
                      <span>Login</span>
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </form>

            <Link
              to="/register"
              dir="rtl"
              className="mt-5 flex min-w-0 flex-wrap items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-center text-[12px] font-semibold text-zinc-300 transition hover:border-white/30 hover:text-white"
            >
              حساب نداری؟ <span className="text-white underline decoration-white/40">ثبت‌نام کن</span>
            </Link>

            <div
              dir="ltr"
              className="mono mt-7 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 border-t border-white/10 pt-4 text-[10px] tracking-[0.18em] break-words text-zinc-500"
            >
              <span className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 shrink-0 text-white" />
                <span className="text-zinc-400">DEVELOPED BY SEPEHR</span>
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

