"use client";

import {useEffect,useMemo,useState} from "react";
import styles from "./IdentityPicker.module.css";
import {dedupeAccounts,normalizeIdentityRows,selectIdentityPair}
  from "../../../lib/sfdc-identity-picker.mjs";

async function findIdentities(query,signal){
  const response=await fetch("/api/sfdc/feishu-report-local",{
    method:"POST",cache:"no-store",credentials:"omit",signal,
    headers:{"Content-Type":"application/json","X-SFDC-Command":"1"},
    body:JSON.stringify({mode:"IDENTITY_SEARCH",query,limit:25})
  });
  const value=await response.json();
  if(!response.ok||value.status!=="PASS"||!Array.isArray(value.rows))
    throw Error(value.code||"IDENTITY_SOURCE_UNAVAILABLE");
  return normalizeIdentityRows(value.rows);
}

export default function IdentityPicker({account,contact,onAccount,onContact,disabled=false}){
  const [accountQuery,setAccountQuery]=useState("");
  const [contactQuery,setContactQuery]=useState("");
  const [accountRows,setAccountRows]=useState([]);
  const [contactRows,setContactRows]=useState([]);
  const [accountStatus,setAccountStatus]=useState("IDLE");
  const [contactStatus,setContactStatus]=useState("IDLE");
  const [open,setOpen]=useState("");
  useEffect(()=>{
    const query=(open==="account"?accountQuery:contactQuery).trim();
    if(!open||query.length<1||disabled)return;
    const ctl=new AbortController();
    const timer=setTimeout(async()=>{
      const setStatus=open==="account"?setAccountStatus:setContactStatus;
      const setRows=open==="account"?setAccountRows:setContactRows;
      setStatus("LOADING");
      try{setRows(await findIdentities(query,ctl.signal));setStatus("PASS");}
      catch(err){if(!ctl.signal.aborted){setRows([]);setStatus(err.message||"SOURCE_UNAVAILABLE");}}
    },320);
    return ()=>{clearTimeout(timer);ctl.abort()};
  },[open,accountQuery,contactQuery,disabled]);
  const accounts=useMemo(()=>dedupeAccounts(accountRows),[accountRows]);
  const matchedContacts=useMemo(()=>contactRows.filter(r=>r.account_name&&r.contact_name),[contactRows]);
  const changeAccount=(row)=>{
    if(disabled)return;
    onAccount({id:row.account_id,name:row.account_name,
      sourceQid:row.source_qid});
    setOpen("");setAccountQuery("");setAccountRows([]);
  };
  const changeContact=(row)=>{
    if(disabled)return;
    const selected=selectIdentityPair(row);
    if(!selected.ok)return;
    onContact(selected);
    setOpen("");setContactQuery("");setContactRows([]);
  };
  return <div className={styles.wrapper} aria-label="기관 및 고객 검색 선택">
    <div className={styles.selected}>
      <div><small>선택된 기관 (Account)</small><b>{account?.name||"기관 미선택"}</b>
        <small>{account?.id||"SFDC ID 미확인"}</small></div>
      <div><small>선택된 고객 (Contact)</small>
        <b>{contact?.name||"고객 미선택"} · {account?.name||"기관 미선택"}</b>
        <small>{contact?.id||"SFDC Contact ID 미확인"} · {contact?.email||"이메일 미확인"}</small></div>
    </div>
    <div className={styles.searchGroup}>
      <label>기관 이름 검색 후 선택
        <input aria-label="기관 검색" value={accountQuery} disabled={disabled}
          placeholder="예: 연세대학교"
          onChange={e=>{setAccountQuery(e.target.value);setOpen("account");setAccountRows([])}}/>
      </label>
      {open==="account"&&accountQuery.trim()&&<div className={styles.results} aria-label="기관 검색 결과">
        <small>참고 Quote에 연결된 Account · {accountStatus==="LOADING"?"검색 중":accountStatus==="PASS"?"결과 "+accounts.length+"개":accountStatus}</small>
        {accounts.map(row=><button key={row.account_id+"|"+row.account_name} type="button"
          onClick={()=>changeAccount(row)} disabled={disabled}>
          <strong>{row.account_name}</strong>
          <small>{row.account_id||"CRM Account ID 미확인"} · 참고 {row.source_qid}</small>
        </button>)}
        {accountStatus==="PASS"&&!accounts.length&&<p>일치하는 기관이 없습니다. 기관명 일부로 다시 검색하세요.</p>}
      </div>}
      <label>고객 이름 검색 후 선택
        <input aria-label="고객 검색" value={contactQuery} disabled={disabled}
          placeholder="예: 김지훈 · 이름 검색 시 기관명 반드시 표시"
          onChange={e=>{setContactQuery(e.target.value);setOpen("contact");setContactRows([])}}/>
      </label>
      {open==="contact"&&contactQuery.trim()&&<div className={styles.results} aria-label="기관명 포함 고객 검색 결과">
        <small>고객 검색 결과 · 이름과 기관은 반드시 함께 표시</small>
        {matchedContacts.map(row=><button key={[
          row.account_id,row.account_name,row.contact_id,row.contact_name,row.contact_email
        ].join("|")} type="button" onClick={()=>changeContact(row)} disabled={disabled}>
          <strong>{row.contact_name} · {row.account_name}</strong>
          <small>기관: {row.account_name} · 이메일: {row.contact_email||"미확인"}</small>
          <small>{row.contact_id||"SFDC Contact ID 미확인"} · 참고 {row.source_qid}
            {row.crm_account_verified&&row.crm_contact_verified?" · CRM ID 있음":" · CRM 재검증 필요"}</small>
        </button>)}
        {contactStatus==="PASS"&&!matchedContacts.length&&<p>일치하는 기관·고객 쌍이 없습니다. 이름을 다시 검색하세요.</p>}
        {contactStatus!=="PASS"&&<p>{contactStatus==="LOADING"?"검색 중":contactStatus}</p>}
      </div>}
    </div>
    <p className={styles.hint}>고객을 선택하면 연결된 기관도 함께 선택됩니다. 동명이인은 기관명으로 구별하세요.
      과거 Quote의 Account·Contact는 참고값이며, 실제 CRM 관계는 저장 전에 재검증해야 합니다.</p>
  </div>;
}
