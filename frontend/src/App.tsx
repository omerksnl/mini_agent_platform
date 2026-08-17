import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";
import { AgentsPage } from "./pages/AgentsPage";
import { ChatPage } from "./pages/ChatPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ToolsPage } from "./pages/ToolsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { CollectionsPage } from "./pages/CollectionsPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { WorkflowStudioPage } from "./pages/WorkflowStudioPage";
import { useGlobalInputUndo } from "./useGlobalInputUndo";

export default function App() {
  useGlobalInputUndo();
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<AgentsPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/multi-agent" element={<WorkflowsPage />} />
            <Route path="/workflows" element={<WorkflowStudioPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
