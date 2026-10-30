'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'mail-queue.html'),'utf8');
const js=fs.readFileSync(path.join(root,'mail-queue.js'),'utf8');

test('review queue is linked from canonical dashboard and script parses',()=>{
  const home=fs.readFileSync(path.join(root,'index.html'),'utf8');
  assert.match(home,/href="\/mail-queue\.html"/);
  assert.match(html,/<script src="\/mail-queue\.js" defer><\/script>/);
  assert.doesNotThrow(()=>new vm.Script(js));
  for(const id of ['rows','excludedRows','prev','next','search','sort',
    'pageSize','syncState','reviewDialog','choice','confirmReview','bodyDialog'])
    assert.ok(html.includes('id="'+id+'"'),id);
});
test('manual review uses only owner-approved, same-origin API, never auto-sends',()=>{
  assert.match(js,/\/api\/lifecycle\/review/);
  assert.match(js,/manualMailReview===true/);
  assert.match(js,/window\.confirm/);
  assert.match(js,/X-CSS-Review-Confirm/);
  assert.match(js,/credentials:'same-origin'/);
  assert.match(js,/expectedDecision:selection\.expectedDecision/);
  assert.doesNotMatch(js,/fetch\([^)]*\/api\/send/);
  assert.doesNotMatch(html,/type="submit"/);
});
test('no private data in HTML or untrusted link destinations',()=>{
  assert.doesNotMatch(html,/@[a-z0-9.-]+\.(?:com|edu|ac\.kr)/i);
  assert.doesNotMatch(js,/innerHTML|outerHTML|insertAdjacentHTML/);
  const links=[...html.matchAll(/href="([^"]+)"/g)].map(x=>x[1]);
  assert.deepEqual(links,['/']);
});
test('pagination and sorting work offline in disabled review mode',async()=>{
  const nodes=new Map();
  class Node {
    constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];
      this.listeners={};this.style={};this.value=tag==='select'?'25':'';
      this.disabled=false;this.textContent='';this.nodeType=1;
      this.open=false;}
    addEventListener(name,fn){this.listeners[name]=fn;}
    replaceChildren(...parts){this.children=parts;}
    append(...parts){this.children.push(...parts);}
    appendChild(part){this.children.push(part);}
    showModal(){this.open=true;}
    close(){this.open=false;}
    trigger(name){return this.listeners[name]?.();}
  }
  const ids=['reload','search','sort','pageSize','prev','next','syncState','range','mode',
    'unansweredCount','excludedCount','selectedCount','rows','excludedRows',
    'reviewDialog','reviewDescription','choice','confirmReview','cancelReview',
    'bodyDialog','bodySubject','bodyMeta','bodyText','closeBody'];
  for(const id of ids)nodes.set(id,new Node());
  nodes.get('sort').value='days';
  const inbox=Array.from({length:60},(_,i)=>({
    uid:'inbox:'+(100+i),days:i,priority:'MONITOR',sender:'client'+i+'@example.edu',
    subject:'Subject '+i,project:'Proj',body:'Body '+i,
    received:'2026-10-30T10:00:00'
  }));
  const snapshot={inbox,reviews:[],capabilities:{manualMailReview:false},refreshed:'latest'};
  const calls=[],opens=[];
  const ctx={document:{getElementById:id=>nodes.get(id),createElement:t=>new Node(t)},
    navigator:{clipboard:{writeText:async()=>{}}},window:{
      open:url=>opens.push(url),confirm:()=>{throw Error('no confirm allowed')}},
    fetch:async(...args)=>{calls.push(args);return {ok:true,json:async()=>snapshot};},
    console};
  vm.runInNewContext(js,ctx);
  await new Promise(r=>setImmediate(r));
  assert.equal(nodes.get('rows').children.length,25);
  assert.equal(nodes.get('unansweredCount').textContent,'60');
  assert.match(nodes.get('range').textContent,/1–25 \/ 60/);
  nodes.get('next').trigger('click');
  assert.equal(nodes.get('rows').children.length,25);
  assert.match(nodes.get('range').textContent,/26–50 \/ 60/);
  nodes.get('search').value='client59@';
  nodes.get('search').trigger('input');
  assert.equal(nodes.get('rows').children.length,1);
  assert.match(nodes.get('range').textContent,/1–1 \/ 1/);
  const action=nodes.get('rows').children[0].children.at(-1).children.at(-1);
  action.trigger('click');
  assert.equal(opens.length,1);
  assert.equal(opens[0],'https://docs.google.com/spreadsheets/d/1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI/edit');
  assert.ok(calls.every(([url,options])=>url==='/api/lifecycle'&&options.credentials==='same-origin'));
});
