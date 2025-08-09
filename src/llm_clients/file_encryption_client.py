"""
서버 저장 전 '파일 암호화 여부' 정적 분석
- 이러닝 시스템 관리자의 관점에서 업로드 처리 코드가 디스크에 쓰기 전에
  실제로 콘텐츠 암호화를 수행하는지 판단
- 1차: LLM(JSON 포맷 응답)
- 실패/타임아웃 시: 휴리스틱(정규식) 폴백
"""
from __future__ import annotations

import json
import re
import typing as t

from .base_client import (
    shrink_code,
    build_prompt,
    generate_json_with_timeout,
    regex_hits,
)

# -----------------------------------------------------------------------------
# LLM 템플릿 (이 모듈 전용)
# -----------------------------------------------------------------------------
PROMPT = """
You are a security code auditor. Analyze the backend upload handler code.

Return ONLY a compact JSON with this exact schema (no extra text):
{
  "encrypted": true|false,
  "reason": "one short sentence in Korean",
  "evidence": [{"line": <int>, "text": "<trimmed code line>"}]
}

Rules:
- "encrypted" must be true if the file content is encrypted BEFORE writing to disk (e.g., AES-GCM, Fernet, NaCl SecretBox).
- If not, set false.
- evidence: 1~3 minimal lines that directly prove your decision (cipher creation, key/nonce, encrypt() call, write/save without encryption, etc.).
- Keep 'text' as actual code lines from input (trimmed).
- Be strict: base64 인코딩, gzip, 단순 해시만으로는 '암호화'가 아님.
""".strip()

# -----------------------------------------------------------------------------
# 휴리스틱(폴백) 패턴
#  - ENC_PATTERNS: 실제 콘텐츠 암호화 정황
#  - PLAIN_PATTERNS: 암호화 없이 저장/쓰기 정황
# -----------------------------------------------------------------------------
ENC_PATTERNS: tuple[str, ...] = (
    # cryptography (Fernet)
    r"from\s+cryptography\.fernet\s+import\s+Fernet",
    r"\bFernet\(",
    r"\.encrypt\(",
    # cryptography (low-level ciphers)
    r"from\s+cryptography\.hazmat\.primitives\.ciphers\s+import\s+Cipher",
    r"\bCipher\(",
    r"modes\.(GCM|CBC|CTR|CFB|OFB)\(",
    r"algorithms\.(AES|ChaCha20)\(",
    r"\.encryptor\(",
    r"\.update\(",
    r"\.finalize\(",
    # PyCryptodome
    r"from\s+Crypto\.Cipher\s+import\s+(AES|ChaCha20)",
    r"AES\.new\(",
    r"ChaCha20\.new\(",
    r"cipher\.encrypt\(",
    # NaCl / PyNaCl
    r"from\s+nacl\.secret\s+import\s+SecretBox",
    r"\bSecretBox\(",
    r"\.encrypt\(",
)

PLAIN_PATTERNS: tuple[str, ...] = (
    # Flask/Werkzeug
    r"\bfile\.save\(",
    # Generic write
    r"open\(.+,\s*[\"']wb?[\"']\)",
    r"\.write\(",
    # pathlib
    r"\.write_bytes\(",
    # 흔한 경로 결합
    r"os\.path\.join\(.+file\.filename",
    r"pathlib\.Path\(.+\)\.with_name\(",
)

NON_ENC_BUT_CONFUSING: tuple[str, ...] = (
    r"base64\.",            # 단순 인코딩
    r"gzip\.open\(",        # 압축
    r"hashlib\.(sha|md5)",  # 해시
)

# -----------------------------------------------------------------------------
# 휴리스틱 판정
# -----------------------------------------------------------------------------
def _heuristic_encryption_detection(code: str) -> dict:
    hits_enc = regex_hits(code, ENC_PATTERNS)
    hits_plain = regex_hits(code, PLAIN_PATTERNS)
    # 인코딩/압축/해시만 있는 경우는 암호화로 보지 않음
    confusing = regex_hits(code, NON_ENC_BUT_CONFUSING)

    if hits_enc:
        # 암호화 API 사용 흔적이 있으면 'true'로 가정
        return {
            "encrypted": True,
            "reason": "암호화 라이브러리 및 encrypt 경로 사용 흔적 발견",
            "evidence": hits_enc[:3],
        }
    if hits_plain:
        return {
            "encrypted": False,
            "reason": "암호화 없이 파일을 그대로 저장/쓰기 하는 코드 발견",
            "evidence": hits_plain[:3],
        }
    if confusing:
        return {
            "encrypted": False,
            "reason": "인코딩/압축/해시만 발견되며 암호화 근거는 없음",
            "evidence": confusing[:3],
        }
    return {
        "encrypted": False,
        "reason": "암호화 여부를 판단할 근거가 부족함",
        "evidence": [],
    }

# -----------------------------------------------------------------------------
# 공개 API
# -----------------------------------------------------------------------------
def analyze_code_for_encryption(code: str) -> dict:
    """
    업로드 처리 코드가 '디스크에 쓰기 전' 실제 암호화를 수행하는지 판단.

    Returns
    -------
    dict: {
      "encrypted": bool,
      "reason": str,
      "evidence": [{"line": int, "text": str}, ...] (최대 3개)
    }
    """
    # 1) 입력 슬리밍: 암호화/저장 관련 키워드 주변만 추출해 토큰수 절감
    slim = shrink_code(code)

    # 2) LLM 호출
    prompt = build_prompt(PROMPT, code_block=slim, suffix="JSON:")
    obj = generate_json_with_timeout(prompt, max_new_tokens=48, timeout_sec=6.0)

    # 3) LLM 실패/타임아웃 → 휴리스틱 폴백
    if not obj:
        return _heuristic_encryption_detection(code)

    # 4) JSON 파싱 및 필드 정리
    try:
        data = json.loads(obj)
        enc = bool(data.get("encrypted", False))
        reason = (data.get("reason") or "").strip() or (
            "암호화 적용으로 판단" if enc else "암호화 미적용으로 판단"
        )
        ev_raw: t.List[dict] = data.get("evidence", []) or []
        evidence: list[dict] = []
        for e in ev_raw[:3]:
            try:
                evidence.append(
                    {"line": int(e.get("line")), "text": str(e.get("text", ""))[:160]}
                )
            except Exception:
                continue
        return {"encrypted": enc, "reason": reason, "evidence": evidence}
    except Exception:
        # 모델이 JSON을 어긋나게 주면 안전하게 폴백
        return _heuristic_encryption_detection(code)

# -----------------------------------------------------------------------------
# (선택) 사람이 읽기 쉬운 포맷으로 변환
#  - 드라이버에서 바로 사용하지 않는다면 생략 가능
# -----------------------------------------------------------------------------
def to_human_readable(result: dict) -> str:
    enc = result.get("encrypted")
    reason = result.get("reason", "")
    lines = [ "[파일 암호화 정적 분석 결과]" ]
    lines.append(f"- 파일 암호화 {'됨' if enc else '되지 않음'}")
    if reason:
        lines.append(f"- 근거: {reason}")
    ev = result.get("evidence") or []
    for i, e in enumerate(ev, 1):
        lines.append(f"  L{e.get('line')}: {e.get('text')}")
    return "\n".join(lines)