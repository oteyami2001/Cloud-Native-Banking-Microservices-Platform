import { config } from "./config";
import type { Account, Balance, Customer, Entry, FraudAlert, Notification, Page, ReconciliationReport, Transfer } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public body: unknown = null,
  ) {
    super(message);
  }
}

export type TokenProvider = () => string | null;

export function newIdempotencyKey(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export class BankApi {
  constructor(
    private token: TokenProvider,
    private base = config.apiBaseUrl,
    private fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async request<T>(method: string, path: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
    const token = this.token();
    const headers: Record<string, string> = { "content-type": "application/json", ...extraHeaders };
    if (token) headers.authorization = `Bearer ${token}`;
    const res = await this.fetchImpl(`${this.base}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit",
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const err = data?.error ?? {};
      throw new ApiError(res.status, err.code ?? "HTTP_ERROR", err.message ?? `Request failed (${res.status})`, data);
    }
    return data as T;
  }

  me = () => this.request<Customer>("GET", "/v1/customers/me");
  register = (display_name: string) => this.request<Customer>("POST", "/v1/customers", { display_name });
  accounts = () => this.request<Page<Account>>("GET", "/v1/accounts");
  account = (id: string) => this.request<Account>("GET", `/v1/accounts/${encodeURIComponent(id)}`);
  balance = (id: string) => this.request<Balance>("GET", `/v1/accounts/${encodeURIComponent(id)}/balance`);
  transactions = (id: string, cursor?: string | null) =>
    this.request<Page<Entry>>("GET", `/v1/accounts/${encodeURIComponent(id)}/transactions?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
  openAccount = (account_type: "CHECKING" | "SAVINGS", sandbox_opening_balance_minor?: number) =>
    this.request<Account>("POST", "/v1/accounts", { account_type, ...(sandbox_opening_balance_minor ? { sandbox_opening_balance_minor } : {}) });

  /** The idempotency key must be reused when retrying the same transfer. */
  transfer = (req: { source_account_id: string; destination_account_id: string; amount_minor: number; currency: string; memo?: string }, idempotencyKey: string) =>
    this.request<Transfer>("POST", "/v1/transfers", req, { "idempotency-key": idempotencyKey });
  getTransfer = (id: string) => this.request<Transfer>("GET", `/v1/transfers/${encodeURIComponent(id)}`);
  notifications = () => this.request<Page<Notification>>("GET", "/v1/notifications");
  fraudAlerts = () => this.request<Page<FraudAlert>>("GET", "/v1/admin/fraud-alerts");
  approve = (id: string, reason: string) => this.request<Transfer>("POST", `/v1/admin/transfers/${encodeURIComponent(id)}/approve`, { reason });
  reject = (id: string, reason: string) => this.request<Transfer>("POST", `/v1/admin/transfers/${encodeURIComponent(id)}/reject`, { reason });
  reconciliation = () => this.request<{ items: ReconciliationReport[] }>("GET", "/v1/admin/reconciliation");
}
