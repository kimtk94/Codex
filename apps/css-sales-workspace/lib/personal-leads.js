'use strict';
// Personal evidence only: never infer email sent from other employees or from Lead status.
const EXPECTED = ['Lead ID','Created Date','Institution','Customer','Email','Description',
  'Description Class','Lead Status','Opportunity ID','My Sent After Lead',
  'My Sent Before Lead','My Sent Ever','Last Sent After Lead','Last Sent Ever',
  'My Mail Status'];
const ALLOWED=new Set(['NO_PERSONAL_OUTBOUND_EVIDENCE','SENT_BEFORE_LEAD_ONLY']);
function projectPersonalLeads(matrix) {
  if(!Array.isArray(matrix)||!Array.isArray(matrix[0])||
     EXPECTED.some((name,i)=>matrix[0][i]!==name))
     throw new Error('PERSONAL_LEAD_SCHEMA_MISMATCH');
  const ids=new Set();
  const result=[];
  for(const row of matrix.slice(1)){
    if(!row || !row[0])continue;
    const id=String(row[0]).trim();
    if(ids.has(id))throw new Error('DUPLICATE_PERSONAL_LEAD_ID');
    ids.add(id);
    const state=String(row[14]||'').trim();
    if(!ALLOWED.has(state) && state!=='SENT_AFTER_LEAD_CONFIRMED')
      throw new Error('UNKNOWN_PERSONAL_LEAD_EVIDENCE');
    const qualified=['QUALIFIED','CONVERTED','CLOSED','UNQUALIFIED'].includes(String(row[7]||'').toUpperCase())||Boolean(row[8]);
    if(!ALLOWED.has(state)||qualified)continue;
    const desc=String(row[5]||'').trim(),recent=/^20\d\d-\d\d-\d\d$/.test(row[1]||'')?Date.parse(row[1]+'T00:00:00Z'):0;
    const age=recent?Math.max(0,Math.floor((Date.now()-recent)/86400000)):999;
    const priority=(age<=7&&desc.length>4&&state==='NO_PERSONAL_OUTBOUND_EVIDENCE')?'P0':(age<=30?'P1':'P2');
    result.push({id,priority,due:row[1]||'',institution:row[2]||'',
      customer:row[3]||'',email:row[4]||'',description:desc,
      status:state==='SENT_BEFORE_LEAD_ONLY'?'과거 발송 후 재연락':'본인 첫 연락',
      next:row[19]||'',personalEvidence:state,descriptionClass:desc?'PRESENT':'MISSING'});
  }
  if(ids.size<450)throw new Error('INCOMPLETE_PERSONAL_LEAD_AUDIT');
  return result;
}
module.exports={projectPersonalLeads};
