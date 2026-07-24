// Where "Back" should go when there is no in-app history entry to pop —
// i.e. the page was deep-linked, reloaded, or is the first page after login.
// In those cases we walk *up* the route hierarchy instead of leaving the app.
import { matchPath } from "react-router-dom";
import { effectiveRole, homePathForRole } from "./roles";
import type { HomeRole } from "./roles";

/** The parent route for `pathname`, or null if it is a role home (nothing above it). */
export function backFallbackFor(
  pathname: string,
  role: string | null | undefined,
): string | null {
  const effective: HomeRole = effectiveRole(role);
  const home = homePathForRole(role);
  if (pathname === home) return null;

  // A task's submit/review form sits under the task itself.
  const submit = matchPath("/tasks/:id/submit", pathname);
  if (submit) return `/tasks/${submit.params.id}`;

  // Viewer / editor for a task → back to that task's detail page.
  const taskViewer =
    matchPath("/viewer/tasks/:id", pathname) ||
    matchPath("/editor/tasks/:id", pathname);
  if (taskViewer) return `/tasks/${taskViewer.params.id}`;

  // Volume viewer → back to the volume page.
  const volumeViewer = matchPath("/viewer/volumes/:id", pathname);
  if (volumeViewer) return `/volumes/${volumeViewer.params.id}`;

  // Projects and volumes hang off the project list, which only managers have;
  // a requester's own list is their dashboard.
  const underProjects =
    matchPath("/projects/:id", pathname) || matchPath("/volumes/:id", pathname);
  if (underProjects) return effective === "manager" ? "/projects" : home;

  // Everything else (/projects, /tasks/:id, /submissions/:id/review,
  // /register-data) goes up to the dashboard.
  return home;
}
