'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {normalize,cleanText,safeCursor,readProjects,BASE,TABLE}=require('../lib/feishu-base');
const ui=require('../feishu.js');
const owner=require('../lib/lifecycle-owner-auth');
const handler=require('../api/feishu/projects');
const raw={
  'Source Key':[{text:'PROJECT:AMEA2026100751'}],
  'AMEA':[{text:'AMEA2026100751'}],
  'Quote Full Name':[{text:'Korea-Yonsei-20-mRNASeq-6Gb-Prof.LeeTaeKwon-ParkSoHee-AMEA2026100751'}],
  'Quote Match State':[{text:'SFDC_EXACT_VERIFIED'}],
  'Institution':'Yonsei Univ.',
  'Customer':'ParkSoHee',
  'Service':'mRNA-Seq',
  'Current Stage':'Sample QC',
  'Progress %':55,
  'Prepayment':'YES',
  'SIF State':'WAIVED_PREPAYMENT',
  'PO Evidence':'PO_ORIGINAL_NOT_VERIFIED',
  'Next Action':'Sample QC review',
};
test('normalizes Feishu rich-text fields without trimming Quote Full Name',()=>{
  const r=normalize({fields:raw});
  assert.equal(r.id,'PROJECT:AMEA2026100751');
  assert.equal(r['Quote Full Name'],'Korea-Yonsei-20-mRNASeq-6Gb-Prof.LeeTaeKwon-ParkSoHee-AMEA2026100751');
  assert.equal(r.progress,55);
  assert.equal(cleanText([{text:'A'},{text:'B'}]),'AB');
});
test('unknown progress remains unknown; no fabricated zero/100',()=>{
  assert.equal(normalize({fields:{'Source Key':'A'}}).progress,null);
  assert.equal(normalize({fields:{'Source Key':'A','Progress %':200}}).progress,null);
  assert.equal(ui.showProgress({progress:null}),'미확인');
});
test('one authenticated Base page and cursor are fetched exclusively server-side',async()=>{
  let count=0;
  const fetcher=async(url,opts)=>{
    count++;
    if(count===1){
      assert.ok(url.endsWith('/open-apis/auth/v3/tenant_access_token/internal'));
      assert.equal(JSON.parse(opts.body).app_secret,'mock-secret');
      return {ok:true,json:async()=>({code:0,tenant_access_token:'mock-access'})};
    }
    assert.ok(url.includes('/apps/'+BASE+'/tables/'+TABLE+'/records?'));
    assert.ok(url.includes('page_token=next_01'));
    assert.equal(opts.headers.Authorization,'Bearer mock-access');
    return {ok:true,json:async()=>({code:0,data:{items:[{fields:raw}],has_more:false}})};
  };
  const r=await readProjects({appId:'mock-id',appSecret:'mock-secret',cursor:'next_01',fetcher});
  assert.equal(r.items.length,1);
  assert.equal(r.source,'FEISHU_BASE');
  assert.equal(r.nextCursor,null);
  assert.equal(count,2);
});
test('no credentials fail closed; invalid page cursor rejected',async()=>{
  await assert.rejects(readProjects({appId:'',appSecret:''}),/FEISHU_CREDENTIALS_MISSING/);
  assert.throws(()=>safeCursor('\nabc'),/BAD_CURSOR/);
});
test('frontend escapes HTML/XSS from untrusted Base fields',()=>{
  const r={...normalize({fields:raw}),'Quote Full Name':'<img src=x onerror=alert(1)>'};
  const card=ui.card(r,0);
  assert.doesNotMatch(card,/<img/);
  assert.match(card,/&lt;img/);
  assert.equal(ui.stats([r]).verified,1);
  assert.equal(ui.stats([r]).prepaid,1);
});
test('frontend category filtering preserves Prepayment exception',()=>{
  const a={...normalize({fields:raw})};
  const b={...a,'Source Key':'B','Quote Match State':'CSS_ORIGINAL_UNVERIFIED',
    'Prepayment':'NOT_VERIFIED','SIF State':'NOT_VERIFIED',progress:null};
  assert.equal(ui.filterRows([a,b],{filter:'prepay'}).length,1);
  assert.equal(ui.filterRows([a,b],{filter:'sif'}).length,1);
  assert.equal(ui.filterRows([a,b],{filter:'quote'}).length,1);
  assert.equal(ui.filterRows([a,b],{filter:'progress'}).length,1);
  assert.equal(ui.stageGroup(a),'SAMPLE');
});
test('frontend reads all Feishu Base pages and validates cursor changes',async()=>{
  const calls=[];
  const fetcher=async path=>{
    calls.push(path);
    return {ok:true,json:async()=>calls.length===1?
      {source:'FEISHU_BASE',items:[{id:'A'}],hasMore:true,nextCursor:'t_2'}:
      {source:'FEISHU_BASE',items:[{id:'B'}],hasMore:false,nextCursor:null}
    };
  };
  const data=await ui.collectPages(fetcher);
  assert.equal(data.rows.length,2);
  assert.ok(calls[1].includes('cursor=t_2'));
});
test('frontend rejects duplicate IDs across Base pages',async()=>{
  const fetcher=async path=>({ok:true,json:async()=>!path.includes('cursor=')?
    {source:'FEISHU_BASE',items:[{id:'A'}],hasMore:true,nextCursor:'t_2'}:
    {source:'FEISHU_BASE',items:[{id:'A'}],hasMore:false}
  });
  await assert.rejects(ui.collectPages(fetcher),/DUPLICATE_RECORD/);
});
test('API blocks unauthenticated requests before Feishu access',async()=>{
  const prior=process.env.CSS_WEB_ACCESS_TOKEN;process.env.CSS_WEB_ACCESS_TOKEN='mock-owner-token';
  const res={statusCode:200,headers:{},setHeader(k,v){this.headers[k]=v;return this},
    status(n){this.statusCode=n;return this},json(v){this.body=v;return v}};
  try{
    await handler({method:'GET',headers:{}},res);
    assert.equal(res.statusCode,401);
    assert.equal(res.body.error,'OWNER_LOGIN_REQUIRED');
    assert.match(res.headers['Cache-Control'],/no-store/);
  }finally{if(prior===undefined)delete process.env.CSS_WEB_ACCESS_TOKEN;else process.env.CSS_WEB_ACCESS_TOKEN=prior}
});
test('owner OAuth cookie path includes both CSS lifecycle and Feishu projects',()=>{
  const cookie=owner.ownerSessionCookie('mock-token',1700000000);
  assert.match(cookie,/Path=\/api;/);
  assert.ok(!cookie.includes('Path=/api/lifecycle'));
});
