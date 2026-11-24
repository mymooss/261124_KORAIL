# KTX 디지털 트윈 관제 시스템 — Flask 웹앱

> ※ 교육 및 시연용 가상 시뮬레이션입니다. 실제 철도 관제 시스템·실제 운행 데이터와 무관하며, AI 분석 결과도 규칙 기반 **가상 결과**입니다.

단일 HTML 아티팩트로 만들었던 관제 화면을 **Flask + Postgres(Supabase)/SQLite** 웹앱으로 옮긴 버전입니다.
열차 시뮬레이션·장애 처리·KPI 계산은 서버(Python)에서 돌고, 화면은 1초마다 상태를 받아(polling) 그리기만 합니다.
그래서 여러 브라우저가 같은 상황을 동시에 보고, 서버를 재시작해도 마지막 상태에서 이어서 실행됩니다.

## 배포 구조 (Vercel + Supabase)

```
브라우저 ──(1초 polling: /api/poll, 조작: REST)──▶ Vercel 서버리스 함수 (Flask, api/index.py, 서울 icn1)
                                                     │  요청마다: 상태 행 잠금(FOR UPDATE) → 흐른 시간만큼 진행 → 저장
                                                     ▼
                                       Supabase Postgres (서울 ap-northeast-2, 모든 테이블 RLS 활성)
```

서버리스에서는 백그라운드 스레드와 SSE 를 유지할 수 없어서, 처음 작업지시서와 달리 다음처럼 바꿨습니다.

- **요청 기반 엔진:** 요청이 올 때마다 마지막 진행 시각(`sim_state.last_real`) 이후 흐른 실제 시간만큼 시뮬레이션을 진행합니다 (한 번에 최대 10초). 아무도 화면을 보지 않으면 시뮬레이션도 멈춰 있다가, 다음 접속 때 이어집니다.
- **SSE → polling:** `/api/stream` 대신 `/api/poll?since_id=` 가 상태와 새 로그를 함께 돌려줍니다. 탭이 숨겨지면 요청을 멈춥니다.
- **장애 변경 알림:** `sim_state.fault_ver` 가 바뀌면 화면이 장애 상세를 다시 받습니다. 새 장애 코드가 보이면 경보음을 냅니다.
- **시연 모드 연출**(스포트라이트·포커스·토스트)은 서버가 보내는 경과 시간을 보고 화면이 계산합니다.
- 실제 시간 기준 타이머(AI 분석 1.7초, 복구 3초)는 `faults.ana_epoch / rec_epoch` 에 저장합니다.

### 배포 명령 (참고)

```bash
# Supabase: 스키마 적용 (supabase/migrations)
npx supabase link --project-ref <ref>
npx supabase db push
# 시드 (운영용 비밀번호는 환경변수로)
DATABASE_URL=<pooler url> ADMIN_PASSWORD=... OPERATOR_PASSWORD=... VIEWER_PASSWORD=... flask seed
# Vercel: 환경변수 SECRET_KEY, DATABASE_URL, APP_TZ 설정 후
npx vercel deploy --prod
```

> 배포된 사이트의 계정 비밀번호는 아래 "기본 계정" 표의 값과 다릅니다 (배포 시 무작위로 생성).

## 실행 방법

Python 3.11 이상이 필요합니다.

```bash
# 1) 가상환경
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2) 패키지 설치
pip install -r requirements.txt

# 3) 환경설정
cp .env.example .env        # Windows: copy .env.example .env
#    → .env 의 SECRET_KEY 를 임의의 긴 문자열로 바꾸세요.

# 4) DB 생성 및 초기 데이터
flask init-db
flask seed

# 5) 실행
python run.py
# → http://127.0.0.1:5000 접속 → operator / operator1234! 로 로그인
```

> 로컬에서는 `DATABASE_URL` 을 비워 두면 SQLite(`instance/ktx.db`)를 씁니다. Supabase 에 붙이려면 `.env` 에 `DATABASE_URL` 을 넣으세요.
> 엔진 상태는 DB 에만 있으므로 여러 워커·서버리스 인스턴스로 띄워도 상태가 갈라지지 않습니다.

## 기본 계정

| 아이디 | 비밀번호 (`.env`로 변경 가능) | 권한 |
|---|---|---|
| admin | admin1234! | 관리자 — 초기화, 로그 삭제, 템플릿 수정 |
| operator | operator1234! | 관제사 — 장애 발생·분석·조치·복구, 일시정지·배속, 시연 모드 |
| viewer | viewer1234! | 조회자 — 화면·로그·이력 조회만 |

기본 비밀번호로 로그인하면 안내가 뜹니다. 화면 오른쪽 위 **비밀번호 변경**에서 바꾸세요.
`.env`의 `*_PASSWORD` 값은 `flask seed`를 실행할 때만 적용됩니다.

