import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import Layout from "../components/Layout";
import LoginPage from "../pages/LoginPage";
import ManagerDashboard from "../pages/ManagerDashboard";
import AnnotatorDashboard from "../pages/AnnotatorDashboard";
import ProjectListPage from "../pages/ProjectListPage";
import ProjectDetailPage from "../pages/ProjectDetailPage";
import VolumeDetailPage from "../pages/VolumeDetailPage";
import TaskDetailPage from "../pages/TaskDetailPage";
import SubmitTaskPage from "../pages/SubmitTaskPage";
import ReviewSubmissionPage from "../pages/ReviewSubmissionPage";
import PaymentSummaryPage from "../pages/PaymentSummaryPage";

function RequireAuth({
  children,
  manager,
}: {
  children: ReactNode;
  manager?: boolean;
}) {
  const { user, loading, isManager } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (manager && !isManager) return <Navigate to="/annotator" replace />;
  return <Layout>{children}</Layout>;
}

function HomeRedirect() {
  const { user, loading, isManager } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={isManager ? "/manager" : "/annotator"} replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<HomeRedirect />} />

      {/* Manager */}
      <Route
        path="/manager"
        element={
          <RequireAuth manager>
            <ManagerDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/projects"
        element={
          <RequireAuth manager>
            <ProjectListPage />
          </RequireAuth>
        }
      />
      <Route
        path="/projects/:id"
        element={
          <RequireAuth manager>
            <ProjectDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/volumes/:id"
        element={
          <RequireAuth manager>
            <VolumeDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/submissions/:id/review"
        element={
          <RequireAuth manager>
            <ReviewSubmissionPage />
          </RequireAuth>
        }
      />
      <Route
        path="/payments"
        element={
          <RequireAuth manager>
            <PaymentSummaryPage mode="manager" />
          </RequireAuth>
        }
      />

      {/* Annotator */}
      <Route
        path="/annotator"
        element={
          <RequireAuth>
            <AnnotatorDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/tasks/:id/submit"
        element={
          <RequireAuth>
            <SubmitTaskPage />
          </RequireAuth>
        }
      />
      <Route
        path="/my-payments"
        element={
          <RequireAuth>
            <PaymentSummaryPage mode="annotator" />
          </RequireAuth>
        }
      />

      {/* Shared */}
      <Route
        path="/tasks/:id"
        element={
          <RequireAuth>
            <TaskDetailPage />
          </RequireAuth>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
