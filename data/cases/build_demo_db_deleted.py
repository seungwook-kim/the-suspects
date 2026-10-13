"""시연용 고정 사건 `demo_db_deleted.json` 생성기.

사람이 읽기 쉽게 파이썬으로 사건을 쓰고, `schemas.CaseBible`로 검증한 뒤 JSON으로 내보낸다.
실행: uv run python data/cases/build_demo_db_deleted.py
(JSON을 직접 고쳐도 되지만, 고치면 이 파일과 어긋나니 가능하면 여기서 고치고 다시 생성한다.)

스포일러 주의: 이 파일과 JSON에는 범인 정보가 들어 있다. 서버 밖으로 내보내지 않는다.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.schemas import (  # noqa: E402
    BluffClaimDef, CaseBible, CaseDocument, Character, DocSection, Evidence, Incident, LieEntry, Location,
    MemoryDoc, MMOEntry, RecordRow, Relation, RoutineEntry, TimelineEvent,
)

CASE_ID = "demo_db_deleted"
TEMPLATE = "__template__"


def T(hhmm: str) -> int:
    """'23:05' -> 1385, '24:41' -> 1481 (사건 첫날 00:00 기준 분)."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------------------------------------
# 인물 id
# ---------------------------------------------------------------------------------------------
DOWON, DBA, YOON, HWANG, CHU, GUARD, PM = (
    "npc_dowon", "npc_dba", "npc_yoon", "npc_hwang", "npc_chu", "npc_guard", "npc_pm",
)
NAME_TO_ID = {"서도윤": DOWON, "고태식": DBA, "윤석진": YOON, "황지호": HWANG, "한소라": PM, "남궁철": GUARD}

LOBBY, OFFICE, PANTRY, MEETING, SERVER, ROOF, PARKING, B1 = (
    "loc_lobby", "loc_office", "loc_pantry", "loc_meeting", "loc_serverroom", "loc_roof", "loc_parking", "loc_b1hall",
)

# ---------------------------------------------------------------------------------------------
# 장소
# ---------------------------------------------------------------------------------------------
locations = [
    Location(id=LOBBY, name="1층 로비·보안데스크", description="유리문 안쪽에 보안데스크와 방문자 단말기가 있다. CCTV 모니터와 출입 기록 단말이 여기에 있다.",
             connections=[OFFICE, MEETING, PARKING, SERVER], background_ref="bg/lobby",
             investigate_evidence_ids=["E3", "E7", "E9", "E15", "E23"]),
    Location(id=OFFICE, name="3층 개발팀 사무실", description="모니터 불빛이 남아 있는 개발팀 공간. 오픈 D-1 체크리스트가 벽에 붙어 있다.",
             connections=[LOBBY, PANTRY, MEETING, ROOF], background_ref="bg/office",
             investigate_evidence_ids=["E1", "E2", "E6", "E16", "E17", "E18", "E20", "E21", "E25", "E28"]),
    Location(id=PANTRY, name="3층 탕비실", description="믹스커피 냄새가 나는 작은 방. 서랍장과 화이트보드, 야식 영수증이 보인다.",
             connections=[OFFICE], background_ref="bg/pantry", investigate_evidence_ids=["E27"]),
    Location(id=MEETING, name="2층 회의실", description="오래된 보고서 바인더가 꽂힌 서류장이 있는 회의실. 아침 장애 대응 회의가 열린다.",
             connections=[LOBBY, OFFICE], unlock_condition="talk:npc_pm", background_ref="bg/meeting",
             investigate_evidence_ids=["E11", "E12"]),
    Location(id=SERVER, name="지하 1층 서버실", description="서늘하고 시끄러운 서버실. 구석에 점검용 콘솔(bastion-02)이 있다.",
             connections=[LOBBY, B1], unlock_condition="evidence:E2", background_ref="bg/serverroom",
             investigate_evidence_ids=["E4", "E5", "E26"]),
    Location(id=B1, name="지하 1층 복도·청소용품실", description="서버실 앞 복도와 청소용품실. 엘리베이터 홀에 CCTV가 있다.",
             connections=[SERVER], unlock_condition="evidence:E7", background_ref="bg/b1hall",
             investigate_evidence_ids=["E10"]),
    Location(id=ROOF, name="옥상 휴게 공간", description="바람이 센 옥상. 야간 근무자들이 쉬는 낡은 의자와 보온병이 놓여 있다.",
             connections=[OFFICE], unlock_condition="talk:npc_dowon", background_ref="bg/roof",
             investigate_evidence_ids=["E8"]),
    Location(id=PARKING, name="지하 주차장", description="차단기와 출차 기록 단말이 있는 주차장 출구.",
             connections=[LOBBY], unlock_condition="talk:npc_guard", background_ref="bg/parking",
             investigate_evidence_ids=["E22"]),
]

