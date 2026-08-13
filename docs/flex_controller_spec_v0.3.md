# Opentrons Flex Python 제어 도구 개발사양서

| 항목 | 내용 |
|---|---|
| 문서 버전 | 0.3 |
| 개정 내용 | 단일 클래스 구조로 재설계, 검증 대상 프로토콜을 OD-600 정규화로 확정 |
| 작성일 | 2026-08-13 |
| 대상 장비 | Opentrons Flex, 내부 코드명 ot3 |
| 통신 규격 | robot-server HTTP API, 포트 31950, Opentrons-Version 3 |
| 구현 언어 | Python 3.10 이상 |
| 런타임 의존성 | requests |

## 1. 목적과 원칙

### 1.1 목적

Opentrons Flex에 실험 프로토콜을 업로드하고, 실행 전 오류를 검증하며, 실행을 제어하고, 로봇 상태와 오류를 수집하는 Python 도구를 개발한다. MCP 계층을 두지 않고 HTTP API를 직접 호출한다.

### 1.2 개발 환경 원칙

인수 시험 이전까지 실기기를 사용하지 않는다. 설계, 구현, 단위 시험, 통합 시험의 전 구간은 개발용 PC에서 구동하는 Flex robot-server 개발서버를 대상으로 수행한다. 개발서버가 실기기와 동일한 코드베이스를 동일한 포트와 API 버전으로 제공하므로 접속 호스트를 제외한 코드 분기가 발생하지 않는다.

### 1.3 검증 기준 프로토콜

Opentrons Protocol Library의 다음 프로토콜을 통합 시험의 단일 기준으로 삼는다.

| 항목 | 값 |
|---|---|
| 프로토콜명 | OD-600 Normalization using 96-channel pipette |
| slug | od-normalization-with-96-ch-pipette |
| 파일명 | OD_Normalization.py |
| 대상 로봇 | Flex |
| requirements | robotType Flex, apiLevel 2.20 |
| 런타임 파라미터 | 3종, CSV 파일 1종 포함 |

이 프로토콜을 선정한 이유는 96채널 피펫, 그리퍼, 모듈 3종, 스테이징 슬롯, 웨이스트 슈트, CSV 런타임 파라미터를 한 번에 사용하므로 본 도구가 다루어야 할 HTTP API 경로를 대부분 관통하기 때문이다.

## 2. 검증 대상 프로토콜 분석

### 2.1 요구 장비

| 구분 | 항목 | 로드 문자열 |
|---|---|---|
| 피펫 | Flex 96-Channel 1000 uL | flex_96channel_1000 |
| 노즐 구성 | 단일 채널 모드, 시작 A1 | configure_nozzle_layout style SINGLE |
| 그리퍼 | 팁랙 교체에 사용 | move_labware use_gripper True |
| 모듈 | Thermocycler Module GEN2 | thermocyclerModuleV2 |
| 모듈 | Temperature Module GEN2 | temperature module gen2 |
| 모듈 | Heater-Shaker Module GEN1 | heaterShakerModuleV1 |
| 랩웨어 | Corning 96 Well Plate 360 uL Flat, 2매 | corning_96_wellplate_360ul_flat |
| 랩웨어 | NEST 1 Well Reservoir 195 mL | nest_1_reservoir_195ml |
| 랩웨어 | Opentrons Flex 96 Tip Rack 200 uL, 2매 | opentrons_flex_96tiprack_200ul |

피펫이 96채널이므로 좌우 마운트를 모두 점유한다. 시뮬레이터 구성에서는 좌측 마운트에만 등록하고 우측 마운트는 비워 둔다.

### 2.2 데크 배치

waste_type 기본값 1, 즉 웨이스트 슈트를 사용하는 경우의 배치이다.

| 슬롯 | 배치물 | 비고 |
|---|---|---|
| A1, B1 | Thermocycler Module GEN2 | 두 슬롯을 점유, location 미지정 |
| A2 | Tiprack 1 | opentrons_flex_96tiprack_200ul |
| A3 | 스테이징 영역 슬롯 | A4 활성화를 위해 필요 |
| A4 | Tiprack 2 | 스테이징 슬롯 |
| B2 | Normalization Plate | corning_96_wellplate_360ul_flat |
| B3 | Diluent Reservoir | nest_1_reservoir_195ml |
| C1 | Temperature Module GEN2 + Culture Plate | 모듈 위에 플레이트 적재 |
| D1 | Heater-Shaker Module GEN1 | |
| D3 | 웨이스트 슈트 + 스테이징 영역 | D4 활성화를 겸함 |
| D4 | Tiprack 1 이동 목적지 | 팁 소진 시 그리퍼로 이송 |

