# The Suspects 웹 프론트엔드

Vite + React + TypeScript로 만든 추리 게임 화면입니다. 백엔드(FastAPI)와는 REST와 SSE(AG-UI 이벤트 형식)로 통신합니다.

## 실행 방법

`apps/web`에서 실행합니다. Node 20 이상이 필요합니다.

```bash
npm install
npm run dev        # 개발 서버 http://localhost:5173 ( /api 는 http://localhost:8000 으로 프록시 )
npm run dev:mock   # 백엔드 없이 가짜 데이터(목 모드)로 끝까지 플레이
npm run build      # 타입 검사 + 프로덕션 빌드
npm test           # vitest
```

목 모드는 `VITE_USE_MOCK=1`일 때 켜집니다. `npm run dev:mock`은 `.env.mock`을 읽어 이 값을 설정합니다.

## 폴더 구조

| 경로 | 내용 |
|:--|:--|
| `src/api/` | 계약 타입(`types.ts`), REST·SSE 클라이언트(`client.ts`, `sse.ts`), JSON Patch(`jsonpatch.ts`), 목 백엔드(`mock.ts`) |
| `src/state/` | AG-UI 이벤트를 화면 상태로 바꾸는 리듀서(`reducer.ts`)와 게임 훅(`useGame.ts`) |
| `src/character/` | 시드로 그리는 절차적 SVG 초상화(`faceRender.ts`, `Portrait.tsx`) |
| `src/components/` | 지도, 수첩, 무대(초상화·대사), 행동 바, 블러핑 창, 오버레이 |
| `src/screens/` | 첫 화면, 브리핑, 메인, 최종 추리, 결과 카드, 클리어 이력 |
| `src/util/` | 지도 자동 배치, 시간·공유 문구, 결과 카드 PNG 생성, 브라우저 저장 |

## 백엔드 계약

- API 계약: 저장소 루트의 `docs/api-contract.md`
- 데이터 모델: `server/schemas.py`의 `PlayerView` 이하 모델
- 화풍: `docs/art-style.md`

클라이언트는 `PlayerView`만 받습니다. 범인이나 비밀 정보는 화면 코드에 없습니다.

## 참고

- 서버의 이어하기 목록(`GET /api/games`)을 받지 못하면 이 브라우저에 기억해 둔 저장본을 대신 보여 줍니다.
- 결과 카드 PNG는 브라우저 캔버스에서 만들며 서버에 저장하지 않습니다.
