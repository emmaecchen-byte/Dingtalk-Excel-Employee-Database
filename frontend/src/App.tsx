import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import DingTalkCallbackPage from "./pages/DingTalkCallbackPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import { queryClient } from "./lib/queryClient";

export default function App() {
  return (
    <ErrorBoundary
      title="Application error"
      onReset={() => {
        void queryClient.clear();
        window.location.reload();
      }}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/dingtalk/callback" element={<DingTalkCallbackPage />} />
        <Route element={<ProtectedRoute />}>
          <Route
            path="/"
            element={
              <ErrorBoundary title="Dashboard error">
                <Dashboard />
              </ErrorBoundary>
            }
          />
          <Route element={<ProtectedRoute allowedRoles={["hr_admin"]} />}>
            <Route path="/register" element={<RegisterPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
