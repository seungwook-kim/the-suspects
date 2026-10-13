"""사건 생성 (작가 팀): 자유 주제 → 검수를 통과한 사건 원본. 진입점은 generate_case."""

from server.cases.generate.graph import TOTAL_STAGES, STAGE_TEXT, GenResult, generate_case

__all__ = ["generate_case", "GenResult", "TOTAL_STAGES", "STAGE_TEXT"]
