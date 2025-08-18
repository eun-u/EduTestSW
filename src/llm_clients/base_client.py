# llm_clients/base_client.py
"""
공용 LLM 베이스 모듈
- 공통 토크나이즈/생성(타임아웃/조기종료) 유틸
- JSON 추출 도우미
- 코드 슬리밍(핵심 라인만 추출) 유틸

런타임 시 모델은 scripts/preload_model.get_tokenizer_model()을 통해
최초 1회만 로딩되고, 이후에는 모듈 싱글톤을 재사용합니다.
"""
from __future__ import annotations

import os, sys, re, time, threading
import typing as t
import torch
from transformers import StoppingCriteria, StoppingCriteriaList


# ---------------------------------------------------------------------
# 모델/토크나이저 로드 (공용)
# ---------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../scripts"))
sys.path.append(SCRIPTS_DIR)
from scripts.preload_model import get_tokenizer_model  # 싱글톤 반환


# ---------------------------------------------------------------------
# Pad/EOS 보정
# ---------------------------------------------------------------------
def ensure_pad_eos(tokenizer) -> None:
    """토크나이저의 pad/eos 설정을 안전하게 맞춤."""
    if getattr(tokenizer, "eos_token_id", None) is None and getattr(tokenizer, "eos_token", None):
        tokenizer.eos_token_id = tokenizer.convert_tokens_to_ids(tokenizer.eos_token)
    if getattr(tokenizer, "pad_token_id", None) is None:
        tokenizer.pad_token = getattr(tokenizer, "eos_token", None) or "</s>"

# ---------------------------------------------------------------------
# 코드 슬리밍 (키워드 주변 라인만 추출)
# ---------------------------------------------------------------------
DEFAULT_KEY_PAT = re.compile(
    r"(encrypt\(|decrypt\(|Fernet|AES\.new\(|Crypto\.Cipher|file\.save\(|open\(.+['\"]wb?['\"]\)|os\.path\.join)"
)

def shrink_code(code: str, *, key_pattern: re.Pattern = DEFAULT_KEY_PAT,
                max_lines: int = 220, ctx: int = 2) -> str:
    """
    긴 소스에서 '관심 키워드' 주변만 추출해서 토큰 수 절감.
    - key_pattern: 관심 정규식
    - ctx: 매치 라인 기준 앞뒤 문맥 라인 수
    - max_lines: 최대 유지 라인 수
    """
    lines = code.splitlines()
    n = len(lines)
    hits: list[int] = []
    for i, ln in enumerate(lines):
        if key_pattern.search(ln):
            start = max(0, i - ctx)
            end = min(n, i + ctx + 1)
            hits.extend(range(start, end))
    if not hits:
        return "\n".join(lines[:min(n, max_lines)])

    keep = sorted(set(hits))
    if len(keep) > max_lines:
        keep = keep[:max_lines]
    return "\n".join(lines[i] for i in keep)

# ---------------------------------------------------------------------
# 휴리스틱(폴백) 유틸 - 패턴 히트 수집
# ---------------------------------------------------------------------
def regex_hits(code: str, patterns: t.Iterable[str]) -> list[dict]:
    """코드에서 패턴을 찾아 (line, text) 리스트 반환."""
    compiled = [re.compile(p) for p in patterns]
    out: list[dict] = []
    for i, ln in enumerate(code.splitlines(), 1):
        s = ln.strip()
        for cp in compiled:
            if cp.search(ln):
                out.append({"line": i, "text": s[:160]})
                break
    return out

# ---------------------------------------------------------------------
# JSON 조기 종료(중괄호 균형) 스토퍼
# ---------------------------------------------------------------------
class JsonEarlyStop(StoppingCriteria):
    """
    생성 중 중괄호가 열고-닫힘 균형을 0으로 회복하면 즉시 정지.
    timeout_sec 초가 지나도 정지.
    """
    def __init__(self, tok, timeout_sec: float = 6.0):
        self.tok = tok
        self.t0 = time.time()
        self.timeout_sec = float(timeout_sec)
        self.depth = 0
        self.started = False

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        # 시간 초과
        if time.time() - self.t0 > self.timeout_sec:
            return True

        # 마지막 토큰만 디코드하여 중괄호 추적
        last_id = input_ids[0, -1].item()
        piece = self.tok.decode([last_id], skip_special_tokens=True)
        for ch in piece:
            if ch == "{":
                self.depth += 1; self.started = True
            elif ch == "}":
                self.depth -= 1

        # 한 번이라도 시작했고, 균형이 0 이하로 복귀하면 종료
        return self.started and self.depth <= 0

