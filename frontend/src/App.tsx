import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import AttendanceSheetsPage from "./pages/AttendanceSheetsPage";
import DingTalkCallbackPage from "./pages/DingTalkCallbackPage";
import AttendanceListPage from "./pages/AttendanceListPage";
import AttendancePeriodTablePage from "./pages/AttendancePeriodTablePage";
import ExceptionPage from "./pages/ExceptionPage";
import ExcelWorkflowPage from "./pages/ExcelWorkflowPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import RuleConfigPage from "./pages/RuleConfigPage";
import WebhooksPage from "./pages/WebhooksPage";
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
          <Route
            path="/sheets"
            element={
              <ErrorBoundary title="Attendance sheets error">
                <AttendanceSheetsPage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/excel-workflow"
            element={
              <ErrorBoundary title="Excel workflow error">
                <ExcelWorkflowPage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/attendance-list"
            element={
              <ErrorBoundary title="Attendance list error">
                <AttendanceListPage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/attendance-table/:periodId"
            element={
              <ErrorBoundary title="Attendance table error">
                <AttendancePeriodTablePage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/exceptions/:periodId"
            element={
              <ErrorBoundary title="Exception page error">
                <ExceptionPage />
              </ErrorBoundary>
            }
          />
          <Route element={<ProtectedRoute allowedRoles={["hr_admin"]} />}>
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/webhooks" element={<WebhooksPage />} />
            <Route
              path="/rule-config"
              element={
                <ErrorBoundary title="Rule config error">
                  <RuleConfigPage />
                </ErrorBoundary>
              }
            />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
