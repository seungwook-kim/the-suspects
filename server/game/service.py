"""게임 서비스: 규칙 엔진·RAG·LangGraph 그래프·저장소를 한 판의 흐름으로 묶는다.

- API 계층(server/api/app.py)만 이 모듈을 부른다.
- 판정은 server.rules(코드), 대사·서술은 LLM(키가 없으면 가짜 LLM).
- 클라이언트로는 build_view가 만든 PlayerView와 AG-UI 형식 이벤트만 나간다.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from pydantic import BaseModel

from server.agents.router import SemanticRouter
from server.cases.generate import STAGE_TEXT, TOTAL_STAGES, generate_case
from server.cases.loader import list_case_ids, load_case_by_id
from server.config import load_game_config
from server.game import content as C
from server.game.events import EventBuilder
from server.game.josa import josa
from server.game.masking import IdMasker, new_salt
from server.game.night_deps import build_night_deps
from server.game.portrait_library import PortraitLibrary
from server.game.portraits import PortraitStore
from server.game.speculative import Speculator, TaggedLLM, state_key
from server.game.view import build_view
from server.graphs.night import run_night
from server.graphs.turn import PreparedAnswer, TurnDeps, prepare_answer, run_turn
from server.llm.client import LLMClient
from server.llm.images import ImageClient
from server.llm.tracing import CallRecord, Tracer
from server.rag.embedding import CachedEmbedding, HashEmbedding
from server.rag.indexer import index_case
from server.rag.relations import RelationGraph
from server.rag.retriever import HybridRetriever
from server.rag.store import RagStore
from server.rules import actions as act_rules
from server.rules import bluff as bluff_rules
from server.rules import director as dir_rules
from server.rules import finale as fin_rules
from server.rules import gm_rules
from server.rules import grade as grade_rules
from server.rules import offtopic as off_rules
from server.rules import reputation as rep_rules
from server.rules import speculative as spec_rules
from server.rules import sufficiency as suff_rules
from server.rules import trust as trust_rules
from server.rules import warrant as war_rules
from server.schemas import (
    BluffAction,
    CaseBible,
    ClearHistory,
    Contradiction,
    GameState,
    GMVerdict,
    MemoryDoc,
    NotebookStatement,
    NPCReply,
    NPCState,
    PlayerView,
    RetrievalHit,
    RouterOutput,
    ShareCard,
)
from server.storage.db import GameStore, StorageError

_ROOT = Path(__file__).resolve().parents[2]

THEMES = {
    "demo_db_deleted": {"emoji": "💾", "description": "서비스 오픈 전날 밤, 운영 DB와 감사 로그가 사라졌다."},
}


def _absorb(target: GameState, new: GameState) -> None:
    """규칙 엔진은 새 상태를 돌려주므로(불변 스타일), 그래프가 들고 있는 객체에 값을 옮겨 담는다."""
    if new is target:
        return
    for k in GameState.model_fields:
        setattr(target, k, getattr(new, k))


class _NoStream:
    """실시간 출력을 쓰지 않게 감싼 모델 연결(설정 speed.stream_npc_answers: false)."""

    can_stream = False

    def __init__(self, llm) -> None:
        self._llm = llm

    def __getattr__(self, name: str):
        return getattr(self._llm, name)


class _LiveEvents(list):
    """붙이는 즉시 화면으로 내보내는 이벤트 목록(인물 답을 첫 문장부터 보여 주기)."""

    def __init__(self, push) -> None:
        super().__init__()
        self._push = push

    def append(self, ev: dict) -> None:  # type: ignore[override]
        super().append(ev)
        self._push(ev)

    def extend(self, evs) -> None:  # type: ignore[override]
        for ev in list(evs):
            self.append(ev)


class GMCheck(BaseModel):
    ok: bool
    reason: str = ""


class GameService:
    def __init__(self, data_dir: str | Path | None = None, *, in_memory: bool = False, llm: LLMClient | None = None):
        self.cfg = load_game_config()
        mode = os.getenv("THE_SUSPECTS_MODE", "dev")
        data = Path(data_dir) if data_dir else _ROOT / "var"
        self.llm = llm or LLMClient(tracer=Tracer(path=None if in_memory else data / "traces.jsonl",
                                                  mode="prod" if mode == "prod" else "dev"))
        self.store = GameStore(":memory:" if in_memory else data / "game.sqlite3")
        self.rag = RagStore(":memory:" if in_memory else str(data / "rag.sqlite3"),
                            embedder=CachedEmbedding(HashEmbedding(256)))
        hybrid = self.cfg.rag.get("hybrid", {})
        self.retriever = HybridRetriever(self.rag, bm25_weight=hybrid.get("keyword_weight", 0.4),
                                         vector_weight=hybrid.get("vector_weight", 0.6))
        self.relations = RelationGraph(self.rag)
        self.router = SemanticRouter()
        self.presets: list[str] = list_case_ids()
        self.cases: dict[str, CaseBible] = {cid: load_case_by_id(cid) for cid in self.presets}
        for cid, case_json in self.store.load_cases():  # 자유 주제로 만든 사건 (진행 중인 판이 있는 것만 남아 있다)
            self.cases[cid] = CaseBible.model_validate_json(case_json)
        for case in self.cases.values():
            self._index_template(case)
        self.jobs: dict[str, dict] = {}  # 사건 생성 작업 (메모리, 서버 재시작 시 사라짐)
        self.spec = Speculator()  # 추천 질문 답 미리 만들기 (메모리, 서버 재시작 시 사라짐)
        self.history_photos = data / "history_photos"  # 클리어 기록용 인물 사진 사본(결과 카드)
        self.portraits = PortraitStore(data / "portraits", ImageClient(tracer=self.llm.tracer),
                                       library=None if in_memory else PortraitLibrary(data / "portrait_library"))

    # ================================================================= 초상화 (AI, 없으면 화면이 SVG로)
    def _portrait_key(self, state: GameState) -> str:
        return state.game_id if state.case_id in self.presets else state.case_id

    @staticmethod
    def _public_people(chars) -> list[dict]:
        """그림 요청에 넣는 공개 정보만 (범인 여부·비밀·성격 제외)."""
        return [{"id": c["id"] if isinstance(c, dict) else c.id,
                 **{k: (c[k] if isinstance(c, dict) else getattr(c, k)) for k in ("role", "age", "gender", "appearance")}}
                for c in chars]

    def _index_template(self, case: CaseBible) -> None:
        tpl = self._template_slot(case.case_id)
        if not self.rag.count_slot(tpl):
            index_case(self.rag, case, tpl)
            self.relations.seed_from_case(case, tpl)

    # ================================================================= 공통
    @staticmethod
    def _template_slot(case_id: str) -> str:
        return f"tpl_{case_id}"

    def _load(self, game_id: str) -> tuple[CaseBible, GameState, IdMasker]:
        state = self.store.load_live(game_id)
        case = self.cases[state.case_id]
        return case, state, IdMasker(case, state.id_salt)

    def _bands(self) -> list[tuple[int, str]]:
        return [(b.min, b.name or "") for b in self.cfg.reputation.titles]

    def _refresh(self, case: CaseBible, state: GameState) -> None:
        state.notebook.sufficiency = suff_rules.all_sufficiency(self.cfg, case, state.notebook)
        C.apply_unlocks(case, state)

    def _chips(self, case: CaseBible, state: GameState, masker: IdMasker):
        chips, defs = C.build_chips(case, state, lambda eid: masker.out("evidence", eid))
        state.director_state["chips"] = defs
        return chips

    def _view(self, case: CaseBible, state: GameState, masker: IdMasker) -> PlayerView:
        self._refresh(case, state)
        key = self._portrait_key(state)
        # 표정 사진은 그 감정이 처음 나올 때 그 사람 것만 그린다 (할당량 절약, 그동안은 기본 사진 + 효과)
        wants = [(p, state.npc_states[p["id"]].emotion) for p in self._public_people(case.characters)
                 if p["id"] in state.npc_states and state.npc_states[p["id"]].emotion != "neutral"]
        self.portraits.want_emotions(key, wants, game_id=state.game_id)
        return build_view(case, state, masker, chips=self._chips(case, state, masker), bands=self._bands(),
                          actions_total=self.cfg.day_actions, portraits=self.portraits.urls(key),
                          portrait_emotions=self.portraits.emotion_urls(key))

    def _obtain(self, case: CaseBible, state: GameState, evidence_ids: list[str]) -> list[str]:
        """증거를 수첩에 넣는다. 새로 얻은 것만 돌려준다."""
        new = [e for e in evidence_ids if e not in state.notebook.evidence_ids]
        for e in new:
            state.notebook.evidence_ids.append(e)
            _absorb(state, rep_rules.apply_event(self.cfg, state, "clue_found"))
        if new:
            state.director_state["actions_since_clue"] = 0
        return new

    def _say(self, events: list[dict], eb: EventBuilder, role: str, speaker: str | None, text: str) -> None:
        events.extend(eb.text(role, speaker, text))

    # ================================================================= 목록·생성
    def themes(self) -> list[dict]:
        return [{"id": cid, "title": self.cases[cid].title, "preset": True,
                 **THEMES.get(cid, {"emoji": "🔍", "description": self.cases[cid].theme})} for cid in self.presets]

    # ================================================================= 사건 직접 만들기 (PRD §4.1·§4.2·§5.2)
    _JOB_PUBLIC = ("job_id", "status", "stage", "total", "stage_text", "preview", "game_id", "view", "message",
                   "fallback_theme_id")

    def create_case_job(self, theme_text: str, options: dict | None = None) -> str:
        """자유 주제 사건 생성을 백그라운드로 시작한다. 실행 중인 이벤트 루프 안에서 불러야 한다."""
        text = " ".join((theme_text or "").split())
        if not 2 <= len(text) <= 80:
            raise ValueError("주제는 2~80자로 적어 주세요.")
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = {"job_id": job_id, "status": "running", "stage": 1, "total": TOTAL_STAGES, "stage_text": STAGE_TEXT[1],
               "preview": None, "game_id": None, "view": None, "message": None, "fallback_theme_id": None}
        self.jobs[job_id] = job
        job["_task"] = asyncio.get_running_loop().create_task(self._run_case_job(job, text, options or {}))
        return job_id

    def case_job(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        out = {k: job[k] for k in self._JOB_PUBLIC}
        if out["preview"]:  # 초상화는 생성 도중에 하나씩 채워진다
            urls = self.portraits.urls(job["_case_id"])
            out["preview"] = {**out["preview"], "characters": [{**c, "portrait_url": urls.get(c["id"])}
                                                                for c in out["preview"]["characters"]]}
        return out

    async def _run_case_job(self, job: dict, text: str, options: dict) -> None:
        case_id = f"gen_{uuid.uuid4().hex[:10]}"
        job["_case_id"] = case_id

        def progress(stage: int, stage_text: str, preview: dict | None) -> None:
            job["stage"], job["stage_text"] = stage, stage_text
            if preview is not None:
                job["preview"] = preview
                # 인물이 정해지는 순간부터 초상화를 동시에 그린다 (PRD §5.2 ③: 이미지 생성 병렬)
                self.portraits.start(case_id, self._public_people(preview["characters"]), setting=text)

        try:
            res = await generate_case(self.llm, case_id, text, options, progress)
            if res.outcome != "ok":
                self.portraits.delete(case_id)  # 못 쓰게 된 사건의 그림은 바로 지움
            if res.outcome == "rejected":
                job.update(status="rejected", message=res.message)
                return
            if res.outcome != "ok" or res.case is None:
                job.update(status="failed", message=(res.message or "사건을 만들지 못했어요.") + " 기본 사건으로 해 볼까요?",
                           fallback_theme_id=self.presets[0] if self.presets else None)
                return
            progress(TOTAL_STAGES, STAGE_TEXT[TOTAL_STAGES], None)
            case = res.case
            self.store.save_case(case.case_id, case.model_dump_json())
            self.cases[case.case_id] = case
            self._index_template(case)
            game_id, view = self.new_game(case.case_id, options)
            job.update(status="ready", game_id=game_id, view=view.model_dump(mode="json"))
        except Exception as e:  # 생성 실패가 서버를 멈추지 않게
            job.update(status="failed", message=f"사건을 만들다 문제가 생겼어요({type(e).__name__}). 기본 사건으로 해 볼까요?",
                       fallback_theme_id=self.presets[0] if self.presets else None)

    def _forget_generated(self, case: CaseBible) -> None:
        """자유 주제 사건은 그 판이 끝나면 사건 원본·색인까지 지운다 (배경·스토리 재사용 금지, PRD §10.2)."""
        if case.case_id in self.presets:
            return
        self.rag.delete_slot(self._template_slot(case.case_id))
        self.store.delete_case(case.case_id)
        self.cases.pop(case.case_id, None)

    def new_game(self, theme_id: str, options: dict | None = None) -> tuple[str, PlayerView]:
        if theme_id not in self.cases:
            raise KeyError(theme_id)
        case = self.cases[theme_id]
        opts = options or {}
        difficulty = opts.get("difficulty") or case.difficulty
        game_id = f"g_{uuid.uuid4().hex[:12]}"
        slot = f"slot_{uuid.uuid4().hex[:12]}"
        unlocked = [l.id for l in case.locations if not l.unlock_condition]
        npc_states = {}
        for ch in case.characters:
            npc_states[ch.id] = NPCState(
                npc_id=ch.id, location_id=C.day_location(case, ch, unlocked, 1),
                trust=trust_rules.start_trust(self.cfg, ch), alertness=self.cfg.alertness.start,
                visible=ch.initial_visible,
            )
        inv = self.cfg.investigation
        state = GameState(
            game_id=game_id, slot_id=slot, case_id=case.case_id, player_location=case.start_location_id, visited_locations=[case.start_location_id],
            unlocked_locations=unlocked, npc_states=npc_states, reputation=self.cfg.reputation.start,
            difficulty=difficulty, max_days=act_rules.investigation_days(self.cfg, difficulty),
            actions_left=act_rules.new_day_actions(self.cfg), clock=inv["day_start_minute"], id_salt=new_salt(),
            phase="briefing",
        )
        self.rag.copy_slot(self._template_slot(case.case_id), slot)
        self.store.create_game(state)
        # 초상화: 판마다 새로 그린다 (자유 주제 사건은 생성 중에 이미 그리기 시작함 — 같은 key면 무시)
        self.portraits.start(self._portrait_key(state), self._public_people(case.characters), setting=case.theme,
                             game_id=game_id)
        return game_id, self._persist_view(case, state)

    def _persist_view(self, case: CaseBible, state: GameState) -> PlayerView:
        view = self._view(case, state, IdMasker(case, state.id_salt))
        self.store.save_live(state)
        return view

    def list_games(self) -> list[dict]:
        out = []
        for g in self.store.list_games():
            case = self.cases.get(g["case_id"])
            out.append({**g, "case_title": case.title if case else g["case_id"]})
        return out

    def view(self, game_id: str) -> PlayerView:
        case, state, _ = self._load(game_id)
        return self._persist_view(case, state)

    def portrait_status(self, game_id: str) -> dict:
        """화면이 사진 완성을 기다리며 가볍게 묻는 용도: 지금까지 그린 사진 주소와 아직 그리는 중인지.
        빠진 사람이 있는데 그리는 중이 아니면(서버 재시작으로 작업이 끊김 등) 빠진 사람만 다시 그린다(상한 있음)."""
        state = self.store.load_live(game_id)
        key = self._portrait_key(state)
        case = self.cases.get(state.case_id)
        if case and not self.portraits.pending(key) and self.portraits.missing(key, [c.id for c in case.characters]):
            self.portraits.start(key, self._public_people(case.characters), setting=case.theme, game_id=game_id)
        return {"pending": self.portraits.pending(key), "urls": self.portraits.urls(key),
                "emotions": self.portraits.emotion_urls(key)}

    # ================================================================= 행동
    async def act(self, game_id: str, action: dict) -> AsyncIterator[dict]:
        """행동 하나. 이벤트는 만들어지는 즉시 내보낸다(인물 답은 첫 문장부터). 화면 연결이 끊겨도 행동은 끝까지
        처리하고 저장한다."""
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.ensure_future(self._act(game_id, action, queue.put_nowait))
        while True:
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield getter.result()
                continue
            getter.cancel()
            while not queue.empty():
                yield queue.get_nowait()
            task.result()  # 처리 중 오류는 그대로 올린다(API 계층이 오류 이벤트로 바꿈)
            return

    async def _act(self, game_id: str, action: dict, push) -> None:
        case, state, masker = self._load(game_id)
        key = state_key(state)  # 행동 전 상태 (미리 만든 칩 답이 이 상태용인지 가른다)
        eb = EventBuilder()
        push(eb.run_started())
        before = self._view(case, state, masker)
        events = _LiveEvents(push)  # 붙이는 즉시 내보낸다
        kind = action.get("type")
        if state.phase in ("ended", "finale"):
            push(eb.run_error("지금은 할 수 없는 행동이에요.", code="phase"))
            push(eb.run_finished())
            return
        if state.phase == "briefing":
            state.phase = "day"
        cost_kind = {"move": "move", "investigate": "investigate", "ask": "ask", "chip": "ask",
                     "present": "present_evidence", "bluff": "bluff", "warrant": "warrant",
                     "hint": "hint", "apologize": "default"}.get(kind)
        if kind == "move":
            cost_kind = act_rules.move_kind(state, action.get("location_id"))
        if cost_kind is None:
            push(eb.run_error(f"모르는 행동입니다: {kind}", code="bad_action"))
            push(eb.run_finished())
            return
        ok, reason = act_rules.can_perform(self.cfg, state, cost_kind)
        if not ok:
            msg = "오늘은 더 움직일 수 없어요. 하루를 끝내세요." if reason == "no_actions_left" else "지금은 할 수 없어요."
            push(eb.run_error(msg, code=reason))
            push(eb.run_finished())
            return
        prepared = await self._take_prepared(game_id, key, state, action) if kind == "chip" else None
        self._spend(state, cost_kind)
        ds = state.director_state
        ds["actions_since_clue"] = ds.get("actions_since_clue", 0) + 1
        ds["actions_since_event"] = ds.get("actions_since_event", 10**6) + 1

        try:
            if kind == "move":
                await self._do_move(case, state, action, events, eb)
            elif kind == "investigate":
                self._do_investigate(case, state, masker, events, eb)
            elif kind in ("ask", "chip"):
                await self._do_ask(case, state, masker, action, events, eb, prepared=prepared)
            elif kind == "present":
                await self._do_present(case, state, masker, action, events, eb)
            elif kind == "bluff":
                await self._do_bluff(case, state, masker, action, events, eb)
            elif kind == "warrant":
                self._do_warrant(case, state, masker, action, events, eb)
            elif kind == "hint":
                self._say(events, eb, "partner", "partner", C.hint_text(case, state))
            elif kind == "apologize":
                self._do_apologize(case, state, action, events, eb)
        except _BadAction as e:
            events.append(eb.run_error(str(e), code="bad_action"))

        self._director(case, state, events, eb)
        state.events_log.append({"type": "action", "day": state.day, "clock": state.clock, "kind": kind,
                                 "npc": action.get("npc_id")})
        after = self._view(case, state, masker)
        self.spec.close(game_id)  # 행동을 했으니 이전 상태용 준비분은 끝. 화면이 새 상태로 다시 부른다
        self._record_speculation(state)
        self.store.save_live(state)
        delta = eb.delta(before, after)
        if delta:
            push(delta)
        push(eb.custom("chips", {"chips": [c.model_dump() for c in after.chips]}))
        push(eb.run_finished())

    async def _gm_llm_judge(self, case: CaseBible, npc_id: str, reply: NPCReply, verdict: GMVerdict,
                            hits: list[RetrievalHit], game_id: str, llm=None) -> bool:
        """게임 마스터 LLM 검사(부록 F.11): 알 수 있는 정보만 말했는지, 숨길 진실을 털어놓지 않았는지. True면 통과."""
        hidden = ""
        if "hidden_truth" in verdict.triggers:  # 숨길 진실을 털어놓았는지도 본다
            truths = [lie.truth for lie in case.lie_ledger if lie.liar_id == npc_id]
            hidden = f"\n이 인물이 증거 없이는 숨겨야 하는 사실: {truths}\n대답이 이 사실을 털어놓았으면 ok=false."
        out, _ = await (llm or self.llm).structured(
            role="gm_check", bucket="gm", schema=GMCheck,
            system="추리 게임의 게임 마스터다. 인물의 대답이 그 인물이 알 수 있는 정보만 말했는지, "
                   "숨겨야 할 사실을 털어놓지 않았는지 판정한다.",
            user=f"인물: {C.char(case, npc_id).name}\n인물이 아는 것: {[h.content for h in hits]}\n"
                 f"대답: {reply.text}\n문제 신호: {verdict.triggers}{hidden}",
            fake=lambda: GMCheck(ok=True), fallback=lambda: GMCheck(ok=False, reason="판정 실패"),
            game_id=game_id, node="gm_llm",
        )
        return out.ok

    def _spend(self, state: GameState, cost_kind: str) -> None:
        """행동 소모와 게임 속 시간 흐름 (실제 행동과 칩 답 미리 만들기가 같은 계산을 쓴다)."""
        _absorb(state, act_rules.spend(self.cfg, state, cost_kind))
        state.clock += self.cfg.investigation["minutes_per_action"] * act_rules.action_cost(self.cfg, cost_kind)

    # ----------------------------------------------------------------- 추천 질문 답 미리 만들기 (PRD §14.1, 부록 F.15)
    async def prepare(self, game_id: str, npc_id: str) -> dict:
        """플레이어가 이 인물을 심문하는 중이다(화면이 알림). 이 인물의 질문 칩 답을 백그라운드로 미리 만든다.
        게임 상태는 바꾸지 않는다. {"prepared": 새로 시작한 수}."""
        case, state, masker = self._load(game_id)
        stats = spec_rules.SpeculativeStats.model_validate(state.director_state.get("speculative") or {})
        ns = state.npc_states.get(npc_id or "")
        if (state.phase not in ("day", "briefing") or not spec_rules.is_enabled(self.cfg, stats)
                or not ns or not ns.visible or ns.location_id != state.player_location
                or (ns.turned_away_until is not None and state.action_no < ns.turned_away_until)
                or not act_rules.can_perform(self.cfg, state, "ask")[0]):
            return {"prepared": 0}
        self._chips(case, state, masker)  # 칩 id는 상태로 정해진다 (행동할 때 다시 만들어도 같다)
        picks = [(cid, d["text"]) for cid, d in state.director_state["chips"].items()
                 if d["kind"] == "ask" and d["npc"] == npc_id][: self.cfg.speed.speculative_chip_count]
        jobs = {cid: (lambda q=q: self._speculate(case, state, npc_id, q)) for cid, q in picks}
        return {"prepared": self.spec.start(game_id, state_key(state), npc_id, jobs)}

    async def _speculate(self, case: CaseBible, base: GameState, npc_id: str, text: str) -> PreparedAnswer:
        st = base.model_copy(deep=True)  # 복사본에만 행동을 써서 그 시각의 사건 정보로 답하게 한다
        if st.phase == "briefing":
            st.phase = "day"
        self._spend(st, "ask")
        # 실시간 경로로 만든다: 화면에는 안 내보내지만, 버릴 때(다른 행동) 취소하면 모델 생성도 바로 멈춘다
        return await prepare_answer(case, st, npc_id, text, self._turn_deps(case, st, llm=TaggedLLM(self.llm)))

    async def _take_prepared(self, game_id: str, key: tuple, state: GameState, action: dict) -> PreparedAnswer | None:
        """누른 칩의 미리 만든 답. 아직 만드는 중이면 끝날 때까지 기다린다. 기다린 시간을 호출 기록에 남긴다."""
        t0 = time.perf_counter()
        prepared = await self.spec.take(game_id, key, action.get("chip_id") or "")
        if prepared is not None:
            self.llm.tracer.record(CallRecord(
                ts=time.time(), role=prepared.role, bucket="npc", model="prepared", latency_s=time.perf_counter() - t0,
                game_id=state.game_id, node="npc_prepared"))
        return prepared

    def _record_speculation(self, state: GameState) -> None:
        """끝난 준비분의 (미리 만든 수, 쓴 수)를 이 판의 적중률 기록에 옮긴다. 낮으면 그 판에서 끈다(F.15)."""
        shows = self.spec.drain(state.game_id)
        if not shows:
            return
        stats = spec_rules.SpeculativeStats.model_validate(state.director_state.get("speculative") or {})
        for prepared, used in shows:
            stats = spec_rules.record_show(self.cfg, stats, prepared, used)
            self.llm.tracer.record(CallRecord(
                ts=time.time(), role="speculative", bucket="npc", model="code", latency_s=0.0, game_id=state.game_id,
                node="speculative", extra={"prepared": prepared, "used": used, "disabled": stats.disabled}))
        state.director_state["speculative"] = stats.model_dump(mode="json")

    # ----------------------------------------------------------------- 이동·조사
    async def _do_move(self, case, state, action, events, eb) -> None:
        loc = action.get("location_id")
        if loc not in state.unlocked_locations:
            raise _BadAction("아직 갈 수 없는 장소예요.")
        ds = state.director_state
        ds["same_place"] = 0 if loc != state.player_location else ds.get("same_place", 0) + 1
        state.player_location = loc
        if loc not in state.visited_locations:
            state.visited_locations.append(loc)
        name = next(l.name for l in case.locations if l.id == loc)
        here = [C.char(case, n).name for n, ns in state.npc_states.items() if ns.visible and ns.location_id == loc]
        self._say(events, eb, "narrator", None,
                  f"{josa(name, '으로/로')} 왔다." + (f" {josa(', '.join(here), '이/가')} 있다." if here else ""))
        # 범인의 경계: 형사가 하루에 자기 위치를 여러 번 찾아오면 경계가 오른다 (부록 F.10)
        from server.rules import alertness as alert_rules
        for n, ns in state.npc_states.items():
            if ns.location_id == loc:
                ns.visits_today += 1
                if bluff_rules.is_guilty(case, n) and alert_rules.repeat_visit_triggered(self.cfg, ns.visits_today):
                    ns.alertness = alert_rules.apply_event(self.cfg, ns.alertness, "repeat_visit")

    def _do_investigate(self, case, state, masker, events, eb) -> None:
        inv = self.cfg.investigation
        state.director_state["same_place"] = state.director_state.get("same_place", 0) + 1
        found = C.next_reveals(case, state, state.player_location, inv["reveal_per_action"], inv["key_evidence_last"])
        new = self._obtain(case, state, found)
        if not new:
            self._say(events, eb, "narrator", None, "더 찾을 만한 건 없어 보인다.")
            return
        for e in new:
            ev = C.evidence(case, e)
            self._say(events, eb, "narrator", None, f"{josa(chr(39) + ev.name + chr(39), '을/를')} 찾았다. {ev.content}")
        events.append(eb.custom("notebook", {"added": {"evidence_ids": [masker.out("evidence", e) for e in new]}}))

    # ----------------------------------------------------------------- 대화
    def _turn_deps(self, case: CaseBible, state: GameState, llm=None, stream: bool = True) -> TurnDeps:
        """stream: 인물 답을 첫 문장부터 내보낼지(설정 speed.stream_npc_answers, 미리 만들기는 False)."""
        cfg, hold, llm = self.cfg, {}, llm or self.llm

        def retrieve(game: GameState, npc_id: str, q: str) -> list[RetrievalHit]:
            hits = self._npc_search(case, game, npc_id, q)
            hold["hits"] = hits
            return hits

        def gm_code_check(case_: CaseBible, game: GameState, npc_id: str, reply: NPCReply) -> GMVerdict:
            v = gm_rules.check_reply(cfg, case_, npc_id, reply.text)
            grounded = " ".join(h.content for h in hold.get("hits", []) if h.id in reply.used_ids or not reply.used_ids)
            return ground_verdict(cfg, case_, v, reply.text, grounded)

        async def gm_llm_check(case_, game, npc_id, reply, verdict) -> bool:
            return await self._gm_llm_judge(case_, npc_id, reply, verdict, hold.get("hits", []), game.game_id, llm)

        def handle_offtopic(game: GameState, npc_id: str, route: RouterOutput) -> dict:
            outcome = off_rules.register_offtopic(cfg, game.offtopic_streak)
            game.offtopic_streak = outcome.streak
            evs: list[dict] = []
            if route.kind == "inappropriate":
                _absorb(game, rep_rules.apply_event(cfg, game, "rude"))
                game.npc_states[npc_id] = trust_rules.apply_event(cfg, game.npc_states[npc_id], "rude")
            elif route.kind == "meta":
                _absorb(game, rep_rules.apply_event(cfg, game, "meta"))
            if outcome.reputation_event:
                _absorb(game, rep_rules.apply_event(cfg, game, outcome.reputation_event))
            if outcome.turn_away:
                game.npc_states[npc_id] = trust_rules.turn_away(cfg, game.npc_states[npc_id], game.action_no)
                evs.append(EventBuilder().custom("turn_away", {"npcId": npc_id, "untilActions": cfg.trust.turnaway_actions}))
            if outcome.rumor_candidate:
                game.director_state["rumor_candidates"] = game.director_state.get("rumor_candidates", 0) + 1
            if outcome.partner_interject:
                evs.extend(EventBuilder().text("partner", "partner", "선배, 시간 없어요. 사건 얘기부터 하죠."))
            ch = C.char(case, npc_id)
            kind = "turn_away" if outcome.turn_away else route.kind
            line = off_rules.line(cfg, kind, ch, outcome.streak + game.action_no)  # 성격별, 같은 말 연달아 안 나오게
            return {"line": line, "events": evs, "chips_again": outcome.show_chips}

        def on_small_talk(game: GameState, ch) -> None:
            game.npc_states[ch.id] = trust_rules.apply_small_talk(cfg, game.npc_states[ch.id], ch.small_talk_style)
            game.offtopic_streak = off_rules.register_normal(cfg, game.offtopic_streak)

        def after_answer(game: GameState, npc_id: str, q: str, reply: NPCReply, hits: list[RetrievalHit]) -> dict:
            game.offtopic_streak = off_rules.register_normal(cfg, game.offtopic_streak)
            talked = game.director_state.setdefault("talked", [])
            if npc_id not in talked:
                talked.append(npc_id)
            asked = game.director_state.setdefault("asked", {})
            asked[npc_id] = asked.get(npc_id, 0) + 1
            game.director_state.setdefault("asked_texts", {}).setdefault(npc_id, []).append(q)
            self.rag.add_memory(MemoryDoc(
                id=f"said_{uuid.uuid4().hex[:10]}", case_id=case.case_id, slot_id=game.slot_id, owner=npc_id,
                visibility=[f"npc:{npc_id}"], doc_type="said", content=f"형사에게 이렇게 말했다: {reply.text}",
                game_time=game.clock, source="direct", tags=["형사", "진술"],
            ))
            # 증언 증거: NPC가 그 증언 기억을 근거로 말했을 때만 얻는다
            memo = {m.id: m for m, _ in self.rag.load_memories(case.case_id, game.slot_id)}
            got = []
            for hid in reply.used_ids:
                m = memo.get(hid)
                if m and m.evidence_id:
                    ev = C.evidence(case, m.evidence_id)
                    if ev.kind == "testimony" and "player" in ev.visibility:
                        got.append(ev.id)
            new = self._obtain(case, game, got)
            masker = IdMasker(case, game.id_salt)
            return {"evidence_ids": [masker.out("evidence", e) for e in new], "contradictions": []}

        return TurnDeps(
            llm=llm, router=self.router, retrieve=retrieve, gm_code_check=gm_code_check,
            fallback_line=lambda ch: gm_rules.fallback_line(cfg, ch), handle_offtopic=handle_offtopic,
            on_small_talk=on_small_talk, after_answer=after_answer,
            lie_guidance=lambda case_, npc_id, q: C.relevant_lies(case_, npc_id, q),
            hidden=lambda case_, npc_id: C.hidden_topics(case_, npc_id),
            case_brief=lambda case_, game: self._brief(case_, game), gm_llm_check=gm_llm_check,
            scene=lambda case_, game: self._scene(case_, game),
            stream=stream and cfg.speed.stream_npc_answers and bool(getattr(llm, "can_stream", False)),
            reply_sentences=(cfg.npc_reply_sentences[0], cfg.npc_reply_sentences[1]),
        )

    def _npc_search(self, case: CaseBible, game: GameState, npc_id: str, q: str) -> list[RetrievalHit]:
        """NPC는 자기 기억을 먼저 본다. 공용 문서(메신저 로그·매뉴얼 등)는 기억이 모자랄 때만 보탠다.
        공용 문서가 위로 올라오면 NPC가 남의 대사를 자기 말처럼 하게 된다."""
        k = self.cfg.rag.get("top_k", 5)
        hits = self.retriever.search(q, case_id=case.case_id, slot_id=game.slot_id, scope=f"npc:{npc_id}",
                                     k=k, kinds=("memory",))
        if len(hits) < 3:
            hits += self.retriever.search(q, case_id=case.case_id, slot_id=game.slot_id, scope=f"npc:{npc_id}",
                                          k=3 - len(hits), kinds=("chunk",))
        return hits

    def _player_search(self, case: CaseBible, game: GameState, q: str, k: int = 5) -> list[RetrievalHit]:
        """플레이어 시점 검색(파트너 문서 검색 등). 증거 청크는 수첩에 있는 것만 허용한다.
        청크의 영장 검사는 시스템 단위라, 다른 사람 영장으로 남의 기록 청크가 보이는 것을 여기서 막는다."""
        hits = self.retriever.search(q, case_id=case.case_id, slot_id=game.slot_id, scope="player",
                                     warrants=game.warrants, k=k * 3, kinds=("chunk",))
        owned = set(game.notebook.evidence_ids)
        out = []
        for h in hits:
            ev = (h.meta.get("kb_meta") or {}).get("evidence_id") or h.meta.get("evidence_id")
            if h.id.startswith("ev:") or ev:
                if (ev or h.id.removeprefix("ev:").split("#")[0]) not in owned:
                    continue
            out.append(h)
        return out[:k]

    def _brief(self, case: CaseBible, game: GameState) -> str:
        """한 판 동안 그대로인 사건 공통 정보 (인물 지시문 쪽, 캐시됨)."""
        return f"사건: {case.incident.summary}"

    def _scene(self, case: CaseBible, game: GameState) -> str:
        """지금 날짜·시각·장소. 행동마다 바뀌므로 사용자 글 쪽에 넣는다(PRD §12.8)."""
        loc = next((l.name for l in case.locations if l.id == game.player_location), "")
        return f"수사 {game.day}일차 {C.hhmm(game.clock)}, 장소: {loc}"

    def _require_npc_here(self, state: GameState, npc_id: str | None) -> str:
        ns = state.npc_states.get(npc_id or "")
        if not ns or not ns.visible:
            raise _BadAction("그런 사람은 없어요.")
        if ns.location_id != state.player_location:
            raise _BadAction("그 사람은 여기 없어요.")
        return npc_id  # type: ignore[return-value]

    async def _do_ask(self, case, state, masker, action, events, eb, prepared: PreparedAnswer | None = None) -> None:
        chip_route = None
        if action.get("type") == "chip":
            d = state.director_state.get("chips", {}).get(action.get("chip_id"))
            if not d:
                raise _BadAction("지난 추천 질문이에요.")
            if d["kind"] == "present":
                await self._do_present(case, state, masker, {"npc_id": d["npc"], "evidence_id": masker.out("evidence", d["evidence"])}, events, eb)
                return
            npc_id, text = d["npc"], d["text"]
            chip_route = RouterOutput(kind="investigate", target_npc=npc_id, via="chip")
        else:
            npc_id, text = action.get("npc_id"), (action.get("text") or "").strip()[:300]
        npc_id = self._require_npc_here(state, npc_id)
        game, evs, _ = await run_turn(case, state, npc_id, text, self._turn_deps(case, state), chip_route=chip_route,
                                      prepared=prepared, events=events)
        _absorb(state, game)
        if evs is not events:  # 그래프가 같은 목록을 썼으면 이미 붙어 있다
            events.extend(evs)

    async def _npc_react(self, case, state, npc_id, prompt_text, events, eb, *, forced_emotion=None, forced_reaction=None,
                         presented: str | None = None, revealed_lies: frozenset[str] = frozenset()) -> NPCReply:
        """revealed_lies: 이번에 깨진 거짓말(반박 증거 제시) 또는 블러핑이 먹힌 경우 전부 → 그 진실은 말해도 된다."""
        """증거 제시·블러핑에 대한 NPC 반응 (핫 패스 LLM 1회)."""
        from server.agents import npc as npc_agent

        hits = self._npc_search(case, state, npc_id, prompt_text)
        ch = C.char(case, npc_id)
        ctx = npc_agent.NPCContext(
            character=ch, state=state.npc_states[npc_id], question=prompt_text, hits=hits,
            case_brief=self._brief(case, state), lie_guidance=C.relevant_lies(case, npc_id, prompt_text),
            scene=self._scene(case, state),
            conversation_summary=state.conversation_summary, forced_emotion=forced_emotion, forced_reaction=forced_reaction,
            sentences=(self.cfg.npc_reply_sentences[0], self.cfg.npc_reply_sentences[1]),
            hidden=C.hidden_topics(case, npc_id, revealed_lies),
        )
        mid = None

        def on_text(piece: str) -> None:  # 첫 문장부터 내보낼 때
            nonlocal mid
            if mid is None:
                mid, start = eb.text_start("npc", npc_id)
                events.append(start)
            events.append(eb.text_delta(mid, piece))

        async def hidden_check(r: NPCReply, v: GMVerdict) -> bool:
            # 반응은 원래 LLM 1회: 숨길 진실 신호만 LLM 검사로 확인한다(이미 깨진 거짓말은 신호에서 빠져 있음)
            if "hidden_truth" not in v.triggers:
                return True
            return await self._gm_llm_judge(case, npc_id, r, v, hits, state.game_id)

        hooks = npc_agent.StreamHooks(
            on_emotion=lambda e: events.append(eb.custom("emotion", {"npcId": npc_id, "emotion": forced_emotion or e})),
            on_text=on_text, llm_check=hidden_check)
        llm = self.llm if self.cfg.speed.stream_npc_answers else _NoStream(self.llm)
        reply, verdict, fb, streamed = await npc_agent.answer_stream(
            llm, ctx, role="npc_minor" if ch.tier == "minor" else "npc",
            gm_code_check=lambda r: ground_verdict(self.cfg, case, gm_rules.check_reply(
                self.cfg, case, npc_id, r.text, revealed_lies=revealed_lies), r.text, " ".join(h.content for h in hits), presented),
            fallback_line=lambda: gm_rules.fallback_line(self.cfg, ch), hooks=hooks, game_id=state.game_id,
        )
        if not streamed and not fb and not await hidden_check(reply, verdict):  # 한 번에 만든 답도 같은 검사
            reply = NPCReply(text=gm_rules.fallback_line(self.cfg, ch), emotion=reply.emotion, used_ids=[])
        if forced_emotion:
            reply.emotion = forced_emotion
        state.npc_states[npc_id].emotion = reply.emotion
        events.append(eb.custom("emotion", {"npcId": npc_id, "emotion": reply.emotion}))
        if streamed:
            events.append(eb.text_end(mid))  # type: ignore[arg-type]
        else:
            self._say(events, eb, "npc", npc_id, reply.text)
        stmt = NotebookStatement(id=f"t_{uuid.uuid4().hex[:8]}", npc_id=npc_id, content=reply.text,
                                 game_time=state.clock, source_ids=list(reply.used_ids))
        state.notebook.statements.append(stmt)
        state.question_count += 1
        return reply

    async def _do_present(self, case, state, masker, action, events, eb) -> None:
        npc_id = self._require_npc_here(state, action.get("npc_id"))
        eid = masker.inn(action.get("evidence_id", ""))
        if not eid or eid not in state.notebook.evidence_ids:
            raise _BadAction("가지고 있지 않은 증거예요.")
        ev = C.evidence(case, eid)
        lies = [l for l in case.lie_ledger if l.liar_id == npc_id and eid in l.rebuttal_evidence_ids]
        if lies:
            events.append(eb.custom("cutin", {"text": "이의 있음!", "style": "objection"}))
            reply = await self._npc_react(case, state, npc_id, f"형사가 {josa(chr(39) + ev.name + chr(39), '을/를')} 내밀었다: {ev.content}", events, eb,
                                          forced_emotion="flustered",
                                          forced_reaction="증거 앞에서 당황한다. 앞서 한 말과 어긋난다는 걸 들킨 반응을 보인다.",
                                          presented=ev.name, revealed_lies=frozenset(l.id for l in lies))
            stmt_id = state.notebook.statements[-1].id
            new_c = []
            for lie in lies:
                if any(c.lie_id == lie.id for c in state.notebook.contradictions):
                    continue
                c = Contradiction(id=f"c_{uuid.uuid4().hex[:8]}", statement_id=stmt_id, evidence_id=eid, lie_id=lie.id,
                                  note=f"{C.char(case, npc_id).name}: '{lie.topic}' 진술이 증거와 어긋남")
                state.notebook.contradictions.append(c)
                new_c.append(c.id)
            if new_c:
                state.npc_states[npc_id] = trust_rules.apply_event(self.cfg, state.npc_states[npc_id], "lie_exposed")
                state.director_state["actions_since_clue"] = 0
                # 계약: 모순은 객체로 보낸다. 화면용 모양(가린 ID, 거짓말 ID 빈 값)은 build_view와 같게
                public = [c.model_dump() for c in self._view(case, state, masker).notebook.contradictions if c.id in new_c]
                events.append(eb.custom("notebook", {"added": {"contradictions": public}}))
        else:
            await self._npc_react(case, state, npc_id, f"형사가 {josa(chr(39) + ev.name + chr(39), '을/를')} 보여 주며 묻는다: {ev.content}", events, eb,
                                  presented=ev.name)

    async def _do_bluff(self, case, state, masker, action, events, eb) -> None:
        npc_id = self._require_npc_here(state, action.get("npc_id"))
        claim_id = masker.inn(action.get("claim_id", ""))
        if not claim_id:
            raise _BadAction("모르는 주장이에요.")
        basis = [e for e in (masker.inn(x) for x in action.get("basis_evidence_ids", [])) if e]
        ba = BluffAction(target_npc=npc_id, claim_id=claim_id, claim_subject=action.get("claim_subject") or None,
                         basis_evidence_ids=basis)
        claim = next(c for c in case.bluff_claims if c.id == claim_id)
        knows_false = self.relations.knows_false(npc_id, claim, case_id=case.case_id, slot_id=state.slot_id)
        result = bluff_rules.resolve_bluff(self.cfg, case, state, ba, npc_knows_false=knows_false)
        _absorb(state, bluff_rules.apply_failure(self.cfg, case, state, ba, result))
        state.events_log.append({"type": "bluff", "npc": npc_id, "claim": claim_id, "outcome": result.outcome})
        reaction = {
            "confession": ("sad", "버티지 못하고 무너진다. 자신이 한 일을 인정한다."),
            "shaken": ("nervous", "흔들린다. 무심코 단서 하나를 흘린다."),
            "rebutted": ("angry", "블러핑이 통하지 않는다. 근거가 없다며 반박한다."),
            "instant_fail": ("angry", "거짓말인 걸 바로 알아챈다. 형사를 비웃는다."),
        }[result.outcome]
        broken = frozenset(l.id for l in case.lie_ledger if l.liar_id == npc_id) \
            if result.outcome in ("shaken", "confession") else frozenset()  # 블러핑이 먹히면 흘리거나 자백한다
        await self._npc_react(case, state, npc_id, f"형사가 블러핑한다: '{claim.label}'", events, eb,
                              forced_emotion=reaction[0], forced_reaction=reaction[1], revealed_lies=broken)
        if result.outcome == "shaken" and result.leaked_hint_id:
            new = self._obtain(case, state, [result.leaked_hint_id])
            if new:
                events.append(eb.custom("notebook", {"added": {"evidence_ids": [masker.out("evidence", e) for e in new]}}))
        if result.outcome == "confession":
            state.director_state["confession"] = npc_id
            events.append(eb.custom("cutin", {"text": "자백!", "style": "confession"}))

    def _do_warrant(self, case, state, masker, action, events, eb) -> None:
        system, target = action.get("system"), action.get("target_id")
        if target not in state.npc_states:
            raise _BadAction("영장 대상이 없어요.")
        basis = [e for e in (masker.inn(x) for x in action.get("basis_evidence_ids", [])) if e]
        decision = war_rules.request_warrant(self.cfg, case, state, system, target, basis)
        name = C.char(case, target).name
        if not decision.needed:
            self._say(events, eb, "chief", "chief", "그건 영장 없이도 볼 수 있는 기록이야.")
            return
        if not decision.approved or decision.warrant is None:
            self._say(events, eb, "chief", "chief", f"근거가 부족해. {name}에 대한 영장은 아직 못 내줘.")
            return
        state.warrants.append(decision.warrant)
        self._say(events, eb, "chief", "chief", f"좋아, {name}에 대한 영장이 나왔다.")
        got = [e.id for e in case.evidence if f"warrant:{system}" in e.visibility and target in e.linked_suspects]
        new = self._obtain(case, state, got)
        for e in new:
            ev = C.evidence(case, e)
            self._say(events, eb, "narrator", None, f"{josa(chr(39) + ev.name + chr(39), '을/를')} 받았다. {ev.content}")
        if new:
            events.append(eb.custom("notebook", {"added": {"evidence_ids": [masker.out("evidence", e) for e in new]}}))

    def _do_apologize(self, case, state, action, events, eb) -> None:
        npc_id = self._require_npc_here(state, action.get("npc_id"))
        before = state.reputation
        _absorb(state, rep_rules.apply_event(self.cfg, state, "apology", npc_id=npc_id))
        if state.reputation != before:
            state.npc_states[npc_id] = trust_rules.apply_event(self.cfg, state.npc_states[npc_id], "apology")
            self._say(events, eb, "npc", npc_id, "…알겠어요. 이번엔 넘어갈게요.")
        else:
            self._say(events, eb, "npc", npc_id, "오늘은 이미 사과받았어요.")

    # ----------------------------------------------------------------- 연출 감독
    def _director(self, case, state, events, eb) -> None:
        ds = state.director_state
        suff = state.notebook.sufficiency or suff_rules.all_sufficiency(self.cfg, case, state.notebook)
        m = dir_rules.DirectorMetrics(
            actions_since_clue=ds.get("actions_since_clue", 0), consecutive_same_place=ds.get("same_place", 0),
            day=state.day, is_last_day=state.day >= state.max_days, max_sufficiency=max(suff.values(), default=0.0),
            actions_since_last_event=ds.get("actions_since_event", 10**6), events_today=ds.get("events_today", 0),
            hint_given_in_streak=ds.get("hint_in_streak", False), event_given_in_streak=ds.get("event_in_streak", False),
            fired=ds.get("fired", []),
        )
        iv = dir_rules.decide(self.cfg, m)
        if iv is None:
            if ds.get("actions_since_clue", 0) == 0:
                ds["hint_in_streak"] = ds["event_in_streak"] = False
            return
        ds["actions_since_event"] = 0
        ds["events_today"] = ds.get("events_today", 0) + 1
        if iv == "partner_hint":
            ds["hint_in_streak"] = True
            self._say(events, eb, "partner", "partner", C.hint_text(case, state))
            return
        if iv in ("early_progress", "escalate_crisis", "late_struggle", "report_nudge"):
            ds.setdefault("fired", []).append({"escalate_crisis": "early_progress", "report_nudge": "late_struggle"}.get(iv, iv))
        texts = {
            "event": ("제보", "누군가 할 말이 있다며 형사를 찾는다고 한다."),
            "call_elsewhere": ("호출", "다른 곳에서 형사님을 찾는 연락이 왔어요. 자리를 옮겨 보죠."),
            "escalate_crisis": ("협박 문자", "모르는 번호: 더 이상 파고들지 마."),
            "report_nudge": ("반장", "반장: 마지막 날이야. 지금까지 정리해서 보고해. " + C.hint_text(case, state)),
        }
        if iv == "event":
            ds["event_in_streak"] = True
        title, text = texts.get(iv, ("알림", ""))
        events.append(eb.custom("director", {"eventId": f"d_{uuid.uuid4().hex[:6]}", "title": title, "text": text}))

    # ================================================================= 밤
    async def night(self, game_id: str) -> AsyncIterator[dict]:
        case, state, masker = self._load(game_id)
        eb = EventBuilder()
        yield eb.run_started()
        if state.phase not in ("day", "briefing"):
            yield eb.run_error("지금은 하루를 끝낼 수 없어요.", code="phase")
            yield eb.run_finished()
            return
        state.phase = "night"
        self.spec.close(game_id)
        self._record_speculation(state)
        deps = build_night_deps(self, case)
        game, events = await run_night(case, state, deps)
        _absorb(state, game)
        for ev in events:
            yield ev
        yield eb.snapshot(self._view(case, state, masker))
        if state.ending != "none":
            yield eb.custom("ending", {"ending": state.ending, "replay": self._replay(case, state)})
        self.store.save_live(state)
        yield eb.run_finished()

    # ================================================================= 최종 추리
    async def finale(self, game_id: str, step: dict) -> AsyncIterator[dict]:
        case, state, masker = self._load(game_id)
        eb = EventBuilder()
        yield eb.run_started()
        events: list[dict] = []
        t = step.get("type")
        last = None

        def emote(npc_id: str | None, emotion: str) -> None:  # 최종 추리 장면의 표정(목 백엔드와 같은 흐름)
            if npc_id and npc_id in state.npc_states:
                state.npc_states[npc_id].emotion = emotion  # type: ignore[assignment]
                events.append(eb.custom("emotion", {"npcId": npc_id, "emotion": emotion}))

        try:
            if t == "start":
                accused = step.get("accused_id")
                if accused not in state.npc_states:
                    raise _BadAction("지목할 사람이 없어요.")
                if state.finale and state.phase == "finale":
                    st = fin_rules.FinaleState.model_validate(state.finale)  # 지목을 무른 뒤 다시 지목
                else:
                    st = fin_rules.start_finale(self.cfg, state.difficulty)
                    self._say(events, eb, "narrator", None, "모두를 회의실로 불러 모았다. 이제 증거로 말할 시간이다.")
                st = fin_rules.accuse(self.cfg, case, st, accused)
                state.phase = "finale"
                if st.pending_confirmation:
                    emote(accused, "angry")
                    self._say(events, eb, "npc", accused, "제가요? 증거라도 있어요? 다시 생각해 보시죠.")
                else:
                    emote(accused, "nervous")
                    self._say(events, eb, "npc", accused, "제, 제가요? 증거라도 있으세요?")
            else:
                if not state.finale:
                    raise _BadAction("최종 추리를 먼저 시작하세요.")
                st = fin_rules.FinaleState.model_validate(state.finale)
                if t == "present":
                    eid = masker.inn(step.get("evidence_id", ""))
                    if not eid:
                        raise _BadAction("가지고 있지 않은 증거예요.")
                    res = fin_rules.present_evidence(self.cfg, case, st, step.get("stage", ""), eid,
                                                     owned_evidence_ids=set(state.notebook.evidence_ids))
                    st = res.state
                    who = C.char(case, st.accused_id).name if st.accused_id else ""
                    if res.correct:
                        events.append(eb.custom("cutin", {"text": "이의 있음!", "style": "objection"}))
                        emote(st.accused_id, "flustered")
                        self._say(events, eb, "npc", st.accused_id, "그, 그건…!")
                    else:
                        emote(st.accused_id, "angry")
                        self._say(events, eb, "npc", st.accused_id, f"그게 저랑 무슨 상관이죠? ({who})")
                    last = {"result": "correct" if res.correct else ("rebutted" if res.rebuttal else "wrong"),
                            "evidence_id": step.get("evidence_id")}
                elif t == "confirm":
                    st = fin_rules.confirm_accusation(st)
                elif t == "retract":
                    st = fin_rules.retract_accusation(st)  # 다시 지목할 수 있다 (최종 추리 단계는 유지)
            state.finale = st.model_dump()
            state.finale_wrong = st.wrong
            ending = fin_rules.ending_of(st)
            if ending == "none":  # 진행 중: 화면이 그릴 상태(다음에 밝힐 단계, 반박 대기 여부)
                events.append(eb.custom("finale", self._finale_value(st, last if t == "present" else None)))
            if ending in ("success", "escaped", "wrong_accusation"):
                state.ending = ending  # type: ignore[assignment]
                state.phase = "ended"
                line = {"success": "결국 모든 게 드러났다.", "escaped": "증거가 모자랐다. 범인은 끝내 버텼다.",
                        "wrong_accusation": "엉뚱한 사람을 지목하고 말았다…"}[ending]
                emote(st.accused_id, {"success": "sad", "escaped": "happy", "wrong_accusation": "angry"}[ending])
                self._say(events, eb, "narrator", None, line)
                events.append(eb.custom("ending", {"ending": ending, "replay": self._replay(case, state)}))
        except (_BadAction, ValueError) as e:
            events.append(eb.run_error(str(e), code="bad_step"))
        self.store.save_live(state)
        for ev in events:
            yield ev
        yield eb.snapshot(self._view(case, state, masker))
        yield eb.run_finished()

    def _finale_value(self, st, last: dict | None = None) -> dict:
        """최종 추리 진행 상태(docs/api-contract.md `finale`). stage = 다음에 밝힐 단계(설정 순서), 다 밝혔으면 "done".
        pending = 무고한 사람을 지목해 반박을 들은 상태(그래도 지목 confirm / 다시 고르기 retract). 지목을 무르면 accused_id가 없다."""
        nxt = next((s for s in self.cfg.finale.stages if s not in st.passed), "done")
        return {"accused_id": st.accused_id, "stage": nxt if st.accused_id else None, "lives": st.lives,
                "filled": list(st.passed), "last": last, "pending": bool(st.pending_confirmation)}

    def _replay(self, case: CaseBible, state: GameState) -> dict:
        """진실 리플레이: 사건 당일 타임라인 + 수사 기간 밤 행동. 엔딩 후에만 공개."""
        name = {c.id: c.name for c in case.characters}
        loc = {l.id: l.name for l in case.locations}
        timeline = [{"time": C.hhmm(t.time), "who": name.get(t.character_id, t.character_id),
                     "where": loc.get(t.location_id, t.location_id), "what": t.action} for t in case.timeline]
        nights = [e for e in state.events_log if e.get("type") == "night"]
        return {"culprit": [name[c] for c in case.culprit_ids], "trick": case.trick, "timeline": timeline,
                "nights": nights}

    # ================================================================= 저장
    def save(self, game_id: str, slot_name: str | None) -> dict:
        case, state, _ = self._load(game_id)
        if state.phase in ("night", "finale"):
            raise StorageError("지금은 저장할 수 없어요 (밤이나 최종 추리 중).")
        slot = self.store.snapshot(state, name=slot_name or f"{state.day}일차 {C.hhmm(state.clock)}")
        self.rag.copy_slot(state.slot_id, slot)
        return {"slot_id": slot, "saved_at": datetime.now().isoformat()}

    def list_saves(self, game_id: str) -> list[dict]:
        self.store.live_slot_id(game_id)
        return self.store.list_slots(game_id)

    def load(self, game_id: str, slot_id: str) -> PlayerView:
        if slot_id not in [s["slot_id"] for s in self.store.list_slots(game_id)]:
            raise StorageError("이 게임의 저장 슬롯이 아니에요.")
        old_live = self.store.live_slot_id(game_id)
        new_live = f"slot_{uuid.uuid4().hex[:12]}"
        self.rag.copy_slot(slot_id, new_live)
        state = self.store.activate_slot(game_id, slot_id, new_live)
        self.rag.delete_slot(old_live)
        self.spec.forget(game_id)  # 불러온 슬롯은 다른 상태다
        return self._persist_view(self.cases[state.case_id], state)

    def sources(self, game_id: str, statement_id: str) -> list[dict]:
        """진술 출처. NPC 기억 원문은 절대 내보내지 않는다(범인이 숨긴 진짜 기억이 샐 수 있음).
        누가 언제 한 말인지 + 그 기억과 연결된 증거 중 플레이어가 이미 가진 것만."""
        case, state, masker = self._load(game_id)
        stmt = next((s for s in state.notebook.statements if s.id == statement_id), None)
        if stmt is None:
            raise StorageError("진술이 없어요.")
        out = [{"kind": "statement", "title": f"{C.char(case, stmt.npc_id).name}의 진술 ({state.day}일차 {C.hhmm(stmt.game_time)})",
                "content": stmt.content}]
        memo = {m.id: m for m, _ in self.rag.load_memories(case.case_id, state.slot_id)}
        for sid in stmt.source_ids:
            m = memo.get(sid)
            if m and m.evidence_id and m.evidence_id in state.notebook.evidence_ids:
                ev = C.evidence(case, m.evidence_id)
                out.append({"kind": "evidence", "title": ev.name, "content": ev.content})
        return out

    # ================================================================= 클리어
    def clear(self, game_id: str) -> dict:
        case, state, _ = self._load(game_id)
        if state.ending == "none":
            raise StorageError("아직 끝나지 않은 사건이에요.")
        success = state.ending == "success"
        score, grade = grade_rules.grade_game(self.cfg, state, state.difficulty,
                                              confession_bonus=bool(state.director_state.get("confession")))
        title = rep_rules.title_for(self.cfg, state.reputation)
        culprit = C.char(case, case.culprit_ids[0])
        bluffs = [e for e in state.events_log if e.get("type") == "bluff" and e.get("outcome") == "confession"]
        if bluffs:
            highlight = f"블러핑으로 {C.char(case, bluffs[-1]['npc']).name}의 자백을 받아냈다"
        elif success:
            n_ev, n_con = len(state.notebook.evidence_ids), len(state.notebook.contradictions)
            highlight = (f"증거 {n_ev}개와 모순 {n_con}개로 진실을 밝혀냈다" if n_con
                         else f"증거 {n_ev}개로 진실을 밝혀냈다")
        else:
            highlight = "끝내 진실에 닿지 못했다"
        hid = f"h_{uuid.uuid4().hex[:10]}"
        shown = [c for c in case.characters if state.npc_states.get(c.id) and state.npc_states[c.id].visible]
        # 판 사진은 아래에서 지우므로, 결과 카드에 쓸 작은 사본을 먼저 남긴다
        photos = self.portraits.keep_for_history(self._portrait_key(state), self._public_people(shown), self.history_photos / hid)
        history = ClearHistory(
            id=hid, player_id="player", case_title=case.title, theme=case.theme,
            cleared_at=datetime.now(), success=success,
            real_minutes=max(1, int((datetime.now() - state.started_at).total_seconds() // 60)),
            game_days=state.day, question_count=state.question_count, grade=grade if success else None,
            titles=[title] if title else [], reputation=state.reputation,
            culprit={"name": culprit.name, "role": culprit.role},
            characters=[{"name": c.name, "role": c.role, "face_seed": c.face_seed, "appearance": c.appearance,
                         "portrait_url": f"/api/history/{hid}/photos/{photos[c.id]}" if c.id in photos else None}
                        for c in shown],
            highlight=highlight, fingerprint=case.fingerprint,
        )
        self.store.add_history(history)
        emoji = "🔍" * max(1, state.day) + ("✅" if success else "❌")
        card = ShareCard(
            emoji_line=emoji,
            share_text=f"The Suspects · {case.title} · {state.question_count}질문 {emoji}" + (f" · {grade}" if success else ""),
            theme_color="#3B5BA5",
        ) if success else None
        # 삭제: 배경·NPC 기억·대화·사건 상태. 남는 것은 클리어 이력뿐 (PRD §10.2)
        for slot in self.store.delete_game(game_id):
            self.rag.delete_slot(slot)
        self.portraits.delete(self._portrait_key(state))
        self._forget_generated(case)
        return {"history": history.model_dump(mode="json"), "card": card.model_dump() if card else None}

    def history_photo(self, hid: str, filename: str) -> Path | None:
        """클리어 기록 사진 파일(경로 조작 방지: h_<영숫자>/<숫자>.webp 만)."""
        import re

        if not re.fullmatch(r"h_[0-9a-f]{10}", hid) or not re.fullmatch(r"\d{1,3}\.webp", filename):
            return None
        p = self.history_photos / hid / filename
        return p if p.is_file() else None

    def history(self) -> list[ClearHistory]:
        return self.store.list_history()


class _BadAction(Exception):
    pass


def _minute_dist(a: int, b: int) -> int:
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def ground_verdict(cfg, case: CaseBible, v: GMVerdict, text: str, grounded_text: str,
                   presented: str | None = None) -> GMVerdict:
    """근거 있는 발언 면제 (PRD 부록 F.11 v1.7): 이번에 받은 검색 결과나 제시된 증거에 이미 있는 이름·시각·장소는
    LLM 검사 대상에서 뺀다. 시각은 ±15분이면 같은 시각으로 본다."""
    if not v.triggers:
        return v
    keep = []
    gt = grounded_text + " " + (presented or "")
    for t in v.triggers:
        if t == "incident_time":
            window = cfg.gm.time_window_hours * 60
            inc = case.incident.time % 1440
            near = [cands for cands in gm_rules.extract_time_candidates(text)
                    if any(_minute_dist(c, inc) <= window for c in cands)]
            src = [s for cands in gm_rules.extract_time_candidates(gt) for s in cands]
            if near and all(any(_minute_dist(c, s) <= 15 for c in cands for s in src) for cands in near):
                continue
        elif t == "incident_location":
            loc = next((l.name for l in case.locations if l.id == case.incident.location_id), "")
            if loc and loc in gt:
                continue
        elif t == "key_evidence":
            names = [e.name for e in case.evidence if e.is_key and e.name in text]
            if names and all(n in gt for n in names):
                continue
        elif t == "culprit_name":
            names = [c.name for c in case.characters if c.id in case.culprit_ids]
            if all(n in gt or n[1:] in gt for n in names if n in text or n[1:] in text):
                continue
        keep.append(t)
    return v.model_copy(update={"triggers": keep, "needs_llm_check": bool(keep) and v.needs_llm_check,
                                "ok": not v.violations and not keep})


_SERVICE: GameService | None = None


def get_service() -> GameService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = GameService()
    return _SERVICE
