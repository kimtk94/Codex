/** Korea-local defaults for a NEW Opportunity (not a historical clone).
 * Calendar-month addition clamps dates such as Jan 31 to Feb 28/29.
 */
export function kstDateParts(now=new Date()){
  const date=now instanceof Date?now:new Date(now);
  if(Number.isNaN(date.getTime()))throw Error("KST_DATE_INVALID");
  const p=new Intl.DateTimeFormat("en-US",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"
  }).formatToParts(date);
  const values=Object.fromEntries(p.filter(x=>["year","month","day"].includes(x.type)).map(x=>[x.type,Number(x.value)]));
  if(!values.year||!values.month||!values.day)throw Error("KST_DATE_INVALID");
  return values;
}
const iso=(y,m,d)=>[String(y).padStart(4,"0"),String(m).padStart(2,"0"),String(d).padStart(2,"0")].join("-");
export function kstToday(now=new Date()){
  const {year,month,day}=kstDateParts(now);
  return iso(year,month,day);
}
export function kstOneCalendarMonthLater(now=new Date()){
  const {year,month,day}=kstDateParts(now);
  const nextYear=year+(month===12?1:0);
  const nextMonth=month===12?1:month+1;
  const lastDay=new Date(Date.UTC(nextYear,nextMonth,0)).getUTCDate();
  return iso(nextYear,nextMonth,Math.min(day,lastDay));
}
export const EXPECTED_SAMPLE_STAGE="SAMPLES_EXPECTED_NOT_RECEIVED";
export function expectedSampleStatement(){
  return "Samples expected soon; sample receipt, QC and PO are not confirmed.";
}