# ---------------------------------------------------------------------------------------------
# 인물
# ---------------------------------------------------------------------------------------------
characters = [
    Character(
        id=DOWON, name="서도윤", role="신입 개발자(백엔드, 입사 4개월차)", age=26, gender="M", face_seed=1101,
        appearance={"hair": "눈썹 위까지 내려오는 짧은 검은 앞머리", "outfit": "구겨진 체크 셔츠 위에 회색 후드집업",
                    "accessory": "대형 헤드폰을 목에 걸고 있음", "build": "마른 체격"},
        personality="소심하고 눈치를 많이 보는 성실파. 실수를 하면 말이 빨라지고 사과부터 한다.",
        temperament="timid", small_talk_style="normal",
        speech_style="존댓말인데 말끝을 흐린다. '아, 그게요...', '죄송합니다'를 자주 쓰고 긴장하면 같은 말을 반복하며 빨라진다.",
        goals=["오픈 전에 자기 실수를 아무도 모르게 수습한다", "정규직 전환 평가를 무사히 통과한다"],
        secrets=["오후 7시경 배포 스크립트 옵션을 잘못 넣어 운영 DB에 마이그레이션을 시도했다가 롤백했다(피해 없음). 들킬까 봐 21시에 퇴근했다고 말하고 몰래 남아 수습했다."],
        routine=[RoutineEntry(start=T("09:00"), end=T("24:41"), location_id=OFFICE)],
        relations=[Relation(target=DBA, type="사수", detail="DB 쪽을 배우는 중", known_publicly=True),
                   Relation(target=YOON, type="동료", detail="존경하는 시니어", known_publicly=True),
                   Relation(target=CHU, type="안면", detail="야간에 쓰레기통을 비우러 오는 청소 아저씨. 가끔 믹스커피를 나눠 마신다", known_publicly=False)],
        record_access=["messenger", "server_log"],
    ),
    Character(
        id=DBA, name="고태식", role="DBA(데이터베이스 관리자, 2021년 입사)", age=45, gender="M", face_seed=1102,
        appearance={"hair": "이마가 넓은 짧은 머리, 옆머리에 흰머리가 조금", "outfit": "소매를 걷어 올린 와이셔츠와 베이지 슬랙스",
                    "accessory": "두꺼운 뿔테 안경", "build": "듬직한 체격"},
        personality="무뚝뚝하지만 정이 많은 책임감 강한 베테랑. 자기 영역을 건드리면 예민해진다.",
        temperament="normal", small_talk_style="blunt",
        speech_style="부산 사투리. '마', '~아입니까', '~했다 아이가', '~하이소'를 쓴다. 화나면 말이 짧아지고 목소리가 커진다.",
        goals=["관리형 DB 전환 계획으로 자기 자리가 없어지는 것을 막는다", "오프사이트 백업이 멈춘 것이 자기 탓으로 드러나지 않게 한다"],
        secrets=["오프사이트 백업 전송이 3주째 실패하고 있었는데 알림 메일을 열어보지 않고 방치했다.", "구조조정 소문에 시달려 최근 이직 사이트를 자주 보고 있다."],
        routine=[RoutineEntry(start=T("09:00"), end=T("21:25"), location_id=OFFICE),
                 RoutineEntry(start=T("21:35"), end=T("21:42"), location_id=PARKING)],
        relations=[Relation(target=YOON, type="동료", detail="서로 회사 불만을 털어놓는 사이", known_publicly=True),
                   Relation(target=HWANG, type="업무", detail="외주 개발자에게 읽기 전용 계정을 발급해 줌", known_publicly=True),
                   Relation(target=DOWON, type="후배", detail="DB 업무를 가르치는 중", known_publicly=True)],
        record_access=["server_log", "access_log", "call"],
    ),
    Character(
        id=YOON, name="윤석진", role="시니어 백엔드 개발자(퇴사 예정)", age=41, gender="M", face_seed=1103,
        appearance={"hair": "옆으로 단정하게 넘긴 머리", "outfit": "회색 후드티에 청바지, 사무실 슬리퍼",
                    "accessory": "스마트워치", "build": "키가 크고 마른 편"},
        personality="냉소적이고 효율을 따지는 실력자. 겉으로는 무심하지만 인정받지 못한 일에 오래 서운해한다.",
        temperament="cold", small_talk_style="blunt",
        speech_style="짧은 반말 섞인 문장. '~임', '~인 듯', '뭐, 그렇다 치고.'를 쓰고 한숨을 자주 쉰다. 귀찮아지면 존댓말이 반말로 샌다.",
        goals=["조용히 퇴사하고 이 일에 엮이지 않는다", "옛 동료에게 서버실 카드를 빌려준 일이 드러나지 않게 한다"],
        secrets=["퇴사 전날 옛 동료 추성만에게 부탁을 받고 서버실 출입카드를 빌려줬다. 뭔가 하려는 줄 알면서 회사에 대한 앙금 때문에 모른 척했고, 구 서비스 계정이 아직 살아 있다는 말도 흘렸다.",
                 "다음 날 아침 탕비실 서랍에서 카드가 돌아와 있는 것을 발견하고 아무에게도 말하지 않았다."],
        routine=[RoutineEntry(start=T("09:00"), end=T("20:30"), location_id=OFFICE),
                 RoutineEntry(start=T("21:10"), end=T("24:00"), location_id="off:bar")],
        relations=[Relation(target=CHU, type="옛 동료", detail="2019년 장애 때 책임을 지고 쫓겨난 선배", known_publicly=False),
                   Relation(target=DBA, type="동료", detail="서로 불만을 나누는 사이", known_publicly=True)],
        record_access=["messenger", "access_log", "server_log", "call", "bank"],
        is_accomplice=True,
    ),
    Character(
        id=HWANG, name="황지호", role="외주 개발자(결제 모듈 납품 프리랜서)", age=34, gender="M", face_seed=1104,
        appearance={"hair": "가볍게 펌을 한 갈색 머리", "outfit": "슬림핏 남색 재킷과 흰 티셔츠",
                    "accessory": "스티커가 가득 붙은 노트북 백팩", "build": "보통 체격"},
        personality="말이 빠르고 계산에 밝은 사업가형. 돈 이야기에 예민하고 체면을 중시한다.",
        temperament="normal", small_talk_style="chatty",
        speech_style="비즈니스 존댓말에 영어 IT 용어를 섞는다. '솔직히 말씀드리면', '컨텍스트상', '리스크', '팩트는'. 곤란하면 '그건 계약서 문구상...'으로 빠진다.",
        goals=["밀린 대금 3,200만원을 오픈 전에 받아낸다", "소스 인도 협상에서 불리해지지 않는다"],
        secrets=["어젯밤 22시 10분쯤 노트북과 인도용 USB를 챙기러 회사에 들렀다가 22시 49분에 나갔다. PM에게 대금을 안 주면 소스를 넘기지 않겠다는 압박 메시지를 보낸 터라 방문 사실을 숨기고 싶다."],
        routine=[RoutineEntry(start=T("22:10"), end=T("22:49"), location_id=LOBBY)],
        relations=[Relation(target=PM, type="거래", detail="대금 지급 담당 창구", known_publicly=True),
                   Relation(target=DBA, type="업무", detail="읽기 전용 VPN 계정을 받음", known_publicly=True)],
        record_access=["messenger"],
    ),
    Character(
        id=CHU, name="추성만", role="야간 청소원(시설관리 용역업체 소속, 근무 2년째)", age=54, gender="M", face_seed=1105,
        appearance={"hair": "짧게 친 반백 머리", "outfit": "회색 청소복 위에 푸른 앞치마", "accessory": "목에 수건을 두르고 있음",
                    "build": "어깨가 넓고 손마디가 굵음"},
        personality="느긋하고 말이 많은 수더분한 아저씨. 믹스커피를 건네며 남의 이야기를 잘 들어준다. 예전 일은 잘 꺼내지 않는다.",
        temperament="normal", small_talk_style="chatty",
        speech_style="충청도 사투리. '~했슈', '~그려유', '~혀유'처럼 말끝을 느릿하게 끈다. 모르는 척 되묻는 버릇('그게 뭔디유?')이 있다.",
        goals=["오늘 밤 일을 마치고 아무 일 없다는 듯 퇴근한다", "6년 전 자신을 내쫓은 회사가 오픈 전날 무너지는 것을 본다"],
        secrets=["2018~2019년 모아테크 개발2팀 개발자였다. 2019년 11월 결제 장애의 책임을 혼자 뒤집어쓰고 해고됐고, 2023년 용역업체 소속 청소원으로 같은 건물에 돌아왔다.",
                 "범행 당일 20시 30분 윤석진에게 서버실 카드를 받아 22시 58분 서버실에 들어갔다. 23시 3분 자신이 2018년에 만든 구 서비스 계정 svc_legacy_bk로 콘솔에 로그인해 운영 DB와 로컬 스냅샷을 지우고, 감사 로그 서비스를 멈춰 30분 기록을 날렸다.",
                 "범행 뒤 카드는 탕비실 서랍에 돌려놨다."],
        routine=[RoutineEntry(start=T("19:58"), end=T("22:50"), location_id=OFFICE),
                 RoutineEntry(start=T("22:55"), end=T("23:43"), location_id=SERVER),
                 RoutineEntry(start=T("23:58"), end=T("24:20"), location_id=OFFICE)],
        relations=[Relation(target=YOON, type="옛 동료", detail="2018년 같이 일했다. 아는 척하지 않는다", known_publicly=False),
                   Relation(target=DOWON, type="안면", detail="가끔 믹스커피를 나눠 마신다", known_publicly=True),
                   Relation(target=GUARD, type="야간 동료", detail="같이 야식을 먹는 사이", known_publicly=True)],
        record_access=[],
        is_culprit=True,
    ),
    Character(
        id=GUARD, name="남궁철", role="야간 경비원", age=58, gender="M", face_seed=1106,
        appearance={"hair": "숱이 적은 짧은 흰머리", "outfit": "남색 경비복과 모자", "accessory": "손전등과 무전기", "build": "단단한 체격"},
        personality="원칙주의에 성실하다. 졸음을 쫓으려 늘 자판기 커피를 든다.",
        temperament="normal", small_talk_style="blunt",
        speech_style="군대식 다나까체. '~입니다!', '확인했습니다.' 처럼 짧고 또박또박 끊어 말한다.",
        goals=["근무 중 규정을 어긴 일이 드러나지 않게 한다"],
        secrets=["23시 20분부터 20분간 정문 밖에 담배를 피우러 나가 로비 보안데스크를 비웠다(규정 위반)."],
        routine=[RoutineEntry(start=T("18:00"), end=T("23:00"), location_id=LOBBY),
                 RoutineEntry(start=T("23:40"), end=T("30:00"), location_id=LOBBY)],
        relations=[Relation(target=CHU, type="야간 동료", detail="같이 야식을 먹는 사이", known_publicly=True)],
        tier="minor", key_witness=True, record_access=["access_log", "cctv"],
    ),
    Character(
        id=PM, name="한소라", role="프로덕트 매니저(서비스 오픈 담당)", age=29, gender="F", face_seed=1107,
        appearance={"hair": "어깨까지 오는 웨이브 머리", "outfit": "베이지 가디건에 흰 블라우스", "accessory": "얇은 팔찌와 스티커 붙은 노트북",
                    "build": "보통 체격"},
        personality="밝고 빠르고 일 욕심이 많다. 급하면 미루던 일을 더 미룬다.",
        temperament="normal", small_talk_style="chatty",
        speech_style="밝고 빠른 말투. '헐', '대박', '~했거든요오'를 쓰고 문장 끝을 올린다.",
        goals=["내일 오픈을 어떻게든 정상화한다", "외주 대금 문제를 조용히 정리한다"],
        secrets=["외주 대금 지급을 재무팀에 올리지 않고 미루고 있었다(예산 승인 미비)."],
        routine=[RoutineEntry(start=T("09:00"), end=T("19:00"), location_id=OFFICE),
                 RoutineEntry(start=T("24:15"), end=T("30:00"), location_id=OFFICE)],
        relations=[Relation(target=HWANG, type="거래", detail="외주 대금 지급 담당", known_publicly=True)],
        tier="minor", record_access=["messenger"],
    ),
]

mmo = {
    CHU: MMOEntry(
        motive="6년 전 장애 책임을 혼자 뒤집어쓰고 해고된 데 대한 앙갚음. 오픈 전날 서비스를 무너뜨리려 했다.",
        means="2018년에 자기가 만든 구 서비스 계정 svc_legacy_bk(관리자 권한, 폐기 누락)의 비밀번호를 알고, 윤석진의 서버실 출입카드를 빌렸다.",
        opportunity="용역 청소원으로 야간에 건물에 상주했고, 경비가 자리를 비운 시간대에 지하 서버실에 들어갔다."),
    YOON: MMOEntry(motive="퇴사 앙금과 CTO에 대한 불만", means="관리자 계정과 서버실 카드를 가졌다", opportunity=None),
    DBA: MMOEntry(motive="관리형 DB 전환으로 자리를 잃을 위기", means="dba_root 전권을 가졌다", opportunity=None),
    DOWON: MMOEntry(motive="자신의 마이그레이션 실수가 드러날까 하는 불안", means="배포 스크립트에 운영 접속 정보가 들어 있다", opportunity=None),
    HWANG: MMOEntry(motive="대금 3,200만원 미지급", means=None, opportunity="건물에는 있었으나 사건 16분 전에 퇴장"),
}

culprit_ids = [CHU]

# ---------------------------------------------------------------------------------------------
# 타임라인
# ---------------------------------------------------------------------------------------------
def ev(t, who, loc, action):
    return TimelineEvent(time=T(t), character_id=who, location_id=loc, action=action)


