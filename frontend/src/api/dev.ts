// Dev-only helpers. The backend only routes these when DEBUG is on, and the
// callers are stripped from production builds by `import.meta.env.DEV`.
import { api } from "./client";

export interface DevResetResult {
  deleted: Record<string, number>;
  summary: Record<string, number>;
}

/** Wipe all dev data (projects, volumes, tasks, non-superuser accounts) and
 *  reseed the standard dev accounts. */
export function resetDevData(): Promise<DevResetResult> {
  return api.post<DevResetResult>("/dev/reset/");
}
