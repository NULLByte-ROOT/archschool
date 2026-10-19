import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Home } from "lucide-react";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <motion.p
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="mono bg-gradient-to-b from-white to-white/30 bg-clip-text text-8xl font-bold text-transparent"
      >
        404
      </motion.p>

      <div className="badge mt-6">
        <span className="dot animate-pulse" />
        page not found
      </div>

      <p className="mt-4 text-lg text-fg-300">دنبال چی میگردی؟</p>
      <p className="mt-1 text-sm text-fg-500">صفحه‌ای که دنبالش هستی وجود نداره</p>

      <Link to="/" className="btn-primary mt-8">
        <Home size={14} />
        بازگشت به داشبورد
      </Link>
    </div>
  );
}
