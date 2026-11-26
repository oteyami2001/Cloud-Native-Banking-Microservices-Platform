import { useMemo } from "react";
import { BankApi } from "./api";
import { useAuth } from "./auth";

export function useApi(): BankApi {
  const { session } = useAuth();
  return useMemo(() => new BankApi(() => session?.token ?? null), [session]);
}