# ---------------------------------------------------------------------
# 생성 텍스트에서 첫 번째 균형 잡힌 JSON만 추출
# ---------------------------------------------------------------------
def extract_first_balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None

# ---------------------------------------------------------------------
# 공용 JSON 생성기
# ---------------------------------------------------------------------
def generate_json_with_timeout(
    prompt: str,
    *,
    max_new_tokens: int = 48,
    timeout_sec: float = 6.0,
    max_input_tokens: int = 1400,
) -> str | None:
    """
    LLM으로 JSON을 생성하되,
    - 중괄호 균형 기반 조기 종료
    - timeout_sec초 경과 시 중단
    실패 시 None 반환
    
    모델/토크나이저는 최초 1회만 실제 로딩되며, 이후에는 모듈 싱글톤을 재사용한다.
    """
    tokenizer, model = get_tokenizer_model(verbose=False)   # <- 여기서 필요 시 최초 1회 로딩
    ensure_pad_eos(tokenizer)

    # 토크나이즈
    print("[LLM] 토크나이즈 시작")
    inputs = tokenizer(
        prompt, return_tensors="pt",
        padding=False, truncation=True, max_length=max_input_tokens
    )
    if "attention_mask" not in inputs:
        inputs["attention_mask"] = torch.ones_like(inputs["input_ids"])
    device = getattr(model, "device", torch.device("cpu"))
    inputs = {k: v.to(device) for k, v in inputs.items()}
    print("[LLM] 토크나이즈 완료")

    # 조기 종료 설정
    stopper = JsonEarlyStop(tokenizer, timeout_sec=timeout_sec)
    stopping = StoppingCriteriaList([stopper])

    # 생성(별도 스레드에서 블로킹 처리)
    print("[LLM] generate 시작")
    torch.set_grad_enabled(False)
    model.eval()

    out_ids = None
    err: dict[str, t.Optional[BaseException]] = {"e": None}

    def _worker():
        nonlocal out_ids
        try:
            with torch.no_grad():
                out_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    max_new_tokens=max_new_tokens,
                    do_sample=False,               # 탐욕(안정/속도)
                    repetition_penalty=1.05,
                    eos_token_id=getattr(tokenizer, "eos_token_id", None),
                    pad_token_id=getattr(tokenizer, "pad_token_id", None),
                    stopping_criteria=stopping,    # 핵심: 조기 종료
                    use_cache=True,                # KV 캐시
                )
        except Exception as e:
            err["e"] = e

    t_thread = threading.Thread(target=_worker, daemon=True)
    t_thread.start()
    t_thread.join(timeout=timeout_sec + 1.0)  # 스토퍼보다 살짝 크게

    if t_thread.is_alive() or err["e"] is not None:
        print("[LLM] 타임아웃/예외 → None 반환")
        return None

    print("[LLM] generate 완료")
    text = tokenizer.decode(out_ids[0], skip_special_tokens=True)

    # 프롬프트 에코 제거
    if text.startswith(prompt):
        text = text[len(prompt):].strip()

    return extract_first_balanced_json(text)

# ---------------------------------------------------------------------
# 프롬프트 결합 유틸
# ---------------------------------------------------------------------
def build_prompt(template: str, *, code_block: str, suffix: str = "JSON:") -> str:
    """
    템플릿 + 코드 블록 결합.
    - template: 지시문/스키마
    - code_block: 코드 또는 데이터
    - suffix: 마지막 토큰(기본: 'JSON:')
    """
    return f"""{template.strip()}

<CODE>
{code_block}
</CODE>
{suffix}
""".strip()
