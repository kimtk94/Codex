/** Read-only, browser-local historical pattern advisor. Never writes Salesforce. */
export const PATTERNS=Object.freeze({
 RNA:{label:"mRNA / RNA-Seq",processes:["Library preparation","Sequencing by data amount","Analysis by sample","Data release"],review:"추출·QC 포함 여부 확인"},
 AMPLICON:{label:"16S / Amplicon",processes:["Library preparation","Sequencing by data amount","Analysis by sample","Data release"],review:"증폭·Primer·K tags는 수동 확인"},
 PMP:{label:"PMP / Platform",processes:["Library QC","Sequencing by data amount","Analysis by sample","Data release"],review:"Library QC 여부, Lane/Gb/M reads 검증"},
 PROTEOMICS:{label:"Proteomics / DIA",processes:["Extraction","Peptide","Sequencing by sample","Database searching","Analysis by sample","Data release"],review:"NGS Gb 견적 사용 금지, 공정별 가격 검증"},
 LONG_READ:{label:"PacBio / Long-read",processes:["Library preparation","Sequencing by data amount","Analysis by sample","Data release"],review:"Revio/HiFi/Cell/Gb 등 단위별 확인"},
 SPATIAL:{label:"Single-cell / Spatial",processes:[],review:"데이터가 희소하여 공정 자동 추천 금지"},
 OTHER:{label:"기타/복합 서비스",processes:[],review:"정식 Product 및 프로세스 직접 확인"}
});
export const UNITS=Object.freeze(["Gb","M reads","Lane","K tags","Cell","sample"]);
export const DEFAULT_INPUT=Object.freeze({institution:"",contact:"",identityMode:"KEEP",service:"",samples:"",production:"",basis:"PER_SAMPLE",unit:"Gb",referenceQuote:"",desiredName:"",cloud:"UNKNOWN",status:"SAMPLES_EXPECTED",sampleType:""});
export function nextMonth(date){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(date)))throw Error("INVALID_DATE");
 const [y,m,d]=date.split("-").map(Number);
 if(new Date(Date.UTC(y,m-1,d)).toISOString().slice(0,10)!==date)throw Error("INVALID_DATE");
 const next=new Date(Date.UTC(y,m,1));
 const max=new Date(Date.UTC(next.getUTCFullYear(),next.getUTCMonth()+1,0)).getUTCDate();
 return new Date(Date.UTC(next.getUTCFullYear(),next.getUTCMonth(),Math.min(d,max))).toISOString().slice(0,10);
}
const clean=(s,n)=>typeof s==="string"&&s===s.trim()&&s.length<=n&&!/[\u0000-\u001f]/.test(s);
export function createIntake(inputRaw,dateKst){
 const x={...DEFAULT_INPUT,...inputRaw};
 const missing=[];
 if(!clean(x.institution,100)||x.institution.length<2)missing.push("institution");
 if(!clean(x.contact,70)||x.contact.length<2)missing.push("contact");
 if(!["KEEP","CHANGE"].includes(x.identityMode))missing.push("identityMode");
 if(!PATTERNS[x.service])missing.push("service");
 const samples=Number(x.samples),production=Number(x.production);
 if(x.samples===""||!Number.isInteger(samples)||samples<1||samples>10000)missing.push("samples");
 if(x.production===""||!Number.isFinite(production)||production<=0||production>10000000)missing.push("production");
 if(!["PER_SAMPLE","TOTAL"].includes(x.basis))missing.push("basis");
 if(!UNITS.includes(x.unit))missing.push("unit");
 if(!["YES","NO","UNKNOWN"].includes(x.cloud))missing.push("cloud");
 if(!["SAMPLES_EXPECTED","QUOTE_REQUESTED","SAMPLES_RECEIVED_CONFIRMED"].includes(x.status))missing.push("status");
 for(const k of ["referenceQuote","desiredName","sampleType"])if(!clean(x[k],180))missing.push(k);
 const total=missing.some(k=>["samples","production","basis","unit"].includes(k))?null:
   {value:x.basis==="PER_SAMPLE"?Number((samples*production).toFixed(8)):production,unit:x.unit};
 const name=x.desiredName||(!missing.some(k=>["institution","service","samples"].includes(k))?
   "Korea-"+x.institution+"-"+x.service+"-"+samples+"samples":"");
 const pattern=PATTERNS[x.service];
 return {
  version:"sfdc-oppo-quote-general-intake-v1",
  status:missing.length?"HOLD_REQUIRED_INPUT":"HOLD_SFDC_ID_PRODUCT_PRICE_APPROVAL",
  missing,
  input:x,
  suggested:{
   opportunityName:name,quotationName:name,closeDateKst:nextMonth(dateKst),
   productionTotal:total,
   alicloudQuantity:total&&total.unit==="Gb"&&x.cloud==="YES"?Math.ceil(total.value/100):null,
   alicloudStatus:x.cloud==="NO"?"NOT_REQUESTED":x.cloud==="UNKNOWN"?"HOLD_CLOUD_REQUIREMENT":total?.unit==="Gb"?"PROVISIONAL_GB_RULE":"HOLD_NOT_GB",
   historicalProcesses:pattern?.processes||[],
   historicalNote:pattern?.review||"NO_VERIFIED_SERVICE",
   historicalSource:"2026-11-15 QQ REPORT AGGREGATE; NOT LIVE SFDC PRODUCT",
   referenceQuoteState:x.referenceQuote?"USER_REFERENCE_UNVERIFIED":"NONE",
   productId:null,contactId:null,accountId:null,pricePerProcess:null,pack:null,
   currency:"KRW_REQUIRES_CURRENT_SFDC_CONFIRMATION",vatRate:0.10,
   progressDescription:"MUST_WRITE_NEWLY_FROM_VERIFIED_FACTS",
   stage:"REQUIRES_CURRENT_SFDC_SELECTION"
  },
  requiredChecks:[
   "ACCOUNT_001_CONTACT_003_LIVE_READBACK","OPPORTUNITY_006_QUOTE_A0P_NATIVE_ID_AND_DUPLICATE_RECHECK",
   "ACTUAL_PRODUCT_ID_AND_PROCESS_OPTIONS","PROCESS_QUANTITIES_PRICES_DISCOUNTS_AND_CURRENCY",
   "PACK_SAMPLE_GROUPING","ALICLOUD_TOTAL_GB_AND_UNIT","CURRENT_PROGRESS_DESCRIPTION_NOT_CLONED",
   "NAME_STAGE_CLOSE_DATE_VAT","PER_RECORD_APPROVAL_BEFORE_ANY_SAVE"
  ],
  salesforceSaveAllowed:false,crmWrites:0,opportunityCreated:false,quotationCreated:false
 };
}
