-- QQ 2026 per-case receipt journal: PRIVATE Neon Postgres schema only.
-- This PUBLIC source file contains no real invoices, user identifiers or secrets.
-- Status is permanently HOLD-only: no VERIFIED, APPROVED or replay/Sheets functions.
-- A committed RESERVED_HOLD is a durable dedupe claim, NOT an execution permit.
-- Neon project credentials must never be stored in this public GitHub repository.
CREATE SCHEMA IF NOT EXISTS qq_receipt_journal;
REVOKE ALL ON SCHEMA qq_receipt_journal FROM PUBLIC;

CREATE TABLE IF NOT EXISTS qq_receipt_journal.claims (
    case_token text PRIMARY KEY
        CHECK (case_token ~ '^[a-f0-9]{64}$'),
    source_token text NOT NULL
        CHECK (source_token ~ '^[a-f0-9]{64}$'),
    attempt_uuid uuid NOT NULL UNIQUE,
    state text NOT NULL DEFAULT 'RESERVED_HOLD'
        CHECK (state IN ('RESERVED_HOLD','UNCERTAIN_HOLD')),
    revision bigint NOT NULL DEFAULT 1
        CHECK (revision >= 1),
    claimed_at timestamptz NOT NULL DEFAULT now(),
    state_changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qq_receipt_journal.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_token text NOT NULL
        REFERENCES qq_receipt_journal.claims(case_token),
    attempt_uuid uuid NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 1),
    event_kind text NOT NULL
        CHECK (event_kind IN ('RESERVED_HOLD','UNCERTAIN_HOLD')),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(case_token,revision)
);

CREATE OR REPLACE FUNCTION qq_receipt_journal.deny_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    RAISE EXCEPTION 'JOURNAL_EVENTS_IMMUTABLE' USING ERRCODE='55000';
END
$body$;

CREATE TRIGGER prevent_event_mutation
BEFORE UPDATE OR DELETE ON qq_receipt_journal.events
FOR EACH ROW EXECUTE FUNCTION qq_receipt_journal.deny_event_mutation();

CREATE OR REPLACE FUNCTION qq_receipt_journal.reserve_hold(
    p_case_token text, p_source_token text, p_attempt_uuid uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,qq_receipt_journal AS $body$
DECLARE inserted boolean := false;
BEGIN
    INSERT INTO qq_receipt_journal.claims(
        case_token,source_token,attempt_uuid)
    VALUES(p_case_token,p_source_token,p_attempt_uuid)
    ON CONFLICT DO NOTHING RETURNING true INTO inserted;

    IF COALESCE(inserted,false) THEN
        INSERT INTO qq_receipt_journal.events
            (case_token,attempt_uuid,revision,event_kind)
        VALUES(p_case_token,p_attempt_uuid,1,'RESERVED_HOLD');
    END IF;
    RETURN COALESCE(inserted,false);
END
$body$;

CREATE OR REPLACE FUNCTION qq_receipt_journal.mark_uncertain_hold(
    p_case_token text, p_attempt_uuid uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,qq_receipt_journal AS $body$
DECLARE updated_case boolean := false;
BEGIN
    UPDATE qq_receipt_journal.claims
       SET state='UNCERTAIN_HOLD',revision=revision+1,
           state_changed_at=now()
     WHERE case_token=p_case_token
       AND attempt_uuid=p_attempt_uuid
       AND state='RESERVED_HOLD'
    RETURNING true INTO updated_case;
    IF COALESCE(updated_case,false) THEN
        INSERT INTO qq_receipt_journal.events
            (case_token,attempt_uuid,revision,event_kind)
        VALUES(p_case_token,p_attempt_uuid,2,'UNCERTAIN_HOLD');
    END IF;
    RETURN COALESCE(updated_case,false);
END
$body$;

REVOKE ALL ON ALL TABLES IN SCHEMA qq_receipt_journal FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA qq_receipt_journal FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qq_receipt_journal FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA qq_receipt_journal
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
