"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { DEFAULT_REQUEST, MODES, unitForMode, validateDraft, formatDraft } from "../../../lib/sfdc-oppo-quote.mjs";
import { parseLocalContacts, lookupLocalContacts } from "../../../lib/sfdc-contact-local.mjs";
import { buildContactReviewPacket } from "../../../lib/sfdc-contact-review.mjs";

const pipeline = [
  { label: "Contact / Account", detail: "이메일 정확 일치 · Account 연결 · 중복 확인", state: "검증 필요" },
  { label: "Opportunity", detail: "현재 거래 기준으로 작성 · 생성된 006 ID 확인", state: "미생성" },
  { label: "Research-AMEA Quote", detail: "Quote 필수값 · 가격 · a0P–006 연결 검증", state: "미생성" },
];

export default function OppoQuoteCommandPage() {
  const [form, setForm] = useState({ ...DEFAULT_REQUEST });
  const [notice, setNotice] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [privateContacts, setPrivateContacts] = useState([]);
  const [isPcLocal, setIsPcLocal] = useState(false);
  const [pcSearchBusy, setPcSearchBusy] = useState(false);
  const [pcReviewBusy, setPcReviewBusy] = useState(false);
  const [liveReview, setLiveReview] = useState("NOT_CHECKED");
  useEffect(() => {
    setIsPcLocal(window.location.hostname === "127.0.0.1");
  }, []);
  const [contactSearchName, setContactSearchName] = useState("");
  const [selectedContactKey, setSelectedContactKey] = useState("");
  const [localStatus, setLocalStatus] = useState("고객 데이터 미연결 · 검색은 로컬 JSON에서만 수행");
  const matchingContacts = useMemo(() => lookupLocalContacts(contactSearchName, privateContacts), [contactSearchName, privateContacts]);
  const selectedContact = useMemo(() =>
    matchingContacts.find(row => row.contact_id + "|" + row.account_id === selectedContactKey) ?? null,
    [matchingContacts, selectedContactKey]);
  const result = useMemo(() => validateDraft(form), [form]);
  const identityBound = Boolean(result.ok && selectedContact && selectedContact.contact_email === form.contact_email);
  const preview = result.ok ? formatDraft(form) : "";
  const set = (key, value) => {
    setLiveReview("NOT_CHECKED");
    setNotice("");
    setShowPreview(false);
    setForm(prev => ({ ...prev, [key]: value }));
  };
  const loadContacts = async event => {
    const file = event.target.files?.[0];
    setSelectedContactKey("");
    setLiveReview("NOT_CHECKED");
    setForm(prev => ({ ...prev, contact_email: "" }));
    setShowPreview(false);
    setPrivateContacts([]);
    if (!file) return;
    try {
      if (file.size > 2_000_000) throw Error("2MB 이하 JSON 파일만 허용됩니다.");
      const rows = parseLocalContacts(await file.text());
      setPrivateContacts(rows);
      setLocalStatus(`로컬 후보 ${rows.length}건 읽음 · 실제 Salesforce 검증 전`);
    } catch {
      setLocalStatus("JSON 형식/필드 검증 실패 · 후보를 불러오지 않았습니다.");
    }
    event.target.value = "";
  };
  const searchPcContacts = async () => {
    if (!isPcLocal || pcSearchBusy) return;
    const name = contactSearchName.normalize("NFKC").trim();
    if (!/^[\uac00-\ud7a3]{2,6}$/.test(name)) {
      setLocalStatus("정확한 한글 고객 이름(2~6자)을 입력하세요.");
      return;
    }
    setPcSearchBusy(true);
    setLiveReview("NOT_CHECKED");
    setSelectedContactKey("");
    setForm(prev => ({...prev, contact_email:""}));
    setShowPreview(false);
    setPrivateContacts([]);
    try {
      const response = await fetch("/api/sfdc/contact-candidates-local?name=" + encodeURIComponent(name), {
        method:"GET",cache:"no-store",credentials:"omit",
        headers:{"X-SFDC-Local-Preview":"1"},
      });
      if (!response.ok) throw new Error("local API not enabled");
      const data=await response.json();
      if (data.status !== "LOCAL_VERIFIED_SNAPSHOT_NOT_LIVE_SALESFORCE" || data.name !== name ||
          !Array.isArray(data.candidates)) throw new Error("unexpected local response");
      const rows=parseLocalContacts(JSON.stringify(data.candidates));
      setPrivateContacts(rows);
      setLocalStatus(`업무용 PC의 비공개 목록에서 ${rows.length}건 조회 · Salesforce 실시간 재검증은 별도 필요`);
    } catch {
      setLocalStatus("PC 로컬 고객 조회가 비활성화되어 있습니다. 비공개 JSON을 직접 선택하세요.");
    } finally {
      setPcSearchBusy(false);
    }
  };
  const chooseContact = key => {
    const matches = matchingContacts.filter(row => row.contact_id + "|" + row.account_id === key);
    if (matches.length !== 1) return;
    setLiveReview("NOT_CHECKED");
    setSelectedContactKey(key);
    set("contact_email", matches[0].contact_email);
    setLocalStatus("연락처 후보 선택 완료 · Salesforce 실시간 신원 확인은 아직 필요");
  };
  const changeMode = mode => {
    setLiveReview("NOT_CHECKED");
    setNotice("");
    setShowPreview(false);
    setForm(prev => ({ ...prev, sequencing_mode: mode, depth_unit: unitForMode(mode) }));
  };
  const reset = () => {
    setForm({ ...DEFAULT_REQUEST });
    setPrivateContacts([]);
    setContactSearchName("");
    setSelectedContactKey("");
    setLiveReview("NOT_CHECKED");
    setLocalStatus("고객 데이터 미연결 · 검색은 로컬 JSON에서만 수행");
    setShowPreview(false);
    setNotice("");
  };
  const copy = async () => {
    if (!result.ok) return setNotice(result.errors[0]);
    try {
      await navigator.clipboard.writeText(preview);
      setNotice("검토용 명령서를 복사했습니다. Salesforce에는 전송하지 않았습니다.");
    } catch {
      setShowPreview(true);
      setNotice("자동 복사를 사용할 수 없습니다. 아래 명령서를 직접 복사하세요.");
    }
  };
  const downloadDraft = () => {
    if (!result.ok) return setNotice(result.errors[0]);
    const blob = new Blob([preview], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    try {
      const link = document.createElement("a");
      link.href = url;
      link.download = "sfdc-oppo-quote-private-draft.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setNotice("검토용 JSON을 이 PC에 저장했습니다. 서버나 Salesforce에는 전송하지 않았습니다.");
    } finally {
      URL.revokeObjectURL(url);
    }
  };
  const downloadReviewPacket = () => {
    if (!identityBound) {
      setNotice("검증된 목록에서 고객을 선택하고, 선택한 이메일을 유지해야 PC 검토 패킷을 만들 수 있습니다.");
      return;
    }
    try {
      const packet = buildContactReviewPacket(form, selectedContact);
      const blob = new Blob([JSON.stringify(packet, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "sfdc-oppo-quote-contact-review-private.json";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setNotice("Contact ID가 포함된 PC 검토 패킷을 이 브라우저에서 저장했습니다. Salesforce 전송이나 저장은 수행하지 않았습니다.");
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "PC 검토 패킷 생성 실패");
    }
  };
  const reviewCurrentContactLive = async () => {
    if (!isPcLocal || !identityBound || pcReviewBusy) {
      setNotice("이 PC의 검증된 Contact를 먼저 선택해야 합니다.");
      return;
    }
    setPcReviewBusy(true);
    setLiveReview("VERIFYING");
    setNotice("현재 Salesforce의 Contact·Account·Opportunity 관계를 읽기 전용으로 확인 중입니다.");
    try {
      const packet=buildContactReviewPacket(form,selectedContact);
      const response=await fetch("/api/sfdc/review-local",{
        method:"POST",cache:"no-store",credentials:"omit",
        headers:{"Content-Type":"application/json","X-SFDC-Local-Preview":"1"},
        body:JSON.stringify(packet),
      });
      const result=await response.json();
      if (!response.ok || result.status!=="LIVE_CONTACT_IDENTITY_CONFIRMED_NO_SAVE" ||
          result.live_identity_verified!==true || result.save_allowed!==false) {
        setLiveReview("HOLD");
        setNotice("실시간 신원 검증 HOLD · CRM 저장 없음. 비공개 목록과 Salesforce Contact 상세를 다시 확인하세요.");
      } else {
        setLiveReview("VERIFIED");
        setNotice("현재 Salesforce Contact·Account·Opportunity 관계 PASS. Product·금액·중복 Quote 검증 및 Save는 계속 차단됩니다.");
      }
    } catch {
      setLiveReview("HOLD");
      setNotice("업무용 PC 읽기 전용 조회 실패 · Salesforce 저장 작업은 수행하지 않았습니다.");
    } finally {
      setPcReviewBusy(false);
    }
  };
  const changeEmail = value => {
    setSelectedContactKey("");
    set("contact_email", value);
    if (privateContacts.length) setLocalStatus("이메일을 직접 변경했습니다. ID 기반 검토는 고객을 다시 선택해야 합니다.");
  };
  const prepare = event => {
    event.preventDefault();
    setShowPreview(true);
    setNotice(result.ok ? "입력 검증 완료. Contact·Account와 견적 조건이 확인되기 전까지 저장 요청은 차단됩니다." : result.errors[0]);
  };

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.breadcrumb}>
            <Link href="/">MasterOS</Link>
            <span>/</span><span>Sales</span><span>/</span><strong>Oppo + Quote</strong>
          </div>
          <div className={styles.headerBottom}>
            <div>
              <p className={styles.eyebrow}>SFDC · COMMAND WORKSPACE</p>
              <h1>Opportunity + Quotation</h1>
              <p className={styles.subhead}>서비스 조건을 입력하고 검증 가능한 생성 명령서를 준비합니다. 실제 CRM 저장은 아직 활성화되지 않았습니다.</p>
            </div>
            <div className={styles.statusPill}>검토용 초안 · No Save</div>
          </div>
        </header>

        <div className={styles.banner} role="status">
          <span className={styles.bannerIcon}>!</span>
          <span>클라우드에는 고객 정보를 전송하지 않습니다. PC에서 ‘실시간 신원 재확인’을 누르는 경우에만 이 PC의 로컬 검증 서버로 고객 정보가 전달되며, Salesforce 조회만 수행합니다. CRM Save는 차단됩니다.</span>
        </div>

        <div className={styles.grid}>
          <section className={styles.panel}>
            <div className={styles.panelHeader}><span className={styles.stepNo}>01</span><div><h2>요청 조건</h2><p>단일 PMP 서비스 · 샘플별 데이터량</p></div></div>
            <form onSubmit={prepare}>
              <div className={styles.localLookup}>
                <strong>고객 이름으로 검색 · PC 로컬 / 비공개 JSON</strong>
                <p>업무용 PC 로컬 미리보기에서는 검증된 목록을 바로 검색할 수 있습니다. 외부 Preview는 비공개 JSON 파일을 브라우저에서만 읽으며, 어느 쪽도 Salesforce를 직접 수정하지 않습니다.</p>
                <div className={styles.field}>
                  <label htmlFor="sfdc-local-contact-file">Contact 목록 JSON 선택</label>
                  <input id="sfdc-local-contact-file" type="file" accept=".json,application/json" onChange={loadContacts} />
                </div>
                <div className={styles.field}>
                  <label htmlFor="sfdc-contact-name">한글 고객 이름 (정확 일치)</label>
                  <input id="sfdc-contact-name" value={contactSearchName} autoComplete="off"
                    placeholder="예: 김민수" onChange={e => {
                      setContactSearchName(e.target.value);
                      setLiveReview("NOT_CHECKED");
                      setSelectedContactKey("");
                      set("contact_email", "");
                    }} />
                </div>
                {isPcLocal && <div className={styles.pcLookupActions}>
                  <button type="button" className={styles.pcSearchButton} onClick={searchPcContacts}
                    disabled={pcSearchBusy}>{pcSearchBusy ? "PC 고객 검색 중…" : "이 PC에서 한글 고객 검색"}</button>
                  <small>127.0.0.1 전용 · 검증된 로컬 기록만 조회 · No Save</small>
                </div>}
                {matchingContacts.length > 0 && <div className={styles.field}>
                  <label htmlFor="sfdc-contact-candidate">고객 선택 · 동명이인은 기관과 Contact ID 구분</label>
                  <select id="sfdc-contact-candidate" value={selectedContactKey}
                    onChange={e => chooseContact(e.target.value)}>
                    <option value="">기관·Contact 확인 후 선택</option>
                    {matchingContacts.map(row => <option key={row.contact_id + "|" + row.account_id}
                      value={row.contact_id + "|" + row.account_id}>
                      {row.institution} · {row.name} · Contact …{row.contact_id.slice(-4)}
                    </option>)}
                  </select>
                </div>}
                {selectedContact && <div className={styles.identityCard} aria-label="선택한 Contact">
                  <strong>{selectedContact.name} · {selectedContact.institution}</strong>
                  <span>Contact …{selectedContact.contact_id.slice(-4)} · Account …{selectedContact.account_id.slice(-4)}</span>
                  <span>기존 Opportunity {selectedContact.opportunity_ids.length}건 · 로컬 후보 (실시간 Salesforce 재검증 필요)</span>
                  {isPcLocal && <button type="button" className={styles.pcSearchButton}
                    disabled={!identityBound || pcReviewBusy} onClick={reviewCurrentContactLive}>
                    {pcReviewBusy ? "Salesforce 읽기 전용 확인 중…" : "이 PC에서 Salesforce 신원 재확인"}
                  </button>}
                  {liveReview === "VERIFIED" && <span role="status">현재 Contact·Account·Opportunity 관계 PASS · 가격 및 Save 미승인</span>}
                  {liveReview === "HOLD" && <span role="status">실시간 신원 확인 HOLD · 고객 검토 필요</span>}
                </div>}
                <small role="status">{localStatus}</small>
                {privateContacts.length > 0 && contactSearchName && matchingContacts.length === 0 &&
                  <p role="status">기존 Opportunity가 있는 일치 고객이 없습니다. 다른 이름 또는 실제 Salesforce 목록을 확인하세요.</p>}
              </div>
              <div className={styles.field}>
                <label htmlFor="sfdc-contact-email">고객 이메일</label>
                <input id="sfdc-contact-email" type="email" autoComplete="off" required maxLength={255}
                  placeholder="researcher@university.ac.kr" value={form.contact_email}
                  onChange={e=>changeEmail(e.target.value)} />
                <small>이메일 주소는 Account/Contact를 자동 추정하는 근거가 아닙니다.</small>
              </div>
              <div className={styles.two}>
                <div className={styles.field}>
                  <label htmlFor="sfdc-service">서비스</label>
                  <select id="sfdc-service" value={form.service} disabled><option value="PMP">PMP</option></select>
                </div>
                <div className={styles.field}>
                  <label htmlFor="sfdc-mode">시퀀싱</label>
                  <select id="sfdc-mode" value={form.sequencing_mode} onChange={e=>changeMode(e.target.value)}>
                    {MODES.map(mode=><option key={mode} value={mode}>{mode === "PE250" ? "250PE · PE250" : mode}</option>)}
                  </select>
                </div>
              </div>
              <div className={styles.two}>
                <div className={styles.field}>
                  <label htmlFor="sfdc-samples">샘플 수량</label>
                  <input id="sfdc-samples" type="number" min="1" max="500" step="1"
                    value={form.sample_count} onChange={e=>set("sample_count",Number(e.target.value))} required/>
                </div>
                <div className={styles.field}>
                  <label htmlFor="sfdc-depth">샘플당 데이터량</label>
                  <div className={styles.inputWithUnit}>
                    <input id="sfdc-depth" type="number" min="0.0001" max="100000" step="any"
                      value={form.depth_per_sample} onChange={e=>set("depth_per_sample",Number(e.target.value))} required />
                    <span>{form.depth_unit}</span>
                  </div>
                </div>
              </div>
              <div className={styles.rule}>
                <strong>단위 자동 전환</strong><span>250PE → M reads / 그 외 → Gb</span>
              </div>
              <div className={styles.buttons}>
                <button type="submit" className={styles.primary}>검토용 명령서 생성</button>
                <button type="button" className={styles.secondary} onClick={reset}>초기화</button>
              </div>
              {notice && <div className={styles.notice} role="status" aria-live="polite">{notice}</div>}
            </form>
          </section>

          <aside className={styles.right}>
            <section className={styles.panel}>
              <div className={styles.panelHeader}><span className={styles.stepNo}>02</span><div><h2>주문 미리보기</h2><p>수량과 데이터 단위를 분리해 계산</p></div></div>
              <div className={styles.metrics}>
                <div><span>샘플</span><strong>{form.sample_count || "—"}</strong><small>samples</small></div>
                <div><span>샘플당</span><strong>{form.depth_per_sample || "—"}</strong><small>{form.depth_unit}</small></div>
                <div><span>총 명목 데이터량</span><strong>{result.ok ? result.draft.summary.nominal_total_depth.toLocaleString() : "—"}</strong><small>{form.depth_unit}</small></div>
              </div>
              <div className={styles.footnote}>M reads가 reads인지 read pairs인지 아직 미확정입니다. 자동 Gb 변환, 견적 금액 계산 또는 과거 Quote 가격 상속을 하지 않습니다.</div>
              <div className={styles.reviewState}><span className={styles.dot} />{identityBound ? "Contact 후보 선택됨 · 실시간 확인 및 가격 검증 대기" : "Contact 미확인 · 가격 미확인"} · Save 차단</div>
            </section>

            <section className={styles.panel}>
              <div className={styles.panelHeader}><span className={styles.stepNo}>03</span><div><h2>CRM 실행 단계</h2><p>작성보다 연결 검증이 먼저입니다</p></div></div>
              <ol className={styles.pipeline}>
                {pipeline.map((step,i)=><li key={step.label}>
                  <span className={styles.pipelineNumber}>{i+1}</span>
                  <div><strong>{step.label}</strong><p>{step.detail}</p></div>
                  <small>{i === 0 && selectedContact ? "로컬 후보 선택" : step.state}</small>
                </li>)}
              </ol>
              <button className={styles.disabled} disabled title="인증된 작업 큐와 Salesforce 생성 권한 연결 전에는 실행할 수 없습니다.">Salesforce 일괄 생성 · 연결 전</button>
            </section>
          </aside>
        </div>

        {showPreview && result.ok && <section className={styles.output} aria-label="검토용 명령서">
          <div className={styles.outputTop}><div><h2>검토용 JSON 명령서</h2><p>이메일이 포함된 개인정보입니다. 공유 저장소에 업로드하지 마세요.</p></div>
            <div className={styles.buttons}>
              <button type="button" className={styles.reviewButton} onClick={downloadReviewPacket} disabled={!identityBound}
                title={identityBound ? "현재 Contact·Account ID를 PC 검토용으로만 전달합니다." : "로컬 Contact 선택 및 이메일 일치가 필요합니다."}>Contact ID 포함 · PC 검토 패킷 저장</button>
              <button type="button" className={styles.secondary} onClick={downloadDraft}>일반 JSON</button>
              <button type="button" className={styles.secondary} onClick={copy}>복사</button>
            </div></div>
          <pre>{preview}</pre>
        </section>}
        <footer className={styles.footer}>Oppo–Quote · Research-AMEA 시범 워크플로우 · 실제 Salesforce 생성 0건</footer>
      </div>
    </main>
  );
}
