import { create } from "zustand";
import { api, ApiError, setCsrfToken, type LoginResponse, type Me, type Role } from "./api";

export type AuthStatus = "loading" | "needs-setup" | "anonymous" | "authenticated" | "offline";
export interface User { id: number; username: string; role: Role }

interface AuthState {
  status: AuthStatus;
  user: User | null;
  bootstrap: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 };
export const hasRole = (user: User | null, min: Role): boolean => !!user && RANK[user.role] >= RANK[min];

export const useAuth = create<AuthState>((set, get) => ({
  status: "loading",
  user: null,

  /** Decide where the user lands: first-run setup, sign-in, or the app (an existing cookie session). */
  async bootstrap() {
    try {
      const s = await api<{ needs_setup: boolean }>("/api/setup/status");
      if (s.needs_setup) {
        set({ status: "needs-setup", user: null });
        return;
      }
      const me = await api<Me>("/api/auth/me");
      setCsrfToken(me.csrf_token);
      set({ status: "authenticated", user: { id: me.id, username: me.username, role: me.role } });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) set({ status: "anonymous", user: null });
      else set({ status: "offline", user: null });
    }
  },

  async login(username, password) {
    const r = await api<LoginResponse>("/api/auth/login", { method: "POST", body: { username, password } });
    setCsrfToken(r.csrf_token); // the session token itself stays in the HttpOnly cookie; the UI never stores it
    set({ status: "authenticated", user: r.user });
  },

  async setup(username, password) {
    await api("/api/setup", { method: "POST", body: { username, password } });
    await get().login(username, password);
  },

  async logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setCsrfToken(null);
      set({ status: "anonymous", user: null });
    }
  },
}));
