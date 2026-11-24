"""Advisory triage from the finalized canonical project board, not an SLA."""
SIGNAL_FIELDS = ("PM Risk", "PM Issue", "PM Recommended Action")
HIGH_STAGES = {
    "abnormal": ("ABNORMAL", "이상 공정 사유와 해결 담당자 확인"),
    "resending sample": ("SAMPLE_RESEND", "재접수 조건과 고객 일정 확인"),
    "resend samples": ("SAMPLE_RESEND", "재접수 조건과 고객 일정 확인"),
    "sample qc failed": ("SAMPLE_QC_FAILED", "QC 결과와 재접수 또는 조건부 진행 확인"),
    "library qc failed": ("LIB_QC_FAILED", "Library QC 실패 원인과 재진행 일정 확인"),
    "lib qc failed": ("LIB_QC_FAILED", "Library QC 실패 원인과 재진행 일정 확인"),
    "qc failed": ("QC_FAILED", "QC 결과와 대응 방법 확인"),
}
WAIT_STAGES = {
    "awaiting feedback(project start)": ("START_FEEDBACK", "착수 조건과 답변 확인"),
    "awaiting feedback(bi form)": ("BI_FORM_FEEDBACK", "BI 양식과 분석 조건 확인"),
    "waiting po/payment": ("PO_PAYMENT_WAIT", "PO 또는 선결제 조건 확인"),
    "add-seq": ("ADD_SEQ", "추가 시퀀싱 사유와 예상 일정 확인"),
}
PAYMENT_CONFLICTS = {
    "MANUAL_RECEIPT_OUTSTANDING_REVIEW", "MANUAL_RECEIPT_INVOICE_REVIEW",
    "SOURCE_RECEIPT_RECHECK_REQUIRED", "RECEIPT_OUTSTANDING_REVIEW",
}
PHASE_ACTIONS = {
    "01 계약/SIF": "착수 조건과 샘플 준비 일정 확인",
    "02 샘플/QC": "샘플 입고와 QC 결과 확인",
    "03 라이브러리": "Library Prep 및 QC 진행 확인",
    "04 시퀀싱": "시퀀싱 진행과 예상 결과 일정 확인",
    "05 데이터/리포트": "데이터 QC·분석 및 결과 전달 확인",
}


def derive_signals(row):
    """Return only advisory fields. Never mutate input or infer a missed deadline."""
    def get(name):
        return str(row.get(name) or "").strip()

    def result(risk, issue, action):
        return dict(zip(SIGNAL_FIELDS, (risk, issue, action)))

    lane = get("Workflow Lane")
    if lane == "PAID_ARCHIVED":
        return result("CLOSED", "ARCHIVED", "기존 완료 및 입금 검증 기록 보존")
    if lane == "PAYMENT_FOLLOWUP":
        if get("Payment Owner Scope") != "MY_VERIFIED":
            return result("UNKNOWN", "PAYMENT_SCOPE_UNVERIFIED", "결제 담당 범위 원본 확인")
        if get("Payment State") in PAYMENT_CONFLICTS:
            return result("HIGH", "PAYMENT_EVIDENCE_CONFLICT", "최신 Invoice·Outstanding·Receipt 원본 대조")
        return result("MEDIUM", "PAYMENT_FOLLOWUP", "Invoice 및 실제 입금 증빙 확인")
    if lane != "PRODUCTION_ACTIVE":
        return result("UNKNOWN", "LANE_UNVERIFIED", "프로젝트 원본과 관리 범위 확인")
    if get("Completion Evidence") in {
        "PARTIAL_SUBPROJECT_COMPLETION_REVIEW", "MULTIPLE_SUBPROJECTS_COMPLETION_REVIEW",
    }:
        return result("HIGH", "SUBPROJECT_COMPLETION_REVIEW", "하위 프로젝트별 완료 증빙 대조")
    # Match exact observed status strings, not substrings in free text.
    stage = get("Current Stage").casefold()
    if stage in HIGH_STAGES:
        return result("HIGH", *HIGH_STAGES[stage])
    if stage in WAIT_STAGES:
        return result("MEDIUM", *WAIT_STAGES[stage])
    phase = get("Progress Phase")
    if (phase == "01 계약/SIF" and get("Prepayment") != "YES"
            and get("SIF State") in {"NOT_VERIFIED", "NUMBER_ONLY_REVIEW", ""}):
        return result("MEDIUM", "SIF_EVIDENCE_REVIEW", "SIF 필요 여부와 실제 제출 증빙 확인")
    if get("Quote Match State") == "MULTIPLE_QUOTE_REVIEW":
        return result("UNKNOWN", "QUOTE_LINK_REVIEW", "AMEA와 승인 Quote 관계 확인")
    if not stage or phase not in PHASE_ACTIONS:
        return result("UNKNOWN", "PHASE_UNVERIFIED", "현재 공정 원본과 누락 정보 확인")
    return result("MONITOR", "STAGE_MONITOR", PHASE_ACTIONS[phase])
