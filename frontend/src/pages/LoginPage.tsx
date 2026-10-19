import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, KeyRound, BookOpen, Shield, ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function VercelWhiteLoginOTP() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [showCode, setShowCode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0, glareX: 50, glareY: 50, isHovering: false });

  const cardRef = useRef<HTMLDivElement>(null);
  const otpRefs = useRef<Array<HTMLInputElement | null>>([]);

  // 🎨 تم سفید خالص
  const config = {
    glowColor: '#ffffff',
    accentColor: '#ffffff',
    cardOpacity: 75,
    cardBlur: 24,
    borderRadius: 16,
    tiltIntensity: 14,
    show3DCore: true,
    coreShape: 'prism', // 'prism' | 'cube' | 'rings'
    coreSpeed: 12,
    borderBeam: true,
    spotlightCursor: true,
    badgeText: 'login to Homework Manager',
    title: 'Welcome',
    subtitle: 'یوزر نیم و کد لاگین که بهتون ارسال شده رو وارد کنید',
    userLabel: 'USERNAME',
    userPlaceholder: 'arsi_dev',
    codeLabel: 'ACCESS CODE',
    submitText: 'Login',
    footerNote: 'DEVELOPED BY SEPEHR',
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const rotateX = ((y - centerY) / centerY) * -config.tiltIntensity;
    const rotateY = ((x - centerX) / centerX) * config.tiltIntensity;
    const glareX = (x / rect.width) * 100;
    const glareY = (y / rect.height) * 100;

    setTilt({ x: rotateX, y: rotateY, glareX, glareY, isHovering: true });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0, glareX: 50, glareY: 50, isHovering: false });
  };

  // ✅ هندلر ۶ خانه کد
  const handleDigitChange = (index: number, val: string) => {
    const clean = val.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
    const next = [...otpDigits];
    next[index] = clean.slice(-1);
    setOtpDigits(next);

    if (clean && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
  };

  const handleDigitKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 6);
    if (!pasted) return;
    const next = ['', '', '', '', '', ''];
    pasted.split('').forEach((ch, i) => { next[i] = ch; });
    setOtpDigits(next);
    const lastIndex = Math.min(pasted.length, 5);
    otpRefs.current[lastIndex]?.focus();
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const code = otpDigits.join('');
    if (!username.trim() || code.length < 6 || loading) return;
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), code);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'خطا در ورود');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      dir="ltr"
      className="min-h-screen bg-black text-white flex items-center justify-center p-4 relative overflow-hidden"
      style={{ fontFamily: "'Vazirmatn', system-ui, sans-serif" }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap');
        .font-mono-tech { font-family: 'JetBrains Mono', monospace; }
        .preserve-3d { transform-style: preserve-3d; }

        @keyframes spin3D {
          0% { transform: rotateX(22deg) rotateY(0deg) rotateZ(0deg); }
          100% { transform: rotateX(22deg) rotateY(360deg) rotateZ(360deg); }
        }
        @keyframes spinReverse3D {
          0% { transform: rotateX(-35deg) rotateY(360deg); }
          100% { transform: rotateX(-35deg) rotateY(0deg); }
        }
        @keyframes floatPulse {
          0%, 100% { transform: translateY(0px) scale(1); }
          50% { transform: translateY(-8px) scale(1.04); }
        }
        @keyframes borderBeamSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }

        .cube-scene { width: 56px; height: 56px; perspective: 400px; }
        .cube-3d {
          width: 100%; height: 100%; position: relative;
          transform-style: preserve-3d;
          animation: spin3D ${config.coreSpeed}s linear infinite;
        }
        .cube-face {
          position: absolute; width: 56px; height: 56px;
          border: 1.5px solid #ffffff;
          background: rgba(255,255,255,0.08);
          box-shadow: 0 0 15px rgba(255,255,255,0.25), inset 0 0 10px rgba(255,255,255,0.15);
        }
        .face-front  { transform: rotateY(  0deg) translateZ(28px); }
        .face-right  { transform: rotateY( 90deg) translateZ(28px); }
        .face-back   { transform: rotateY(180deg) translateZ(28px); }
        .face-left   { transform: rotateY(-90deg) translateZ(28px); }
        .face-top    { transform: rotateX( 90deg) translateZ(28px); }
        .face-bottom { transform: rotateX(-90deg) translateZ(28px); }

        /* مخفی کردن فلش‌های input number */
        input[type=password]::-ms-reveal,
        input[type=password]::-ms-clear { display: none; }
      `}</style>

      {/* پس‌زمینه شبکه */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundSize: '48px 48px',
          backgroundImage: `
            linear-gradient(to right, rgba(255,255,255,0.055) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255,255,255,0.055) 1px, transparent 1px)
          `,
          maskImage: 'radial-gradient(circle at center, black 30%, transparent 80%)',
          WebkitMaskImage: 'radial-gradient(circle at center, black 30%, transparent 80%)',
        }}
      />

      {/* کف پرسپکتیو */}
      <div
        className="absolute inset-x-0 bottom-0 h-72 pointer-events-none opacity-30"
        style={{
          backgroundImage: `linear-gradient(to right, rgba(255,255,255,0.2) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.2) 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
          transform: 'perspective(450px) rotateX(68deg) translateY(80px) scale(1.4)',
          transformOrigin: 'bottom center',
          maskImage: 'linear-gradient(to top, rgba(0,0,0,1), transparent)',
          WebkitMaskImage: 'linear-gradient(to top, rgba(0,0,0,1), transparent)',
        }}
      />

      {/* هاله سفید */}
      <div className="w-[420px] h-[420px] rounded-full blur-[135px] opacity-25 absolute -top-24 pointer-events-none bg-white" />

      {/* کارت */}
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
          transition: tilt.isHovering ? 'transform 0.08s ease-out' : 'transform 0.55s cubic-bezier(0.22, 1, 0.36, 1)',
          borderRadius: `${config.borderRadius}px`,
          transformStyle: 'preserve-3d',
        }}
        className="preserve-3d relative z-10 w-full max-w-[430px] p-[1.5px] group"
      >
        {/* Border Beam سفید */}
        {config.borderBeam && (
          <div
            className="absolute inset-0 overflow-hidden pointer-events-none"
            style={{ borderRadius: `${config.borderRadius}px` }}
          >
            <div
              className="w-[200%] h-[200%] -top-1/2 -left-1/2 absolute opacity-70 group-hover:opacity-100 transition-opacity duration-500"
              style={{
                background: `conic-gradient(from 0deg, transparent 70%, #ffffff 88%, #ffffff 100%)`,
                animation: 'borderBeamSpin 6s linear infinite',
              }}
            />
          </div>
        )}

        {/* کارت شیشه‌ای */}
        <div
          style={{
            backgroundColor: `rgba(6, 6, 10, ${config.cardOpacity / 100})`,
            backdropFilter: `blur(${config.cardBlur}px)`,
            WebkitBackdropFilter: `blur(${config.cardBlur}px)`,
            borderRadius: `${Math.max(0, config.borderRadius - 1)}px`,
            boxShadow: `0 30px 60px -15px rgba(0,0,0,0.85), 0 0 40px -10px rgba(255,255,255,0.25)`,
          }}
          className="preserve-3d relative w-full p-7 sm:p-9 border border-white/10"
        >
          {/* Spotlight سفید */}
          {config.spotlightCursor && (
            <div
              className="pointer-events-none absolute inset-0 transition-opacity duration-300"
              style={{
                opacity: tilt.isHovering ? 1 : 0,
                borderRadius: `${Math.max(0, config.borderRadius - 1)}px`,
                background: `radial-gradient(380px circle at ${tilt.glareX}% ${tilt.glareY}%, rgba(255,255,255,0.12), transparent 65%)`,
              }}
            />
          )}

          {/* کراس‌هیرها */}
          <span className="absolute top-3 right-3 w-2 h-2 border-t border-r border-white/30 pointer-events-none" />
          <span className="absolute top-3 left-3 w-2 h-2 border-t border-l border-white/30 pointer-events-none" />
          <span className="absolute bottom-3 right-3 w-2 h-2 border-b border-r border-white/30 pointer-events-none" />
          <span className="absolute bottom-3 left-3 w-2 h-2 border-b border-l border-white/30 pointer-events-none" />

          {/* ===== هولوگرام ===== */}
          {config.show3DCore && (
            <div className="flex justify-center mb-6" style={{ transform: 'translateZ(50px)' }}>
              {config.coreShape === 'prism' && (
                <div
                  className="relative w-16 h-16 flex items-center justify-center"
                  style={{ animation: 'floatPulse 4s ease-in-out infinite' }}
                >
                  <div className="absolute inset-0 rounded-full blur-xl opacity-60 bg-white" />
                  <div className="relative w-14 h-14 rounded-2xl bg-gradient-to-b from-white/20 to-white/[0.03] border border-white/40 flex items-center justify-center shadow-2xl backdrop-blur-md">
                    <BookOpen className="w-7 h-7 text-white drop-shadow-[0_0_12px_rgba(255,255,255,0.9)]" />
                  </div>
                </div>
              )}

              {config.coreShape === 'cube' && (
                <div className="cube-scene my-1">
                  <div className="cube-3d">
                    <div className="cube-face face-front" />
                    <div className="cube-face face-back" />
                    <div className="cube-face face-right" />
                    <div className="cube-face face-left" />
                    <div className="cube-face face-top" />
                    <div className="cube-face face-bottom" />
                  </div>
                </div>
              )}

              {config.coreShape === 'rings' && (
                <div className="relative w-16 h-16 flex items-center justify-center preserve-3d">
                  <div
                    className="w-16 h-16 rounded-full border-2 border-dashed absolute border-white"
                    style={{ animation: `spin3D ${config.coreSpeed}s linear infinite` }}
                  />
                  <div
                    className="w-11 h-11 rounded-full border border-white/80 absolute"
                    style={{ animation: `spinReverse3D ${Math.max(4, config.coreSpeed - 4)}s linear infinite` }}
                  />
                  <div className="w-3 h-3 rounded-full bg-white shadow-[0_0_15px_#fff]" />
                </div>
              )}
            </div>
          )}

          {/* ===== هدر ===== */}
          <div className="text-center mb-7 relative" style={{ transform: 'translateZ(35px)' }}>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] border border-white/10 text-[10px] font-mono-tech tracking-widest text-zinc-300 mb-3">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse bg-white" />
              <span>{config.badgeText}</span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-black tracking-tight bg-gradient-to-b from-white via-white to-zinc-400 bg-clip-text text-transparent">
              {config.title}
            </h1>

            <p className="text-xs text-zinc-400 mt-2 leading-relaxed">{config.subtitle}</p>
          </div>

          {/* ===== فرم ===== */}
          <form className="space-y-5 relative" style={{ transform: 'translateZ(25px)' }} onSubmit={handleSubmit}>
            {/* Username */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-mono-tech font-semibold tracking-wider text-zinc-300 uppercase flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-white" />
                  <span>{config.userLabel}</span>
                </label>
                <span className="text-[10px] font-mono-tech text-zinc-500">ID // REQUIRED</span>
              </div>

              <div className="relative">
                <input
                  type="text"
                  dir="ltr"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={config.userPlaceholder}
                  className="w-full px-4 py-3 rounded-xl bg-white/[0.03] hover:bg-white/[0.05] focus:bg-black/80 border border-white/10 focus:border-white/60 text-white font-mono-tech text-sm outline-none transition-all placeholder:text-zinc-600"
                  style={{
                    boxShadow: username ? `0 0 20px -8px #ffffff` : 'none',
                  }}
                />
                <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs font-mono-tech text-zinc-500 pointer-events-none">
                  @
                </span>
              </div>
            </div>

            {/* ✅ Access Code - 6 خانه مجزا */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-mono-tech font-semibold tracking-wider text-zinc-300 uppercase flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-white" />
                  <span>{config.codeLabel}</span>
                </label>

                <button
                  type="button"
                  onClick={() => setShowCode(!showCode)}
                  className="text-[11px] font-mono-tech text-zinc-400 hover:text-white flex items-center gap-1 cursor-pointer transition"
                >
                  {showCode ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                  <span>{showCode ? 'HIDE' : 'SHOW'}</span>
                </button>
              </div>

              <div dir="ltr" className="grid grid-cols-6 gap-2" onPaste={handlePaste}>
                {otpDigits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => { otpRefs.current[idx] = el; }}
                    type={showCode ? 'text' : 'password'}
                    inputMode="text"
                    autoComplete="one-time-code"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleDigitChange(idx, e.target.value)}
                    onKeyDown={(e) => handleDigitKeyDown(idx, e)}
                    placeholder="•"
                    className="h-12 text-center font-mono-tech text-base font-bold rounded-xl bg-white/[0.03] hover:bg-white/[0.06] focus:bg-black border border-white/10 focus:border-white text-white outline-none transition-all focus:scale-105 focus:-translate-y-0.5 placeholder:text-zinc-700"
                    style={{
                      borderColor: digit ? 'rgba(255,255,255,0.55)' : undefined,
                      boxShadow: digit ? '0 0 15px -4px rgba(255,255,255,0.5)' : 'none',
                    }}
                  />
                ))}
              </div>

              <p className="text-[10px] font-mono-tech text-zinc-500 mt-2 text-center">
                در صورت داشتن کد کامل، آن را Paste کنید
              </p>
            </div>

            {/* خطا */}
            {error && (
              <p
                dir="rtl"
                className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] text-red-300"
              >
                {error}
              </p>
            )}

            {/* دکمه */}
            <div className="pt-2" style={{ transform: 'translateZ(15px)' }}>
              <button
                type="submit"
                disabled={loading || username.trim().length === 0 || otpDigits.join('').length < 6}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#000000',
                  boxShadow: `0 0 30px -5px rgba(255,255,255,0.6)`,
                }}
                className="w-full py-3.5 px-6 rounded-xl font-extrabold text-xs sm:text-sm transition-all transform active:scale-[0.98] hover:bg-zinc-100 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>...</span>
                  </>
                ) : (
                  <>
                    <span>{config.submitText}</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </form>

          {/* فوتر */}
          <div
            dir="ltr"
            className="mt-7 pt-4 border-t border-white/10 flex items-center justify-center text-[10px] text-zinc-500 font-mono-tech tracking-wider uppercase"
            style={{ transform: 'translateZ(20px)' }}
          >
            <span className="flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-white shrink-0" />
              <span className="text-zinc-400">{config.footerNote}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}