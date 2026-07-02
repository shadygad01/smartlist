// Base URL for the api-server (Portfolio Tracker / uploads backend).
//
// On GitHub Pages the dashboard is static files only — there is no server on
// that origin, so relative `/api/...` calls 404. Set VITE_API_BASE_URL at
// build time to the api-server's public deployment URL (e.g. a Replit
// Autoscale deployment: https://<repl-name>.replit.app) so the dashboard can
// reach it cross-origin. Leave unset for local dev, where Vite proxies
// `/api` to localhost:8080 (see vite.config.ts).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
