import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import Layout from "../components/Layout";
import LoginPage from "../pages/LoginPage";
import RegisterPage from "../pages/RegisterPage";
import ManagerDashboard from "../pages/ManagerDashboard";
import AnnotatorDashboard from "../pages/AnnotatorDashboard";
import RequesterDashboard from "../pages/RequesterDashboard";
import RegisterDataPage from "../pages/RegisterDataPage";
import ProjectListPage from "../pages/ProjectListPage";
import ProjectDetailPage from "../pages/ProjectDetailPage";
import VolumeDetailPage from "../pages/VolumeDetailPage";
import TaskDetailPage from "../pages/TaskDetailPage";
import SubmitTaskPage from "../pages/SubmitTaskPage";
import ReviewSubmissionPage from "../pages/ReviewSubmissionPage";

export type HomeRole = "manager" | "requester" | "annotator";

export function effectiveRole(role: string | null | undefined): HomeRole {
  if (role === "manager") return "manager";
  if (role === "requester" || role === "client") return "requester";
  return "annotator";
}

export function homePathForRole(role: string | null | undefined): string {
  return `/${effectiveRole(role)}`;
}

// `roles` restricts a route to specific roles; omit to allow any authenticated user.
function RequireAuth({
  children,
  roles,
}: {
  children: ReactNode;
  roles?: HomeRole[];
}) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(effectiveRole(user.role))) {
    return <Navigate to={homePathForRole(user.role)} replace />;
  }
  return <Layout>{children}</Layout>;
}

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homePathForRole(user.role)} replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/" element={<HomeRedirect />} />

      {/* Manager */}
      <Route
        path="/manager"
        element={
          <RequireAuth roles={["manager"]}>
            <ManagerDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/projects"
        element={
          <RequireAuth roles={["manager"]}>
            <ProjectListPage />
          </RequireAuth>
        }
      />

      {/* Requester */}
      <Route
        path="/requester"
        element={
          <RequireAuth roles={["requester"]}>
            <RequesterDashboard />
          </RequireAuth>
        }
      />

      {/* Register data — shared by requesters and managers */}
      <Route
        path="/register-data"
        element={
          <RequireAuth roles={["manager", "requester"]}>
            <RegisterDataPage />
          </RequireAuth>
        }
      />

      {/* Project + volume detail — managers and requesters (own projects) */}
      <Route
        path="/projects/:id"
        element={
          <RequireAuth roles={["manager", "requester"]}>
            <ProjectDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/volumes/:id"
        element={
          <RequireAuth roles={["manager", "requester"]}>
            <VolumeDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/submissions/:id/review"
        element={
          <RequireAuth roles={["manager"]}>
            <ReviewSubmissionPage />
          </RequireAuth>
        }
      />

      {/* Annotator */}
      <Route
        path="/annotator"
        element={
          <RequireAuth roles={["annotator", "manager"]}>
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