waste_type을 2로 설정하면 A3에 트래시 빈이 놓이며, 이 경우 A4 스테이징 슬롯을 사용할 수 없어 팁랙 교체 로직이 실패한다. 따라서 검증에서는 waste_type을 1로 고정한다.

### 2.3 런타임 파라미터

| 변수명 | 형식 | 기본값 | 검증 시 지정값 |
|---|---|---|---|
| csv_data | CSV 파일 | 없음, 필수 | 별도 준비한 CSV의 파일 ID |
| dry_run | bool | true | true |
| waste_type | int | 1 | 1 |

csv_data가 파일형 파라미터이므로 프로토콜 업로드 이전에 CSV를 먼저 로봇에 업로드해 파일 ID를 확보해야 한다. 이는 본 도구가 반드시 구현해야 하는 추가 단계이다.

### 2.4 검증용 CSV 규격

프로토콜은 CSV를 파싱해 4개 열을 순서대로 source_wells, dest_wells, dil_volumes, dna_volumes로 언팩하며 첫 행을 헤더로 간주해 건너뛴다. 따라서 최소 형식은 다음과 같다.

```
source,destination,diluent_volume,dna_volume
A1,A1,90,10
A2,A2,80,20
B1,B1,70,30
```

행 수는 임의로 정할 수 있으며, 초기 검증은 3행에서 8행 규모로 시작해 통과 후 96행으로 확대한다.

## 3. 개발서버 구축 사양

### 3.1 구축 절차

```bash
git clone https://github.com/Opentrons/opentrons.git
cd opentrons
make setup
make -C robot-server dev-flex
curl -H "Opentrons-Version: 3" http://localhost:31950/health
```

### 3.2 dev-flex 환경변수

| 환경변수 | 값 | 의미 |
|---|---|---|
| ENABLE_VIRTUAL_SMOOTHIE | true | 가상 모션 컨트롤러 사용 |
| OT_API_FF_enableOT3HardwareController | true | Flex 하드웨어 컨트롤러 활성화 |
| OT_ROBOT_SERVER_simulator_configuration_file_path | simulators/test-flex.json | 가상 장비 구성 파일 경로 |
| OT_ROBOT_SERVER_persistence_directory | automatically_make_temporary | 임시 DB, 재기동 시 초기화 |
| DEV_ROBOT_NAME | opentrons-dev | 로봇 표시 이름 |

### 3.3 시뮬레이터 구성 파일

실기기 구성이 미확정이므로 2.1의 요구 장비를 그대로 반영한 구성 파일을 사용한다. 별도 첨부한 sim-od-normalization.json을 robot-server/simulators 아래에 두고, dev-flex.env의 OT_ROBOT_SERVER_simulator_configuration_file_path를 해당 파일로 변경한다.

| 마운트 또는 슬롯 | 모델 | 식별자 |
|---|---|---|
| left | p1000_96_3.7 | 96ch_sim_001 |
| right | 없음 | 96채널이 양쪽 마운트 점유 |
| gripper | gripper_1.3 | gripper_sim_001 |
| thermocycler | thermocyclerModuleV2 | therm-sim-001 |
| tempdeck | temperatureModuleV2 | temp-sim-001 |
| heatershaker | heaterShakerModuleV1 | hs-sim-001 |

피펫 모델 문자열의 버전 접미사는 shared-data/pipette/definitions/2/general/ninety_six_channel/p1000 아래에 존재하는 정의 버전과 일치해야 한다. 현재 3_0, 3_3, 3_4, 3_5, 3_6, 3_7이 존재하며 사양서는 최신인 3_7을 기준으로 한다. strict_attached_instruments를 false로 두어 버전 불일치 시 즉시 실패하지 않도록 한다.

### 3.4 데크 구성 설정

웨이스트 슈트와 스테이징 슬롯은 랩웨어가 아니라 데크 픽스처이므로 프로토콜 업로드 이전에 PUT /deck_configuration으로 등록해야 한다. 등록하지 않으면 analysis 단계에서 슈트 또는 스테이징 슬롯 부재 오류가 발생한다.

