import { useEffect, useState } from "react";
import {
  Bot,
  Sparkles,
  Save,
  RotateCcw,
  Check,
  Loader2,
  Copy,
  RefreshCw,
  Sliders,
  Send,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Corners from "../components/Corners";
import {
  getBotSettings,
  updateBotSettings,
  resetBotPrompts,
  fetchBotAvailableModels,
  testBotIntegration,
  type BotSettings,
  type ModelItem,
} from "../api/client";

const PROVIDER_PRESETS: { id: string; name: string; baseUrl: string; defaultModel: string }[] = [
  {
    id: "openrouter",
    name: "OpenRouter (پیش‌فرض پیشنهادی)",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "openai/gpt-4o-mini",
  },
  {
    id: "gemini",
    name: "Google Gemini (رایگان و سریع)",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    defaultModel: "gemini-3.1-flash-lite",
  },
  {
    id: "groq",
    name: "Groq (سرعت پاسخ زیر نیم‌ثانیه)",
    baseUrl: "https://api.groq.com/openai/v1",
    defaultModel: "openai/gpt-oss-120b",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    defaultModel: "deepseek-chat",
  },
  {
    id: "xai",
    name: "xAI (Grok)",
    baseUrl: "https://api.x.ai/v1",
    defaultModel: "grok-2",
  },
  {
    id: "openai",
    name: "OpenAI Official",
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4o-mini",
  },
];

export default function BotSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [activeTab, setActiveTab] = useState<"prompt" | "ai" | "telegram">("prompt");

  // Form State
  const [systemPrompt, setSystemPrompt] = useState("");
  const [personaAnchor, setPersonaAnchor] = useState("");
  const [followupAnchor, setFollowupAnchor] = useState("");
  const [temperature, setTemperature] = useState(0.85);
  const [maxTokens, setMaxTokens] = useState(600);

  const [aiProvider, setAiProvider] = useState("openrouter");
  const [aiApiKey, setAiApiKey] = useState("");
  const [aiBaseUrl, setAiBaseUrl] = useState("");
  const [aiModel, setAiModel] = useState("");

  const [botToken, setBotToken] = useState("");
  const [groupId, setGroupId] = useState("");
  const [botEnabled, setBotEnabled] = useState(true);

  // Live model fetching
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  // Testing
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data: BotSettings = await getBotSettings();
      setSystemPrompt(data.ai_system_prompt || "");
      setPersonaAnchor(data.ai_persona_anchor || "");
      setFollowupAnchor(data.ai_followup_anchor || "");
      setTemperature(data.ai_temperature ?? 0.85);
      setMaxTokens(data.ai_max_tokens ?? 600);

      setAiProvider(data.ai_provider || "openrouter");
      setAiApiKey(data.ai_api_key || "");
      setAiBaseUrl(data.ai_base_url || "");
      setAiModel(data.ai_model || "");

      setBotToken(data.bot_token || "");
      setGroupId(data.group_id || "");
      setBotEnabled(data.bot_enabled ?? true);
    } catch (err: any) {
      setErrorMsg(err.message || "خطا در دریافت تنظیمات");
    } finally {
      setLoading(false);
    }
  }

  function handleProviderSelect(pId: string) {
    setAiProvider(pId);
    const preset = PROVIDER_PRESETS.find((p) => p.id === pId);
    if (preset) {
      setAiBaseUrl(preset.baseUrl);
      if (!aiModel || PROVIDER_PRESETS.some((p) => p.defaultModel === aiModel)) {
        setAiModel(preset.defaultModel);
      }
    }
  }

  async function handleSave() {
    setSaving(true);
    setErrorMsg(null);
    try {
      await updateBotSettings({
        ai_system_prompt: systemPrompt,
        ai_persona_anchor: personaAnchor,
        ai_followup_anchor: followupAnchor,
        ai_temperature: Number(temperature),
        ai_max_tokens: Number(maxTokens),
        ai_provider: aiProvider,
        ai_api_key: aiApiKey,
        ai_base_url: aiBaseUrl,
        ai_model: aiModel,
        bot_token: botToken,
        group_id: groupId,
        bot_enabled: botEnabled,
      });
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2500);
    } catch (err: any) {
      setErrorMsg(err.message || "خطا در ذخیره تنظیمات");
    } finally {
      setSaving(false);
    }
  }

  async function handleResetPrompt() {
    if (!window.confirm("آیا از بازنشانی پرامپت‌ها و لنگرها به تنظیمات اولیه اطمینان دارید؟")) {
      return;
    }
    setResetting(true);
    setErrorMsg(null);
    try {
      const res = await resetBotPrompts();
      setSystemPrompt(res.settings.ai_system_prompt);
      setPersonaAnchor(res.settings.ai_persona_anchor);
      setFollowupAnchor(res.settings.ai_followup_anchor);
      setTemperature(res.settings.ai_temperature);
      setMaxTokens(res.settings.ai_max_tokens);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2500);
    } catch (err: any) {
      setErrorMsg(err.message || "خطا در بازنشانی پرامپت");
    } finally {
      setResetting(false);
    }
  }

  async function handleFetchModels() {
    if (!aiApiKey.trim()) {
      setErrorMsg("ابتدا کلید API را وارد کنید تا لیست مدل‌ها استعلام شود.");
      return;
    }
    setFetchingModels(true);
    setErrorMsg(null);
    try {
      const res = await fetchBotAvailableModels(aiProvider, aiApiKey, aiBaseUrl);
      setAvailableModels(res.models || []);
      if (res.models && res.models.length > 0 && !aiModel) {
        setAiModel(res.models[0].id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "خطا در استعلام لیست مدل‌ها");
    } finally {
      setFetchingModels(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setErrorMsg(null);
    setTestResult(null);
    try {
      const res = await testBotIntegration("پیام تستی پنل ادمین ArchSchool");
      setTestResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || "خطا در اجرای تست ربات و هوش مصنوعی");
    } finally {
      setTesting(false);
    }
  }

  function handleCopyPrompt() {
    navigator.clipboard.writeText(systemPrompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="animate-spin text-fg-500" size={32} />
      </div>
    );
  }

  return (
    <div className="max-w-4xl pb-16">
      <PageHeader
        kicker="ADMIN / AI & BOT"
        title="هوش مصنوعی و ربات تلگرام"
        subtitle="مدیریت زنده پرامپت، شخصیت و لحن مدل، تنظیمات API و یکپارچه‌سازی تلگرام"
      />

      {/* Tabs */}
      <div className="mb-6 flex flex-wrap gap-2 border-b border-white/10 pb-3">
        <button
          onClick={() => setActiveTab("prompt")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
            activeTab === "prompt"
              ? "border border-white/20 bg-white/10 text-white shadow-[0_0_20px_-8px_rgba(255,255,255,0.5)]"
              : "text-fg-500 hover:bg-white/5 hover:text-white"
          }`}
        >
          <Sparkles size={15} />
          سیستم پرامپت و لحن
        </button>

        <button
          onClick={() => setActiveTab("ai")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
            activeTab === "ai"
              ? "border border-white/20 bg-white/10 text-white shadow-[0_0_20px_-8px_rgba(255,255,255,0.5)]"
              : "text-fg-500 hover:bg-white/5 hover:text-white"
          }`}
        >
          <Sliders size={15} />
          مدل و ارائه‌دهنده (API)
        </button>

        <button
          onClick={() => setActiveTab("telegram")}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
            activeTab === "telegram"
              ? "border border-white/20 bg-white/10 text-white shadow-[0_0_20px_-8px_rgba(255,255,255,0.5)]"
              : "text-fg-500 hover:bg-white/5 hover:text-white"
          }`}
        >
          <Bot size={15} />
          ربات تلگرام
        </button>
      </div>

      {/* Error alert */}
      {errorMsg && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4 text-xs text-danger">
          <AlertCircle size={18} className="shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Success alert */}
      {savedSuccess && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-success/30 bg-success/10 p-4 text-xs text-success">
          <CheckCircle2 size={18} className="shrink-0" />
          <span>تنظیمات و پرامپت‌ها با موفقیت ذخیره و در حافظه سیستم بروزرسانی شدند!</span>
        </div>
      )}

      {/* TAB 1: SYSTEM PROMPT & PERSONA */}
      {activeTab === "prompt" && (
        <div className="space-y-6">
          <div className="panel relative p-4 sm:p-6">
            <Corners />
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-bold text-white">
                  <Sparkles size={16} className="text-primary" />
                  پرامپت دستور سیستمی اصلی (System Instruction)
                </h3>
                <p className="mt-1 text-xs text-fg-500">
                  تعریف نقش، دستورالعمل سیستمی، قوانین پاسخگویی و سبک تعامل مدل هوش مصنوعی.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopyPrompt}
                  className="btn-ghost flex h-8 items-center gap-1.5 px-3 text-[11px]"
                  title="کپی پرامپت"
                >
                  {copied ? <Check size={13} className="text-success" /> : <Copy size={13} />}
                  {copied ? "کپی شد" : "کپی"}
                </button>
                <button
                  type="button"
                  onClick={handleResetPrompt}
                  disabled={resetting}
                  className="btn-ghost flex h-8 items-center gap-1.5 border-danger/30 px-3 text-[11px] text-danger hover:bg-danger/10"
                  title="بازنشانی پرامپت‌ها به حالت پیش‌فرض"
                >
                  <RotateCcw size={13} className={resetting ? "animate-spin" : ""} />
                  بازنشانی به پیش‌فرض
                </button>
              </div>
            </div>

            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={18}
              dir="rtl"
              className="input w-full resize-y font-mono text-[13px] leading-relaxed tracking-wide text-fg-100"
              placeholder="دستورالعمل سیستمی، قوانین پاسخگویی و نقش هوش مصنوعی را در این بخش بنویسید (در صورت خالی بودن، مدل با رفتار استاندارد خود عمل می‌کند)..."
            />
            <div className="mt-2 flex justify-between text-[11px] text-fg-500">
              <span>تعداد کاراکتر: {systemPrompt.length.toLocaleString("fa-IR")}</span>
              <span>تغییرات بلافاصله پس از ذخیره روی پاسخ‌های مدل اعمال می‌شود.</span>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* Persona Anchor */}
            <div className="panel relative p-4 sm:p-6">
              <Corners />
              <h3 className="mb-1 text-xs font-bold text-white">
                لنگر پیوستگی لحن و رفتار (Persona Anchor)
              </h3>
              <p className="mb-3 text-[11px] text-fg-500">
                این پیام سیستمی پیش از آخرین پیام کاربر جهت هدایت مدل و حفظ پیوستگی لحن تزریق می‌شود (اختیاری).
              </p>
              <textarea
                value={personaAnchor}
                onChange={(e) => setPersonaAnchor(e.target.value)}
                rows={5}
                dir="rtl"
                className="input w-full resize-y text-xs leading-relaxed text-fg-100"
                placeholder="دستور لنگر لحن و رفتار..."
              />
            </div>

            {/* Follow-up Anchor */}
            <div className="panel relative p-4 sm:p-6">
              <Corners />
              <h3 className="mb-1 text-xs font-bold text-white">
                یادآوری پس از فراخوانی ابزارها (Follow-up Anchor)
              </h3>
              <p className="mb-3 text-[11px] text-fg-500">
                این پیام پس از اجرای ابزارها (مانند دریافت تکالیف یا برنامه) جهت قالب‌بندی و ارائه مناسب اطلاعات اعمال می‌شود (اختیاری).
              </p>
              <textarea
                value={followupAnchor}
                onChange={(e) => setFollowupAnchor(e.target.value)}
                rows={5}
                dir="rtl"
                className="input w-full resize-y text-xs leading-relaxed text-fg-100"
                placeholder="دستور نحوه گزارش و قالب‌بندی داده‌های ابزار..."
              />
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: AI ENGINE & MODEL */}
      {activeTab === "ai" && (
        <div className="space-y-6">
          <div className="panel relative p-4 sm:p-6">
            <Corners />
            <h3 className="mb-4 text-sm font-bold text-white">انتخاب و پیکربندی ارائه‌دهنده (AI Provider)</h3>
            
            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {PROVIDER_PRESETS.map((p) => {
                const isSelected = aiProvider === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleProviderSelect(p.id)}
                    className={`flex flex-col items-start rounded-xl p-3 text-right transition ${
                      isSelected
                        ? "border border-white/30 bg-white/10 text-white shadow-lg"
                        : "border border-white/5 bg-white/[0.02] text-fg-500 hover:border-white/15 hover:text-white"
                    }`}
                  >
                    <span className="text-xs font-bold">{p.name}</span>
                    <span className="mono mt-1 text-[10px] opacity-70" dir="ltr">
                      {p.defaultModel}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="space-y-4">
              {/* API Key */}
              <div>
                <label className="mono-label mb-1.5 flex items-center justify-between">
                  <span>AI API KEY</span>
                  <span className="text-[10px] text-fg-500">کلید دسترسی به موتور هوش مصنوعی</span>
                </label>
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    value={aiApiKey}
                    onChange={(e) => setAiApiKey(e.target.value)}
                    dir="ltr"
                    className="input w-full pl-10 font-mono text-xs"
                    placeholder="sk-or-v1-..."
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-500 hover:text-white"
                  >
                    {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* Base URL */}
              <div>
                <label className="mono-label mb-1.5 flex items-center justify-between">
                  <span>BASE URL</span>
                  <span className="text-[10px] text-fg-500">آدرس اندپوینت OpenAI-compatible</span>
                </label>
                <input
                  type="text"
                  value={aiBaseUrl}
                  onChange={(e) => setAiBaseUrl(e.target.value)}
                  dir="ltr"
                  className="input w-full font-mono text-xs"
                  placeholder="https://openrouter.ai/api/v1"
                />
              </div>

              {/* Model Name */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="mono-label">MODEL NAME</label>
                  <button
                    type="button"
                    onClick={handleFetchModels}
                    disabled={fetchingModels || !aiApiKey.trim()}
                    className="flex items-center gap-1 text-[11px] text-primary hover:underline disabled:opacity-50"
                  >
                    <RefreshCw size={12} className={fetchingModels ? "animate-spin" : ""} />
                    دریافت لیست زنده مدل‌ها از ارائه‌دهنده
                  </button>
                </div>
                <input
                  type="text"
                  value={aiModel}
                  onChange={(e) => setAiModel(e.target.value)}
                  dir="ltr"
                  className="input w-full font-mono text-xs"
                  placeholder="openai/gpt-4o-mini"
                />

                {availableModels.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-[10px] text-fg-500">مدل‌های قابل انتخاب از اکانت شما:</p>
                    <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-white/5 bg-black/40 p-2">
                      {availableModels.map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => setAiModel(m.id)}
                          className={`rounded px-2 py-0.5 text-[10px] font-mono transition ${
                            aiModel === m.id ? "bg-white text-black font-bold" : "bg-white/5 text-fg-400 hover:bg-white/10 hover:text-white"
                          }`}
                        >
                          {m.id}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Hyperparameters */}
          <div className="panel relative p-4 sm:p-6">
            <Corners />
            <h3 className="mb-4 text-sm font-bold text-white">پارامترهای تولید پاسخ (Hyperparameters)</h3>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="mono-label">TEMPERATURE</label>
                  <span className="mono text-xs font-bold text-white">{temperature}</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.5"
                  step="0.05"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full accent-white"
                />
                <p className="mt-1 text-[10px] text-fg-500">
                  مقدار پیش‌فرض 0.7 تعادل مناسبی بین دقت و تنوع پاسخ‌ها ایجاد می‌کند.
                </p>
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="mono-label">MAX TOKENS</label>
                  <span className="mono text-xs font-bold text-white">{maxTokens}</span>
                </div>
                <input
                  type="number"
                  min={100}
                  max={4000}
                  step={50}
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(parseInt(e.target.value) || 600)}
                  className="input w-full font-mono text-xs"
                />
                <p className="mt-1 text-[10px] text-fg-500">سقف طول پاسخ به توکن (پیش‌فرض: ۶۰۰)</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: TELEGRAM INTEGRATION */}
      {activeTab === "telegram" && (
        <div className="space-y-6">
          <div className="panel relative p-4 sm:p-6">
            <Corners />
            <h3 className="mb-4 text-sm font-bold text-white">اتصال ربات تلگرام به مدرسه</h3>

            <div className="space-y-4">
              <div>
                <label className="mono-label mb-1.5 block">TELEGRAM BOT TOKEN</label>
                <input
                  type="text"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                  dir="ltr"
                  className="input w-full font-mono text-xs"
                  placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ..."
                />
                <p className="mt-1 text-[10px] text-fg-500">توکن ارائه‌شده توسط @BotFather در تلگرام</p>
              </div>

              <div>
                <label className="mono-label mb-1.5 block">GROUP CHAT ID (شناسه گروه)</label>
                <input
                  type="text"
                  value={groupId}
                  onChange={(e) => setGroupId(e.target.value)}
                  dir="ltr"
                  className="input w-full font-mono text-xs"
                  placeholder="-1001234567890"
                />
                <p className="mt-1 text-[10px] text-fg-500">
                  شناسه گروه مدرسه برای ارسال اتوماتیک تکالیف جدید و تبریک رتبه یک
                </p>
              </div>

              <div className="flex items-center justify-between pt-2">
                <div>
                  <span className="text-xs font-bold text-white">فعال بودن ربات تلگرام</span>
                  <p className="text-[10px] text-fg-500">در صورت خاموش بودن، وب‌هوک به پیام‌ها پاسخ نمی‌دهد.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setBotEnabled(!botEnabled)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                    botEnabled ? "bg-white" : "bg-white/20"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-black shadow ring-0 transition duration-200 ease-in-out ${
                      botEnabled ? "-translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Test Box */}
          <div className="panel relative p-4 sm:p-6">
            <Corners />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-white">تست زنده اتصال ربات و هوش مصنوعی</h3>
                <p className="mt-1 text-xs text-fg-500">
                  یک پیام تستی به ارائه‌دهنده هوش مصنوعی و گروه تلگرام ارسال و صحت عملکرد بررسی می‌شود.
                </p>
              </div>
              <button
                type="button"
                onClick={handleTest}
                disabled={testing}
                className="btn-ghost flex items-center gap-2 border-white/20 px-4 text-xs font-bold text-white hover:bg-white hover:text-black"
              >
                {testing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                شروع تست اتصال
              </button>
            </div>

            {testResult && (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-xs">
                <div className="mb-2 flex items-center gap-2 text-success">
                  <CheckCircle2 size={16} />
                  <span className="font-bold">تست با موفقیت انجام شد:</span>
                </div>
                <div className="space-y-1 font-mono text-[11px] text-fg-300" dir="ltr">
                  <div>Bot Identity: @{testResult?.identity?.username} (ID: {testResult?.identity?.id})</div>
                  <div>AI Status: {testResult?.ai_status}</div>
                  <div>Group Sent: {testResult?.group_sent ? "Yes" : "No / Skipped"}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Floating Save Action Bar */}
      <div className="sticky bottom-6 mt-8 flex items-center justify-between rounded-2xl border border-white/20 bg-black/80 p-4 backdrop-blur-xl shadow-[0_10px_40px_rgba(0,0,0,0.8)]">
        <div className="flex items-center gap-2 text-xs text-fg-500">
          <ShieldCheck size={16} className="text-white" />
          <span>تغییرات فوراً در حافظه بلادرنگ ربات تلگرام ذخیره می‌شوند.</span>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="btn flex items-center gap-2 rounded-xl bg-white px-6 py-2.5 text-xs font-bold text-black shadow-[0_0_20px_rgba(255,255,255,0.4)] transition hover:scale-105 disabled:opacity-60"
        >
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          ذخیره تمام تنظیمات
        </button>
      </div>
    </div>
  );
}
