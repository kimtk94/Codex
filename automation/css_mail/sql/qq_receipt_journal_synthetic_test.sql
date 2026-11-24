-- Synthetic-only SQL tests. All writes are rolled back.
-- Fail with an exception on any violated invariant.
BEGIN;
DO $body$
DECLARE
    k text := repeat('a',64);
    p text := repeat('b',64);
    id1 uuid := '00000000-0000-4000-8000-000000000001';
    id2 uuid := '00000000-0000-4000-8000-000000000002';
BEGIN
    IF NOT qq_receipt_journal.reserve_hold(k,p,id1) THEN
        RAISE EXCEPTION 'FIRST_CLAIM_FAILED';
    END IF;
    IF qq_receipt_journal.reserve_hold(k,p,id2) THEN
        RAISE EXCEPTION 'DUPLICATE_CLAIM_ACCEPTED';
    END IF;
    IF (SELECT count(*) FROM qq_receipt_journal.claims) <> 1 THEN
        RAISE EXCEPTION 'CLAIM_COUNT_INVALID';
    END IF;
    IF NOT qq_receipt_journal.mark_uncertain_hold(k,id1) THEN
        RAISE EXCEPTION 'UNCERTAIN_MARK_FAILED';
    END IF;
    IF qq_receipt_journal.mark_uncertain_hold(k,id1) THEN
        RAISE EXCEPTION 'DUPLICATE_UNCERTAIN_ACCEPTED';
    END IF;
    IF (SELECT count(*) FROM qq_receipt_journal.events) <> 2 THEN
        RAISE EXCEPTION 'EVENT_COUNT_INVALID';
    END IF;
    IF (SELECT state FROM qq_receipt_journal.claims) <> 'UNCERTAIN_HOLD' THEN
        RAISE EXCEPTION 'UNEXPECTED_CLAIM_STATE';
    END IF;
    BEGIN
        UPDATE qq_receipt_journal.events SET event_kind='RESERVED_HOLD';
        RAISE EXCEPTION 'EVENT_MUTATION_WAS_ALLOWED';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;
    BEGIN
        DELETE FROM qq_receipt_journal.events;
        RAISE EXCEPTION 'EVENT_DELETE_WAS_ALLOWED';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;
    BEGIN
        UPDATE qq_receipt_journal.claims SET state='VERIFIED';
        RAISE EXCEPTION 'VERIFIED_STATE_WAS_ALLOWED';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END
$body$;
ROLLBACK;

-- The test deliberately leaves the PRIVATE database empty.
DO $body$
BEGIN
  IF (SELECT count(*) FROM qq_receipt_journal.claims) <> 0 THEN
      RAISE EXCEPTION 'TEST_LEFT_CLAIMS';
  END IF;
  IF (SELECT count(*) FROM qq_receipt_journal.events) <> 0 THEN
      RAISE EXCEPTION 'TEST_LEFT_EVENTS';
  END IF;
END
$body$;
SELECT 'PASS_HOLD_ONLY_NO_REAL_RECEIPTS' AS result;
