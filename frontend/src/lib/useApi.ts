import { useMemo } from "react";
import { BankApi } from "./api";
import { useAuth } from "./auth";

export function useApi(): BankApi {
  const { session, getAccessToken, expireSession } = useAuth();
  return useMemo(() => new BankApi(getAccessToken, undefined, undefined, expireSession), [session, getAccessToken, expireSession]);
}
