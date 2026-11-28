# Integration boundary — issuer evidence cache
This proposal does not modify Daily20. The manual readback has no schedule,
no PR or push trigger, and no Drive write scope. The account must be exactly
the existing Daily20 service account; the backup ID/name/size/hash are fixed.
The manual workflow can only be tested after reviewed main integration.
 
The current Daily20 producer counts *live* anchors and freshly fetched
bodies. Do not inject cached bytes as if fetched live, or replace the current
report. Future integration must retain the live report unchanged, add a
separate origin-tagged effective evidence report, and validate the exact
HTTP 403 fallback, fixed historical evidence pins, source re-extraction,
and unchanged research HOLD. Any modified gate must require either independently
verified current evidence or explicitly approved pinned historical context;
it must not certify payment, source finality, or a trading signal.
 
A protected main push to research/kalman_daily20/** or its writer workflow
can trigger full research and Drive writes. Keep integration unmerged until
a dedicated trigger review, dry-run parity and output isolation are verified.
No delayed first seal or reconstructed missed signal may be called prospective.