| cutoutId | cutoutFixtureId | 목적 |
|---|---|---|
| cutoutA1 | thermocyclerModuleV2Rear | 서멀사이클러 후면 |
| cutoutB1 | thermocyclerModuleV2Front | 서멀사이클러 전면 |
| cutoutC1 | temperatureModuleV2 | 온도 모듈 |
| cutoutD1 | heaterShakerModuleV1 | 히터셰이커 |
| cutoutA2 | singleCenterSlot | Tiprack 1 |
| cutoutB2 | singleCenterSlot | Normalization Plate |
| cutoutC2 | singleCenterSlot | 미사용 |
| cutoutD2 | singleCenterSlot | 미사용 |
| cutoutA3 | stagingAreaRightSlot | A4 스테이징 활성화 |
| cutoutB3 | singleRightSlot | Diluent Reservoir |
| cutoutC3 | singleRightSlot | 미사용 |
| cutoutD3 | stagingAreaSlotWithWasteChuteRightAdapterNoCover | 웨이스트 슈트와 D4 스테이징 동시 활성화 |

모듈 픽스처에는 opentronsModuleSerialNumber 필드로 3.3의 시리얼을 지정한다. cutoutD3의 픽스처는 커버 유무에 따라 두 가지가 있으며, analysis에서 커버 관련 오류가 나오면 Covered 변형으로 교체한다.

## 4. 소프트웨어 구조

### 4.1 단일 클래스 설계

본 도구는 FlexController 단일 클래스로 구현한다. 설정, HTTP 전송, 엔드포인트 호출, 워크플로 조립, 상태 모니터링을 하나의 클래스가 모두 보유한다. 외부에 노출되는 진입점은 이 클래스와 CLI 함수 하나이다.

```
FlexController
  생성자
    host, timeout, allow_mutations, profile, artifact_dir
  내부 상태
    _session, _protocol_id, _analysis_id, _run_id, _data_file_ids
```

### 4.2 메서드 명세

| 구분 | 메서드 | 대응 엔드포인트 | 반환 |
|---|---|---|---|
| 전송 | _request | 공통 | JSON dict |
| 전송 | _retry | 공통 | JSON dict |
| 상태 | health | GET /health | name, api_version, system_version |
| 상태 | is_reachable | GET /health | bool |
| 데크 | get_deck_configuration | GET /deck_configuration | cutoutFixtures 목록 |
| 데크 | set_deck_configuration | PUT /deck_configuration | 적용 결과 |
| 데이터 | upload_data_file | POST /dataFiles | file_id |
| 데이터 | list_data_files | GET /dataFiles | 파일 목록 |
| 프로토콜 | upload_protocol | POST /protocols | protocol_id, analysis_id |
| 프로토콜 | get_analysis | GET /protocols/{pid}/analyses/{aid} | analysis 문서 |
| 프로토콜 | wait_for_analysis | 위 반복 호출 | analysis 문서 |
| 프로토콜 | assert_analysis_clean | 없음 | None 또는 예외 |
| 프로토콜 | list_protocols | GET /protocols | 목록 |
| 프로토콜 | delete_protocol | DELETE /protocols/{pid} | None |
| 실행 | create_run | POST /runs | run_id |
| 실행 | play, pause, stop | POST /runs/{rid}/actions | None |
| 실행 | get_run | GET /runs/{rid} | run 문서 |
| 실행 | get_commands | GET /runs/{rid}/commands | 명령 배열 |
| 실행 | get_errors | GET /runs/{rid} 파생 | 오류 배열 |
| 실행 | monitor | 위 반복 호출 | 최종 run 문서 |
| 실행 | list_runs | GET /runs | 목록 |
| 실행 | delete_run | DELETE /runs/{rid} | None |
| 워크플로 | verify_only | 업로드와 분석까지 | 판정 결과 |
| 워크플로 | execute | 업로드부터 종료까지 | 최종 run 문서 |
| 기록 | save_artifact | 없음 | 저장 경로 |
| 기록 | log_event | 없음 | None |

### 4.3 단일 클래스 채택에 따른 제약

단일 클래스 구조는 파일 수가 적고 호출 경로가 짧다는 장점이 있으나 책임이 집중되므로 다음을 강제한다.

