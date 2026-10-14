# API 계약 (백엔드 ↔ 프론트엔드)

- 기준: `server/schemas.py`의 `PlayerView`와 하위 모델.
- **클라이언트로는 PlayerView만 나간다.** 사건 원본, 거짓말 장부, 범인 여부, 다른 NPC 비밀은 보내지 않는다(AGENTS.md 규칙 7).
- 실시간 이벤트는 SSE(`text/event-stream`)로 보내고, 이벤트 이름과 모양은 **AG-UI 이벤트 형식**을 따른다. 나중에 `ag-ui-langgraph`로 바꿔도 프론트엔드가 그대로 동작하게 하기 위해서다(PRD §11.10).
- 시각(`clock`, `game_time`)은 사건 첫날 00:00 기준 분(정수). 표시: `day`일차 `HH:MM`.
- 개발 서버: 백엔드 `http://localhost:8000`, 프론트엔드 `http://localhost:5173` (Vite 프록시로 `/api` → 8000).

## REST

| 메서드 | 경로 | 요청 | 응답 |
|:--|:--|:--|:--|
| GET | `/api/themes` | — | `[{id, title, emoji, description, preset: bool}]` |
| POST | `/api/games` | `{theme_id: string, options?: {tone?: "comic"\|"balanced"\|"serious", difficulty?: "easy"\|"normal"\|"hard", play_minutes?: 20\|40\|60}}` | `{game_id, view: PlayerView}` (MVP는 고정 사건 `demo_db_deleted`) |
| GET | `/api/games` | — | 진행 중인 게임 목록 `[{game_id, case_title, day, last_seen}]` (이어하기) |
| GET | `/api/games/{game_id}` | — | `PlayerView` |
| GET | `/api/games/{game_id}/saves` | — | 세이브 슬롯 목록 `[{slot_id, name, kind, saved_at}]` |
| POST | `/api/games/{game_id}/actions` | `Action` (아래) | SSE 이벤트 스트림 |
| POST | `/api/games/{game_id}/night` | — | SSE 이벤트 스트림 (하루 끝내기: 밤 시뮬레이션 진행 → 아침) |
| POST | `/api/games/{game_id}/save` | `{slot_name?: string}` | `{slot_id, saved_at}` |
| POST | `/api/games/{game_id}/load` | `{slot_id}` | `PlayerView` |
| GET | `/api/games/{game_id}/sources/{statement_id}` | — | 진술 출처 원문 `[{kind, title, content}]` (플레이어 권한 안의 것만) |
| POST | `/api/games/{game_id}/finale` | `FinaleStep` | SSE 이벤트 스트림 |
| POST | `/api/games/{game_id}/clear` | — | `{history: ClearHistory, card: ShareCard}` |
| GET | `/api/history` | — | `ClearHistory[]` |

### 사건 직접 만들기 (자유 주제, PRD §4.1·§4.2·§5.2)
| 메서드 | 경로 | 요청 | 응답 |
|:--|:--|:--|:--|
| POST | `/api/cases` | `{theme_text: string(2~80자), options?: CreateOptions}` | `202 {job_id}` · 빈 문자열/너무 길면 `400 {detail}` |
| GET | `/api/cases/{job_id}` | — | `CaseJob` (아래) · 없는 작업이면 `404` |

```ts
CaseJob = {
  job_id: string
  status: "running" | "ready" | "failed" | "rejected"
  stage: number            // 1부터 total까지
  total: number
  stage_text: string       // 게임 안 말투. 예: "사건 파일 작성 중…", "용의자 명단 정리 중…"
  preview: null | {        // 세계관·인물이 정해지면 채워짐 → 이때부터 브리핑을 보여 준다
    title: string
    incident_summary: string
    characters: PublicCharacter[]   // location_id는 null
  }
  game_id: string | null   // status=ready 일 때만
  view: PlayerView | null  // status=ready 일 때만 (바로 메인 화면 진입 가능)
  message: string | null   // failed/rejected 사유 (플레이어용 문장)
  fallback_theme_id: string | null  // failed일 때 대신 할 수 있는 기본 주제
}
```
- 화면 흐름: "사건 생성 ▶" → 1초 간격으로 GET 폴링 → `preview`가 생기면 **브리핑 화면**(제목·요약·인물 카드)을 띄우고 아래에 `stage_text` 진행 표시 → `ready`면 "수사 시작" 버튼 활성화.
- `rejected`: 부적절한 주제. `message`를 보여 주고 시작 화면으로. `failed`: `message`와 함께 `fallback_theme_id`로 바로 시작하는 버튼.
- 자유 주제 카드에는 "실험실" 표시(결과가 들쭉날쭉할 수 있음). 생성에는 1~3분 걸린다.

