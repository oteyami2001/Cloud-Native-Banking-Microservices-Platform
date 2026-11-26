export type AuthMode = "local" | "cognito";

export const config = {
  authMode: (import.meta.env.VITE_AUTH_MODE ?? "local") as AuthMode,
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8080").replace(/\/$/, ""),
  cognitoDomain: (import.meta.env.VITE_COGNITO_DOMAIN ?? "").replace(/\/$/, ""),
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID ?? "",
  redirectUri: import.meta.env.VITE_REDIRECT_URI ?? `${window.location.origin}/callback`,
  scopes: "openid email novabank/read novabank/write novabank/admin",
};
