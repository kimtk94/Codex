# 통합 운영 대시보드와 프로젝트 관리

이 안내는 통합 화면에서 지표를 확인하고 Project Progress Board에서 수동
후속 업무를 관리하는 방법을 설명합니다. 코드 기준은 PR #1044의
`4871d205d0f46838cf75c8ed81f72c75d8141c11`이며, 아래 추가 자동화는 그 위에
제안된 변경입니다. UI 생성과 코드 배포 상태를 별도로 확인해야 합니다.

## 적용 상태와 고정 대상

2026-11-24 UI 저장 후 확인한 메타데이터만 기록합니다. 이 문서에는 실제 고객,
프로젝트 행, 담당자 배정, 금액 집계, 인증 정보가 포함되지 않습니다.

| 항목 | UI 상태 또는 구성 계약 | 코드 상태 |
| --- | --- | --- |
| 통합 대시보드 | `Novogene 통합 운영 대시보드`, ID `blkagqTkkxI8dd8c`에 6개 차트와 안내 3줄 저장 확인. 공정 bar와 `Payment State`별 미수금 SUM 설정도 UI에서 다시 확인했습니다. | 6개 차트의 신규 owner는 아직 main 미배포입니다. 안내는 UI 소유입니다. UI 저장 확인은 owner의 API verify 실행 완료를 뜻하지 않습니다. |
| 프로젝트 원본 | 기존 `Project Progress Board`, ID `tblTZe5tkRUeOHM8`를 유지한 채 `02 영업 업무` 폴더로 이동 완료했습니다. | 새 테이블을 생성하거나 기존 테이블을 교체하지 않습니다. 폴더 위치는 데이터 writer의 조회 조건이 아닙니다. |
| 수동 관리 필드 | 아래 정확한 이름·타입·옵션의 5필드 생성 완료. 사람과 날짜의 기본값은 없으며 담당자·날짜를 추정 입력하지 않았습니다. | helper는 기존 필드 타입과 속성 차이를 확인하며, 새 source write guard는 아직 main 미배포입니다. |
| 관리 뷰 | 아래 4개 뷰를 생성·저장하고 00 → 01 → 02 → 03 순서로 맨 앞에 배치했습니다. 기존 6개 뷰는 전부 유지했습니다. | helper는 고정 view ID·이름·타입을 검사합니다. 그룹·날짜 바인딩·필터는 UI에서 확인했지만 helper 자체는 `UI_MANAGED_NOT_VERIFIED`로 보고합니다. |
| 수동 값 보호와 결제 재검토 | UI 필드 생성만으로 새 상태 전이 로직이 배포되지는 않습니다. | `sales_metrics_sync.py`와 `project_settlement.py`의 보강은 이 변경에 포함됩니다. main 병합 전까지 기존 운영 코드와 구분합니다. |

기존 5개 상세 대시보드와 Home의 기존 7개 shortcut은 유지합니다. 통합 화면은
자주 보는 지표의 입구이며, 상세 근거와 개별 행 확인은 기존 화면에서 합니다.
새 통합 대시보드를 Home shortcut 필터에 임의로 추가하지 않습니다. 그 필터는
별도의 고정 key 계약으로 관리됩니다.

## 통합 대시보드의 지표

아래 제목은 [통합 대시보드 owner](native_overview_dashboard.py)의 정확한
식별 계약입니다. 제목이나 종류를 바꾸면 새 블록을 자동 생성하는 대신 검증을
중단합니다. 블록의 API ID는 해당 고정 대시보드에서 유일한 이름·타입으로
확인하고, 같은 실행 동안 그 ID를 보존합니다. UI의 widget 식별자와 API의
block ID를 서로 대체해서 사용하지 않습니다.

저장 확인한 UI 배치는 상단 안내 블록(높이 192px) 아래의 2열 구성입니다.
첫 줄은 공정/SIF, 둘째 줄은 결제 상태/상태별 미수금, 셋째 줄은
Weekly Quote/Monthly Revenue입니다. 이 배치는 UI 소유이며 신규 owner가
위치나 높이를 다시 적용하지 않습니다.

