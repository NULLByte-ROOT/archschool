import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function ProtectedRoute({
  adminOnly = false,
  ownerOnly = false,
}: {
  adminOnly?: boolean;
  ownerOnly?: boolean;
}) {
  const { isAuthenticated, isAdmin, isOwner } = useAuth();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (ownerOnly && !isOwner) return <Navigate to="/" replace />;
  if (adminOnly && !isAdmin) return <Navigate to="/" replace />;
  return <Outlet />;
}
