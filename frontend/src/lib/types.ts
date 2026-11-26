export interface Customer {
  customer_id: string;
  display_name: string;
  status: string;
  synthetic: true;
}

export interface Account {
  account_id: string;
  account_type: "CHECKING" | "SAVINGS";
  nickname: string | null;
  currency: string;
  status: string;
  masked_number: string;
  created_at: string;
}

export interface Balance {
  account_id: string;
  available_balance_minor: number;
  currency: string;
  status: string;
}

export interface Entry {
  entry_id: string;
  journal_type: string;
  transfer_id: string | null;
  direction: "DEBIT" | "CREDIT";
  amount_minor: number;
  signed_amount_minor: number;
  currency: string;
  counterparty_account_id: string | null;
  description: string;
  posted_at: string;
}

export type TransferStatus = "SCREENING" | "PENDING_REVIEW" | "APPROVED_FOR_POSTING" | "COMPLETED" | "REJECTED" | "FAILED";

export interface Transfer {
  transfer_id: string;
  status: TransferStatus;
  source_account_id: string;
  destination_account_id: string;
  amount_minor: number;
  currency: string;
  reason_code: string | null;
  created_at: string;
  fraud?: { risk_score: number; triggered_rules: string[]; policy_version: string };
}

export interface FraudAlert {
  decision_id: string;
  transfer_id: string;
  risk_score: number;
  decision: string;
  triggered_rules: string[];
  policy_version: string;
  decided_at: string;
  review_expires_at: string;
  amount_minor: number;
  currency: string;
}

export interface Notification {
  event_type: string;
  title: string;
  message: string;
  created_at: string;
}

export interface ReconciliationReport {
  run_id: string;
  status: "BALANCED" | "DISCREPANCIES_FOUND";
  accounts_checked: number;
  journals_checked: number;
  transfers_checked: number;
  discrepancy_count: number;
  total_assets_minor: number;
  total_liabilities_minor: number;
  generated_at: string;
  sha256: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}
