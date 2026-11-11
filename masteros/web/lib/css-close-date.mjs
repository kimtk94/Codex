/** Date-only SFDC Close Date: one calendar month after the current KST date.
 * Clamp 31st to last day when the next month is shorter; never use UTC day.
 */
export function closeDateOneMonthFromKst(now=new Date()){
  if(!(now instanceof Date)||!Number.isFinite(now.getTime()))throw Error("DATE_INVALID");
  const parts=new Intl.DateTimeFormat("en-US",{
    timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"
  }).formatToParts(now);
  const value=Object.fromEntries(parts.map(x=>[x.type,Number(x.value)]));
  const y=value.year,m=value.month,d=value.day;
  const month=m===12?1:m+1,year=m===12?y+1:y;
  const last=new Date(Date.UTC(year,month,0)).getUTCDate();
  return year+"-"+String(month).padStart(2,"0")+"-"+String(Math.min(d,last)).padStart(2,"0");
}
