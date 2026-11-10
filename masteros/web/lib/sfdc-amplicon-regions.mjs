/** Strict, provenance-aware Amplicon Region reference parser.
 * N biological samples sequenced in R Regions = N x R sample-region services.
 * A quotation's raw process Sample Quantity is never the biological count.
 */
export const REGION_OPTIONS=[
  {code:"16S_V3V4",label:"16S V3-V4"},
  {code:"16S_V4V5",label:"16S V4-V5"},
  {code:"ARCHAEAL16S_V4V5",label:"Archaeal 16S V4-V5"},
  {code:"ARCHAEAL16S_V4",label:"Archaeal 16S V4"},
  {code:"16S_FULL",label:"16S full-length"},
  {code:"ITS1",label:"ITS1"},
  {code:"ITS2",label:"ITS2"},
  {code:"18S_V4",label:"18S V4"}
];
const str=v=>String(v??"").trim();
const int=v=>/^\d+$/.test(str(v))?Number(v):null;
const byCode=new Map(REGION_OPTIONS.map(x=>[x.code,x]));
function regionCode(raw){
  const clean=str(raw).replace(/[^a-zA-Z0-9]/g,"").toLowerCase();
  const exact={
    "16sv3v4":"16S_V3V4","16sv4v5":"16S_V4V5",
    "archaeal16sv4v5":"ARCHAEAL16S_V4V5",
    "archaeal16sv4":"ARCHAEAL16S_V4",
    "16sfulllength":"16S_FULL","its1":"ITS1","its2":"ITS2",
    "18sv4":"18S_V4"
  };
  return exact[clean]||null;
}
export function inferAmpliconReference(name,lines=[]){
  const original=str(name);
  const seen=[...original.matchAll(/(?:^|-)(\d{1,5})-(Archaeal16Sv4v5|Archaeal16Sv4|16Sv3v4|16Sv4v5|16Sfull[- ]?length|ITS1|ITS2|18Sv4)(?=-|$)/gi)];
  const items=seen.map(x=>({
    count:int(x[1]),code:regionCode(x[2])
  }));
  if(items.length<2||items.some(x=>!x.code||!Number.isSafeInteger(x.count)||x.count<1))
    return {status:"NOT_CONFIRMED",enabled:false,regions:[],samples:""};
  const biological=items[0].count;
  if(items.some(x=>x.count!==biological))
    return {status:"MIXED_SAMPLE_COUNTS",enabled:false,regions:[],samples:""};
  if(new Set(items.map(x=>x.code)).size!==items.length)
    return {status:"DUPLICATE_REGION",enabled:false,regions:[],samples:""};
  const regions=items.map(x=>({...byCode.get(x.code),unitKrw:""}));
  const serviceUnits=biological*regions.length;
  // Process K tags is an independent cross-check, not a new sample count.
  const observed=new Set(lines.filter(x=>/K\s*tags/i.test(str(x.data_unit)))
    .map(x=>Number(x.sample_quantity)).filter(x=>Number.isSafeInteger(x)&&x>0));
  const crosschecked=observed.size===1&&observed.has(serviceUnits);
  return {status:crosschecked?"REGION_SERVICE_UNITS_MATCHED":"REGIONS_IN_REFERENCE_NAME",
    enabled:true,regions,samples:String(biological),
    referenceServiceUnits:crosschecked?serviceUnits:null,sourceQuoteName:original};
}
export function ampliconRegionUnits(samples,regions){
  const count=int(samples);
  if(!Number.isSafeInteger(count)||count<1||count>10000||
     !Array.isArray(regions)||regions.length<1||regions.length>8||
     regions.some(x=>!str(x.code)||!str(x.label))||
     new Set(regions.map(x=>x.code)).size!==regions.length)return null;
  return count*regions.length;
}
export function regionByCode(code){
  const item=byCode.get(str(code));
  return item?{...item,unitKrw:""}:null;
}