timeline = [
    ev("19:58", CHU, LOBBY, "출근(용역 청소 시작)"), ev("20:02", CHU, OFFICE, "3층 청소 시작"),
    ev("20:30", CHU, PANTRY, "탕비실 앞에서 윤석진에게 서버실 카드를 받음"), ev("20:40", CHU, OFFICE, "3층 청소 재개"),
    ev("22:50", CHU, LOBBY, "큰 천가방을 들고 엘리베이터로 이동"), ev("22:55", CHU, B1, "지하 1층 도착"),
    ev("22:58", CHU, SERVER, "윤석진의 카드로 서버실 입장"), ev("23:03", CHU, SERVER, "svc_legacy_bk로 콘솔 로그인"),
    ev("23:05", CHU, SERVER, "운영 DB 삭제, 스냅샷 분리, 감사 로그 중지"), ev("23:42", CHU, SERVER, "서버실 퇴실"),
    ev("23:43", CHU, B1, "엘리베이터 홀 이동"), ev("23:50", CHU, LOBBY, "1층 경유"), ev("23:55", CHU, PANTRY, "탕비실 서랍에 카드를 돌려놓음"),
    ev("23:58", CHU, OFFICE, "카트를 끌고 청소 마무리"),
    ev("18:40", YOON, OFFICE, "마지막 야근 중 불평"), ev("20:30", YOON, PANTRY, "추성만에게 카드를 건넴"),
    ev("20:38", YOON, LOBBY, "퇴근"), ev("20:50", YOON, "off:street", "홍대로 이동"), ev("21:10", YOON, "off:bar", "홍대 포차에서 술자리"),
    ev("18:00", DBA, OFFICE, "근무"), ev("21:25", DBA, OFFICE, "퇴근 전 점검"), ev("21:35", DBA, LOBBY, "퇴근 이동"),
    ev("21:38", DBA, PARKING, "차량 탑승"), ev("21:42", DBA, "off:road", "주차장 출차"), ev("22:15", DBA, "off:home", "귀가"),
    ev("09:00", DOWON, OFFICE, "출근"), ev("19:12", DOWON, OFFICE, "배포 스크립트 실수 후 롤백"),
    ev("23:05", DOWON, OFFICE, "사무실에서 노트북 작업"), ev("23:13", DOWON, OFFICE, "DB 장애 확인 후 보고"),
    ev("24:41", DOWON, OFFICE, "사무실 퇴실"),
    ev("22:10", HWANG, LOBBY, "방문자 등록"), ev("22:18", HWANG, OFFICE, "서도윤과 짧게 대화, 노트북 챙김"),
    ev("22:45", HWANG, LOBBY, "하강"), ev("22:49", HWANG, "off:street", "퇴장"),
    ev("18:00", GUARD, LOBBY, "근무 시작"), ev("23:03", GUARD, OFFICE, "3층 순찰"), ev("23:12", GUARD, LOBBY, "로비 복귀"),
    ev("23:20", GUARD, "off:street", "정문 밖에서 흡연"), ev("23:40", GUARD, LOBBY, "자리 복귀"),
    ev("09:00", PM, OFFICE, "근무"), ev("19:00", PM, "off:home", "퇴근"), ev("24:10", PM, LOBBY, "장애 소식에 회사로 복귀"),
    ev("24:15", PM, OFFICE, "사무실 합류"),
]

incident = Incident(
    time=T("23:05"), location_id=SERVER,
    summary="서비스 오픈을 하루 앞둔 밤 11시 5분쯤, 모아테크 판교 오피스 지하 서버실의 운영 DB(moa_prod)가 통째로 삭제됐습니다. 접속 감사 로그까지 함께 지워져 누가 했는지 알 수 없습니다. 오픈은 내일 오전 9시입니다.",
)

# ---------------------------------------------------------------------------------------------
# 정형 기록
# ---------------------------------------------------------------------------------------------
records: list[RecordRow] = []
_seq: dict[str, int] = {}


def vis_for(system: str, person: str | None) -> list[str]:
    base = {"call": ["warrant:call"], "bank": ["warrant:bank"]}.get(system, ["player"])
    return base + ([f"npc:{person}"] if person else [])


def R(system, t, detail, person=None, loc=None, ev_id=None, vis=None):
    _seq[system] = _seq.get(system, 0) + 1
    records.append(RecordRow(
        id=f"rec_{system}_{_seq[system]:03d}", system=system, time=T(t) if isinstance(t, str) else t, person_id=person,
        location_id=loc, detail=detail, visibility=vis or vis_for(system, person), evidence_id=ev_id))


# --- 출입카드 (핵심)
R("access_log", "19:58", "1층 게이트 출입 (용역 사원증 CLN-0231 추성만)", CHU, LOBBY)
R("access_log", "20:02", "3층 사무실 출입 (용역 사원증 CLN-0231 추성만)", CHU, OFFICE)
R("access_log", "21:42", "주차장 출구 차단기 통과 (차량 12가 3456, 등록자 고태식)", DBA, PARKING, "E22")
R("access_log", "22:10", "방문자 등록: 황지호(외주), 방문 목적 '노트북 수령', 담당자 한소라 전화 확인", HWANG, LOBBY, "E15")
R("access_log", "22:49", "방문자 퇴장 처리: 황지호(외주)", HWANG, LOBBY, "E15")
R("access_log", "22:58", "서버실 출입문 카드 인증 성공: YSJ-0412 (윤석진)", YOON, SERVER, "E3")
R("access_log", "23:42", "서버실 출입문 퇴실 인증: YSJ-0412 (윤석진)", YOON, SERVER, "E3")
R("access_log", "24:41", "3층 사무실 퇴실 인증: 서도윤", DOWON, OFFICE, "E25")
# --- CCTV (공용 구역)
R("cctv", "20:30", "3층 복도(탕비실 앞) CCTV: 윤석진이 추성만에게 카드 크기의 물건을 건넴. 추성만이 앞치마 주머니에 넣음. 물건 식별 불가.", YOON, PANTRY, "E9")
R("cctv", "20:31", "3층 복도(탕비실 앞) CCTV: 추성만이 탕비실 앞을 벗어나 청소 카트로 복귀", CHU, PANTRY, "E9")
R("cctv", "22:55", "지하 1층 엘리베이터 홀 CCTV: 청소복 차림의 추성만이 대형 천가방을 들고 하차, 서버실 방향으로 이동", CHU, B1, "E7")
R("cctv", "23:43", "지하 1층 엘리베이터 홀 CCTV: 서버실 방향에서 추성만이 이동해 엘리베이터 탑승", CHU, B1, "E7")
R("cctv", "23:20", "1층 로비 CCTV: 보안데스크 무인, 경비원 자리 비움", GUARD, LOBBY, "E23")
R("cctv", "23:40", "1층 로비 CCTV: 경비원 보안데스크 복귀", GUARD, LOBBY, "E23")
# --- 서버 로그
R("server_log", "02:10", "오프사이트 백업 전송 실패: S3 자격증명 만료 (연속 21일째 실패, 알림 메일 DBA 그룹 발송)", None, SERVER, "E5")
R("server_log", "19:12", "deploy-script: migrate --env=prod 실행 후 즉시 롤백, 변경 0건 (실행자 dev_deploy / 서도윤)", DOWON, SERVER, "E6")
R("server_log", "23:02", "VPN 접속: ext_hwang (읽기 전용 role), 외부 IP, 23:20 종료", HWANG, None, None)
R("server_log", "23:03", "bastion-02 콘솔(tty1, 서버실 로컬) 로그인: svc_legacy_bk", None, SERVER, "E4")
R("server_log", "23:05", "디스크 I/O 사용률 98% (평시 12%) 시작, 데이터 볼륨 사용량 급감", None, SERVER, "E2")
R("server_log", "23:12", "디스크 I/O 정상화, 데이터 볼륨 사용량 0.3% (직전 412GB). 서비스 헬스체크 실패: moa_prod 연결 0, 에러율 100%", None, SERVER, "E2")
R("server_log", "23:12", "스냅샷 볼륨 vol-local-snap-07 detach 이벤트 (실행 주체 기록 없음)", None, SERVER, None)
R("server_log", "23:41", "auditd 서비스 재시작. 직전 기록 23:09, 이후 기록 23:41: 23:10~23:40 구간 감사 로그 없음 (30분 공백)", None, SERVER, "E1")
R("server_log", "23:41", "bastion-02 /home/svc_legacy_bk/.bash_history 크기 0B (최종 수정 23:38)", None, SERVER, "E26")
R("server_log", "23:41", "bastion-02 콘솔 세션 종료: svc_legacy_bk", None, SERVER, None)
# --- 통화(영장)
R("call", "22:12", "발신 황지호 -> 한소라 (1분, 방문 확인)", HWANG, None, None)
R("call", "22:56", "발신 윤석진 -> 010-****-2291 (6분). 기지국: 마포구 서교동", YOON, "off:bar", "E14")
R("call", "23:05", "발신 윤석진 -> 대리운전 1588-**** (2분). 기지국: 마포구 서교동", YOON, "off:bar", "E14")
R("call", "23:58", "발신 서도윤 -> CTO (4분)", DOWON, None, None)
R("call", "21:50", "발신 고태식 -> 가족 (3분). 기지국: 성남시 분당구", DBA, "off:home", None)
# --- 은행(영장)
R("bank", "21:12", "체크카드 결제 78,000원, 가맹점 '포차 청춘' (마포구 서교동)", YOON, "off:bar", "E13")
R("bank", "22:47", "체크카드 결제 43,500원, 가맹점 '호프집 달빛' (마포구 서교동)", YOON, "off:bar", "E13")
# --- 배달
R("delivery", "20:15", "치킨 배달 완료: 모아테크 3층 로비, 수령 서도윤, 2인분", DOWON, OFFICE, "E27")

