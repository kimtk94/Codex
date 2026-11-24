# Novogene Project Management Center

> Deployment: [INTEGRATED_RELEASE.md](INTEGRATED_RELEASE.md) defines the single-candidate alternative to the historical stacked PR sequence below. Review and approve one route only; CI is not live verification.

## 목적과 화면

영업 통합 대시보드와 구분하여 동일 Sales Base 안에 프로젝트 전용 native dashboard
`Novogene 프로젝트 관리 센터`를 구성한다. 별도 Base나 프로젝트 레코드의 복제는
하지 않는다. 기존 Sales, Payment, Quote, Revenue 대시보드와 관리 뷰는 유지한다.
신규 페이지는 배포 전 상태이며 실제 생성·렌더링은 아직 확인하지 않았다.

| 영역 | 화면 구성 |
| --- | --- |
| 상단 업무 안내 | 기존 작업대, 오늘 확인, 칸반, 확인 일정, 위험 검토 및 결제/보관으로 이동하는 방법 |
| 핵심 카드 (4) | 보드상 진행 중, 자동 HIGH, 원본 확인 UNKNOWN, 내 담당 결제 확인 |
| 프로젝트 차트 (4) | 공정 분포, 위험 신호, 이슈 유형, SIF |
| 결제 차트 (2) | 내 담당 결제 상태, 상태별 미수금(M KRW) |
| 추가 카드 (3) | 위험 신호 미계산, 내 담당 결제 HIGH, 내 담당 입금 검증 보관 |
| 해석 안내 | 보드 기준 분류, 원본 최신성·위험·금액의 제한 |

