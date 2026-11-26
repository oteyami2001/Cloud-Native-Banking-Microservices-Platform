-- NovaBank Digital — reference relational ledger (PostgreSQL 16). Not deployed.
-- Mirrors the DynamoDB accounting model in docs/banking-business-model.md.

CREATE TYPE account_class AS ENUM ('ASSET', 'LIABILITY');
CREATE TYPE entry_side    AS ENUM ('D', 'C');
CREATE TYPE account_state AS ENUM ('ACTIVE', 'FROZEN', 'CLOSED');

CREATE TABLE ledger_account (
    account_id              text PRIMARY KEY,
    customer_id             text,
    account_class           account_class NOT NULL,
    currency                char(3)       NOT NULL CHECK (currency = 'USD'),
    available_balance_minor bigint        NOT NULL DEFAULT 0 CHECK (available_balance_minor >= 0),
    status                  account_state NOT NULL DEFAULT 'ACTIVE',
    version                 bigint        NOT NULL DEFAULT 0,
    created_at              timestamptz   NOT NULL DEFAULT now()
);

CREATE TABLE journal (
    journal_id     text PRIMARY KEY,               -- = transfer id: posting idempotency
    journal_type   text        NOT NULL CHECK (journal_type IN ('OPENING_BALANCE', 'TRANSFER', 'REVERSAL')),
    currency       char(3)     NOT NULL,
    journal_hash   char(64)    NOT NULL,
    correlation_id text,
    posted_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger_entry (
    entry_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journal_id   text       NOT NULL REFERENCES journal (journal_id),
    account_id   text       NOT NULL REFERENCES ledger_account (account_id),
    side         entry_side NOT NULL,
    amount_minor bigint     NOT NULL CHECK (amount_minor > 0),
    posted_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (journal_id, account_id)
);
CREATE INDEX ledger_entry_account_time ON ledger_entry (account_id, posted_at DESC);

-- Every journal must balance at COMMIT time.
CREATE FUNCTION assert_journal_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d bigint; c bigint;
BEGIN
    SELECT COALESCE(SUM(amount_minor) FILTER (WHERE side = 'D'), 0),
           COALESCE(SUM(amount_minor) FILTER (WHERE side = 'C'), 0)
      INTO d, c FROM ledger_entry WHERE journal_id = NEW.journal_id;
    IF d <> c OR d = 0 THEN
        RAISE EXCEPTION 'journal % is unbalanced (debits %, credits %)', NEW.journal_id, d, c;
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER journal_balanced
    AFTER INSERT ON ledger_entry DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION assert_journal_balanced();

-- Entries are append-only; corrections are compensating journals.
CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'ledger entries are immutable'; END $$;
CREATE TRIGGER ledger_entry_immutable BEFORE UPDATE OR DELETE ON ledger_entry
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- Posting procedure: lock balance rows in a deterministic order, apply deltas,
-- insert entries; the deferred trigger validates balance at commit.
CREATE PROCEDURE post_transfer(p_journal text, p_src text, p_dst text, p_amount bigint, p_hash char(64))
LANGUAGE plpgsql AS $$
BEGIN
    IF p_src = p_dst THEN RAISE EXCEPTION 'self transfer'; END IF;
    PERFORM 1 FROM ledger_account WHERE account_id IN (p_src, p_dst) ORDER BY account_id FOR UPDATE;
    INSERT INTO journal (journal_id, journal_type, currency, journal_hash) VALUES (p_journal, 'TRANSFER', 'USD', p_hash);
    UPDATE ledger_account SET available_balance_minor = available_balance_minor - p_amount, version = version + 1
     WHERE account_id = p_src AND status = 'ACTIVE';  -- CHECK (>= 0) rejects overdraft
    IF NOT FOUND THEN RAISE EXCEPTION 'source not active'; END IF;
    UPDATE ledger_account SET available_balance_minor = available_balance_minor + p_amount, version = version + 1
     WHERE account_id = p_dst AND status = 'ACTIVE';
    IF NOT FOUND THEN RAISE EXCEPTION 'destination not active'; END IF;
    INSERT INTO ledger_entry (journal_id, account_id, side, amount_minor)
    VALUES (p_journal, p_src, 'D', p_amount), (p_journal, p_dst, 'C', p_amount);
END $$;

-- Reconciliation query R1: authoritative balance vs. sum of entries.
-- SELECT a.account_id, a.available_balance_minor,
--        SUM(CASE WHEN (e.side = 'C') = (a.account_class = 'LIABILITY') THEN e.amount_minor ELSE -e.amount_minor END) AS entries
--   FROM ledger_account a LEFT JOIN ledger_entry e USING (account_id)
--  GROUP BY a.account_id HAVING a.available_balance_minor <> COALESCE(SUM(...), 0);
