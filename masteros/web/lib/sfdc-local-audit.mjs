/** Workstation-only, read-only aggregate SFDC audit projection.
 * Never returns any customer name, email, institution, native CRM ID or price.
 */
export function authorizeAuditRead({enabled,platform,method,host,origin,fetchSite,header}) {
  if (enabled!==true || platform!=="win32") return {ok:false,status:404,code:"LOCAL_AUDIT_DISABLED"};
  if (method!=="GET" || !/^127\.0\.0\.1:[0-9]{2,5}$/.test(host||""))
    return {ok:false,status:403,code:"NON_LOOPBACK_REQUEST"};
  if (origin && origin!=="http://"+host)
    return {ok:false,status:403,code:"FOREIGN_ORIGIN"};
  if (fetchSite && fetchSite!=="same-origin")
    return {ok:false,status:403,code:"CROSS_SITE_REQUEST"};
  if (header!=="1")
    return {ok:false,status:403,code:"USER_INITIATED_HEADER_REQUIRED"};
  return {ok:true};
}

export function projectPrivateAudit(full,opportunities,shortlist,nativeRows,aliases) {
  const numeric=x=>Number.isSafeInteger(x)&&x>=0?x:null;
  const records=shortlist?.summary;
  if (!Array.isArray(nativeRows)||!Array.isArray(aliases) ||
      full?.scope!=="PRIVATE_PREVIOUSLY_ENUMERATED_SNAPSHOT_NOT_LIVE_FULL_RECORD_RECHECK" ||
      opportunities?.scope!=="IN_SCOPE_OPPORTUNITY_SNAPSHOT_NOT_FULL_LIVE_RECHECK" ||
      !records || typeof records!=="object")
    throw new Error("INVALID_PRIVATE_AUDIT_SOURCE");
  const verified=new Set();
  for (const row of nativeRows) {
    if (row?.native_relation_status==="PASS_NATIVE_QUOTE_AND_PARENT_IDS" &&
        typeof row?.opportunity_id==="string" && typeof row?.quote_id==="string") {
      verified.add(row.opportunity_id+"|"+row.quote_id);
    }
  }
  const result={
    snapshot_opportunities:numeric(opportunities.opportunity_inventory_count),
    snapshot_quotations:numeric(full.full_quotation_count),
    single_product_quotes:numeric(full.one_product_manifest_count),
    nontraining_quotes:numeric(full.non_one_product_or_unclassified_quote_count),
    one_to_one_name_candidates:numeric(records.structurally_one_to_one_candidates),
    live_contact_opportunity_pairs:numeric(opportunities.approved_native_opportunity_ids_in_manifest),
    approved_contact_aliases:numeric(aliases.length),
    verified_quote_native_parents:numeric(verified.size),
    quote_parent_conflict_or_missing:numeric(full.opportunity_relation_counts?.parent_not_in_in_scope_opportunity_snapshot),
    original_quote_contact_label_hold:numeric(full.name_comparison_counts?.contact_label_mismatch_or_missing),
    data_scope:"LOCAL_PRIVATE_SNAPSHOT_WITH_PARTIAL_LIVE_VERIFICATION",
    save_allowed:false,
    live_quote_price_verified:false,
    full_snapshot_refreshed_live:false,
  };
  if (Object.values(result).some(x=>x===null))throw new Error("PRIVATE_AUDIT_COUNT_INVALID");
  if (result.single_product_quotes+result.nontraining_quotes!==result.snapshot_quotations)
    throw new Error("QUOTE_COHORT_PARTITION_MISMATCH");
  if (result.verified_quote_native_parents>result.one_to_one_name_candidates)
    throw new Error("QUOTE_PARENT_PASS_COUNT_TOO_LARGE");
  return result;
}