기존 [Project Management 안내](PROJECT_MANAGEMENT.md)의 네 관리 뷰를 그대로
사용한다. 공식 Lark CLI v1.0.99의
[텍스트 블록 지원 범위](https://github.com/larksuite/cli/blob/v1.0.99/skills/lark-base/references/lark-base-dashboard-block-config.md#text-%E7%B1%BB%E5%9E%8B%E7%89%B9%E6%AE%8A%E7%BB%93%E6%9E%84)에는 Markdown 링크가 포함되지 않는다.
따라서 자동화는 클릭 불가능한 가짜 바로가기를 생성하지 않는다. 기존 뷰 ID는
[관리 뷰 계약](project_management_setup.py)과 [기존 운영 뷰 계약](sales_home_links.py)
에서 확인한다. 실제 페이지의 클릭 가능한 바로가기와 폴더 위치는 Feishu UI에서
지원 여부를 확인해 별도로 구성한다.

## 자동 위험 신호

기존 `sales_metrics_sync.py`의 프로젝트 board writer가 최종 Workflow Lane 및
Payment State 판정 후 세 필드를 생성한다. 기존 writer가 단일 소유자이며 신규
수집 작업과 정기 예약은 추가하지 않는다. Quote-only 실행은 신규 PM 필드와
위험 뷰의 생성·검증 대상이 아니다. 기존의 다른 공통 metadata 조회는 유지한다.
원래 Next Action, 수동 관리 담당·우선순위·상태·일정·메모, 수동 입금 증빙은 보존한다.

| 자동 필드 | 의미 |
| --- | --- |
| PM Risk | HIGH, MEDIUM, UNKNOWN, MONITOR, CLOSED |
| PM Issue | 판단 근거를 나타내는 고정 이슈 코드 |
| PM Recommended Action | 검토 권장 업무 |

HIGH: 명시적인 Abnormal, QC 실패, 재접수, 하위 프로젝트 완료 근거 충돌 또는
내 담당 결제 증빙 충돌. MEDIUM: 착수·BI Form·PO/payment 대기, Add-seq, 초기 SIF
증빙 확인 또는 내 담당 결제 확인. UNKNOWN: 단계·범위·Quote 관계 검토 필요.
MONITOR: 인식된 공정에서 후속 확인 권장. CLOSED: 기존 완료 및 입금 검증에
따른 보관 상태.

명시적 공정 상태는 정확 일치로만 처리한다. CSS 보드에 해당 상태 문자열이 실제
들어오는 경우에만 적용된다. Prepayment와 늦은 공정은 SIF 미확인만으로 신규
위험 신호를 만들지 않는다. 납기일, 공정 시작일, 결제기한 증거가 없는 경우
지연·연체·SLA 위반을 자동 판단하지 않는다. MONITOR는 정상 납기의 인증이 아니다.
실제 고객 연락 및 상태 변경은 자동 실행하지 않는다.

`04 위험 검토`는 기존 Project Progress Board의 source-owned grid view이며
PRODUCTION_ACTIVE 및 PM Risk=HIGH인 행만 보여준다. 다른 위험도는 PM Risk로
필터링하고, 결제 위험은 기존 내 담당 결제 뷰에서 PM Risk를 확인한다.
기존 관리 상태를 조작해 실제 프로젝트 완료나 입금 완료로 판정할 수 없다.
위험 뷰의 필터는 기존 writer가 검증하고 표시 열·탭 순서는 UI에서 확인한다.
별도 자료 복제나 새 예약은 없다.

보드는 기존 보존 정책을 유지하므로 이전 원본에서 사라진 행도 남아 있을 수 있다.
수치는 보드의 분류이며 최신 원본 인증이 아니다. 아직 위험 필드가 없는 행은
미계산 카드로 표시하고 0/정상으로 간주하지 않는다. 이전 위험 분류가 남은 행은
최신 원본과 다시 대조한다. 결제는 기존 MY_VERIFIED 범위만 차트에 사용하고
미확인 잔액은 0원 확정으로 취급하지 않는다.

## 배포 절차

1. 선행 PR #1044, #1047의 병합 및 본 변경의 오프라인 검증을 확인한다.
2. main의 기존 Sources Unified 운영 동기화가 성공한 뒤 PM 필드 3개와
   위험 뷰 필터, 프로젝트 record readback을 확인한다.
3. main의 **Feishu Project Management Center** workflow를 mode=plan으로 실행한다.
   고정 원본 table ID와 차트에 필요한 필드, 대시보드 목록·설정을 읽기만 한다.
4. 신규 페이지라면 명시적 mode=apply로 생성한다. 기존 동일 제목 페이지가
   있으면 먼저 내용을 검토하고 plan의 dashboard ID를 expected_dashboard_id에 넣는다.
   신규 페이지와 누락 블록만 생성하며 기존 블록의 설정을 수정하거나 삭제하지 않는다.
   잘못된 source, 중복 이름/ID, 설정 차이 또는 불완전한 목록은 실패 처리한다.
   생성 응답 ID와 목록·상세 readback이 일치해야 성공한다.
5. mode=verify에서 구성 계약을 다시 확인한다. 최초 12열 배치가 서버에 의해
   변경됐으면 layout_review를 보고한다. 이후 실제 UI에서 차트 렌더링,
   표시 열, 폴더 위치 및 바로가기를 별도 확인한다.

신규 workflow는 수동 실행만 허용하며 main 이외에는 인증 job이 실행되지 않는다.
PR에서는 offline tests만 실행한다. 신규 owner는 record 쓰기, 기존 dashboard 수정,
삭제, 권한 변경, 고객 연락 및 알림을 수행하지 않는다. 이후 TAT/납기 연동,
실제 완료일, 공정 이력은 검증된 AMEA↔하위 프로젝트 관계 및 일정 증거를 확보한
뒤 확장한다.

## Data connectivity and status checks

The follow-up contract in [PROJECT_DATA_CONTRACT.md](PROJECT_DATA_CONTRACT.md) supersedes the original page's input-coverage assumptions. It separates current-input, retained, and unclassified records, with dedicated connection/status distributions; deploy the latest combined contract, not the earlier page spec alone.
