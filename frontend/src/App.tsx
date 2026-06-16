import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import Dashboard from "./pages/Dashboard";
import DingTalkCallbackPage from "./pages/DingTalkCallbackPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/dingtalk/callback" element={<DingTalkCallbackPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Dashboard />} />
        <Route element={<ProtectedRoute allowedRoles={["hr_admin"]} />}>
          <Route path="/register" element={<RegisterPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