| 차트 제목 | 원본과 범위 | 읽는 방법 |
| --- | --- | --- |
| 진행 중 AMEA 프로젝트 · 공정별 | Project Progress Board의 `Workflow Lane=PRODUCTION_ACTIVE`, `Progress Phase`별 건수 | 공정 분포입니다. 낮은 진행률이 높은 업무 우선순위를 뜻하지 않습니다. |
| SIF 상태 | 같은 진행 중 프로젝트 범위의 `SIF State`별 건수 | SIF 상태를 확인합니다. Prepayment 면제 등 원본 규칙을 유지합니다. |
| 결제 대기 상태 분포 | Project Progress Board의 `PAYMENT_FOLLOWUP`이면서 `Payment Owner Scope=MY_VERIFIED`인 행 | `Payment State`별 AMEA 프로젝트 건수입니다. 새 수동 `관리 담당` 필드로 원본 결제 담당 범위가 바뀌지 않습니다. |
| 결제 대기 프로젝트 미수금 (M KRW) | 위 결제 범위의 `Payment State`별 `Outstanding Balance M KRW` 합계 | 백만원 단위로 상태별 잔액 규모를 비교합니다. 프로젝트별 상세는 기존 결제 대시보드에서 확인합니다. 빈 잔액은 미확인이며 0원 확정으로 해석하지 않습니다. |
| KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD) | Weekly Quote Review의 기존 Active·승인·제외 체크 조건 | 최근 완료 4주와 이번 주의 건수 및 계산 USD 추정치입니다. Quote 추정치를 Tax Invoice Revenue와 합산하지 않습니다. |
| 월별 Revenue · VAT 제외 · M KRW (K USD) | 기존 Monthly Tax Invoice의 월별 순액 | 공식 Tax Invoice 원본의 수신월 기준이며 VAT를 제외합니다. K USD는 보고용 환산값입니다. 입금 완료나 회계상 매출 인식을 뜻하지 않습니다. |

UI 안내의 첫 제목 줄은 **운영 지표 확인 안내**이며, 아래 3줄 문안이 저장되어
있습니다. 코드의 `NOTE`는 이 문안의 reference일 뿐입니다. UI RichText의
첫 줄이 API block name/type과 같다는 근거가 없으므로, 안내의 이름·종류·본문은
자동 읽기 검증이나 수정 대상에서 제외합니다.

> 프로젝트는 진행 중 AMEA 건수입니다. 결제는 내 담당·원천 확인분이며 빈 잔액은 미확인입니다.
>
> 견적은 Active·승인·제외 해제 건의 추정치입니다. 월별 Tax Invoice는 VAT 제외·수신월 기준이며 입금 완료나 회계상 매출 인식이 아닙니다.
>
> Revenue의 K USD는 1 USD=1,500 KRW 표시 환산입니다. 화면 갱신과 원본 최신성은 별개이며 상세 근거는 세부 화면에서 확인하세요.

Native 차트는 기존 테이블을 직접 읽습니다. 수동 체크 변경과 Feishu 화면
캐시 반영은 별개일 수 있습니다. 차트가 보이거나 메타데이터 verify가 성공해도
원본 파일·메일 수집이 최신이라는 증거는 아닙니다. 원본 최신성은 기존
[운영 아키텍처 안내](ARCHITECTURE.md)의 source/sink 확인 절차를 따릅니다.

## 사람이 관리하는 다섯 필드

수동 업무는 canonical Project Progress Board에 기록합니다. Quote별 파생
운영 테이블은 source lane에서 빠진 행을 정리할 수 있으므로, 유일한 수동
메모·담당자·확인일을 그 파생 행에 보관하지 않습니다.

| 필드 | 형식과 선택값 | 사용 방법 |
| --- | --- | --- |
| 관리 담당 | 단일 person, 기본값 없음 | 실제 후속 업무 담당자를 사람이 선택합니다. 자동 배정하지 않습니다. |
| 관리 우선순위 | 단일 선택: 긴급 / 높음 / 보통 / 낮음 | 업무상 판단에 따라 선택합니다. 공정 진행률에서 자동 추정하지 않습니다. |
| 관리 상태 | 단일 선택: 미착수 / 진행 중 / 대기 / 확인 완료 | 수동 확인 작업의 상태입니다. 프로젝트 완료나 입금 완료 판정과 별개입니다. |
| 다음 확인일 | date, UI 표시 `yyyy/MM/dd`, 기본값 없음 | 실제 다음 확인일을 입력합니다. 빈 날짜를 자동 보충하지 않습니다. |
| 관리 메모 | text | 다음 조치, 확인한 근거, 남은 질문을 간단히 기록합니다. |

