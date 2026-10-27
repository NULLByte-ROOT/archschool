import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ImageViewer from "./components/ImageViewer";
import ProtectedRoute from "./components/ProtectedRoute";
import HomePage from "./pages/HomePage";
import TimetablePage from "./pages/TimetablePage";
import AssignmentsPage from "./pages/AssignmentsPage";
import OverdueAssignmentsPage from "./pages/OverdueAssignmentsPage";
import AssignmentDetailPage from "./pages/AssignmentDetailPage";
import SettingsPage from "./pages/SettingsPage";
import NotFoundPage from "./pages/NotFoundPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import UsersPage from "./pages/UsersPage";
import ChatPage from "./pages/ChatPage";
import LeaderboardPage from "./pages/LeaderboardPage";
import BellSchedulePage from "./pages/BellSchedulePage";
import ServerStatsPage from "./pages/ServerStatsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="timetable" element={<TimetablePage />} />
            <Route path="assignments" element={<AssignmentsPage />} />
            <Route path="assignments/overdue" element={<OverdueAssignmentsPage />} />
            <Route path="assignments/:id" element={<AssignmentDetailPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="leaderboard" element={<LeaderboardPage />} />
            <Route path="settings" element={<SettingsPage />} />

            {/* پنل ادمین — بالای منو، فقط نقش‌های staff */}
            <Route element={<ProtectedRoute adminOnly />}>
              <Route path="rootvoid" element={<UsersPage />} />
            </Route>

            {/* تنظیمات زنگ‌ها و داشبورد زندهٔ سرور — فقط Owner */}
            <Route element={<ProtectedRoute ownerOnly />}>
              <Route path="admin/bells" element={<BellSchedulePage />} />
              <Route path="admin/stats" element={<ServerStatsPage />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
      <ImageViewer />
    </BrowserRouter>
  );
}