## 화면

- `/` 관제 화면 — 원본 디자인 그대로. 지도·KPI·열차 상세·AI 장애 분석·이벤트 로그·발표용 시연 모드
- `/history` 장애 이력 — 해결된 장애 목록, 장애별 처리 타임라인·리포트, KPI 추이 그래프, 로그 검색, CSV 내보내기
- `/login`, `/password`

다크/화이트 모드, 경보음 음소거, 지도 확대 상태, 「로그 지우기」(화면에서만 비우기)는 브라우저 `localStorage`에 저장됩니다.

## CLI 명령

| 명령 | 동작 |
|---|---|
| `flask init-db [--force]` | `schema.sql` 실행 (기존 DB는 `--force`일 때만 삭제 후 재생성) |
| `flask seed` | 시드 데이터 입력 (이미 있으면 건너뜀) |
| `flask reset-sim` | 열차·미해결 장애·sim_state 를 시드 값으로 (서버가 실행 중이면 재시작 필요) |
| `flask prune --days 30 --kpi-days 7` | 오래된 이벤트 로그·KPI 스냅샷 정리 |
| `flask create-user <username> --role operator` | 계정 추가 (비밀번호는 입력받음) |

## API 요약

모든 응답은 JSON, 오류는 `{"error": {"code": "...", "message": "..."}}` 형식입니다 (400/401/403/404/409).

| 메서드 | 경로 | 권한 |
|---|---|---|
| GET | `/api/health` | 없음 |
| GET | `/api/network`, `/api/state`, `/api/poll?since_id=`, `/api/trains/<no>` | viewer |
| GET | `/api/faults?status=active\|resolved\|all&page=&size=`, `/api/faults/<code>` | viewer |
| GET | `/api/events?category=&since_id=&before_id=&limit=&from=&to=` | viewer |
| GET | `/api/events/export.csv`, `/api/faults/export.csv`, `/api/kpi/history?minutes=` | viewer |
| POST | `/api/faults` `{"type":"signal","line_id":"gb"}` (선택: `segment_key`, `train_no`) | operator |
| POST | `/api/faults/<code>/analyze`, `/actions/<seq>/complete`, `/recover` | operator |
| POST | `/api/sim/pause`, `/api/sim/resume`, `/api/sim/speed {"mul":1\|2\|5}` | operator |
| POST | `/api/demo/start`, `/api/demo/stop` | operator |
| POST | `/api/sim/reset` | admin |
| DELETE | `/api/events` `{"confirm":"DELETE"}` | admin |
| GET/PUT | `/api/admin/templates[/<id>]` | admin |

POST/PUT/DELETE 요청은 같은 출처(Origin)에서 온 것만 허용합니다.

## 테스트

```bash
pytest -q
```

임시 DB와 `ENGINE_AUTOSTART=0`으로 돌고, 엔진은 `engine.step(sim_dt)`로 시간을 결정적으로 진행합니다.

## 구조

```
app/
  __init__.py      create_app(), 블루프린트 등록, get_engine() (요청 단위 엔진)
  config.py        .env → 설정
  db.py            SQLite/Postgres 공통 연결 래퍼, CLI 명령
  schema.sql (SQLite), schema_pg.sql (Postgres), seed.py
api/index.py       Vercel 함수 진입점
supabase/          Supabase CLI 설정·마이그레이션
vercel.json
  auth/            /login, /logout, /password, @login_required, @role_required
  sim/             engine(스레드·tick·SSE 브로드캐스트), train, faults, kpi, demo, geo, constants
  repo/            테이블별 SQL
  api/             REST(routes.py), SSE(stream.py)
  views/           /, /history
  templates/, static/css, static/js (api · map · panels · console · history)
tests/
```

## 지시서와 다르게 처리한 부분

- **초기화 시 `fault_seq`는 되돌리지 않습니다.** 해결된 장애 이력을 보존하면서 `F-001` 같은 코드가 중복(UNIQUE 위반)되지 않게 하기 위해서입니다.
- **백그라운드 엔진·SSE 대신 요청 기반 엔진·polling** (위 "배포 구조" 참고). 상태 전송 주기는 4Hz → 1Hz 이며 화면은 그 사이를 보간합니다.
- 서버리스 지원을 위해 `trains.speed_hist`, `faults.ana_epoch/rec_epoch`, `sim_state.last_real` 등 컬럼을 추가했습니다.
- 기본 계정용 **비밀번호 변경 화면**(`/password`)을 추가했습니다.
- AI 분석 대기(`detected`) 상태의 장애에는 화면에 「AI 분석 시작」 버튼을 보여 줍니다 (시연 모드 외에는 생기지 않음).
