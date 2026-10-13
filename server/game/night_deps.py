"""밤 시뮬레이션 그래프에 넣을 실제 의존성 (규칙 엔진·RAG·관계 그래프 연결)."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from server.game import content as C
from server.graphs.night import NightDeps, NightLine, NightTalk
from server.rules import actions as act_rules
from server.rules import alertness as alert_rules
from server.rules import bluff as bluff_rules
from server.rules import memory as mem_rules
from server.rules import reputation as rep_rules
from server.schemas import CaseBible, FeedItem, GameState, MemoryDoc, NPCAction, Rumor

if TYPE_CHECKING:
    from server.game.service import GameService


def _fid(text: str) -> str:
    return "rumor:" + hashlib.sha1(text.encode()).hexdigest()[:10]


def _feed(state: GameState, channel: str, author: str, text: str) -> FeedItem:
    item = FeedItem(id=f"f_{uuid.uuid4().hex[:8]}", channel=channel, author=author, text=text, game_time=state.clock)
    state.feed.append(item)
    return item


def build_night_deps(svc: "GameService", case: CaseBible) -> NightDeps:
    cfg = svc.cfg
    key_names = [e.name for e in case.evidence if e.is_key]
    in_building = [l.id for l in case.locations]

    def most_asked(game: GameState) -> str | None:
        asked = game.director_state.get("asked", {})
        return max(asked, key=asked.get) if asked else None

    # ---------------------------------------------------------------- 결정 (코드)
    def decide_actions(case_: CaseBible, game: GameState) -> list[NPCAction]:
        suff = game.notebook.sufficiency or {}
        max_suff = max(suff.values(), default=0.0)
        acts: list[NPCAction] = []
        night_locs: dict[str, str] = {}
        accomplices = [c.id for c in case_.characters if c.is_accomplice]
        for ch in case_.characters:
            ns = game.npc_states[ch.id]
            if bluff_rules.is_guilty(case_, ch.id) and ch.id in case_.culprit_ids:
                cands = alert_rules.night_action_candidates(cfg, ns.alertness, game.reputation, max_suff)
                for a in cands:
                    if a == "contact" and accomplices:
                        acts.append(NPCAction(npc_id=ch.id, action="contact", target=accomplices[0], reason="형사가 다가오고 있다"))
                    elif a in ("hide_evidence", "anonymous_tip", "threat_message"):
                        acts.append(NPCAction(npc_id=ch.id, action=a, reason="들키지 않으려고"))
            # 밤 위치: 건물 안 열린 장소 중 하나 (날마다 다르게, 결정적)
            options = [l for l in game.unlocked_locations if l in in_building]
            night_locs[ch.id] = C.stable_pick(sorted(options), case_.case_id, ch.id, game.day, "night") or ns.location_id
        game.director_state["night_locs"] = night_locs
        return acts

    def pick_encounters(case_: CaseBible, game: GameState, acts: list[NPCAction]) -> list[tuple[str, str]]:
        cap = int(cfg.night.get("max_encounters", 5))
        pairs: list[tuple[str, str]] = []
        for a in acts:  # 범인이 공범에게 연락하면 반드시 만남
            if a.action == "contact" and a.target:
                pairs.append((a.npc_id, a.target))
        locs = game.director_state.get("night_locs", {})
        by_loc: dict[str, list[str]] = {}
        for npc, loc in sorted(locs.items()):
            if game.npc_states[npc].visible:
                by_loc.setdefault(loc, []).append(npc)
        for loc, people in sorted(by_loc.items()):
            for i in range(0, len(people) - 1, 2):
                p = (people[i], people[i + 1])
                if p not in pairs and (p[1], p[0]) not in pairs:
                    pairs.append(p)
        return pairs[:cap]

    # ---------------------------------------------------------------- 대화 (LLM)
    def talk_prompt(case_: CaseBible, game: GameState, a: str, b: str) -> tuple[str, str]:
        ca, cb = C.char(case_, a), C.char(case_, b)
        target = most_asked(game)
        rumor_hint = f"요즘 형사가 {C.char(case_, target).name} 씨에 대해 자주 묻고 다닌다." if target else ""
        mem = lambda npc: [h.content for h in svc.retriever.search(  # noqa: E731
            "형사 수사 어젯밤", case_id=case_.case_id, slot_id=game.slot_id, scope=f"npc:{npc}", k=3, kinds=("memory",))]
        system = ("추리 게임 속 두 인물이 밤에 나누는 짧은 대화를 쓴다. 각자 아는 것만 말하고, 범인이라면 들키지 않으려 한다. "
                  "대화는 4~6줄. 퍼진 소문이 있으면 rumors에 담는다. 범인·핵심 증거를 단정하는 소문은 만들지 않는다.")
        user = (f"[{ca.name}] {ca.role}, 말투: {ca.speech_style}, 아는 것: {mem(a)}\n"
                f"[{cb.name}] {cb.role}, 말투: {cb.speech_style}, 아는 것: {mem(b)}\n"
                f"분위기: {rumor_hint}\nspeaker_id는 {a} 또는 {b}만 쓴다.")
        return system, user

    def fake_talk(case_: CaseBible, game: GameState, a: str, b: str) -> NightTalk:
        ca, cb = C.char(case_, a), C.char(case_, b)
        target = most_asked(game)
        if target:
            tname = C.char(case_, target).name
            lines = [NightLine(speaker_id=a, text=f"오늘 형사가 {tname} 씨 얘기를 계속 묻더라고요."),
                     NightLine(speaker_id=b, text="정말요? 뭔가 알아낸 건가…")]
            rumors = [Rumor(content=f"형사가 {tname} 씨를 의심하는 것 같다", origin_npc=a, told_by=a, told_to=b,
                            distortion_level=0, game_time=game.clock)]
        else:
            lines = [NightLine(speaker_id=a, text="오늘 하루 정신없었네요."), NightLine(speaker_id=b, text="그러게요. 내일은 좀 조용하려나.")]
            rumors = []
        if game.director_state.get("rumor_candidates", 0) > 0 or rep_rules.rumor_count(cfg, game.reputation) > 0:
            rumors.append(Rumor(content="새로 온 형사가 좀 이상한 소리를 하고 다닌대", origin_npc=a, told_by=a, told_to=b,
                                distortion_level=1, game_time=game.clock, about_player=True))
        return NightTalk(lines=lines, rumors=rumors)

    def validate_rumor(case_: CaseBible, r: Rumor) -> list[str]:
        problems = []
        if r.distortion_level > 2:
            problems.append("왜곡 단계 초과")
        if any(n in r.content for n in key_names):
            problems.append("핵심 증거를 소문에 담음")
        if "범인" in r.content:
            problems.append("범인을 단정하는 소문")
        return problems

    def apply_talk(game: GameState, a: str, b: str, talk: NightTalk) -> None:
        for r in talk.rumors:
            svc.rag.add_memory(MemoryDoc(
                id=f"rumor_{uuid.uuid4().hex[:10]}", case_id=case.case_id, slot_id=game.slot_id, owner=r.told_to,
                visibility=[f"npc:{r.told_to}"], doc_type="rumor", content=r.content, game_time=game.clock,
                confidence=mem_rules.initial_confidence(cfg, "heard"), source="heard", source_npc=r.told_by,
                tags=["소문", "형사"],
            ))
            svc.relations.record_fact(case.case_id, game.slot_id, _fid(r.content), r.content, is_true=False)
            svc.relations.record_knowledge(case.case_id, game.slot_id, _fid(r.content), r.told_to, game.clock,
                                           from_who=r.told_by, via="rumor", distortion=r.distortion_level)
            # 형사가 자기를 의심한다는 소문을 들은 범인은 경계한다 (부록 F.10)
            target = r.told_to
            if bluff_rules.is_guilty(case, target) and C.char(case, target).name in r.content:
                ns = game.npc_states[target]
                ns.alertness = alert_rules.apply_event(cfg, ns.alertness, "heard_suspicion")
            if r.about_player:
                _feed(game, "단톡방", C.char(case, r.told_to).name, f"혹시 들었어요? {r.content}")
        # 엿듣기·진실 리플레이용 기록
        game.director_state.setdefault("overheard", []).append(
            {"day": game.day, "location": game.director_state.get("night_locs", {}).get(a),
             "lines": [l.model_dump() for l in talk.lines]})

    def apply_actions(case_: CaseBible, game: GameState, acts: list[NPCAction]) -> list[dict]:
        events = []
        for a in acts:
            if a.action == "threat_message":
                item = _feed(game, "문자", "모르는 번호", "더 이상 파고들지 마.")
                events.append({"type": "CUSTOM", "name": "feed", "value": item.model_dump()})
            elif a.action == "anonymous_tip":
                innocents = [c for c in case_.characters if not bluff_rules.is_guilty(case_, c.id) and c.tier == "main"]
                pick = C.stable_pick(innocents, case_.case_id, game.day, "tip")
                if pick:
                    item = _feed(game, "제보", "익명", f"{pick.name} 씨가 그날 밤 서버실 근처에서 서성이는 걸 봤어요.")
                    events.append({"type": "CUSTOM", "name": "feed", "value": item.model_dump()})
            # hide_evidence: 흔적은 반드시 남으므로(PRD §3.4) MVP에서는 기록만 남기고 증거는 지우지 않는다
        for npc, loc in game.director_state.get("night_locs", {}).items():
            game.npc_states[npc].location_id = loc
        return events

    def end_of_night(case_: CaseBible, game: GameState) -> list[dict]:
        events: list[dict] = []
        # 기억 확신도 감소 (부록 F.8)
        for m, _ in svc.rag.load_memories(case_.case_id, game.slot_id):
            if m.doc_type in ("observation", "heard", "rumor") and m.visibility:
                kind = "detail" if any(ch.isdigit() for ch in m.content) else "core"
                new = mem_rules.daily_decay(cfg, m.confidence, kind)
                if abs(new - m.confidence) > 1e-9:
                    svc.rag.update_memory_confidence(case_.case_id, game.slot_id, m.id, new)
        # 평판 하루 마감, 형사에 대한 소문
        new_state = rep_rules.end_of_day(cfg, game)
        for k in GameState.model_fields:
            setattr(game, k, getattr(new_state, k))
        for _ in range(rep_rules.rumor_count(cfg, game.reputation)):
            item = _feed(game, "단톡방", "익명", "그 형사, 사람들한테 엉뚱한 걸 묻고 다닌대요.")
            events.append({"type": "CUSTOM", "name": "feed", "value": item.model_dump()})
        # 다음 날 아침
        game.day += 1
        game.director_state.update({"events_today": 0, "rumor_candidates": 0, "same_place": 0})
        for ns in game.npc_states.values():
            ns.visits_today = 0
        if game.day > game.max_days:
            game.ending = "escaped"
            game.phase = "ended"
            game.day = game.max_days
            return events
        game.phase = "day"
        game.actions_left = act_rules.new_day_actions(cfg)
        game.clock = (game.day - 1) * 24 * 60 + cfg.investigation["day_start_minute"]
        # 낮에는 다시 각자의 일과 위치로 (밤 위치는 만남·엿듣기·리플레이에만 쓰인다)
        for ch in case_.characters:
            game.npc_states[ch.id].location_id = C.day_location(case_, ch, game.unlocked_locations, game.day)
        return events

    return NightDeps(
        llm=svc.llm, decide_actions=decide_actions, pick_encounters=pick_encounters, talk_prompt=talk_prompt,
        fake_talk=fake_talk, validate_rumor=validate_rumor, apply_talk=apply_talk, apply_actions=apply_actions,
        end_of_night=end_of_night,
    )
