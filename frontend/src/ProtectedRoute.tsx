import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { me, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-shell">
        <p className="muted">Loading...</p>
      </div>
    );
  }

  if (!me) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