[프로젝트 sync](sales_metrics_sync.py)는 이 다섯 이름을 source-owned 쓰기
payload에서 제외합니다. 새로운 projector가 같은 이름을 생성하더라도
최종 쓰기 직전에 제거합니다. `관리 상태=확인 완료`를 선택해도 `Workflow Lane`,
`Payment State`, `Current Stage`, `Progress Phase`, `Progress %`, `Next Action`
같은 원본 파생 필드가 바뀌지 않습니다.

`Payment Owner Scope`는 원본 결제 담당 범위이며 `관리 담당`과 별도입니다.
수동 담당자를 선택해서 미확인 원본 결제 건을 검증된 건으로 바꿀 수 없습니다.

### 네 가지 업무 뷰

| 뷰 이름 | 종류 | UI 상태와 설정 |
| --- | --- | --- |
| 00 관리 작업대 | grid, ID `vewsBMUPG6` | 저장 완료. `Workflow Lane is not PAID_ARCHIVED`로 보관 건을 제외하고, `Source Key`·`Project Display Name`·다섯 수동 관리 필드만 표시합니다. |
| 01 오늘 확인 | grid, ID `vewB79tmDj` | 저장 완료. ALL 조건은 `Workflow Lane is not PAID_ARCHIVED`, `다음 확인일 is before tomorrow`, `관리 상태 is not 확인 완료`입니다. 상대 날짜의 내일 이전은 오늘을 포함합니다. 빈 관리 상태도 포함되는 것을 확인했습니다. |
| 02 관리 칸반 | kanban, ID `vewp5jdx1d` | 저장 완료. 그룹은 수동 `관리 상태`의 4옵션과 미분류이며, 필터는 `PAID_ARCHIVED` 제외입니다. 카드 이동은 이 수동 상태를 바꾸는 업무 동작입니다. |
| 03 확인 일정 | calendar, ID `vewmYMuKkO` | 저장 완료. 시작일·종료일은 모두 `다음 확인일`, 제목은 `Project Display Name`입니다. `PAID_ARCHIVED` 제외 필터도 저장했습니다. |

작업대의 표시 열은 수동 관리 입력에 집중한 7개입니다. 자동 공정·진행률·결제
필드와 원본 근거는 기존 상세 뷰와 record에 남아 있으며, 이 작업대에서 열을
숨긴 것이 해당 필드를 삭제하거나 값을 변경한 것은 아닙니다.

`01 오늘 확인`은 다음 확인일이 없는 행을 표시하지 않습니다. 날짜를 아직
입력하지 않았다면 결과가 비어 있는 것이 정상이며, 날짜 없는 업무는 작업대에서
확인합니다. 빈 관리 상태가 포함되는지는 임시 날짜 조건으로 확인한 뒤 원래의
`is before tomorrow` 조건으로 복원·저장했습니다. 이 확인을 위해 실제 담당자,
우선순위, 상태, 날짜, 메모 값을 채우지 않았습니다.

네 뷰의 ID는 helper에도 고정했습니다. 동일한 이름으로 삭제·재생성되거나
기존 ID의 이름이 바뀌면 자동으로 새 뷰를 채택하지 않습니다. 기존 identity를
유지한 채 UI 설정을 검토합니다.

칸반을 source-owned `Workflow Lane`이나 `Current Stage`로 그룹화하고 카드를
옮기면 다음 원본 sync가 값을 다시 계산할 수 있습니다. 작업용 칸반은
`관리 상태`를 사용합니다. 캘린더 날짜나 오늘 확인 필터를 설정했다고 해서
알림·이메일·자동 담당자 배정이 생성되지는 않습니다.

기존의 `프로젝트별 진행률`, `진행 중 프로젝트`, `완료 · 결제 관리`,
`결제 완료 · 보관` 등 source-owned 뷰는 기존 owner가 필터를 재적용할 수
있습니다. 새 관리 뷰 이름을 기존 관리 이름으로 바꾸지 않습니다. 기존 view를
삭제하고 새 ID로 재생성하는 대신, 기존 identity를 유지합니다.

