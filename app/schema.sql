-- ===== 마스터 데이터 =====
CREATE TABLE lines (
  id          TEXT PRIMARY KEY,            -- 'gb','hn','gr','jr'
  name        TEXT NOT NULL,               -- '경부선'
  color_dark  TEXT NOT NULL,               -- '#00E5FF'
  color_light TEXT NOT NULL,               -- '#0891B2'
  sort_order  INTEGER NOT NULL
);

CREATE TABLE stations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL UNIQUE,
  lat          REAL NOT NULL,
  lon          REAL NOT NULL,
  is_major     INTEGER NOT NULL DEFAULT 0 CHECK (is_major IN (0,1)),
  label_dx     REAL NOT NULL DEFAULT 9,
  label_dy     REAL NOT NULL DEFAULT 4,
  label_anchor TEXT NOT NULL DEFAULT 'start' CHECK (label_anchor IN ('start','middle','end'))
);

CREATE TABLE line_stations (
  line_id    TEXT NOT NULL REFERENCES lines(id),
  seq        INTEGER NOT NULL,             -- 0부터, 서울/용산 기점
  station_id INTEGER NOT NULL REFERENCES stations(id),
  PRIMARY KEY (line_id, seq)
);

CREATE TABLE segments (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  seg_key       TEXT NOT NULL UNIQUE,       -- 역명 정렬 후 'A|B'
  station_a_id  INTEGER NOT NULL REFERENCES stations(id),
  station_b_id  INTEGER NOT NULL REFERENCES stations(id),
  length_km     REAL NOT NULL,              -- 대권거리 × 1.12
  max_speed_kmh INTEGER NOT NULL DEFAULT 300
);

-- ===== 열차 =====
CREATE TABLE trains (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  train_no      TEXT NOT NULL UNIQUE,       -- 'KTX 001'
  line_id       TEXT NOT NULL REFERENCES lines(id),
  direction     INTEGER NOT NULL CHECK (direction IN (-1,1)),  -- 1=하행, -1=상행
  st_idx        INTEGER NOT NULL,           -- 마지막으로 지난 역의 line_stations.seq
  progress      REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
  speed_kmh     REAL NOT NULL DEFAULT 0,
  dwell_sec     REAL NOT NULL DEFAULT 0,
  delay_min     REAL NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT '정상운행'
                CHECK (status IN ('정상운행','주의운행','서행','정차','지연')),
  passengers    INTEGER NOT NULL DEFAULT 500,
  phase_seed    REAL NOT NULL DEFAULT 0,    -- 속도 흔들림 위상
  last_check_sim INTEGER NOT NULL,          -- 마지막 점검 시뮬레이션 시각(초)
  speed_hist    TEXT NOT NULL DEFAULT '[]', -- 최근 60초 속도 (JSON, 요청 기반 엔진용)
  updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE train_inspections (
  train_id    INTEGER NOT NULL REFERENCES trains(id) ON DELETE CASCADE,
  item        TEXT NOT NULL CHECK (item IN ('제동장치','출입문','대차·차륜','전력·팬터그래프','신호수신(ATP)','객실 공조')),
  base_status TEXT NOT NULL DEFAULT 'ok' CHECK (base_status IN ('ok','warn','bad')),
  PRIMARY KEY (train_id, item)
);

-- ===== 장애 분석 템플릿 (F10) =====
CREATE TABLE fault_templates (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  fault_type      TEXT NOT NULL CHECK (fault_type IN ('signal','track','weather','delay')),
  sub_type        TEXT,                      -- weather: '폭우','강풍','폭설'
  name            TEXT NOT NULL,             -- '신호 장애'
  code_prefix     TEXT NOT NULL,             -- 'SIG'
  default_severity TEXT NOT NULL CHECK (default_severity IN ('주의','위험','심각')),
  summary_tpl     TEXT NOT NULL,             -- '{segment} 구간 궤도회로가 ...'
  delay_min       INTEGER NOT NULL,
  delay_max       INTEGER NOT NULL,
  UNIQUE (fault_type, sub_type)
);
CREATE TABLE template_causes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES fault_templates(id) ON DELETE CASCADE,
  label       TEXT NOT NULL,
  base_prob   INTEGER NOT NULL CHECK (base_prob BETWEEN 0 AND 100)
);
CREATE TABLE template_actions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES fault_templates(id) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,
  label       TEXT NOT NULL
);

-- ===== 사용자 (F7) =====
CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name  TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('viewer','operator','admin')),
  is_active     INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ===== 장애 =====