- `phase`는 첫 행동이 들어오면 서버가 `briefing` → `day`로 바꾼다. 화면은 "수사 시작" 버튼으로 넘어가도 된다.
- **인물 목록 순서는 서버가 판마다 섞어 보낸다**(범인이 앞이나 뒤에 몰리면 순서로 추측 가능). 화면은 받은 순서를 쓴다.
- `ShareCard`: `{emoji_line: "🔍🔍❌🔍✅", share_text: string, theme_color: "#RRGGBB"}`. 실패한 판에는 `card`가 `null`.
- 결과 카드에는 범인 이름을 가리지 않고 그대로 보여 준다(PRD §10.3: 다른 사람이 같은 사건을 할 일이 없어 스포일러 문제 없음).

### Action (POST /actions 본문)
```json
{ "type": "move",        "location_id": "loc_server_room" }
{ "type": "investigate", "location_id": "loc_server_room" }
{ "type": "ask",         "npc_id": "npc_dba", "text": "어젯밤 11시쯤 어디 계셨어요?" }
{ "type": "chip",        "chip_id": "chip_3" }
{ "type": "present",     "npc_id": "npc_dba", "evidence_id": "ev_access_log" }
{ "type": "bluff",       "npc_id": "npc_dba", "claim_id": "claim_accomplice_confessed", "claim_subject": null, "basis_evidence_ids": ["ev_access_log"] }
{ "type": "warrant",     "system": "call", "target_id": "npc_dba", "basis_evidence_ids": ["ev_access_log", "ev_chat_edit"] }
{ "type": "apologize",   "npc_id": "npc_dba" }
{ "type": "hint" }
```
하루 끝내기는 행동이 아니라 `POST /night`로 한다.

### FinaleStep (POST /finale 본문)
```json
{ "type": "start",   "accused_id": "npc_cleaner" }
{ "type": "present", "stage": "opportunity", "evidence_id": "ev_access_log" }
{ "type": "confirm" }
```

## SSE 이벤트 (AG-UI 형식)

각 이벤트는 `data: <JSON>\n\n` 한 줄. JSON에는 항상 `type`이 있다.

| type | 필드 | 쓰임 |
|:--|:--|:--|
| `RUN_STARTED` | `runId` | 처리 시작 |
| `TEXT_MESSAGE_START` | `messageId`, `role`(`"npc"`\|`"narrator"`\|`"partner"`\|`"chief"`), `speakerId` | 대사 시작 (초상화 표시, 글자 찍기 준비) |
| `TEXT_MESSAGE_CONTENT` | `messageId`, `delta` | 대사 조각 (글자 찍힘 효과) |
| `TEXT_MESSAGE_END` | `messageId` | 대사 끝 |
| `STATE_SNAPSHOT` | `snapshot: PlayerView` | 전체 뷰 교체 (처음, 불러오기, 아침) |
| `STATE_DELTA` | `delta: JSONPatch[]` (RFC 6902) | 바뀐 부분만 (행동 수, 위치, 수첩 등) |
| `CUSTOM` | `name`, `value` | 게임 전용 이벤트 (아래) |
| `RUN_FINISHED` | `runId` | 처리 끝 |
| `RUN_ERROR` | `message`, `code` | 오류 (화면은 멈추지 말고 안내) |