## 결제 증빙과 재검토 상태

[결제 상태 판정](project_settlement.py)은 프로젝트 완료 근거와 유효한 입금
증빙을 함께 확인합니다. 새 보강은 다음 원칙을 적용합니다.

- 이전 자동 입금 증빙이 이번 exact-match 결과에서 사라지면 과거 Receipt
  reference·검증 금액·검증일·receipt snapshot은 남기고 자동 검증 상태를
  `SOURCE_RECHECK_REQUIRED`로 바꿉니다. 자동 증빙의 Invoice 번호와 Outstanding
  snapshot은 최신 billing 근거로 갱신될 수 있습니다. 완료 프로젝트는 결제
  후속 목록에서 재검토합니다.
- `BANK_RECEIPT`와 `ERP_CASH_RECEIPT`의 수동 증빙은 미완성·대기 초안까지
  사람이 소유합니다. 원본 sync가 증빙 열을 대체하지 않습니다.
- 수동 초안을 보호하는 것과 입금 완료를 승인하는 것은 다릅니다. 보관에는
  별도의 `VERIFIED` 상태, 필수 식별·검증 정보, `YYYY-MM-DD` 형식의 검증일, 일치하는 양수
  Invoice/입금 금액이 필요합니다.
- 최신 양수 미수 잔액이나 다른 Invoice 범위·총액이 발견되면 재검토 상태를
  유지합니다. 수동 증빙을 지워서 충돌을 숨기지 않습니다.

이 상태 전이는 source-owned 상태를 보수적으로 판정하는 코드입니다. 업무
담당자·우선순위·메모를 자동으로 추정하거나 변경하지 않습니다.

## 갱신과 소유자 워크플로

| 대상 | 소유자 | 실행 및 쓰기 범위 |
| --- | --- | --- |
| Project Progress Board의 원본 파생 값 | [Sources Unified](../../.github/workflows/feishu-sources-unified.yml)의 payment 단계 | 기존 3시간 주기와 `operations` 범위를 유지합니다. 이번 변경으로 예약·권한·운영 gate를 바꾸지 않습니다. |
| 기존 metric schema와 source-owned 뷰 | [sales_metrics_sync.py](sales_metrics_sync.py) | Quote scope에서도 공통 schema/view 검사가 실행될 수 있습니다. 새 수동 관리 뷰는 기존 managed 이름과 구분합니다. |
| Weekly Quote 및 Monthly Revenue 원본 | 기존 SFDC report / Sources Unified 경로 | 기존 freshness·증빙·scope 계약을 유지합니다. 통합 dashboard owner가 원본 record를 생성하지 않습니다. |
| 새 통합 대시보드의 6개 차트 | [Native Overview Dashboard](../../.github/workflows/feishu-native-overview-dashboard.yml) | main에서 하루 한 번 02:25 UTC / 11:25 KST 메타데이터 `verify`. 수동 기본값은 `plan`; 명시적 `apply`만 검토된 차트 설정 차이를 수정합니다. 안내 문안은 UI 소유이며 검사·수정하지 않습니다. |
| 다섯 수동 관리 필드와 뷰 검사 | [Project Management Metadata Setup](../../.github/workflows/feishu-project-management-setup.yml) | 수동 `plan` / `apply`만 제공합니다. 고정 table/view ID와 이름을 확인하며, `apply`는 누락된 정확한 다섯 필드만 추가할 수 있고 기존 필드·뷰·레코드를 수정하지 않습니다. |

신규 두 workflow의 PR 실행은 오프라인 테스트만 수행합니다. Overview의 main
push도 오프라인 테스트이며, 인증 job은 main의 schedule 또는 명시적 dispatch에만
열립니다. 관리 setup은 명시적 dispatch에만 열리며 선택한 브랜치의 코드를
실행하므로, 운영 준비 시에는 병합된 main을 선택합니다. PR concurrency는 운영
그룹과 분리하고 운영 실행끼리의 취소를 도입하지 않습니다.