1. 밑줄로 시작하는 메서드는 내부 전용이며 외부 호출을 금지한다.
2. 인스턴스 상태는 4.1에 열거한 항목 외에 추가하지 않는다.
3. 호스트, 포트, 타임아웃, 폴링 주기는 생성자 인자로만 받으며 메서드 내부에 상수로 기입하지 않는다.
4. 단위 시험은 _request를 대체하는 방식으로 수행하며, 각 공개 메서드는 독립적으로 시험 가능해야 한다.
5. 메서드 총수가 30개를 초과하면 전송 계층 분리를 재검토한다.

### 4.4 프로필

| 프로필 | host | 예상 name | 실행 전 확인 입력 | 용도 |
|---|---|---|---|---|
| dev | localhost | opentrons-dev | 불요 | S1에서 S4 |
| robot | 실기기 IP | 실기기 등록명 | 필수 | S5 |

프로필 차이는 host 값과 확인 입력 요구 여부로만 표현하며, 코드에 개발서버 판별 분기를 두지 않는다.

## 5. 실행 워크플로

검증 대상 프로토콜을 기준으로 한 execute 메서드의 처리 순서이다.

| 순번 | 동작 | 엔드포인트 | 실패 시 처리 |
|---|---|---|---|
| 1 | 연결 및 대상 확인 | GET /health | 중단 |
| 2 | 데크 구성 조회 | GET /deck_configuration | 계속, 경고 |
| 3 | 데크 구성 적용 | PUT /deck_configuration | 중단 |
| 4 | CSV 업로드 | POST /dataFiles | 중단 |
| 5 | 프로토콜 업로드 | POST /protocols | 중단 |
| 6 | 분석 완료 대기 | GET /protocols/{pid}/analyses/{aid} | 중단 |
| 7 | 분석 오류 판정 | 없음 | 오류 1건 이상이면 중단 |
| 8 | 실행 확인 입력 | 없음 | robot 프로필에서만 수행 |
| 9 | run 생성 | POST /runs | 중단 |
| 10 | 실행 시작 | POST /runs/{rid}/actions | 중단 |
| 11 | 상태 폴링 | GET /runs/{rid} 및 commands | 종료 상태까지 반복 |
| 12 | 결과 저장 | 없음 | 경고 후 종료 |

### 5.1 런타임 파라미터 전달

5단계의 프로토콜 업로드는 multipart 요청이며 다음 폼 필드를 포함한다.

| 필드 | 값 | 형식 |
|---|---|---|
| files | OD_Normalization.py | 파일 |
| runTimeParameterValues | dry_run과 waste_type | JSON 문자열 |
| runTimeParameterFiles | csv_data와 4단계의 파일 ID | JSON 문자열 |

9단계의 run 생성 시에도 동일한 두 필드를 요청 본문의 data 아래에 runTimeParameterValues, runTimeParameterFiles로 전달한다. 두 단계 모두에서 값이 일치해야 하며, 불일치 시 재분석이 발생한다.

### 5.2 분석 오류 판정 게이트

analysis 문서의 status가 completed가 될 때까지 폴링하고, errors 배열의 길이가 1 이상이면 예외를 발생시켜 run 생성으로 진행하지 않는다. 이 게이트는 프로필과 무관하게 항상 동작하며 우회 옵션을 제공하지 않는다.

### 5.3 run 상태 전이

| 상태 | 의미 | 다음 가능 상태 |
|---|---|---|
| idle | 생성 직후, 미시작 | running, stopped |
| running | 실행 중 | paused, stop-requested, succeeded, failed |
| paused | 일시정지 | running, stop-requested |
| blocked-by-open-door | 도어 열림으로 중단 | running, stop-requested |
| stop-requested | 정지 요청 접수 | stopped |
| stopped | 사용자 중단 종료 | 종료 |
| succeeded | 정상 완료 | 종료 |
| failed | 오류 종료 | 종료 |

종료 상태 집합은 succeeded, stopped, failed이며 상수로 분리한다. 미지의 상태 문자열을 만나면 예외를 발생시키지 않고 경고 기록 후 폴링을 계속한다.

## 6. 비기능 요구사항

| 구분 | 요구사항 | 개발서버 기준값 | 실기기 조정 |
|---|---|---|---|
| 응답 타임아웃 | 단일 HTTP 호출 | 10초 | S5 재측정 |
| 업로드 타임아웃 | POST /protocols, POST /dataFiles | 120초 | S5 재측정 |
| 분석 폴링 | 주기 및 상한 | 2초 간격, 600초 상한 | S5 재측정 |
| 실행 폴링 | 주기 | 3초 | 유지 |
| 재시도 | 연결 오류 및 5xx | 최대 3회, 백오프 1초, 2초, 4초 | 유지 |
| 재시도 제외 | 4xx 및 POST actions | 재시도 없음 | 유지 |
| 로그 | 형식 | 구조화 JSON, 실행별 디렉터리 | 유지 |

