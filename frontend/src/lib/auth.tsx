import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { config } from "./config";
import { challengeFor, randomString } from "./pkce";

/**
 * Token handling (ADR-0008): access tokens are held in memory only — never in
 * localStorage — so they are not persisted where injected scripts could read
 * them later. Only the PKCE verifier/state live briefly in sessionStorage to
 * survive the redirect, and are removed immediately after the exchange.
 */
export interface Session {
  token: string;
  name: string;
  groups: string[];
}

interface AuthContextValue {
  session: Session | null;
  loginLocal: (persona: Persona) => void;
  loginCognito: () => Promise<void>;
  completeCognito: (code: string, state: string) => Promise<void>;
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  const loginLocal = useCallback((p: Persona) => {
    if (config.authMode !== "local") throw new Error("Local personas are disabled");
    setSession({ token: `local:sandbox-${p.id}:${p.groups.join(",")}`, name: p.name, groups: p.groups });
  }, []);

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
    const res = await fetch(`${config.cognitoDomain}/oauth2/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: config.cognitoClientId,
        code,
        redirect_uri: config.redirectUri,
        code_verifier: verifier,
      }),
    });
    if (!res.ok) throw new Error("Token exchange failed");
    const tokens = await res.json();
    setSession({ token: tokens.access_token, name: "Signed in", groups: decodeGroups(tokens.access_token) });
  }, []);

  const logout = useCallback(() => {
    setSession(null);
    if (config.authMode === "cognito" && config.cognitoDomain) {
      const params = new URLSearchParams({ client_id: config.cognitoClientId, logout_uri: `${window.location.origin}/` });
      window.location.assign(`${config.cognitoDomain}/logout?${params}`);
    }
  }, []);

  const value = useMemo(() => ({ session, loginLocal, loginCognito, completeCognito, logout }), [session, loginLocal, loginCognito, completeCognito, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
