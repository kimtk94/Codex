/** Loopback-only local mail review security and response contracts. */
const HOST = /^127\.0\.0\.1:[0-9]{2,5}$/;
const ACTIONS = new Set(["SKIP_MAIL","SKIP_CC_TO","SKIP_CC_SENDER","RESTORE_MAIL","RESTORE_RULE"]);
const TEXT = ["key","uid","sender","subject","to","cc","target","note"];

export function authorizeCssMailLocal({enabled,method,host,origin,fetchSite,header,contentType}) {
  if (!enabled) return {ok:false,status:404,code:"LOCAL_MAIL_DISABLED"};
  if (!["GET","POST"].includes(method)||!HOST.test(host||""))
    return {ok:false,status:403,code:"LOOPBACK_ONLY"};
  if (origin && origin!=="http://"+host)
    return {ok:false,status:403,code:"ORIGIN_MISMATCH"};
  if (method==="POST" && origin!=="http://"+host)
    return {ok:false,status:403,code:"SAME_ORIGIN_REQUIRED"};
  if (fetchSite && !["same-origin","none"].includes(fetchSite))
    return {ok:false,status:403,code:"CROSS_SITE_DENIED"};
  if (header!=="1") return {ok:false,status:403,code:"EXPLICIT_HEADER_REQUIRED"};
  if (method==="POST" && !/^application\/json(?:;|$)/i.test(contentType||""))
    return {ok:false,status:415,code:"JSON_ONLY"};
  return {ok:true,status:200};
}

export function parseLocalMailAction(input) {
  if (!input||typeof input!=="object"||Array.isArray(input)||input.mode!=="decision")
    throw Error("DECISION_REQUIRED");
  if (!ACTIONS.has(input.action))throw Error("UNSUPPORTED_ACTION");
  const keys=new Set(["mode","action",...TEXT]);
  if (Object.keys(input).some(k=>!keys.has(k)))throw Error("UNKNOWN_FIELDS");
  for (const field of TEXT)
    if (input[field]!==undefined && (typeof input[field]!=="string"||input[field].length>500))
      throw Error("INVALID_FIELD_"+field);
  if ((input.note||"").length>300)throw Error("NOTE_TOO_LONG");
  if (JSON.stringify(input).length>1600)throw Error("BODY_TOO_LONG");
  return input;
}

export function validateLocalMailResult(data,mode) {
  if (!data||typeof data!=="object"||Array.isArray(data))throw Error("INVALID_WORKER_RESULT");
  if (data.status==="BLOCK"&&typeof data.code==="string"&&data.code.length<100)return data;
  if (mode==="snapshot"){
    if (!["PASS","STALE"].includes(data.status)||
      !Array.isArray(data.mail)||!Array.isArray(data.leads)||
      !Array.isArray(data.rules)||!Array.isArray(data.skippedMails)||
      data.mail.length>1600||data.leads.length>2000||
      !Number.isInteger(data.mailCount)||!Number.isInteger(data.leadCount)||
      data.mail.length!==data.mailCount||data.leads.length!==data.leadCount)
      throw Error("INVALID_WORKER_SNAPSHOT");
  }else if (data.status!=="PASS"||typeof data.result!=="string")
    throw Error("INVALID_WORKER_DECISION");
  return data;
}