### CUSTOM 이벤트 이름
| name | value | 화면 처리 |
|:--|:--|:--|
| `emotion` | `{npcId, emotion}` | 초상화 표정(표정 사진 교체 + 표정 글자 칩, 그림 얼굴은 표정 그림) |
| `notebook` | `{added: {evidence_ids?, statements?, contradictions?}}` | 수첩에 추가, 모순이면 ⚠ 강조 |
| `feed` | `FeedItem` | 단톡방·사내 메신저 피드에 추가 |
| `chips` | `{chips: Chip[]}` | 질문 추천 칩 갱신 |
| `cutin` | `{text: "이의 있음!"\|..., style}` | 컷인 연출 |
| `turn_away` | `{npcId, untilActions}` | NPC가 등 돌림, 대화창 잠금 |
| `director` | `{eventId, title, text}` | 연출 감독 이벤트(전화, 제보, 정전 등) |
| `night_progress` | `{step, total, text}` | "밤이 깊어 갑니다…" 진행 표시 |
| `overheard` | `{locationId, lines: [{speakerId, text}]}` | 엿듣기 |
| `finale` | `{accused_id, stage, lives, filled: ["opportunity"\|"means"\|"motive"], last: {result: "correct"\|"wrong"\|"rebutted", evidence_id?}}` | 최종 추리 쇼 진행 상태 |
| `ending` | `{ending, replay?}` | 엔딩·진실 리플레이 데이터 (replay 모양은 Phase 3에서 확정) |

## 캐릭터 그림
### AI 초상화 (실사 사진 느낌, 2026-10-13 사용자 결정)
- `PublicCharacter.portrait_url: string | null` — 서버가 그 판을 위해 새로 그린 초상화 주소(예: `/api/portraits/<key>/<id>.webp?v=1`, 480×640 WebP. 확장자는 png·jpg·webp 중 하나일 수 있음).
  `PlayerView.characters`와 `CaseJob.preview.characters` 모두에 있다. 그림은 백그라운드로 그려지므로 **처음엔 `null`이었다가 나중에 채워질 수 있다**
  (폴링 응답·`STATE_SNAPSHOT`·`STATE_DELTA`로 바뀐 값이 온다).
- `null`이거나 이미지 로드에 실패하면 아래 절차적 SVG로 대신 그린다.
- `GET /api/games/{id}/portraits` → `{pending: boolean, urls: {인물 id: 주소}, emotions: {인물 id: {표정: 주소}}}`. 화면은 빠진 사진이 있으면 3초마다 묻고,
  `pending=false`가 되면(다 그렸거나 그리지 않는 중) 멈춘다(최대 3분). 서버는 그리는 중이 아닌데 빠진 사람이 있으면
  (서버 재시작으로 끊김 등) 그 사람만 한 번 더 그린다(한 판에 최대 2번).
- `PublicCharacter.portrait_emotions: {표정: 주소} | null` — 같은 얼굴의 표정 사진(그린 것만). 서버는 그 인물의 그 감정이 처음 나올 때 그린다(약 10초).
  화면은 감정에 맞는 표정 사진이 있으면 그것을, 없으면 기본 사진(`portrait_url`)을 쓴다. 행동이 끝날 때마다 사진 상태를 다시 묻는다.
- 사진에는 감정 효과를 얹지 않는다(PRD §9.4, 2026-10-14 변경). 표정이 바뀌면 180ms 크로스페이드, 이름 옆에 표정 글자 칩.
  `GET /portraits` 의 `pending` 이 true 인 동안 사진이 없는 인물은 "사진 준비 중" 칸으로 보여 준다.
- `GET /api/portraits/{key}/{file}` → 이미지(`image/png`·`image/jpeg`·`image/webp`). 클리어하면 그 판의 초상화 파일은 삭제된다
  (서버의 사진 보관함에는 남지만 이 주소로는 다시 열 수 없다).

### 절차적 SVG (대체 그림)
- `PublicCharacter.face_seed`(정수)와 `appearance`(예: `{"hair": "short", "hair_color": "#3b2f2f", "outfit": "cleaner_uniform", "accessory": "mop"}`)로 SVG를 그린다.
- 같은 시드는 항상 같은 얼굴. 얼굴 생김새는 시드로 연속값을 뽑아 그린다(저장형 부품 아님).
- 표정은 `emotion`에 따라 눈·눈썹·입 파라미터만 바꾼다.
- 화풍: 현대식 깔끔한 플랫 일러스트(`docs/art-style.md`).