Overview `plan`은 현재 차트 설정 차이의 건수와 확인된 API block ID를 보고합니다.
`verify`는 차이가 있으면 실패하고 수정하지 않습니다. `apply`는 고정 dashboard
안의 유일한 6개 차트를 모두 먼저 검사한 뒤, 바뀐 설정 키만 수정하고
독립 readback을 수행합니다. block 생성·삭제·위치 변경, 기존 상세 dashboard,
UI 안내의 이름·종류·본문, Home shortcut, 레코드 값은 이 owner의 쓰기 범위에 없습니다. 알려지지 않은
집계 family 전환이나 source/type/identity 교체는 자동 수리하지 않습니다.

공식 block-list의 전체 `items`에 있는 API ID는 접두어나 이름·타입을 추정하지
않고 보존 검사에 포함합니다. 따라서 알 수 없는 RichText나 추가 블록도
목록에서 사라지지 않았는지 확인하지만, 그 블록의 상세 GET이나 patch는
수행하지 않습니다. UI 안내의 문안·표시는 UI에서 관리합니다.

관리 setup은 기본 `plan`입니다. 기존 필드 옵션·person multiple·date auto-fill이
계약과 다르면 `UI_REVIEW_REQUIRED`로 보고하며, 추가 사용자 옵션을 삭제하지
않습니다. 뷰가 누락되면 `UI_SETUP_REQUIRED`로 보고합니다. 공개 API 모델에서
칸반 그룹과 캘린더 날짜 바인딩의 확인 범위가 확정되지 않았으므로, helper의
성공을 그 UI 설정까지 완료되었다는 뜻으로 사용하지 않습니다.

2026-11-24 배포 후 실제 metadata plan에서 고정 일정 뷰의 API 유형 검증이
실패했습니다. 배포 전후 독립 native export에서는 기존 일정 뷰의 identity,
내부 유형 및 설정이 보존됐습니다. UI의 calendar와 공개 API의 view_type
표현이 동일하다고 가정하지 않습니다. 읽기 전용 plan은 정확한 기존 ID와
이름을 가진 `03 확인 일정`의 유형 불일치를 `UI_REVIEW_REQUIRED`로
별도 보고합니다. 이는 type 검증 통과가 아닙니다. 다른 뷰 유형 불일치,
중복, 이름/ID 변경은 계속 차단하며 apply에서는 일정 뷰 유형 불일치도
계속 모든 필드 생성을 차단합니다. 실제 API 값과 UI 설정을 검토한 뒤
필요한 경우에만 별도 계약 변경을 승인합니다.

## 배포 및 확인 순서

1. 이 변경의 오프라인 테스트와 코드 리뷰를 확인합니다. UI가 이미 생성되어
   있어도 main 병합 전에는 새 schedule이나 수동 보호 로직이 배포되었다고
   보고하지 않습니다.
2. main 병합 후 관리 setup을 `plan`으로 실행해 고정 table ID/name, 다섯 필드,
   네 뷰의 고정 ID·이름·타입을 확인합니다. 누락 필드만 추가해야 할 때 명시적 `apply`를
   사용하고 결과를 다시 확인합니다.
3. UI에서 오늘 확인 필터, 칸반의 관리 상태 그룹, 캘린더의 다음 확인일 연결을
   확인합니다. 실제 담당자·날짜·우선순위는 사용자가 정합니다.
4. Overview `plan`으로 고정 dashboard·source table·block 범위와 차이를 확인합니다.
   필요한 설정 차이만 검토해 `apply`한 뒤 `verify`로 확인합니다. UI 생성만으로
   source 최신성이나 차트 semantic 검증을 통과한 것으로 간주하지 않습니다.
5. 정상 예약 실행에서 기존 upstream source/sink 증거를 확인합니다. 신규 daily
   verify는 메타데이터 drift 신호이며, 수집 실패를 대신 검증하지 않습니다.

오프라인 검증은 synthetic fixture와 mock transport를 사용합니다. 실제 고객,
프로젝트·Invoice 식별자, 메일 본문, 담당자 배정값을 fixture나 로그에 넣지
않습니다. 범위별 기존 테스트와 신규 두 test module을 함께 실행하며,
`google-auth`와 `requests` 등 기존 테스트 의존성은 기존 CI와 같이 설치합니다.
