import test from "node:test";
import assert from "node:assert/strict";
import {calculateDraft} from "../lib/sfdc-report-quote-draft.mjs";

const makeDraft=(samples,gb,cloudRate)=>({
 feeMode:"EXCLUDE",
 products:[{
   id:"source-product-1",
   serviceLabel:"mRNA-Seq",
   samples:String(samples),
   productionGb:String(gb),
   sampleUnitKrw:"200000",
   cloudUnitKrw:cloudRate,
   processes:[{name:"Sequencing",processId:"Process-12345678"}]
 }]
});

test("AliCloud quantity is ceil(total Gb / 100), including 150 Gb -> 2",()=>{
 const calc=calculateDraft(makeDraft(3,50,"30000"));
 assert.equal(calc.items[0].cloudUnits,2);
 assert.equal(calc.items[0].cloudUnitKrw,30000);
 assert.equal(calc.items[0].cloudNetKrw,60000);
 assert.equal(calc.netKrw,660000);
});

test("changing sample quantity or Gb recalculates AliCloud without manual input",()=>{
 const first=calculateDraft(makeDraft(2,50,"30000"));
 const changed=calculateDraft(makeDraft(3,50,"30000"));
 assert.equal(first.items[0].cloudUnits,1);
 assert.equal(changed.items[0].cloudUnits,2);
});

test("missing source AliCloud unit price cannot silently become zero cost",()=>{
 const calc=calculateDraft(makeDraft(3,50,""));
 assert.equal(calc.items[0].cloudUnits,2);
 assert.equal(calc.items[0].cloudUnitKrw,null);
 assert.equal(calc.items[0].cloudNetKrw,null);
 assert.equal(calc.items[0].ready,false);
 assert.equal(calc.netKrw,null);
});
