import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { AuthProvider } from "./contexts/AuthContext.tsx";

// اپ همیشه تاریک است؛ کلاس dark همیشه روی ریشه می‌نشیند.
const rootElement = document.documentElement;
rootElement.classList.add("dark");
rootElement.classList.remove("light");
rootElement.style.colorScheme = "dark";
try {
  localStorage.removeItem("archschool-theme");
} catch {
  /* ignore */
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>
);
