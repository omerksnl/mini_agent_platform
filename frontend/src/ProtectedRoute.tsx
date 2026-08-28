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

  // Remount the active page when another account becomes active. This clears
  // tenant/user-scoped selections that may still be open in another browser tab.
  return <Outlet key={me.user.id} />;
}
