'use strict';
const ACTIONS=new Set(['EXCLUDE_MAIL','EXCLUDE_SENDER','RESTORE_MAIL','RESTORE_SENDER']);
const UID=/^(?:inbox|sent|imap|qq):[0-9]{1,15}$/i;

function validateAction(input){
  if(!input||typeof input!=='object'||Array.isArray(input))throw Error('INVALID_REVIEW_REQUEST');
  const keys=Object.keys(input).sort();
  if(keys.join('|')!=='action|expectedDecision|uid')throw Error('INVALID_REVIEW_FIELDS');
  const {uid,action,expectedDecision}=input;
  if(typeof uid!=='string'||!UID.test(uid))throw Error('INVALID_MAIL_UID');
  if(typeof action!=='string'||!ACTIONS.has(action))throw Error('INVALID_REVIEW_ACTION');
  if(typeof expectedDecision!=='string'||!ACTIONS.has(expectedDecision)&&expectedDecision!=='NONE')
    throw Error('INVALID_EXPECTED_DECISION');
  return {uid,action,expectedDecision};
}

function locateTarget(rows,request){
  if(!Array.isArray(rows)||rows[0]?.[4]!=='Mail UID (Key)'||rows[0]?.[0]!=='Decision (Edit)')
    throw Error('REVIEW_LEDGER_SCHEMA_CHANGED');
  let target=null,found=0;
  for(let i=1;i<rows.length;i++){
    const row=rows[i]||[];
    if(String(row[4]||'').trim()!==request.uid)continue;
    target={rowIndex:i+1,action:String(row[0]||'NONE').trim().toUpperCase(),
      status:String(row[7]||'').trim(),sender:String(row[1]||'').trim()};
    found++;
  }
  if(found!==1)throw Error(found?'DUPLICATE_MAIL_UID':'MAIL_UID_NOT_FOUND');
  if(target.action!==request.expectedDecision)throw Error('REVIEW_DECISION_CHANGED');
  if(request.action.endsWith('SENDER')&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(target.sender))
    throw Error('SENDER_ADDRESS_NOT_VERIFIED');
  return target;
}
module.exports={validateAction,locateTarget,ACTIONS,UID};
