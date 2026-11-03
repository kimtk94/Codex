"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { DEFAULT_REQUEST, MODES, unitForMode, validateDraft } from "../../../lib/sfdc-oppo-quote.mjs";
import { validateKoreanNameQuery, auditContactCandidates, selectExistingContact, createContactLinkedNoSaveCommand } from "../../../lib/sfdc-contact-first-command.mjs";

const pipeline = [
  { label: "Contact / Account", detail: "이메일 정확 일치 · Account 연결 · 중복 확인", state: "검증 필요" },
  { label: "Opportunity", detail: "현재 거래 기준으로 작성 · 생성된 006 ID 확인", state: "미생성" },
  { label: "Research-AMEA Quote", detail: "Quote 필수값 · 가격 · a0P–006 연결 검증", state: "미생성" },
];

export default function OppoQuoteCommandPage() {
  const [form, setForm] = useState({ ...DEFAULT_REQUEST });
  const [koreanName, setKoreanName] = useState("");
  const [searchNotice, setSearchNotice] = useState("");
  const [contactCandidates, setContactCandidates] = useState(null);
  const [selectedContact, setSelectedContact] = useState(null);
  const [notice, setNotice] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const result = useMemo(() => validateDraft(form), [form]);
  const candidateReview = useMemo(() => auditContactCandidates(koreanName, contactCandidates), [koreanName, contactCandidates]);
  const linkedDraft = selectedContact?.ok
    ? createContactLinkedNoSaveCommand(form, selectedContact)
    : { ok: false };
  const preview = linkedDraft.ok ? JSON.stringify(linkedDraft.command, null, 2) : "";
  const checkKoreanName = () => {
    const check = validateKoreanNameQuery(koreanName);
    setSearchNotice(check.ok
      ? "검색어 형식이 확인됐습니다. Salesforce 인증 검색 연결 전이므로 실제 고객 조회는 아직 실행되지 않습니다."
      : check.error);
  };
  const chooseContact = (candidate) => {
    const picked = selectExistingContact(koreanName, contactCandidates, candidate.contact_id, candidate.account_id);
    if (!picked.ok) {
      setSearchNotice("Contact 선택 보류: " + picked.status + ". 기관 내 동명이인은 별도 확인이 필요합니다.");
      return;
    }
    setSelectedContact(picked);
    setForm(prev => ({ ...prev, contact_email: picked.email }));
    setSearchNotice("기존 Contact와 기관 선택 완료. 실행 전 Salesforce에서 ID와 소속 기관을 다시 확인해야 합니다.");
    setShowPreview(false);
  };
  const set = (key, value) => {
    setNotice("");
    setShowPreview(false);
    setForm(prev => ({ ...prev, [key]: value }));
  };
  const changeMode = mode => {
    setNotice("");
    setShowPreview(false);
    setForm(prev => ({ ...prev, sequencing_mode: mode, depth_unit: unitForMode(mode) }));
  };
  const reset = () => {
    setForm({ ...DEFAULT_REQUEST });
    setKoreanName("");
    setSearchNotice("");
    setSelectedContact(null);
    setContactCandidates(null);
    setShowPreview(false);
    setNotice("");
  };
  const copy = async () => {
    if (!linkedDraft.ok) return setNotice("한글 이름으로 검색한 기존 Contact와 기관 선택이 필요합니다.");
    try {
      await navigator.clipboard.writeText(preview);
      setNotice("검토용 명령서를 복사했습니다. Salesforce에는 전송하지 않았습니다.");
    } catch {
      setShowPreview(true);
      setNotice("자동 복사를 사용할 수 없습니다. 아래 명령서를 직접 복사하세요.");
    }
  };
  const prepare = event => {
    event.preventDefault();
    setShowPreview(true);
    setNotice(!selectedContact?.ok
      ? "한글 이름 검색 후 기존 Contact와 소속 기관을 먼저 선택하세요. Salesforce 검색은 아직 미연결입니다."
      : linkedDraft.ok
        ? "검토용 명령서입니다. Contact 재검증 전에는 Salesforce 생성·저장이 금지됩니다."
        : result.errors[0]);
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
              <p className={styles.subhead}>서비스 조건을 입력하고 검증 가능한 생성 명령서를 준비합니다. 실제 CRM 검색·저장은 아직 활성화되지 않았습니다.</p>
            </div>
            <div className={styles.statusPill}>검토용 초안 · No Save</div>
          </div>
        </header>

        <div className={styles.banner} role="status">
          <span className={styles.bannerIcon}>!</span>
          <span>현재는 한글 이름 검색 UI만 준비됐고 실제 Salesforce Contact 검색은 미연결입니다. 고객 정보는 서버나 GitHub Actions에 전송하지 않습니다.</span>
        </div>

        <div className={styles.grid}>
          <section className={styles.panel}>
            <div className={styles.panelHeader}><span className={styles.stepNo}>01</span><div><h2>요청 조건</h2><p>기존 Contact 이름 검색 · 단일 PMP 서비스 · 샘플별 데이터량</p></div></div>
            <form onSubmit={prepare}>
              <div className={styles.field}>
                <label htmlFor="sfdc-contact-name">고객 한글 이름</label>
                <div className={styles.contactSearchRow}>
                  <input id="sfdc-contact-name" type="text" autoComplete="off" maxLength={40}
                    placeholder="예: 김민수" value={koreanName}
                    onChange={e => {
                      setKoreanName(e.target.value);
                      setSearchNotice("");
                      setContactCandidates(null);
                      setSelectedContact(null);
                      setForm(prev => ({ ...prev, contact_email: "" }));
                      setShowPreview(false);
                    }} />
                  <button type="button" className={styles.secondary} onClick={checkKoreanName}>검색어 확인</button>
                </div>
                <small>실제 검색은 기존 Salesforce Contact의 한글 이름 기준으로 진행하며, 동명이인은 기관까지 직접 선택합니다. 현재 검색 연결 전입니다.</small>
                {searchNotice && <div className={styles.notice} role="status">{searchNotice}</div>}
              </div>
              {Array.isArray(contactCandidates) && candidateReview.ok &&
                <div className={styles.contactCandidates} aria-label="고객 검색 결과">
                  <strong>기존 Contact 후보 {candidateReview.exact_match_count}건</strong>
                  {candidateReview.requires_institution_choice &&
                    <small>동명이인입니다. 소속 기관을 확인한 후 해당 Contact를 선택하세요.</small>}
                  {candidateReview.candidates.map(candidate =>
                    <button key={candidate.contact_id} type="button" className={styles.contactCandidate}
                      onClick={() => chooseContact(candidate)}>
                      <span>{candidate.korean_name}</span>
                      <small>{candidate.institution_name}</small>
                    </button>)}
                </div>}
              <div className={styles.field}>
                <label htmlFor="sfdc-contact-email">선택된 Contact 이메일</label>
                <input id="sfdc-contact-email" type="email" autoComplete="off" readOnly
                  placeholder="Contact 검색 및 기관 선택 후 자동 입력" value={form.contact_email} />
                <small>이메일은 선택한 기존 Contact에서만 가져옵니다. 직접 입력하거나 이메일로 고객을 추정하지 않습니다.</small>
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
              <div className={styles.reviewState}><span className={styles.dot} />{selectedContact?.ok ? "Contact 선택됨 · 서버 재검증 필요" : "Contact 미확인"} · 가격 미확인 · Save 차단</div>
            </section>

            <section className={styles.panel}>
              <div className={styles.panelHeader}><span className={styles.stepNo}>03</span><div><h2>CRM 실행 단계</h2><p>작성보다 연결 검증이 먼저입니다</p></div></div>
              <ol className={styles.pipeline}>
                {pipeline.map((step,i)=><li key={step.label}>
                  <span className={styles.pipelineNumber}>{i+1}</span>
                  <div><strong>{step.label}</strong><p>{step.detail}</p></div>
                  <small>{step.state}</small>
                </li>)}
              </ol>
              <button className={styles.disabled} disabled title="인증된 작업 큐와 Salesforce 생성 권한 연결 전에는 실행할 수 없습니다.">Salesforce 일괄 생성 · 연결 전</button>
            </section>
          </aside>
        </div>

        {showPreview && linkedDraft.ok && <section className={styles.output} aria-label="검토용 명령서">
          <div className={styles.outputTop}><div><h2>검토용 JSON 명령서</h2><p>이메일이 포함된 개인정보입니다. 공유 저장소에 업로드하지 마세요.</p></div>
            <button type="button" className={styles.secondary} onClick={copy}>명령서 복사</button></div>
          <pre>{preview}</pre>
        </section>}
        <footer className={styles.footer}>Oppo–Quote · Research-AMEA 시범 워크플로우 · 실제 Salesforce 생성 0건</footer>
      </div>
    </main>
  );
}
