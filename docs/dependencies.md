# 의존성 표 (PRD §11.12.1)

버전은 `uv.lock`에 고정된다. 0.0.x·RC 의존성은 CI 스모크 테스트 3종(엔드포인트 응답, 스트리밍 이벤트 순서, 상태 변화분)을 통과해야 올린다.

| 의존성 | 버전 (2026-10-13 설치) | 상태 | 확인일 | 실패 시 대체 |
|:--|:--|:--|:--|:--|
| Python | 3.12 (uv 관리) | 정식판 | 2026-10-13 | — |
| langgraph | 1.2.15 | 정식판 | 2026-10-13 | — |
| langchain-core | 1.6.10 | 정식판 | 2026-10-13 | — |
| langchain-openai | 1.7.1 | 정식판 | 2026-10-13 | OpenRouter는 OpenAI 호환 API라 httpx 직접 호출로 대체 가능 |
| fastapi | 0.143.0 | 정식판 | 2026-10-13 | — |
| uvicorn | 0.54.0 | 정식판 | 2026-10-13 | — |
| pydantic | 2.14.1 | 정식판 | 2026-10-13 | — |
| rank-bm25 | 0.2.2 | 정식판(오래됨) | 2026-10-13 | 키워드 점수를 직접 구현 |
| numpy | 2.5.4 | 정식판 | 2026-10-13 | — |
| AG-UI | 자체 SSE (AG-UI 이벤트 형식) | — | 2026-10-13 | `ag-ui-langgraph` 0.0.47은 Phase 1 이후 검토. 지금은 같은 이벤트 형식을 직접 내보냄 |
| MCP Python SDK v2.x | 미설치 (Phase 2~4) | 정식판 | 2026-10-12 | — |
| MCP Apps | 미설치 (Phase 4) | 공식 확장, 일부 앱 렌더링 버그 열림 | 2026-10-12 | 다른 호스트 + 텍스트 응답 |
| MCP Tasks | 사용 안 함 | 공식 Python SDK 미구현 | 2026-10-12 | `start_case` + `get_case_status` |
| DB | SQLite (표준 라이브러리) | 정식판 | 2026-10-13 | 배포 시 Postgres + 벡터 확장으로 이전 (저장소 계층 분리) |
| 임베딩 모델 | 미선정 | — | — | MVP는 키워드(BM25) + 해시 임베딩(테스트용) |
| pillow | 12.3.0 | 정식판 | 2026-10-13 | 초상화 축소·WebP 압축. 실패하면 그 그림만 버리고 SVG로 대신 |
| 인물 초상화 모델 | Cloudflare Workers AI `flux-2-klein-4b` (REST, httpx) | 정식판 | 2026-10-13 | 할당량 초과·키 없음 → 절차적 SVG. 설정으로 OpenRouter 이미지 모델 |
| 배경 이미지 모델 | 미선정 | — | — | Phase 2. 임시 배경(장소 이름 + 아이콘) |
| 프론트엔드 | Vite + React + TypeScript (Node 24.20.0 LTS, npm 11.19.0) | 정식판 | 2026-10-13 | — |
| 글꼴 | @fontsource/ibm-plex-sans-kr 5.3.0, @fontsource/nanum-gothic-coding 5.3.0 (SIL OFL 1.1) | 정식판 | 2026-10-14 | 앱에 포함(유니코드 범위 조각이라 쓰는 글자만 받음). 전문 `apps/web/public/licenses/` |
| 아이콘 | Phosphor Icons 2.1.1 (MIT) | 정식판 | 2026-10-14 | 패키지 대신 SVG 경로만 `apps/web/src/components/Icon.tsx`에 담음. 전문 `apps/web/public/licenses/` |
| Docker / Postgres | 미설치 | — | 2026-10-13 | MVP는 SQLite로 충분. Postgres 이전 시 재판단 |