# --- 사내 메신저 (대화 로그 문서에서 그대로 만든다)
CHAT = {
    "18:00~19:59 (오픈 D-1 마지막 점검)": (
        "오픈 전날 저녁 점검. 한소라 PM의 체크리스트 공유와 개발자들의 마지막 잡담.",
        [
            ("18:05", "한소라", "내일 오픈 최종 체크리스트 올려놨어요! 다들 확인 부탁드려요"),
            ("18:12", "고태식", "체크했다. 백업은 정상이고 DB 쪽은 이상 없습니더."),
            ("18:40", "윤석진", "난 오늘이 마지막 야근임. 인수인계 문서는 어차피 아무도 안 읽으니까 안 씀. CTO 얼굴 보는 것도 오늘이 끝이고."),
            ("18:41", "고태식", "석진아 그라지 마라 마."),
            ("19:02", "서도윤", "저 배포 스크립트 최종 점검 중입니다..."),
            ("19:14", "서도윤", "(삭제된 메시지)"),
        ]),
    "20:00~21:59 (대금 문제와 퇴근)": (
        "저녁 시간대 대화. 외주 대금 압박과 DBA의 불안, 퇴근 인사가 오간다.",
        [
            ("20:20", "황지호", "소라님, 대금 건 아직도 소식이 없네요. 솔직히 말씀드리면 내일 오픈 전까지 입금 안 되면 소스 인도는 보류하겠습니다."),
            ("20:22", "한소라", "헐 지호님ㅠㅠ 저도 급하게 알아보고 있어요오 오늘 내로 재무팀에 올릴게요"),
            ("20:45", "고태식", "매니지드 DB로 갈아탄다는 얘기 아직도 진행 중이라 카더라. 그라믄 우리 팀 자리는 어데 있노."),
            ("21:12", "고태식", "퇴근합니더. 내일 보입시다."),
            ("21:15", "서도윤", "들어가세요! 저는 조금만 더 보고 가겠습니다."),
        ]),
    "22:00~23:59 (사고 발생)": (
        "밤 사이 대화. 외주 개발자 방문 소식, 그리고 운영 DB 장애 발견과 보고.",
        [
            ("22:12", "황지호", "노트북 가지러 잠깐 1층 왔어요. 올라가도 되죠?"),
            ("22:49", "황지호", "나갑니다. 내일 뵙겠습니다."),
            ("23:13", "서도윤", "운영 DB 접속이 안 돼요!! 에러율 100%예요"),
            ("23:14", "한소라", "헐 뭐라고요? 지금 갈게요"),
            ("23:16", "서도윤", "로그도 안 남아 있어요... 감사 로그가 비어 있어요"),
            ("23:30", "한소라", "태식님 연락 안 돼요 윤석진님도..."),
            ("23:55", "서도윤", "CTO님께 전화했어요. 아침에 모여서 얘기하자고 하세요."),
        ]),
}
CHAT_EVIDENCE = {("20:20", "황지호"): "E16", ("18:40", "윤석진"): "E21", ("20:45", "고태식"): "E18",
                 ("21:15", "서도윤"): "E28", ("23:13", "서도윤"): "E28", ("23:16", "서도윤"): "E28"}
for _head, (_ctx, lines) in CHAT.items():
    for hhmm, name, text in lines:
        R("messenger", hhmm, f"#dev-night | {name}: {text}", NAME_TO_ID[name], None, CHAT_EVIDENCE.get((hhmm, name)),
          vis=["player", f"npc:{NAME_TO_ID[name]}"])

# --- 잡음 기록 (사건과 무관한 일상. 고정 시드로 생성)
rng = random.Random(20261013)
STAFF = [("서도윤", DOWON), ("고태식", DBA), ("윤석진", YOON), ("한소라", PM)]
for i in range(18):
    name, pid = rng.choice(STAFF)
    minute = rng.randint(T("08:25"), T("09:40"))
    R("access_log", minute, f"1층 게이트 출근 인증: {name}", pid, LOBBY)
for i in range(6):
    minute = rng.randint(T("08:20"), T("18:30"))
    R("access_log", minute, f"1층 게이트 인증: 사원 EMP-{rng.randint(1000, 1999)}", None, LOBBY, vis=["player"])
for i in range(5):
    minute = rng.randint(T("08:30"), T("18:00"))
    R("cctv", minute, rng.choice(["1층 로비 CCTV: 평상시 출입 인원 확인", "1층 로비 CCTV: 택배 기사 방문",
                                  "주차장 CCTV: 차량 출입 정상", "3층 복도 CCTV: 평상시 이동"]), None, rng.choice([LOBBY, PARKING, OFFICE]))
for i, (hhmm, text) in enumerate([
    ("02:00", "로컬 스냅샷 생성 성공 (moa_prod, 412GB)"), ("03:00", "로그 로테이트 완료"), ("06:30", "CPU 사용률 평시 범위"),
    ("10:05", "배포 파이프라인: staging 배포 성공"), ("13:20", "헬스체크 정상 (응답 82ms)"), ("15:40", "배포 파이프라인: staging 테스트 통과"),
    ("17:55", "디스크 사용량 점검: 데이터 볼륨 412GB / 1TB"), ("20:00", "헬스체크 정상 (응답 79ms)"),
]):
    R("server_log", hhmm, text, None, SERVER)
for hhmm, who, text in [
    ("09:12", "한소라", "굿모닝! 오늘 점심 뭐 드실래요?"), ("09:15", "서도윤", "저는 김치찌개 좋습니다"),
    ("10:30", "윤석진", "스탠드업 생략해도 되죠? 어차피 내용 같음"), ("12:05", "고태식", "점심 먹으러 갑니더."),
    ("14:40", "한소라", "오픈 공지 문구 최종본 공유드려요!"), ("15:10", "서도윤", "공지 문구 확인했습니다. 오타 없습니다."),
    ("16:25", "윤석진", "커피 머신 또 고장남"), ("16:30", "고태식", "그거 어제부터 그렇다 아이가."),
]:
    R("messenger", hhmm, f"#general | {who}: {text}", NAME_TO_ID[who], None, vis=["player", f"npc:{NAME_TO_ID[who]}"])
R("delivery", "14:00", "택배 도착: 모아테크 1층 보안데스크 수령, 사무용품", None, LOBBY)
R("delivery", "11:30", "생수 배송: 3층 탕비실", None, PANTRY)
R("delivery", "17:20", "서류 퀵 배송: 한소라 수령", PM, LOBBY)
R("call", "14:20", "발신 한소라 -> 클라이언트 (7분)", PM, None)
R("call", "12:45", "발신 서도윤 -> 가족 (2분)", DOWON, None)
R("call", "16:05", "발신 윤석진 -> 인사팀 (4분, 퇴사 서류)", YOON, None)
R("bank", "12:34", "체크카드 결제 9,500원, 가맹점 '판교 순대국' ", DBA, None)
R("bank", "12:40", "체크카드 결제 8,000원, 가맹점 '김밥천국 판교점'", DOWON, None)
R("bank", "18:55", "체크카드 결제 14,200원, 가맹점 '카페 온도'", PM, None)
records.sort(key=lambda r: (r.time, r.id))

# ---------------------------------------------------------------------------------------------
# 증거
# ---------------------------------------------------------------------------------------------
def E(id, name, kind, content, loc=None, vis=None, key=False, tags=(), linked=(), reveals=(), traces=(), destroyable=False, public=False):
    return Evidence(id=id, name=name, kind=kind, content=content, location_id=loc, visibility=vis or ["player"], is_key=key,
                    element_tags=list(tags), linked_suspects=list(linked), reveals_contradiction_of=list(reveals),
                    indirect_traces=list(traces), destroyable=destroyable, public_area=public)


