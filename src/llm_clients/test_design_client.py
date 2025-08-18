"""
시험/평가 설계 보조 LLM 클라이언트

- src/llm_clients/base_client.py의 API를 호출하여 동작
  * build_prompt(template: str, *, code_block: str, suffix: str="JSON:")
  * generate_json_with_timeout(prompt: str, *, max_new_tokens:int=..., timeout_sec:float=..., max_input_tokens:int=...) -> str|None

- 모델 응답 포맷은 '균형 잡힌 JSON'이어야 하며, base_client가 중괄호 균형으로
  조기 종료/추출을 수행한다. (JSON 이외 응답은 None 처리)

- 실패/미설정이어도 assessment_design 모듈은 Rule로 완전 동작하도록
  상위 레벨에서는 None/{} 폴백을 사용한다.
"""
from __future__ import annotations

import json
from typing import Optional, Dict

# 팀 공용 LLM 유틸 (필수)
from .base_client import build_prompt, generate_json_with_timeout


# -------------------------
# 프롬프트 템플릿 (JSON 강제)
# -------------------------
DIFFICULTY_PROMPT_JSON = """
당신은 교육평가 전문가입니다. 아래 문항 본문을 읽고 난이도를 결정하세요.
가능한 값: Easy, Medium, Hard

오직 아래 JSON 스키마로만 출력하세요. 추가 텍스트/설명 금지.
{
  "difficulty": "Easy|Medium|Hard"
}
""".strip()

OBJTYPE_PROMPT_JSON = """
아래 문항의 평가목표와 문항유형을 한 단어로 각각 요약하세요.
- objective: 지식/이해/적용/분석/평가/창안 중 하나
- type: 객관식/단답형/서술형/사례형/프로젝트/발표 중 하나

오직 아래 JSON 스키마로만 출력하세요. 추가 텍스트/설명 금지.
{
  "objective": "지식|이해|적용|분석|평가|창안",
  "type": "객관식|단답형|서술형|사례형|프로젝트|발표"
}
""".strip()

ALLOWED_DIFFICULTY = {"Easy", "Medium", "Hard"}
ALLOWED_OBJECTIVE = {"지식", "이해", "적용", "분석", "평가", "창안"}
ALLOWED_TYPE = {"객관식", "단답형", "서술형", "사례형", "프로젝트", "발표", "프로그래밍"}


def _trim(text: str, limit: int = 2000) -> str:
    """문항 본문이 너무 길 때 토큰 절약용으로 잘라냄."""
    text = (text or "").strip()
    return text if len(text) <= limit else (text[:limit] + " ...")


class TestDesignLLM:
    """
    시험/평가 설계 보조 LLM 클라이언트.
    - base_client의 build_prompt, generate_json_with_timeout을 직접 호출
    - 실패 시 None/{} 반환하여 상위 모듈이 Rule로 폴백 가능
    """

    def __init__(self, *, difficulty_max_new_tokens: int = 24, objtype_max_new_tokens: int = 64):
        self.difficulty_max_new_tokens = int(difficulty_max_new_tokens)
        self.objtype_max_new_tokens = int(objtype_max_new_tokens)

    # -------------------------
    # 내부 공용 호출기
    # -------------------------
    def _ask_json(self, template: str, *, code_block: str, max_new_tokens: int, timeout_sec: float) -> Optional[dict]:
        """
        base_client.build_prompt로 프롬프트를 만들고,
        base_client.generate_json_with_timeout으로 JSON을 받아 dict로 파싱.
        실패 시 None.
        """
        prompt = build_prompt(template, code_block=code_block, suffix="JSON:")
        out = generate_json_with_timeout(prompt, max_new_tokens=max_new_tokens, timeout_sec=timeout_sec)
        if not out:
            return None
        try:
            return json.loads(out)
        except Exception:
            return None

    # -------------------------
    # 퍼블릭 API
    # -------------------------
    def estimate_difficulty(self, stem: str, *, timeout_sec: float = 5.0) -> Optional[str]:
        """
        문항 본문으로 난이도(Easy/Medium/Hard) 추정.
        - JSON 스키마: {"difficulty":"Easy|Medium|Hard"}
        - 실패 시 None (상위에서 Rule 기반 추정으로 폴백)
        """
        data = self._ask_json(
            DIFFICULTY_PROMPT_JSON,
            code_block=_trim(stem),
            max_new_tokens=self.difficulty_max_new_tokens,
            timeout_sec=timeout_sec,
        )
        if not data:
            return None
        val = str(data.get("difficulty", "")).strip()
        return val if val in ALLOWED_DIFFICULTY else None

    def summarize_objective_and_type(self, stem: str, *, timeout_sec: float = 6.0) -> Dict[str, str]:
        """
        문항 본문으로 평가목표/문항유형 요약(JSON).
        - JSON 스키마: {"objective":"...", "type":"..."}
        - 실패 시 빈 dict (상위에서 Rule 또는 누락 처리)
        """
        data = self._ask_json(
            OBJTYPE_PROMPT_JSON,
            code_block=_trim(stem),
            max_new_tokens=self.objtype_max_new_tokens,
            timeout_sec=timeout_sec,
        )
        if not data:
            return {}
        obj = str(data.get("objective", "")).strip()
        typ = str(data.get("type", "")).strip()
        out: Dict[str, str] = {}
        if obj in ALLOWED_OBJECTIVE:
            out["objective"] = obj
        if typ in ALLOWED_TYPE:
            out["type"] = typ
        return out


# -------------------------
# 모듈 레벨 편의 함수
# -------------------------
def llm_estimate_difficulty(stem: str, *, timeout_sec: float = 5.0) -> Optional[str]:
    """
    간편 호출: 난이도 추정 (실패 시 None).
    """
    try:
        client = TestDesignLLM()
        return client.estimate_difficulty(stem, timeout_sec=timeout_sec)
    except Exception:
        return None


def llm_summarize_objective_type(stem: str, *, timeout_sec: float = 6.0) -> Dict[str, str]:
    """
    간편 호출: 목적/유형 요약 (실패 시 {}).
    """
    try:
        client = TestDesignLLM()
        return client.summarize_objective_and_type(stem, timeout_sec=timeout_sec)
    except Exception:
        return {}
