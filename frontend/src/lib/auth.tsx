import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { config } from "./config";
import { challengeFor, randomString } from "./pkce";

/**
 * Token handling (ADR-0008): access and refresh tokens are held in memory only —
 * never in localStorage — so they are not persisted where injected scripts could
 * read them later. Access tokens live 15 minutes; they are renewed silently with
 * the in-memory refresh token shortly before expiry, and an unrecoverable 401
 * returns the user to the login page. Only the PKCE verifier/state live briefly
 * in sessionStorage to survive the redirect, and are removed after the exchange.
 */
export interface Session {
  token: string;
  name: string;
  groups: string[];
  refreshToken?: string;
  expiresAt?: number; // epoch ms
}

interface AuthContextValue {
  session: Session | null;
  getAccessToken: () => Promise<string | null>;
  expireSession: () => void;
  loginLocal: (persona: Persona) => void;
  loginCognito: () => Promise<void>;
  completeCognito: (code: string, state: string) => Promise<Session>;
  logout: () => void;
}

export interface Persona {
  id: string;
  name: string;
  groups: string[];
  description: string;
}

export const PERSONAS: Persona[] = [
  { id: "alice", name: "Alice (customer)", groups: ["customers"], description: "Checking and savings, everyday transfers" },
  { id: "bob", name: "Bob (customer)", groups: ["customers"], description: "Receives transfers from Alice" },
  { id: "riley", name: "Riley (fraud reviewer)", groups: ["fraud-reviewers"], description: "Reviews held transfers" },
  { id: "avery", name: "Avery (auditor)", groups: ["auditors"], description: "Views reconciliation evidence" },
];

const AuthContext = createContext<AuthContextValue | null>(null);

function decodeGroups(jwt: string): string[] {
  try {
    const payload = JSON.parse(atob(jwt.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/")));
    return payload["cognito:groups"] ?? [];
  } catch {
    return [];
  }
}

const RENEW_BEFORE_MS = 60_000;

async function tokenRequest(body: Record<string, string>): Promise<{ access_token: string; refresh_token?: string; expires_in: number }> {
  const res = await fetch(`${config.cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: config.cognitoClientId, ...body }),
  });
  if (!res.ok) throw new Error("Token request failed");
  return res.json();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<Session | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const navigate = useNavigate();
  const setSession = useCallback((s: Session | null) => {
    sessionRef.current = s;
    setSessionState(s);
  }, []);

  const expireSession = useCallback(() => {
    if (!sessionRef.current) return;
    setSession(null);
    navigate("/login?expired=1", { replace: true });
  }, [navigate, setSession]);

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    const current = sessionRef.current;
    if (!current) return null;
    if (!current.expiresAt || !current.refreshToken || Date.now() < current.expiresAt - RENEW_BEFORE_MS) return current.token;
    try {
      const t = await tokenRequest({ grant_type: "refresh_token", refresh_token: current.refreshToken });
      const renewed = { ...current, token: t.access_token, expiresAt: Date.now() + t.expires_in * 1000 };
      setSession(renewed);
      return renewed.token;
    } catch {
      expireSession();
      return null;
    }
  }, [expireSession, setSession]);

  const loginLocal = useCallback((p: Persona) => {
    if (config.authMode !== "local") throw new Error("Local personas are disabled");
    setSession({ token: `local:sandbox-${p.id}:${p.groups.join(",")}`, name: p.name, groups: p.groups });
  }, [setSession]);

  const loginCognito = useCallback(async () => {
    const verifier = randomString(48);
    const state = randomString(16);
    sessionStorage.setItem("pkce_verifier", verifier);
    sessionStorage.setItem("pkce_state", state);
    const params = new URLSearchParams({
      response_type: "code",
      client_id: config.cognitoClientId,
      redirect_uri: config.redirectUri,
      scope: config.scopes,
      state,
      code_challenge: await challengeFor(verifier),
      code_challenge_method: "S256",
    });
    window.location.assign(`${config.cognitoDomain}/oauth2/authorize?${params}`);
  }, []);

  const completeCognito = useCallback(async (code: string, state: string) => {
    const verifier = sessionStorage.getItem("pkce_verifier");
    const expected = sessionStorage.getItem("pkce_state");
    sessionStorage.removeItem("pkce_verifier");
    sessionStorage.removeItem("pkce_state");
    if (!verifier || !expected || state !== expected) throw new Error("Invalid login state");
    const tokens = await tokenRequest({
      grant_type: "authorization_code",
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    }).catch(() => {
      throw new Error("Token exchange failed");
    });
    const session: Session = {
      token: tokens.access_token,
      refreshToken: tokens.refresh_token,
      expiresAt: Date.now() + tokens.expires_in * 1000,
      name: "Signed in",
      groups: decodeGroups(tokens.access_token),
    };
    setSession(session);
    return session;
  }, [setSession]);

  const logout = useCallback(() => {
    setSession(null);
    if (config.authMode === "cognito" && config.cognitoDomain) {
      const params = new URLSearchParams({ client_id: config.cognitoClientId, logout_uri: `${window.location.origin}/` });
      window.location.assign(`${config.cognitoDomain}/logout?${params}`);
    }
  }, [setSession]);

  const value = useMemo(
    () => ({ session, getAccessToken, expireSession, loginLocal, loginCognito, completeCognito, logout }),
    [session, getAccessToken, expireSession, loginLocal, loginCognito, completeCognito, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Landing page for a role: customers see accounts, staff see their queue. */
export function homeFor(groups: string[]): string {
  if (groups.includes("customers")) return "/dashboard";
  if (groups.includes("fraud-reviewers")) return "/admin/fraud";
  if (groups.includes("auditors")) return "/admin/reconciliation";
  return "/";
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