CREATE TABLE faults (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  code               TEXT NOT NULL UNIQUE,      -- 'F-001'
  fault_type         TEXT NOT NULL CHECK (fault_type IN ('signal','track','weather','delay')),
  sub_type           TEXT,
  line_id            TEXT NOT NULL REFERENCES lines(id),
  target_train_id    INTEGER REFERENCES trains(id),   -- delay 유형만
  location_text      TEXT NOT NULL,             -- '대전–김천구미'
  severity           TEXT NOT NULL CHECK (severity IN ('주의','위험','심각')),
  phase              TEXT NOT NULL CHECK (phase IN ('detected','analyzing','analyzed','recovering','resolved')),
  summary            TEXT,
  confidence         INTEGER,
  impact_trains      INTEGER,
  expected_delay_min INTEGER,
  source             TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','demo')),
  created_by         INTEGER REFERENCES users(id),
  recovered_by       INTEGER REFERENCES users(id),
  created_sim        INTEGER NOT NULL,          -- 시뮬레이션 시각(초)
  created_at         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  analysis_started_at TEXT,
  analyzed_at        TEXT,
  recovering_at      TEXT,
  resolved_at        TEXT,
  ana_epoch          REAL,                      -- 분석 시작 실제 시각(epoch 초)
  rec_epoch          REAL                       -- 복구 개시 실제 시각(epoch 초)
);
CREATE INDEX idx_faults_phase ON faults(phase);

CREATE TABLE fault_segments (
  fault_id   INTEGER NOT NULL REFERENCES faults(id) ON DELETE CASCADE,
  segment_id INTEGER NOT NULL REFERENCES segments(id),
  level      TEXT NOT NULL CHECK (level IN ('warn','danger')),
  PRIMARY KEY (fault_id, segment_id)
);
CREATE TABLE fault_causes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  fault_id    INTEGER NOT NULL REFERENCES faults(id) ON DELETE CASCADE,
  rank        INTEGER NOT NULL,
  label       TEXT NOT NULL,
  probability INTEGER NOT NULL
);
CREATE TABLE fault_actions (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  fault_id INTEGER NOT NULL REFERENCES faults(id) ON DELETE CASCADE,
  seq      INTEGER NOT NULL,
  label    TEXT NOT NULL,
  done     INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0,1)),
  done_at  TEXT,
  done_by  INTEGER REFERENCES users(id),
  UNIQUE (fault_id, seq)
);
CREATE TABLE fault_affected_trains (
  fault_id INTEGER NOT NULL REFERENCES faults(id) ON DELETE CASCADE,
  train_id INTEGER NOT NULL REFERENCES trains(id),
  PRIMARY KEY (fault_id, train_id)
);

-- ===== 로그·이력 =====
CREATE TABLE event_logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  sim_time   INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  category   TEXT NOT NULL CHECK (category IN ('info','ok','warn','danger','ai','action','audit')),
  message    TEXT NOT NULL,
  fault_id   INTEGER REFERENCES faults(id) ON DELETE SET NULL,
  train_id   INTEGER REFERENCES trains(id) ON DELETE SET NULL,
  user_id    INTEGER REFERENCES users(id)
);
CREATE INDEX idx_events_cat ON event_logs(category, id);
CREATE INDEX idx_events_created ON event_logs(created_at);

CREATE TABLE kpi_snapshots (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  sim_time       INTEGER NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  total_trains   INTEGER NOT NULL,
  on_time_rate   REAL NOT NULL,
  safety_index   REAL NOT NULL,
  delayed_trains INTEGER NOT NULL,
  active_faults  INTEGER NOT NULL
);
CREATE INDEX idx_kpi_created ON kpi_snapshots(created_at);

-- ===== 시뮬레이션 상태 (단일 행) =====
CREATE TABLE sim_state (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  sim_time     REAL NOT NULL DEFAULT 28800,   -- 08:00:00
  speed_mul    INTEGER NOT NULL DEFAULT 1 CHECK (speed_mul IN (1,2,5)),
  paused       INTEGER NOT NULL DEFAULT 0,
  demo_active  INTEGER NOT NULL DEFAULT 0,
  demo_elapsed REAL NOT NULL DEFAULT 0,
  fault_seq    INTEGER NOT NULL DEFAULT 0,
  -- 요청 기반 엔진(서버리스)용
  last_real      REAL NOT NULL DEFAULT 0,     -- 마지막으로 시간을 진행한 실제 시각(epoch 초)
  last_hist_real REAL NOT NULL DEFAULT 0,
  last_kpi_real  REAL NOT NULL DEFAULT 0,
  fault_ver      INTEGER NOT NULL DEFAULT 0,  -- 장애가 바뀔 때마다 1 증가 (화면 갱신 신호)
  demo_user_id   INTEGER,
  demo_result    TEXT,                        -- 'done' | 'stopped' | NULL
  updated_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