분석 폴링 상한을 300초에서 600초로 상향한 근거는 검증 대상 프로토콜이 96웰 단위 반복 전송을 포함해 분석 시간이 단순 프로토콜보다 길기 때문이다. 실측값은 TC-12에서 확정한다.

## 7. 오류 처리 정책

| 오류 계층 | 발생 지점 | 처리 | 개발서버 재현 방법 |
|---|---|---|---|
| 네트워크 오류 | 연결 실패, 타임아웃 | 재시도 후 중단 | 개발서버 프로세스 중지 |
| HTTP 4xx | 잘못된 요청, 미존재 ID | 즉시 중단, 본문 출력 | 존재하지 않는 run_id 조회 |
| HTTP 5xx | robot-server 내부 오류 | 재시도 후 중단 | 손상 파일 업로드 |
| 데크 구성 오류 | 슈트 또는 스테이징 미등록 | 중단, 필요한 픽스처 안내 | cutoutD3를 singleRightSlot으로 설정 |
| RTP 오류 | CSV 파일 ID 누락 | 중단 | runTimeParameterFiles 생략 |
| 분석 오류 | 문법, 랩웨어 미정의 | run 생성 차단 | 미정의 loadName 사용 |
| 실행 오류 | 실행 중 하드웨어 오류 | errors 수집 후 종료 대기 | 일부만 재현, S5 보완 |
| 도어 열림 | blocked-by-open-door | 경고, 자동 재개 금지 | 재현 불가, S5 확인 |

## 8. 테스트 계획

TC-01에서 TC-11까지는 전량 개발서버에서 수행한다.

| ID | 유형 | 대상 | 합격 기준 |
|---|---|---|---|
| TC-01 | 단위 | 응답 파서 | 저장된 JSON 픽스처 파싱 성공 |
| TC-02 | 단위 | 재시도 로직 | 5xx에서 3회 재시도, 4xx에서 0회 |
| TC-03 | 통합 | health 조회 | name이 opentrons-dev로 반환 |
| TC-04 | 통합 | 데크 구성 적용 | 3.4의 12개 픽스처가 GET으로 재확인 |
| TC-05 | 통합 | CSV 업로드 | file_id 반환, GET /dataFiles에 존재 |
| TC-06 | 통합 | 프로토콜 업로드 | protocol_id와 analysis_id 반환 |
| TC-07 | 통합 | 분석 정상 판정 | errors 0건, 96채널과 그리퍼 명령 포함 |
| TC-08 | 통합 | 분석 오류 판정 | 미정의 랩웨어 프로토콜에서 errors 1건 이상, run 미생성 |
| TC-09 | 통합 | 데크 구성 누락 판정 | cutoutD3 미등록 시 분석 오류 검출 |
| TC-10 | 통합 | 전체 실행 | run이 succeeded로 종료 |
| TC-11 | 통합 | 실행 중단 | play 후 stop 호출 시 stopped 도달 |
| TC-12 | 인수 | 실기기 dry-run | 업로드와 분석만 수행, 무동작 확인 |
| TC-13 | 인수 | 실기기 실행 | 데크 확인 후 완주, 소요 시간 기록 |

TC-07의 세부 확인 항목은 다음과 같다.

| 확인 항목 | 판정 근거 |
|---|---|
| 96채널 피펫 인식 | analysis 결과에 flex_96channel_1000 등장 |
| 노즐 구성 변경 | configureNozzleLayout 명령 존재 |
| 그리퍼 이송 | moveLabware 명령의 strategy가 그리퍼 사용 |
| 모듈 3종 로드 | loadModule 명령 3건 |
| 웨이스트 슈트 | 팁 폐기 대상이 슈트로 지정 |
| CSV 반영 | 전송 명령 수가 CSV 행 수와 일치 |

## 9. 개발 단계