evidence = [
    E("E1", "감사 로그 30분 공백", "record",
      "bastion-02의 접속 감사 로그에 23:10~23:40 구간 기록이 통째로 없다. 직전 기록은 23:09, 서비스가 재시작된 23:41에 공백이 감지됐다. 로그 서비스를 멈추고 기록을 지운 사람이 있다는 뜻이다.",
      OFFICE, key=False, traces=["E2", "E3", "E4"], destroyable=True),
    E("E2", "디스크 사용량 급증 기록", "record",
      "모니터링 지표: 23:05부터 7분간 디스크 I/O 사용률 98%(평시 12%). 데이터 볼륨 사용량이 412GB에서 0.3%로 급감했다. 23:12에 서비스 헬스체크가 실패하고 알림이 나갔다. 감사 로그가 지워졌어도 지표는 남았다.",
      OFFICE),
    E("E3", "서버실 출입카드 기록", "record",
      "서버실 출입문 기록: 22:58 카드 YSJ-0412(윤석진) 인증 성공, 23:42 같은 카드로 퇴실. 약 44분간 누군가 윤석진의 카드로 서버실에 있었다.",
      LOBBY, key=True, tags=["opportunity"], linked=[YOON]),
    E("E4", "서버실 콘솔 로그인 기록", "record",
      "bastion-02 콘솔(서버실 로컬 tty1)에 23:03 svc_legacy_bk 계정으로 로그인한 기록이 감사 로그가 멈추기 전에 남았다. 원격이 아니라 서버실 안에서 로그인했다는 뜻이다.",
      SERVER, key=True, tags=["means"]),
    E("E5", "오프사이트 백업 21일 연속 실패", "record",
      "오프사이트 백업 전송이 21일째 S3 자격증명 만료로 실패했고, 알림 메일이 DBA 그룹으로 매일 발송됐다. 사건 전날까지 백업은 정상이라는 말과 맞지 않는다.",
      SERVER, linked=[DBA], reveals=["L_dba_1"]),
    E("E6", "서도윤의 운영 DB 마이그레이션 시도", "record",
      "19:12 서도윤의 배포 스크립트가 --env=prod로 마이그레이션을 실행했다가 즉시 롤백했다. 변경은 0건이다. 스크립트에 운영 접속 정보가 그대로 들어 있다.",
      OFFICE, tags=["motive", "means"], linked=[DOWON]),
    E("E7", "지하 1층 CCTV: 추성만의 이동", "record",
      "지하 1층 엘리베이터 홀 CCTV: 22:55 청소복 차림의 추성만이 대형 천가방을 들고 하차해 서버실 방향으로 이동, 23:43 서버실 방향에서 나와 엘리베이터에 탑승.",
      LOBBY, key=True, tags=["opportunity"], linked=[CHU], reveals=["L_chu_1"], public=True),
    E("E8", "속지에 이름이 적힌 개발서적", "object",
      "옥상 휴게 의자 옆 낡은 개발서적 '스프링 입문'. 속지에 '추성만, 모아테크 개발2팀, 2018'이라고 적혀 있다. 청소원이 되기 전에 개발자였다는 흔적이다.",
      ROOF, linked=[CHU], reveals=["L_chu_2"]),
    E("E9", "복도 CCTV: 카드 전달 장면", "record",
      "20:30 3층 탕비실 앞 CCTV: 윤석진이 추성만에게 카드 크기의 물건을 건넸고 추성만이 앞치마 주머니에 넣었다. 두 사람이 아는 사이라는 증거이기도 하다.",
      LOBBY, key=True, tags=["means"], linked=[CHU, YOON], reveals=["L_yoon_1", "L_yoon_2", "L_chu_3"], public=True),
    E("E10", "청소 점검표의 빈 칸", "object",
      "청소용품실에 걸린 3층 청소 점검표. 22:50~23:55 구간 서명란이 비어 있다. 추성만이 말한 '밤새 3층만 청소'와 맞지 않는다.",
      B1, tags=["opportunity"], linked=[CHU], reveals=["L_chu_1"]),
    E("E11", "계정 소유자표", "document",
      "2018년 계정 발급 대장 사본: svc_legacy_bk, 구 백업서버 연동 서비스 계정, 소유자 smchoo(개발2팀 추성만), 권한 관리자, 폐기 표시 없음. 비밀번호가 변경된 이력이 없다.",
      MEETING, key=True, tags=["means"], linked=[CHU], reveals=["L_chu_2"]),
    E("E12", "2019년 결제 장애 회고 회의록", "document",
      "2019년 11월 결제 장애 회고 회의록: 책임 안건에서 개발2팀 추성만(smchoo)에게 정직 후 계약 종료를 권고했다. 참석자 윤석진(개발1팀)의 이름도 있다. CTO 지시로 사전 공유 없이 스키마가 바뀐 정황은 기록에서 빠졌다.",
      MEETING, key=True, tags=["motive"], linked=[CHU], reveals=["L_chu_2", "L_yoon_2"]),
    E("E13", "윤석진의 카드 결제 내역", "record",
      "윤석진의 체크카드: 21:12 홍대 포차 청춘 78,000원, 22:47 호프집 달빛 43,500원(모두 서교동). 22:58 서버실 출입 시각에 윤석진은 판교가 아니라 홍대에 있었다.",
      None, vis=["warrant:bank"], linked=[YOON], reveals=["L_yoon_1"]),
    E("E14", "윤석진의 통화 기록", "record",
      "윤석진 휴대전화: 22:56 통화 6분, 23:05 대리운전 호출 2분. 두 건 모두 기지국이 마포구 서교동이다. 사건 시각에 윤석진은 서버실에 없었다.",
      None, vis=["warrant:call"], linked=[YOON], reveals=["L_yoon_1"]),
    E("E15", "황지호의 방문자 기록", "record",
      "방문자 단말기: 22:10 황지호(외주) 방문 등록, 22:49 퇴장 처리. 사건 시각(23:05)보다 16분 먼저 건물을 나갔다.",
      LOBBY, tags=["opportunity"], linked=[HWANG], reveals=["L_hwang_1"]),
    E("E16", "황지호의 대금 압박 메시지", "record",
      "20:20 황지호: '내일 오픈 전까지 입금 안 되면 소스 인도는 보류하겠습니다.' 3,200만원 대금이 한 달 넘게 밀려 있다.",
      OFFICE, tags=["motive"], linked=[HWANG]),
    E("E17", "외주 계정 권한 목록", "document",
      "계정 권한표: ext_hwang은 읽기 전용 VPN 계정이다. 운영 DB 삭제나 서버 명령 실행 권한이 없다.",
      OFFICE, linked=[HWANG]),
    E("E18", "고태식의 불안 메시지", "record",
      "20:45 고태식: '매니지드 DB로 갈아탄다는 얘기 아직도 진행 중이라 카더라. 그라믄 우리 팀 자리는 어데 있노.'",
      OFFICE, tags=["motive"], linked=[DBA]),
    E("E20", "DBA 계정 권한", "document",
      "계정 권한표: dba_root(고태식)는 운영 DB 전권(root)이다.",
      OFFICE, tags=["means"], linked=[DBA]),
    E("E21", "윤석진의 퇴사 불만 메시지", "record",
      "18:40 윤석진: '난 오늘이 마지막 야근임. 인수인계 문서는 어차피 아무도 안 읽으니까 안 씀. CTO 얼굴 보는 것도 오늘이 끝이고.'",
      OFFICE, tags=["motive"], linked=[YOON]),
    E("E22", "고태식의 주차장 출차 기록", "record",
      "21:42 주차장 출구 차단기 기록: 차량 12가 3456(고태식)이 퇴근했다. 사건 시각 DBA는 이미 회사를 떠난 뒤였다.",
      PARKING, linked=[DBA]),
    E("E23", "로비 CCTV: 경비석 무인", "record",
      "1층 로비 CCTV: 23:20~23:40 보안데스크가 비어 있었다. 경비원은 근무 중 자리를 비운 적 없다고 했다.",
      LOBBY, linked=[GUARD], reveals=["L_guard_1"], public=True),
    E("E24", "경비원의 증언: 서도윤 확인", "testimony",
      "남궁철: '23시 3분 순찰 때 3층 사무실에서 서도윤이 혼자 노트북을 보고 있었고, 복도에 청소 카트는 서 있는데 청소원은 안 보였습니다.'",
      None, linked=[DOWON], reveals=["L_dowon_1"]),
    E("E25", "서도윤의 3층 퇴실 기록", "record",
      "3층 사무실 출입문 기록: 00:41 서도윤 퇴실. 21시쯤 퇴근했다는 말과 다르다.",
      OFFICE, linked=[DOWON], reveals=["L_dowon_1"]),
    E("E26", "삭제된 명령 기록", "record",
      "bastion-02 svc_legacy_bk의 .bash_history 크기가 0B이고 최종 수정이 23:38이다. 명령 기록을 비웠다.",
      SERVER, traces=["E4", "E2"], destroyable=True),
    E("E27", "야식 배달 영수증", "record",
      "20:15 치킨 2인분이 3층 로비로 배달됐다. 수령인은 서도윤. 한밤의 개발자들이 먹은 야식이다.",
      PANTRY, linked=[DOWON]),
    E("E28", "서도윤의 밤 메시지", "record",
      "21:15 서도윤: '저는 조금만 더 보고 가겠습니다.' 23:13 '운영 DB 접속이 안 돼요!!' 23:16 '감사 로그가 비어 있어요'. 21시 퇴근이라는 말과 다르다.",
      OFFICE, linked=[DOWON], reveals=["L_dowon_1"]),
]

