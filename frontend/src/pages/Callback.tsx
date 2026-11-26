import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { ErrorNote } from "../components/Layout";

export function Callback() {
  const { completeCognito } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    window.history.replaceState({}, "", "/callback"); // drop the code from the address bar
    if (!code || !state) {
      setError(new Error("Missing authorization code"));
      return;
    }
    completeCognito(code, state).then(() => navigate("/dashboard"), setError);
  }, [completeCognito, navigate]);
  return <section className="card narrow">{error ? <ErrorNote error={error} /> : <p>Completing sign-in…</p>}</section>;
}
