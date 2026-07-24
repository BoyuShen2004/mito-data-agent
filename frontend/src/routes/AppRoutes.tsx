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
import NewProjectPage from "../pages/NewProjectPage";
import ProjectDetailPage from "../pages/ProjectDetailPage";
import VolumeDetailPage from "../pages/VolumeDetailPage";
import TaskDetailPage from "../pages/TaskDetailPage";
import { TaskViewerPage, VolumeViewerPage } from "../pages/ViewerPage";
import SubmitTaskPage from "../pages/SubmitTaskPage";
import ReviewSubmissionPage from "../pages/ReviewSubmissionPage";
import { effectiveRole, homePathForRole, homeLabelForRole } from "./roles";
import type { HomeRole } from "./roles";

export { effectiveRole, homePathForRole, homeLabelForRole };
export type { HomeRole };

// `roles` restricts a route to specific roles; omit to allow any authenticated user.
// `fullBleed` keeps the global navbar but skips the centered max-width container
// so viewer/editor pages can fill the remaining window under the navbar.
function RequireAuth({
  children,
  roles,
  fullBleed = false,
}: {
  children: ReactNode;
  roles?: HomeRole[];
  fullBleed?: boolean;
}) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(effectiveRole(user.role))) {
    return <Navigate to={homePathForRole(user.role)} replace />;
  }
  return <Layout fullBleed={fullBleed}>{children}</Layout>;
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

      {/* Step 1 of new work: create the project, then register data into it.
          Requesters own projects too, so both roles may create one. */}
      <Route
        path="/projects/new"
        element={
          <RequireAuth roles={["manager", "requester"]}>
            <NewProjectPage />
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

      {/* Visualization — any role that can view. Editing entry is gated in the
          page (managers + assigned annotator); requesters only reach /viewer.
          fullBleed keeps the global navbar but lets the canvas fill the rest. */}
      <Route
        path="/viewer/volumes/:id"
        element={
          <RequireAuth fullBleed>
            <VolumeViewerPage />
          </RequireAuth>
        }
      />
      <Route
        path="/viewer/tasks/:id"
        element={
          <RequireAuth fullBleed>
            <TaskViewerPage />
          </RequireAuth>
        }
      />
      <Route
        path="/editor/tasks/:id"
        element={
          <RequireAuth fullBleed roles={["manager", "annotator"]}>
            <TaskViewerPage editable />
          </RequireAuth>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