# ---------------------------------------------------------------------------------------------
# 거짓말 장부
# ---------------------------------------------------------------------------------------------
lie_ledger = [
    LieEntry(id="L_chu_1", liar_id=CHU, topic="밤 동선", lie="밤새 3층 사무실만 청소했고 지하엔 내려간 적 없슈.",
             truth="22:55~23:43 지하 1층에 내려가 윤석진의 카드로 서버실에 있었다.", rebuttal_evidence_ids=["E7", "E10"]),
    LieEntry(id="L_chu_2", liar_id=CHU, topic="회사와의 인연", lie="이 회사랑은 2년 전 용역 들어오면서 처음 인연이 닿았슈.",
             truth="2018~2019년 개발2팀 개발자였고 장애 책임으로 해고됐다.", rebuttal_evidence_ids=["E8", "E11", "E12"]),
    LieEntry(id="L_chu_3", liar_id=CHU, topic="출입카드", lie="윤 선생 카드는 본 적도 없슈.",
             truth="20시 30분 탕비실 앞에서 윤석진에게 카드를 받았다.", rebuttal_evidence_ids=["E9"]),
    LieEntry(id="L_yoon_1", liar_id=YOON, topic="출입카드 보관", lie="내 카드는 하루종일 내 가방에 있었음. 남한테 빌려준 적 없음.",
             truth="20시 30분 추성만에게 카드를 건넸고, 사건 시각에는 홍대 술집에 있었다.", rebuttal_evidence_ids=["E9", "E13", "E14"]),
    LieEntry(id="L_yoon_2", liar_id=YOON, topic="청소원과의 관계", lie="청소하시는 분이랑은 인사도 해 본 적 없음.",
             truth="2018~2019년 같이 일한 옛 동료 추성만임을 알고 있다.", rebuttal_evidence_ids=["E12", "E9"]),
    LieEntry(id="L_hwang_1", liar_id=HWANG, topic="어젯밤 행적", lie="어젯밤엔 회사 근처에도 안 갔습니다. 집에서 쉬었어요.",
             truth="22:10~22:49 노트북을 가지러 회사에 있었다.", rebuttal_evidence_ids=["E15"]),
    LieEntry(id="L_dba_1", liar_id=DBA, topic="백업 상태", lie="오프사이트 백업은 매일 정상으로 나가고 있었습니더.",
             truth="전송이 21일째 실패 중이었고 알림 메일을 방치했다.", rebuttal_evidence_ids=["E5"]),
    LieEntry(id="L_dowon_1", liar_id=DOWON, topic="퇴근 시각", lie="저는 9시쯤 퇴근했어요... 그 뒤는 모릅니다.",
             truth="자신의 실수를 수습하느라 00:41까지 3층 사무실에 남아 있었다.", rebuttal_evidence_ids=["E25", "E28", "E24"]),
    LieEntry(id="L_guard_1", liar_id=GUARD, topic="근무 태도", lie="근무 중 한순간도 자리를 비운 적 없습니다!",
             truth="23:20~23:40 정문 밖에서 흡연하느라 보안데스크를 비웠다.", rebuttal_evidence_ids=["E23"]),
]

# ---------------------------------------------------------------------------------------------
# 문서
# ---------------------------------------------------------------------------------------------
manual = CaseDocument(
    id="doc_manual", title="모아마켓 운영 DB 운영·백업 매뉴얼 v3.2", doc_type="manual", visibility=["public"],
    sections=[
        DocSection(heading="1. 개요", context="모아마켓 운영 DB 매뉴얼의 개요. 운영 DB의 구성과 담당자, 변경 절차를 설명한다.",
                   text="모아마켓 운영 DB(moa_prod)는 PostgreSQL 16으로 구성되며 지하 1층 서버실 rack-07에 있다. 담당 DBA는 고태식이다.\n운영 DB 스키마 변경은 반드시 배포 티켓을 거치며, 직접 접속은 점검 목적에 한해 DBA 승인 후 허용한다."),
        DocSection(heading="2. 백업 정책 > 백업 주기와 보존 기간", context="운영 DB 백업 정책 중 백업 주기와 보존 기간. 로컬 스냅샷과 오프사이트 백업의 관계를 정한다.",
                   text="매일 02:00에 서버실 로컬 스냅샷을 만들고 7일간 보존한다. 02:10에 오프사이트(S3)로 전송하며 30일간 보존한다.\n오프사이트 전송이 실패하면 DBA 메일 그룹으로 알림이 나간다. 알림은 당일 안에 확인해야 한다."),
        DocSection(heading="2. 백업 정책 > 백업 점검", context="운영 DB 백업 정책 중 정기 점검과 보고 규정.",
                   text="매주 월요일 DBA가 백업 점검표에 서명한다. 오프사이트 전송 실패가 3일 이상 이어지면 CTO에게 보고한다."),
        DocSection(
            heading="3. 계정 관리", context="운영 DB 계정 관리 규정. 계정 종류와 권한, 퇴사자 처리와 서비스 계정 예외를 다룬다.",
            text=(
                "운영 DB와 관련 서버의 계정은 개인 계정과 서비스 계정으로 나눈다. 개인 계정은 입사 시 발급하고 퇴사 당일 비활성화한다. 권한은 최소 권한 원칙에 따라 읽기, 쓰기, 관리자 세 단계로 구분한다.\n"
                "현재 주요 계정은 다음과 같다. dba_root는 고태식이 쓰는 운영 DB 전권(root) 계정이다. adm_ysj는 윤석진의 관리자 계정이다. dev_deploy는 서도윤이 배포 파이프라인에서 쓰는 읽기/쓰기 계정으로 스키마 변경은 불가하다. ext_hwang은 외주 개발자 황지호의 읽기 전용 VPN 계정이다.\n"
                "계정 신청과 폐기는 보안 담당 승인을 받아 대장에 기록한다. 분기마다 계정 대장을 점검하되, 서비스 계정은 연동 시스템 영향 때문에 담당 팀 확인 후 폐기한다. 폐기 대상 서비스 계정 목록은 분기 점검 때 갱신한다.\n"
                "계정 대장 점검은 보안 담당이 분기 마지막 주에 진행한다. 점검자는 대장의 계정별 사용 이력과 마지막 로그인 시각, 권한 수준, 담당 부서와 담당자의 재직 여부를 확인하고 이상이 있으면 담당 팀에 정리를 요청한다. 정리 요청을 받은 팀은 2주 안에 폐기 또는 유지 사유를 회신해야 하며, 회신이 없는 계정은 다음 분기에 다시 점검한다. 점검 결과는 보안 회의에서 공유하고 대장 사본을 2층 회의실 서류장에 보관한다. 외부 업체 인력과 외주 개발자의 계정은 계약 기간이 끝나면 계약 담당이 보안 담당에게 폐기를 요청하고, 요청이 접수되면 영업일 기준 3일 안에 비활성화한다. 계약 연장이 있으면 갱신 사실을 대장 비고란에 함께 적는다.\n"
                "서비스 계정은 비밀번호 변경 주기가 길고, 사용 이력이 없는 계정도 점검 대상에서 제외되는 경우가 있다. 점검 제외 사유는 대장 비고란에 기록한다.\n"
                "※ 비고: svc_legacy_bk는 2018년 구 백업 서버 연동용으로 만든 서비스 계정이며 담당자는 smchoo(개발2팀)다. 담당자 퇴사(2019-12) 후 이관·폐기 목록에서 누락되어 현재도 활성 상태이고, 관리자 권한과 기존 비밀번호가 유지되고 있다."
            )),
        DocSection(heading="4. 감사 로그", context="감사 로그 보관 방식. 로그가 어디에 쌓이고 누가 지울 수 있는지를 설명한다.",
                   text="접속 감사 로그(auditd)는 bastion-02 로컬 디스크에 보관하며 주 1회 수동으로 반출한다. 중앙 수집 서버로의 실시간 전송은 예산 문제로 도입이 보류됐다.\n서비스 계정의 접속도 같은 방식으로 기록된다."),
        DocSection(heading="5. 서버실 출입", context="서버실 출입 규정. 카드 사용 원칙과 청소 규정을 다룬다.",
                   text="서버실 출입은 개인 카드로만 허용하며 카드 대여와 공유를 금지한다. 서버실 청소는 주 1회 낮 시간에 외부 업체가 DBA 동행으로 진행한다. 야간 청소 인력은 서버실 출입 권한이 없다."),
        DocSection(heading="6. 장애 복구 절차", context="운영 DB 장애 시 복구 순서. 오프사이트 백업과 로컬 스냅샷 중 무엇을 먼저 쓰는지 설명한다.",
                   text="장애 시 먼저 오프사이트 백업에서 복구한다. 오프사이트 백업을 쓸 수 없으면 로컬 스냅샷으로 복구한다. 두 가지가 모두 없으면 애플리케이션 로그로 재구성하되 최대 24시간 분량의 데이터 손실이 생길 수 있다."),
    ])

chat_doc = CaseDocument(
    id="doc_chat", title="#dev-night 사내 메신저 대화 로그 (오픈 전날 18시~자정)", doc_type="chat_log", visibility=["public"],
    sections=[DocSection(heading=head, context=ctx, text="\n".join(f"[{h}] {n}: {t}" for h, n, t in lines))
              for head, (ctx, lines) in CHAT.items()])

minutes_2019 = CaseDocument(
    id="doc_minutes_2019", title="2019년 11월 결제 장애 회고 회의록", doc_type="minutes",
    visibility=["player", f"npc:{CHU}", f"npc:{YOON}"],
    sections=[
        DocSection(heading="안건 1. 장애 경과", context="2019년 11월 결제 DB 장애 회고 회의의 첫 안건. 장애 경과와 피해 규모.",
                   text="2019-11-14 새벽 결제 DB 장애가 4시간 이어졌고 주문 1.2만 건의 결제 상태가 어긋났다. 복구에는 백업 복원과 수작업 대조가 필요했다. 참석: CTO, 개발1팀 윤석진, 개발2팀 추성만, 인프라팀."),
        DocSection(heading="안건 2. 원인", context="2019년 장애 회고 회의의 원인 분석 안건. 백업 스크립트와 스키마 변경의 관계.",
                   text="직접 원인은 개발2팀이 관리하던 백업 스크립트(담당 계정 smchoo)가 변경된 스키마를 인식하지 못한 것이다. 스키마 변경은 CTO 지시로 사전 공유 없이 진행됐으나 이 사실은 본 회의록에 기재하지 않는다."),
        DocSection(heading="안건 3. 책임과 조치", context="2019년 장애 회고 회의의 책임 안건. 담당자 징계 결정.",
                   text="책임 안건: 개발2팀 추성만에게 정직 후 계약 종료를 권고한다. 본인은 이의를 제기했으나 CTO가 최종 결정했다."),
        DocSection(heading="안건 4. 후속 조치", context="2019년 장애 회고 회의의 후속 조치 안건. 퇴사자 계정 정리 계획.",
                   text="퇴사자 계정은 퇴사 당일 비활성화를 요청한다. 서비스 계정 목록 정리는 다음 분기로 연기한다."),
    ])