| 단계 | 기간 | 작업 | 산출물 | 대상 |
|---|---|---|---|---|
| S1 | 1주 | 개발서버 구축, 시뮬레이터 구성 적용, 데크 구성 확정, 검증용 CSV 작성 | 구축 절차서, sim-od-normalization.json, 검증 CSV | 개발서버 |
| S2 | 1주 | FlexController 전송 및 조회 메서드 구현 | 클래스 초판, TC-01에서 TC-05 통과 | 개발서버 |
| S3 | 1주 | 업로드, 분석, 게이트, 실행 메서드 구현 | TC-06에서 TC-11 통과 | 개발서버 |
| S4 | 3일 | CLI, 기록, 프로필 전환 | 실행 가능한 도구 일체 | 개발서버 |
| S5 | 2일 | 실기기 인수 시험 | TC-12, TC-13 성적서, 타임아웃 재설정본 | 실기기 |

S5 진입 조건은 TC-01에서 TC-11 전건 통과이다.

## 10. 실기기 전환 체크리스트

| 순번 | 확인 항목 | 판정 기준 |
|---|---|---|
| 1 | 개발서버 시험 전건 통과 | TC-01에서 TC-11 기록 |
| 2 | 실기기 네트워크 도달 | health 응답 200 |
| 3 | 로봇 소프트웨어 버전 | 7.0.0 이상, apiLevel 2.20 지원 |
| 4 | 대상 확인 | health의 name이 의도한 실기기와 일치 |
| 5 | 피펫 장착 | 96채널 피펫이 실제로 장착됨 |
| 6 | 그리퍼 장착 | 익스텐션 마운트에 장착됨 |
| 7 | 모듈 3종 연결 | 서멀사이클러, 온도 모듈, 히터셰이커 |
| 8 | 데크 픽스처 물리 설치 | 웨이스트 슈트 및 스테이징 슬롯 실물 설치 |
| 9 | 데크 구성 등록 | 3.4의 픽스처가 앱 또는 API로 등록됨 |
| 10 | 랩웨어 위치 점검 | LPC 수행 완료 |
| 11 | 프로필 전환 | profile을 robot으로 변경, 확인 입력 활성 |
| 12 | dry-run 선행 | TC-12 통과 후에만 TC-13 착수 |

8번과 9번은 개발서버에서 검증할 수 없는 항목이므로 실기기 도입 시 별도 확인이 필요하다.

## 11. 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| 실기기 구성 미확정 | 시뮬레이터 구성과 불일치 | 3.3 파일을 형상 관리, 구성 확정 시 즉시 갱신 후 TC-03에서 TC-11 재수행 |
| 96채널 피펫 정의 버전 차이 | 시뮬레이터 기동 실패 | strict_attached_instruments false 유지, 정의 디렉터리에서 존재 버전 확인 |
| 데크 픽스처 조합 오류 | 분석 단계 실패 | TC-04와 TC-09로 사전 검출 |
| CSV 파라미터 처리 누락 | 분석 실패 또는 실행 불가 | TC-05를 선행 조건으로 배치 |
| 단일 클래스의 책임 과다 | 유지보수성 저하 | 4.3의 제약 5개 항목 준수, 메서드 30개 초과 시 재검토 |
| 가상 하드웨어와 실물 차이 | 실기기에서만 발생하는 오류 | S5를 dry-run 우선으로 구성 |
| 시간 설정값의 비현실성 | 조기 타임아웃 | 전 시간값 생성자 인자화, TC-13에서 실측 반영 |
| 개발서버 재기동 시 DB 초기화 | 이력 및 데크 구성 소실 | 기동 스크립트에 데크 구성 적용 단계 포함 |

## 12. 참조

1. Opentrons Protocol Library, od-normalization-with-96-ch-pipette
2. Opentrons/opentrons, robot-server/README.rst, Developer Modes 항목
3. Opentrons/opentrons, robot-server/Makefile, dev-flex 타겟
4. Opentrons/opentrons, robot-server/dev-flex.env 및 simulators/test-flex.json
5. Opentrons/opentrons, robot-server/robot_server/protocols/router.py, runTimeParameterValues 및 runTimeParameterFiles 폼 필드
6. Opentrons/opentrons, robot-server/robot_server/data_files/router.py, POST /dataFiles
7. Opentrons/opentrons, shared-data/deck/definitions/5/ot3_standard.json, cutoutFixtures 목록
8. Opentrons/opentrons-integration-tools, http-api 디렉터리
9. http://{robot_ip}:31950/redoc, 로봇 자체 제공 OpenAPI 문서
