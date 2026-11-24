# Feishu 통합 배포 후보 — 2026-11-24

## 변경 범위

이 후보는 아래 7개 PR의 결과를 최신 main 기준으로 통합하여 한 번에 검토한다.
개별 PR을 병합하거나 닫지 않으며 운영을 배포하지 않는다.

| PR | 기능 |
| --- | --- |
| #825 | QQ import와 독립 mail audit, mail/business catalog 판정 분리 |
| #1043 | Payment mirror schema/원본 식별 검증, GET rate-limit 재시도 |
| #1044 | metadata 조회 최적화, SFDC batchGet, PR/운영 queue 분리 |
| #1047 | 통합 차트, 수동 관리 필드 보호, 입금 근거 재검토 |
| #1051 | 별도 Project Management Center와 위험 신호 |
| #1052 | 데이터 연결/상태 검토, 보존 행 분리 |
| #1053 | 읽기 전용 Health Check 및 원본 metadata 기준 |

검토 기준: main `814b1bc79e18c240275205571d8252fbfed10769`.
공통 조상 `64070c00b91244c54033534e89a6220ca8f9c2d0` 이후 main의 독립
Kalman 변경 13개 파일을 보존한다. 7개 PR의 고유 변경 59개 중 중복
workflow 2개는 각각 원본 변경과 concurrency 변경을 합쳤다. 이번 통합에서
신규 관리 metadata workflow에 main-only 인증 job 제한 및 배포 조건 회귀
테스트를 추가한다.

기존 초안의 순차 병합 절차 대신 **이 단일 통합 후보를 승인/병합하는 경로를
선택할 수 있다**. 둘 다 병합하지 않는다. 기존 #825의 자동 병합 금지 지침을
존중하며 단일 통합 후보도 승인 전 Draft이다. main의 다른 변경과 검증 기준을
최종 병합 직전에 다시 대조한다.

## 배포 전 게이트

1. 통합 후보의 최종 SHA와 최신 main, 파일 차이, CI 전체 성공 확인.
   PR에서 모든 authenticated job이 skip되었는지 실제 job 결과로 확인.
2. 현재 Feishu Sales Base와 정확한 Project Progress Board ID를 확인.
   권한 있는 환경에서 기존 schema, view ID, 수동 관리 정보, 결제 증빙 및
   운영 지표 기준선을 안전한 내부 위치에 확보한다. 이 문서/PR은 운영
   데이터 백업이 아니다. 고객·메일·금액 등의 실제 내용을 GitHub에 올리지 않는다.
3. 기존 Sources Unified의 마지막 원본 대조/ingest/payment/lifecycle/monthly
   결과와 QQ mail import/audit, SFDC report provenance, X registry를 확인.
   실패한 원본 검증, stale/ambiguous schema, 수동 관리 필드 충돌은 먼저 해결.
4. 변경 범위와 병합에 따른 예약/기존 main push 실행을 담당자가 승인한다.
   단일 통합 PR 병합 이후 원래 workflow가 자동 실행할 수 있다.
   신규 프로젝트 센터/Health Check는 별도 명시 실행 전에는 작동하지 않는다.
   CI 통과만으로 운영 안전성/최신성/완료 건수를 보장하지 않는다.

## 승인 후 적용 순서

| 단계 | 실행 / 확인 | 통과 조건 |
| --- | --- | --- |
| 1 | main의 기존 Sources Unified 운영 갱신 | 원본-미러 독립 parity, 모든 의존 작업 및 저장 후 검증 성공. 실패 시 다음 단계 중단 |
| 2 | Project Management Metadata Setup, mode=plan | 기존 5개 수동 필드, 4개 뷰 ID와 UI 검토 항목 확인. 누락 필드만 명시 apply; 기존 뷰/수동값 변경 금지 |
| 3 | Board 확인 | PM Risk/Issue/Recommended Action, PM 연결/상태 6개 필드, 04~07 검토 뷰; 진행률 0/blank, current/carryover, 기존 완료·입금 증빙·수동값 비교 |
| 4 | Project Management Center, mode=health | aggregate 결과 확인, source freshness 제한과 충돌/누락 개수 평가. 실제 업무 판정은 변경하지 않음 |
| 5 | Project Management Center, mode=plan | source schema, 기존 동일 이름 page/ID 및 blocks 점검. 기존 동일 이름 페이지가 있으면 ID 검토 |
| 6 | Project Management Center, mode=apply | 누락된 신규 page/blocks만 생성. 기존 page면 reviewed expected_dashboard_id 필요. drift/partial readback 시 중단하고 plan 재점검 |
| 7 | Project Management Center, mode=verify | chart filter, 집계, source, ID readback 성공. UI 배치, 뷰 표시 열, 실제 클릭 가능한 바로가기 별도 확인 |
| 8 | Native Overview, mode=verify | 기존 통합 대시보드 6개 차트 보존. 업무/상세 뷰 및 기존 원본 테이블은 삭제하지 않음 |
| 9 | 이후 정기 실행 | 기존 Sources Unified, X registry, mail import/audit, Quote 및 KPI의 동작·오류·실제 시간 비교 |

단계 4와 5는 읽기 전용이다. 단계 6은 명시적으로 승인된 경우만 수행한다.
신규 health job은 프로젝트별 결과를 Feishu에 기록하지 않는다. 최초 실측
결과를 검토한 후 상세 Health 뷰/알림의 지속 갱신을 별도 결정한다.

## 실패 대응

- 실패 시 원인 범위에 해당하는 배포 단계 중단. 불완전한 원본/누락/오래된
  원본을 0, 결제 완료, 정상 진행으로 대체하지 않는다.
- 페이지 부분 생성은 동일 이름/ID를 다시 검토하고 누락 컴포넌트만 재개.
  중복 생성 또는 자동 삭제 금지. 기존 manual notes와 view IDs 보호.
- 문제 발생 시 담당자가 영향 범위를 점검해 필요한 writer를 일시 정지하고
  검토된 코드 revert를 선택한다. revert는 이미 적용된 record/schema/view
  변경을 되돌리지 않으므로 실제 원본 대조와 readback 후 비파괴 복구한다.
  전체 Base 삭제·일괄 복구·과거 결제 상태 덮어쓰기 금지.
- 새 예약은 overview의 일일 읽기 전용 metadata 점검 1개만 존재하며
  Health Check와 project center 생성은 수동이다. API 요청 감소 수치는
  offline fixture 구간에 한정하고 운영 성능은 정기 실행에서 측정한다.

관련 문서: [Architecture](ARCHITECTURE.md), [Project Management](PROJECT_MANAGEMENT.md),
[Project Center](PROJECT_CENTER.md), [Data Contract](PROJECT_DATA_CONTRACT.md),
[Health Check](PROJECT_HEALTH_CHECK.md).

## Additional pre-deployment diagnostic refinement

SIF/PO issue diagnosis now distinguishes exact SIF tracker key-set differences, invalid or duplicate keys, and field-level evidence drift on unambiguous shared keys. The existing count-only warning is retained for compatibility. Source-owned SIF notice fields are compared without Last Sync UTC. Independently refreshed source and tracker snapshots can differ legitimately; additional keys are unobserved in this input, not certified historical or safe to remove. The read-only diagnostic emits fixed field names and counts only, does not link ambiguous notices, and never edits the tracker. The existing workflow and schedule are unchanged except for PR/production concurrency isolation, preserving the original production group and non-cancellation policy. The enhanced check requires deployment before an authenticated run can report the new categories.