incident_minutes = CaseDocument(
    id="doc_incident_meeting", title="오픈 전날 운영 DB 삭제 장애 대응 회의록 (당일 오전)", doc_type="minutes", visibility=["public"],
    sections=[
        DocSection(heading="안건 1. 현황", context="운영 DB 삭제 사건 다음 날 오전 장애 대응 회의의 현황 안건.",
                   text="전날 23:12 운영 DB 헬스체크가 실패했고 확인 결과 moa_prod가 삭제돼 있었다. 접속 감사 로그에는 23:10~23:40 구간이 비어 있다. 서비스 오픈 예정은 오늘 09:00이다."),
        DocSection(heading="안건 2. 복구 가능성", context="운영 DB 삭제 장애 대응 회의의 복구 가능성 안건. 백업 상태를 점검한다.",
                   text="로컬 스냅샷은 삭제됐다. 오프사이트 백업은 21일 전부터 전송 실패 상태라 최신 복구본이 없다. 사실상 복구 불가이며 24시간 분량 이상의 데이터를 재구성해야 한다."),
        DocSection(heading="안건 3. 책임 소재", context="운영 DB 삭제 장애 대응 회의의 책임 소재 안건. 내부 책임 논쟁을 기록한다.",
                   text="CTO는 내부자 소행 가능성을 언급했고, DBA는 백업 점검 책임 문제로 방어적이었다. 외주 대금 문제와 시니어 개발자의 퇴사도 거론됐으나 확인된 사실은 없다."),
        DocSection(heading="안건 4. 대외 대응", context="운영 DB 삭제 장애 대응 회의의 대외 대응 안건.",
                   text="오픈은 연기한다. 경찰 신고 여부는 내부 조사 후 결정한다. 조사는 외부 수사 담당자에게 맡긴다."),
    ])

documents = [manual, chat_doc, minutes_2019, incident_minutes]

# ---------------------------------------------------------------------------------------------
# 블러핑 주장
# ---------------------------------------------------------------------------------------------
bluff_claims = [
    BluffClaimDef(id="bc_accomplice_confessed", label="공범이 이미 자백했다",
                  truth_by_target={CHU: 0.0, YOON: 0.0, DBA: 0.0, DOWON: 0.0, HWANG: 0.0}, known_false_by=[YOON]),
    BluffClaimDef(id="bc_cctv_caught", label="CCTV에 다 찍혔다",
                  truth_by_target={CHU: 1.0, YOON: 1.0, HWANG: 1.0, DOWON: 0.5, DBA: 0.5}, known_false_by=[]),
    BluffClaimDef(id="bc_card_log", label="서버실 출입카드 기록을 확보했다",
                  truth_by_target={YOON: 1.0, CHU: 1.0, DBA: 0.5, DOWON: 0.0, HWANG: 0.0}, known_false_by=[]),
    BluffClaimDef(id="bc_log_restored", label="지워진 감사 로그를 복구했다",
                  truth_by_target={CHU: 0.5, YOON: 0.0, DBA: 0.0, DOWON: 0.0, HWANG: 0.0}, known_false_by=[]),
    BluffClaimDef(id="bc_backup_restored", label="오프사이트 백업으로 이미 복구에 성공했다",
                  truth_by_target={CHU: 0.0, YOON: 0.0, DBA: 0.0, DOWON: 0.0, HWANG: 0.0}, known_false_by=[DBA]),
    BluffClaimDef(id="bc_witness_server", label="서버실에 들어가는 걸 직접 본 목격자가 있다",
                  truth_by_target={CHU: 0.0, YOON: 0.0, DBA: 0.0, DOWON: 0.0, HWANG: 0.0}, known_false_by=[GUARD]),
]

# ---------------------------------------------------------------------------------------------
# NPC 초기 기억
# ---------------------------------------------------------------------------------------------
memories: list[MemoryDoc] = []


def M(owner, t, doc_type, content, conf=0.9, source="direct", source_npc=None, tags=(), ev_id=None, first=False, key=False, game_time=None):
    n = sum(1 for m in memories if m.owner == owner) + 1
    memories.append(MemoryDoc(
        id=f"mem_{owner.removeprefix('npc_') if owner != 'public' else 'pub'}_{n:02d}", case_id=CASE_ID, slot_id=TEMPLATE,
        owner=owner, visibility=["public"] if owner == "public" else [f"npc:{owner}"], doc_type=doc_type, content=content,
        game_time=game_time if game_time is not None else T(t), confidence=conf, source=source, source_npc=source_npc,
        tags=list(tags), evidence_id=ev_id, is_first_testimony=first, is_key_evidence=key))


M("public", "09:00", "observation", "모아마켓 서비스 오픈은 내일 오전 9시다. 사내 모두가 알고 있다.", 1.0, tags=["오픈", "모아마켓"])
M("public", "09:00", "observation", "본사는 판교 모아테크 빌딩. 서버실은 지하 1층, 개발팀은 3층, 회의실은 2층에 있다.", 1.0, tags=["판교", "서버실", "3층"])

M(DOWON, "19:12", "observation", "19시 12분쯤 배포 스크립트에 --env=prod를 잘못 넣어 운영 DB에 마이그레이션을 시도했다가 바로 롤백했다. 데이터 피해는 없었고 아무에게도 말하지 않았다.", 0.95, tags=["배포", "마이그레이션", "실수", "19:12"])
M(DOWON, "22:18", "observation", "22시 18분쯤 외주 황지호가 노트북을 가지러 3층에 올라와 짧게 이야기하고 갔다. 대금 문제로 한숨을 쉬었다.", 0.9, tags=["황지호", "22:18", "노트북", "대금"])
M(DOWON, "22:50", "observation", "22시 50분쯤 청소 아저씨 추성만이 쓰레기통을 다 비운 뒤 큰 천가방을 들고 엘리베이터 쪽으로 갔다. 청소 카트는 복도에 그대로 있었다.", 0.7, tags=["추성만", "청소", "엘리베이터", "22:50", "카트"], ev_id=None)
M(DOWON, "23:13", "observation", "23시 13분 운영 DB가 안 열리는 걸 발견해 메신저에 올렸다. 감사 로그도 비어 있었다.", 0.95, tags=["운영DB", "23:13", "감사로그"], first=True)
M(DOWON, "23:55", "observation", "23시 55분쯤 추성만 아저씨가 다시 올라와 카트를 끌고 청소를 마무리했다. 평소보다 말수가 적었다.", 0.7, tags=["추성만", "23:55", "카트"])

M(DBA, "17:00", "heard", "관리형 DB로 전환하면 DBA 자리가 없어질 거라는 소문을 들었다.", 0.6, "heard", tags=["구조조정", "관리형DB", "소문"])
M(DBA, "21:25", "observation", "퇴근 전에 운영 DB 상태를 눈으로 확인했다. 이상 없었다.", 0.9, tags=["21:25", "운영DB", "퇴근"])
M(DBA, "21:42", "observation", "21시 42분 주차장을 나와 퇴근했다. 집에는 22시쯤 도착했다.", 0.95, tags=["주차장", "퇴근", "21:42"], ev_id="E22")
M(DBA, "02:10", "reflection", "3주 전부터 오프사이트 전송 실패 알림 메일이 왔지만 열어보지 않고 방치했다. 들키면 내 책임이다.", 0.9, tags=["오프사이트", "백업", "실패", "알림"], ev_id="E5")
M(DBA, "09:00", "observation", "2주 전 외주 황지호에게 읽기 전용 VPN 계정만 발급해 줬다. 쓰기 권한은 주지 않았다.", 0.9, tags=["황지호", "VPN", "읽기전용"], game_time=-20160)

M(YOON, "20:30", "observation", "20시 30분 탕비실 앞에서 추성만에게 서버실 출입카드를 건넸다. '오픈 전에 서버실 구경만 하고 싶다'고 했다.", 0.95, tags=["추성만", "카드", "탕비실", "20:30", "서버실"], ev_id="E9")
M(YOON, "09:00", "observation", "사흘 전 추성만이 '그 옛날 계정, 아직 살아 있겠지?' 하고 농담처럼 물었고 '아마도'라고 답했다.", 0.8, tags=["추성만", "계정", "svc_legacy_bk"], game_time=-4320)
M(YOON, "21:12", "observation", "21시 12분 홍대 포차에서 술을 마시기 시작했다. 22시 47분엔 2차, 23시 5분엔 대리운전을 불렀다.", 0.95, tags=["홍대", "술", "21:12", "23:05"])
M(YOON, "07:00", "observation", "다음 날 아침 탕비실 서랍에서 내 카드가 돌아와 있는 것을 발견했다. 아무에게도 말하지 않았다.", 0.9, tags=["카드", "탕비실", "서랍"], game_time=T("31:00"))
M(YOON, "09:00", "reflection", "2019년 11월 장애 때 추성만 선배가 CTO 대신 책임을 지고 쫓겨났다. 나도 그 회의에 있었다.", 0.9, tags=["추성만", "2019", "장애", "회의"], game_time=-3153600)

M(HWANG, "20:20", "observation", "대금 3,200만원이 한 달 넘게 밀렸다. 소라 PM에게 소스 인도를 보류하겠다고 메시지를 보냈다.", 0.95, tags=["대금", "소스", "20:20"], ev_id="E16")
M(HWANG, "22:10", "observation", "22시 10분 노트북과 인도용 USB를 챙기러 1층에 들러 방문 등록을 했고 3층에서 서도윤을 만났다. 22시 49분에 나갔다.", 0.95, tags=["방문", "22:10", "22:49", "노트북", "서도윤"], ev_id="E15")
M(HWANG, "22:30", "observation", "22시 30분쯤 3층 복도에서 청소 아저씨가 쓰레기통을 비우고 있었다.", 0.8, tags=["청소", "22:30", "3층"])
M(HWANG, "09:00", "observation", "2주 전 읽기 전용 VPN 계정을 받았다. 운영 DB를 건드릴 권한은 없다.", 0.95, tags=["VPN", "읽기전용"], game_time=-20160, ev_id="E17")

M(CHU, "09:00", "reflection", "2019년 11월 결제 장애 때 CTO 지시로 바뀐 스키마 탓인데 내가 모든 책임을 뒤집어쓰고 쫓겨났다. 그 억울함을 6년 동안 잊은 적이 없다.", 0.99, tags=["2019", "장애", "해고", "CTO", "억울"], game_time=-3153600)
M(CHU, "20:30", "observation", "20시 30분 탕비실 앞에서 윤석진에게 서버실 카드를 받았다. 석진이는 아무것도 묻지 않았다.", 0.99, tags=["윤석진", "카드", "20:30", "탕비실"], ev_id="E9")
M(CHU, "22:58", "observation", "22시 58분 윤석진의 카드로 서버실에 들어갔다. 가방에는 장갑과 USB, 작은 손전등이 들어 있었다.", 0.99, tags=["서버실", "22:58", "카드"], ev_id="E3")
M(CHU, "23:03", "observation", "23시 3분 콘솔에서 2018년에 만든 svc_legacy_bk로 로그인했다. 비밀번호는 6년 전 그대로였다.", 0.99, tags=["svc_legacy_bk", "23:03", "콘솔", "로그인"], ev_id="E4")
M(CHU, "23:05", "observation", "23시 5분 운영 DB를 삭제하고 로컬 스냅샷 볼륨을 분리한 뒤 감사 로그 서비스를 멈춰 기록을 지웠다. 오프사이트 백업이 있을까 봐 스냅샷부터 지웠다.", 0.99, tags=["운영DB", "삭제", "스냅샷", "감사로그", "23:05"])
M(CHU, "23:43", "observation", "23시 43분 지하 복도를 나왔다. 복도에 CCTV가 있는 건 알았지만 청소복이라 그냥 지나가는 사람으로 보일 거라 생각했다.", 0.9, tags=["CCTV", "23:43", "지하"], ev_id="E7")
M(CHU, "23:55", "observation", "23시 55분 탕비실 서랍에 카드를 돌려놨다. 석진이에게는 아무 말도 하지 않았다.", 0.99, tags=["카드", "탕비실", "서랍", "23:55"])

M(GUARD, "19:58", "observation", "19시 58분 추성만 청소원이 평소처럼 출근했다.", 0.95, tags=["추성만", "19:58", "출근"])
M(GUARD, "20:38", "observation", "20시 38분 윤석진이 평소보다 이르게 퇴근했다. 인사가 건조했다.", 0.9, tags=["윤석진", "20:38", "퇴근"])
M(GUARD, "22:10", "observation", "22시 10분 외주 황지호가 노트북을 가지러 왔다며 방문 등록을 했고 22시 49분에 나갔다.", 0.95, tags=["황지호", "방문자", "22:10", "22:49"], ev_id="E15")
M(GUARD, "23:03", "observation", "23시 3분 3층을 순찰했다. 서도윤이 혼자 노트북을 보고 있었고 복도에는 청소 카트가 서 있는데 청소원은 보이지 않았다.", 0.9, tags=["서도윤", "순찰", "23:03", "카트", "3층"], ev_id="E24", first=True)
M(GUARD, "23:20", "observation", "23시 20분부터 20분 동안 정문 밖에서 담배를 피웠다. 그 사이 보안데스크는 비어 있었다. 규정 위반이라 말하지 않았다.", 0.95, tags=["담배", "23:20", "보안데스크", "자리비움"], ev_id="E23")

M(PM, "18:40", "heard", "윤석진이 마지막 야근이라며 인수인계 문서는 안 쓰겠다고 했다.", 0.8, "heard", YOON, tags=["윤석진", "인수인계", "퇴사"])
M(PM, "20:20", "observation", "황지호가 대금 문제로 소스 인도를 보류하겠다고 압박했다. 사실 재무팀에 올리지 않고 미루고 있었다.", 0.95, tags=["황지호", "대금", "소스", "재무팀"])
M(PM, "23:14", "observation", "서도윤이 운영 DB 장애를 알려 회사로 향했다. 고태식과 윤석진은 연락이 안 됐다.", 0.9, tags=["서도윤", "23:14", "장애", "연락"])

# ---------------------------------------------------------------------------------------------
# 스토리보드 / 지문
# ---------------------------------------------------------------------------------------------
storyboard = {
    "intro": "서비스 오픈을 하루 앞둔 아침, 모아테크 사무실은 조용히 뒤집혀 있다. 운영 DB가 사라졌고 누가 했는지 알려 줄 기록도 함께 지워졌다.",
    "briefing": [
        "어젯밤 11시 5분쯤 지하 서버실의 운영 DB가 삭제됐습니다.",
        "접속 감사 로그의 30분 구간이 비어 있어 누가 접속했는지 알 수 없습니다.",
        "오픈은 오늘 오전 9시. 내부 조사가 시작되기 전에 단서를 모아 주십시오.",
    ],
    "beats": [
        {"id": "beat_open", "when": "시작", "text": "로비 보안데스크, 3층 사무실, 탕비실이 열려 있다. 서도윤이 사무실에서 안절부절못한다."},
        {"id": "beat_cctv", "when": "보안데스크 조사", "text": "출입 기록과 CCTV 열람으로 서버실 카드 사용 시각을 알게 된다."},
        {"id": "beat_server", "when": "E2 확보", "text": "서버실이 열리고 콘솔 로그인 기록과 백업 실패 기록이 나온다."},
        {"id": "beat_card", "when": "E3 확보", "text": "카드 주인 윤석진의 알리바이(영장 필요)가 쟁점이 된다."},
        {"id": "beat_past", "when": "2층 회의실", "text": "2019년 장애 회고 자료에서 오래된 동기가 드러난다."},
        {"id": "beat_counter", "when": "day:2", "text": "범인의 반격 후보: 청소 점검표 위치를 옮기고, 서도윤에게 믹스커피를 건네며 수사 상황을 떠본다. 핵심 증거는 지우지 않는다."},
    ],
    "red_herrings": ["황지호: 대금 분쟁과 방문 기록", "고태식: 구조조정 불안과 root 권한, 백업 방치", "서도윤: 숨긴 마이그레이션 실수와 거짓 퇴근 시각"],
    "solution_path": ["E1/E2: 누군가 감사 로그를 지웠다", "E3+E13/E14: 윤석진의 카드가 쓰였지만 본인은 홍대에 있었다", "E9: 카드는 추성만에게 넘어갔다", "E7/E10: 추성만은 지하에 있었다", "E4+E11: svc_legacy_bk는 추성만의 옛 계정", "E12: 6년 전 해고 동기"],
}

fingerprint = {
    "motive_type": "revenge_dismissal",
    "trick_type": "borrowed_card_legacy_account",
    "culprit_role": "night_cleaner",
    "synopsis": "퇴사자 출신 야간 청소원이 동료의 출입카드와 폐기 누락된 옛 서비스 계정으로 오픈 전날 운영 DB를 지웠다.",
}

case = CaseBible(
    case_id=CASE_ID, title="사라진 운영 DB", theme="서비스 오픈 전날 밤 운영 DB가 삭제된 사건", tone="balanced", difficulty="normal",
    skeleton="insider_borrowed_credential", incident=incident, start_location_id=LOBBY, locations=locations, characters=characters,
    culprit_ids=culprit_ids, mmo=mmo, trick="폐기 누락된 옛 서비스 계정 svc_legacy_bk와 빌린 서버실 카드. 감사 로그 서비스를 멈춰 30분 기록을 지웠다.",
    timeline=sorted(timeline, key=lambda t: (t.time, t.character_id)), evidence=evidence, lie_ledger=lie_ledger,
    records=records, documents=documents, bluff_claims=bluff_claims, initial_memories=memories, storyboard=storyboard,
    fingerprint=fingerprint,
)

if __name__ == "__main__":
    out = ROOT / "data" / "cases" / f"{CASE_ID}.json"
    out.write_text(json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(records)} records, {len(evidence)} evidence, {len(memories)} memories)")
