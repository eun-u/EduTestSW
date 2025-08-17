"""
========== 시험 및 평가 설계 Test Design ==========

| 출제기준 | Blueprint |
- blueprint_presence :     출제 기준 필드 존재/최소 길이 확인

| 난이도 | Difficulty |
- difficulty_balance :     난이도 분포 적정성(쏠림/엔트로피) 검사 + 휴리스틱 추정 (SKELETON, LLM 훅 선택적)

| 정합성 | Alignment |
- objective_type_alignment : 평가목표-문항유형 정합성 검사 (SKELETON, LLM 훅 선택적)

| 채점기준 | Rubric |
- rubric_quality :         주관식/서술형 채점 기준 존재/간단 품질 룰 검사

| 자동 채점 | AutoGrading |
- autograde_accuracy :     객관식/단답형/서술형 자동 채점 정확도 측정(간단 유사도)

+ print_test_result : 점검 결과 요약 출력
====================================
"""
# ---------------------------------------------------------------------
# 모듈 임포트
# ---------------------------------------------------------------------
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter, defaultdict
import math, re

try:
    # 선택: LLM 보조 사용 (없어도 전체 Rule은 동작)
    from src.llm_clients.test_design_client import (
        llm_estimate_difficulty,
        llm_summarize_objective_type,
    )
except Exception:  # pragma: no cover
    llm_estimate_difficulty = lambda stem, **kw: None           # type: ignore
    llm_summarize_objective_type = lambda stem, **kw: {}        # type: ignore
    
    
# ---------------------------------------------------------------------
# 엔트리 포인트: 시험/평가 설계 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    assessment_type = step.get("type")
    
    if assessment_type == "blueprint_presence":
        return blueprint_presence(step)
    
    elif assessment_type == "difficulty_balance":
        return difficulty_balance(step)
    
    elif assessment_type == "objective_type_alignment":
        return objective_type_alignment(step)
    
    elif assessment_type == "rubric_quality":
        return rubric_quality(step)
    
    elif assessment_type == "autograde_accuracy":
        return autograde_accuracy(step)
    
    elif assessment_type == "run_all":
        results = [
            blueprint_presence(step),
            difficulty_balance(step),
            objective_type_alignment(step),
            rubric_quality(step),
        ]
        if "autograde_dataset" in step:
            results.append(autograde_accuracy(step))

        final = "pass"
        if any(r["status"] == "fail" for r in results):
            final = "fail"
        elif any(r["status"] == "warn" for r in results):
            final = "warn"

        out = {"module": "test_design", "status": final, "results": results}
        # 표준 출력 요약(선택)
        print_test_result(out)
        return out
    else:
        raise ValueError(f"[TEST_DESIGN] 알 수 없는 검사 유형: {assessment_type}")
    
    
# ---------------------------------------------------------------------
# 공용 유틸
# ---------------------------------------------------------------------
WORD_RE = re.compile(r"[ㄱ-ㅎ가-힣A-Za-z0-9]+")

def sk_print(name: str, msg: str = ""):
    print(f"[TEST_DESIGN][SKELETON] {name}: {msg or '미구현(placeholder)'}")

def print_result(name: str, ok: bool, reason: str = ""):
    status = "PASS" if ok else "FAIL"
    if reason:
        print(f"[TEST_DESIGN] {name:28s} [{status}] {reason}")
    else:
        print(f"[TEST_DESIGN] {name:28s} [{status}]")


def print_test_result(result: Dict[str, Any]):
    """
    일관된 PASS/WARN/FAIL와 핵심 지표를 간단 출력
    """
    status = result.get("status", "pass").upper()
    print(f"[TEST_DESIGN] MODULE STATUS: {status}")
    for r in result.get("results", []):
        name = r.get("name")
        st = r.get("status", "pass").upper()
        extras = []
        for k in ("coverage", "align_rate", "entropy_norm", "max_skew"):
            if k in r:
                extras.append(f"{k}={r[k]}")
        for k in ("accuracy",):
            if k in r:
                extras.append(f"{k}={r[k]}")
        extra_s = f" ({', '.join(extras)})" if extras else ""
        print(f"  - {name:24s} [{st}]{extra_s}")

def brief_explain(res: Dict[str, Any]) -> str:
    name = res.get("name")
    st = res.get("status")
    if name == "blueprint_presence":
        fail = res.get("fail", 0)
        warn = res.get("warn", 0)
        if st == "pass":
            return "모든 문항에 충분한 출제기준이 기재되었습니다."
        parts = []
        if fail: parts.append(f"누락 {fail}건")
        if warn: parts.append(f"길이부족 {warn}건")
        return "출제기준 보완 필요 (" + ", ".join(parts) + ")."

    elif name == "difficulty_balance":
        issues = res.get("issues") or []
        skew_issue = next((i for i in issues if i.get("issue") == "SKEW_HIGH"), None)
        if st == "pass":
            return "난이도 분포가 균형적입니다."
        if skew_issue:
            return f"{skew_issue.get('top_label')} 난이도가 {skew_issue.get('skew')}로 치우쳤습니다."
        return "난이도 라벨 누락 항목이 있어 확인이 필요합니다."

    elif name == "objective_type_alignment":
        if st == "pass":
            return "평가목표와 문항유형의 매핑이 적절합니다."
        return f"허용되지 않는 유형 매핑 {res.get('bad', 0)}건이 확인되었습니다."

    elif name == "rubric_quality":
        if st == "pass":
            return "주관식/서술형의 채점기준이 구체적입니다."
        weak = sum(1 for d in (res.get("details") or []) if d.get("issue") == "RUBRIC_WEAK")
        missing = sum(1 for d in (res.get("details") or []) if d.get("issue") == "MISSING_RUBRIC")
        parts = []
        if weak: parts.append(f"모호 {weak}건")
        if missing: parts.append(f"누락 {missing}건")
        return "채점기준 보완 필요 (" + (", ".join(parts) or "세부 기준 점검") + ")."

    elif name == "autograde_accuracy":
        acc = res.get("accuracy", {})
        bad_types = [
            k for k, v in acc.items()
            if (k == "객관식" and v < 0.95) or (k in ("단답형", "서술형") and v < 0.80)
        ]
        if not bad_types:
            return "자동 채점 정확도가 기준 이상입니다."
        return "정확도 기준 미달: " + ", ".join(f"{t} {acc.get(t):.3f}" for t in bad_types)

    return ""

def print_step_result(res: Dict[str, Any]) -> None:
    """각 함수 내부에서 즉시 호출되는 단일 스텝 요약 출력기 + 짧은 설명."""
    name = res.get("name", "(unknown)")
    st = res.get("status", "pass").upper()
    line = f"[TEST_DESIGN][STEP] {name:24s} [{st}]"

    # 공통 메트릭 추가
    if "coverage" in res:
        line += f" coverage={res['coverage']}"
    if "entropy_norm" in res:
        line += f" entropy_norm={res['entropy_norm']}"
    if "max_skew" in res:
        line += f" max_skew={res['max_skew']}"
    if "align_rate" in res:
        line += f" align_rate={res['align_rate']}"
    if "accuracy" in res:
        line += f" accuracy={res['accuracy']}"

    print(line)

    # 대표 이슈/디테일 샘플
    if "details" in res and res["details"]:
        print(f"    details(sample): {res['details'][:3]}")
    if "issues" in res and res["issues"]:
        print(f"    issues(sample): {res['issues'][:3]}")
    if "mismatches" in res and res["mismatches"]:
        print(f"    mismatches(sample): {res['mismatches'][:3]}")

    # 한 줄 설명
    note = brief_explain(res)
    if note:
        print(f"    note: {note}")
        print()


def tokenize(text: str) -> List[str]:
    return WORD_RE.findall((text or "").lower())

def ngram_chars(text: str, n: int = 3) -> List[str]:
    s = (text or "").strip().lower()
    return [s[i:i+n] for i in range(max(0, len(s)-n+1))]

def jaccard_char_ngrams(a: str, b: str, n: int = 3) -> float:
    A, B = set(ngram_chars(a, n)), set(ngram_chars(b, n))
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def as_list(v):
    if v is None: return []
    if isinstance(v, list): return v
    return [v]

def field_present(item: Dict[str, Any], keys: List[str]) -> Tuple[bool, Optional[str]]:
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return True, k
    return False, None

def get(obj: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in obj:
            return obj[k]
    return None


# ---------------------------------------------------------------------
# 시험 및 평가 설계: 출제 기준 존재/형식 점검
# ---------------------------------------------------------------------
def blueprint_presence(step: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = step.get("items", [])
    min_len: int = int(step.get("min_blueprint_len", 10))

    ok, warn, fail = 0, 0, 0
    details = []
    for q in items:
        present, key = field_present(q, ["출제기준", "blueprint", "기준", "standard"])
        if not present:
            fail += 1
            details.append({"id": q.get("id"), "issue": "MISSING_BLUEPRINT"})
            continue
        text = str(q.get(key, "")).strip()
        if len(text) < min_len:
            warn += 1
            details.append({"id": q.get("id"), "issue": "BLUEPRINT_TOO_SHORT", "len": len(text)})
        else:
            ok += 1
    coverage = round(ok / max(1, len(items)), 3)
    status = "pass" if fail == 0 and warn == 0 else ("warn" if fail == 0 else "fail")
    res = {"name": "blueprint_presence", "status": status, "coverage": coverage, "ok": ok, "warn": warn, "fail": fail, "details": details[:30]}
    print_step_result(res)
    return res


# ---------------------------------------------------------------------
# 시험 및 평가 설계: 난이도 분포 적절성
# ---------------------------------------------------------------------
def difficulty_rule_guess(q: Dict[str, Any]) -> str:
    stem = str(q.get("stem") or q.get("question") or "")
    options = as_list(q.get("options"))
    has_equation = bool(re.search(r"[=+\-*/^]|∑|√|integral|미분|적분", stem))
    tokens = tokenize(stem)
    opt_count = len(options)

    score = 0
    score += (len(tokens) // 10)          # 길이 10단어당 +1
    score += 1 if has_equation else 0     # 수식 포함 +1
    score += 1 if opt_count >= 5 else 0
    score += 1 if re.search(r"옳(은|지).*모두|다(고|인) 것", stem) else 0
    if score >= 3: return "Hard"
    if score == 2: return "Medium"
    return "Easy"

def normalized_entropy(counts: Dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0 or len(counts) <= 1:
        return 0.0
    H = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            H -= p * math.log(p + 1e-12)
    return H / math.log(len(counts))

def difficulty_balance(step: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = step.get("items", [])
    max_skew: float = float(step.get("max_skew", 0.70))
    use_llm: bool = bool(step.get("use_llm", False))

    counts: Counter = Counter()
    missing_ids = []

    for q in items:
        diff = get(q, ["difficulty", "난이도"])
        if not diff:
            # 1) Rule 추정
            diff = difficulty_rule_guess(q)
            # 2) (선택) LLM 보정
            if use_llm:
                try:
                    llm_pred = llm_estimate_difficulty(q.get("stem") or q.get("question") or "")
                    if llm_pred in ("Easy", "Medium", "Hard"):
                        diff = llm_pred
                except Exception:
                    pass
        if not diff:
            missing_ids.append(q.get("id"))
        else:
            label = str(diff).strip().capitalize()
            counts[label] += 1

    total_labeled = sum(counts.values())
    top_label, skew = None, 0.0
    if total_labeled > 0:
        top_label, top_count = counts.most_common(1)[0]
        skew = top_count / total_labeled
    ent = round(normalized_entropy(counts), 3)

    status = "pass"
    issues = []
    if skew >= max_skew:
        status = "warn"
        issues.append({"issue": "SKEW_HIGH", "top_label": top_label, "skew": round(skew, 3)})
    if missing_ids:
        if status == "pass":
            status = "warn"
        issues.append({"issue": "MISSING_DIFFICULTY", "count": len(missing_ids), "ids": missing_ids[:10]})

    res = {
        "name": "difficulty_balance",
        "status": status,
        "counts": dict(counts),
        "entropy_norm": ent,
        "max_skew": round(skew, 3),
        "issues": issues
    }
    print_step_result(res)
    return res


# ---------------------------------------------------------------------
# 시험 및 평가 설계: 평가목표-문항유형 정합성
# ---------------------------------------------------------------------
def allowed_types_for_objective() -> Dict[str, List[str]]:
    return {
        "지식": ["객관식", "단답형"],
        "이해": ["객관식", "단답형", "서술형"],
        "적용": ["서술형", "사례형", "프로그래밍"],
        "분석": ["서술형", "사례형", "프로젝트"],
        "평가": ["서술형", "프로젝트", "발표"],
        "창안": ["프로젝트", "서술형", "발표"],
    }

def objective_type_alignment(step: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = step.get("items", [])
    use_llm: bool = bool(step.get("use_llm", False))

    mapping = allowed_types_for_objective()
    ok, bad = 0, 0
    mismatches = []

    for q in items:
        obj = get(q, ["목표", "objective"])
        qtype = get(q, ["문항유형", "type"])

        # (선택) 텍스트만 있을 때 LLM으로 요약 추정 (간편 함수 사용)
        if (not obj or not qtype) and use_llm:
            try:
                stem = q.get("stem") or q.get("question") or ""
                pred = llm_summarize_objective_type(stem)
                obj = obj or pred.get("objective")
                qtype = qtype or pred.get("type")
            except Exception:
                pass

        if not obj or not qtype:
            mismatches.append({"id": q.get("id"), "issue": "MISSING_OBJECTIVE_OR_TYPE"})
            continue

        allowed = mapping.get(str(obj).strip())
        if not allowed:
            mismatches.append({"id": q.get("id"), "issue": "UNKNOWN_OBJECTIVE", "objective": obj})
            continue

        if str(qtype).strip() not in allowed:
            bad += 1
            mismatches.append({"id": q.get("id"), "issue": "TYPE_NOT_ALLOWED", "objective": obj, "type": qtype, "allowed": allowed})
        else:
            ok += 1

    total_pairs = ok + bad
    align_rate = round(ok / max(1, total_pairs), 3)
    status = "pass" if bad == 0 else ("warn" if align_rate >= 0.9 else "fail")
    res = {"name": "objective_type_alignment", "status": status, "align_rate": align_rate, "ok": ok, "bad": bad, "mismatches": mismatches[:30]}
    print_step_result(res)
    return res


# ---------------------------------------------------------------------
# 시험 및 평가 설계: 채점 기준(루브릭) 명확성
# ---------------------------------------------------------------------
def rubric_quality(step: Dict[str, Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = step.get("items", [])
    min_len: int = int(step.get("min_rubric_len", 15))
    subjective_types: List[str] = step.get("subjective_types", ["서술형", "단답형", "프로젝트", "발표"])

    ok, warn, fail, applicable = 0, 0, 0, 0
    details = []

    for q in items:
        qtype = get(q, ["문항유형", "type"])
        if qtype not in subjective_types:
            continue
        applicable += 1

        present, key = field_present(q, ["채점기준", "루브릭", "rubric", "scoring_criteria"])
        if not present:
            fail += 1
            details.append({"id": q.get("id"), "issue": "MISSING_RUBRIC"})
            continue

        text = str(q.get(key, "")).strip()
        # 너무 포괄적/모호한 표현 감지(간단 룰)
        weak = (len(text) < min_len) or ("적절히" in text) or ("충분히" in text)
        if weak:
            warn += 1
            details.append({"id": q.get("id"), "issue": "RUBRIC_WEAK", "len": len(text)})
        else:
            ok += 1

    coverage = round(ok / max(1, applicable), 3)
    status = "pass" if fail == 0 and warn == 0 else ("warn" if fail == 0 else "fail")
    res = {"name": "rubric_quality", "status": status, "coverage": coverage, "ok": ok, "warn": warn, "fail": fail, "details": details[:30]}
    print_step_result(res)
    return res


# ---------------------------------------------------------------------
# 시험 및 평가 설계: 자동 채점 정확도
# ---------------------------------------------------------------------
def mcq_exact(a: Any, b: Any) -> bool:
    return str(a).strip() == str(b).strip()


def short_answer_sim(answer: str, gold: str, threshold: float = 0.7) -> bool:
    sim = jaccard_char_ngrams(answer or "", gold or "", n=3)
    return sim >= threshold


def autograde_accuracy(step: Dict[str, Any]) -> Dict[str, Any]:
    dataset: Dict[str, Any] = step.get("autograde_dataset", {})
    thresholds: Dict[str, float] = step.get("thresholds", {"단답형": 0.7, "서술형": 0.5})

    qmap = {str(q["id"]): q for q in dataset.get("questions", []) if "id" in q}
    subs = dataset.get("submissions", [])

    per_type = defaultdict(lambda: {"ok": 0, "total": 0})
    sample_errors = []

    for sub in subs:
        answers = sub.get("answers", {})
        for qid, q in qmap.items():
            qtype = str(q.get("type"))
            gold = str(q.get("gold", ""))
            pred = str(answers.get(qid, ""))

            correct = False
            if qtype == "객관식":
                correct = mcq_exact(pred, gold)
            elif qtype == "단답형":
                correct = short_answer_sim(pred, gold, thresholds.get("단답형", 0.7))
            else:  # 서술형 등
                correct = short_answer_sim(pred, gold, thresholds.get("서술형", 0.5))

            per_type[qtype]["total"] += 1
            if correct:
                per_type[qtype]["ok"] += 1
            else:
                if len(sample_errors) < 10:
                    sample_errors.append({"student_id": sub.get("student_id"), "qid": qid, "gold": gold, "pred": pred, "type": qtype})

    metrics = {t: round(c["ok"] / max(1, c["total"]), 3) for t, c in per_type.items()}

    status = "pass"
    if metrics.get("객관식", 1.0) < 0.95 or metrics.get("단답형", 1.0) < 0.80 or metrics.get("서술형", 1.0) < 0.80:
        status = "warn"

    res = {"name": "autograde_accuracy", "status": status, "accuracy": metrics, "samples": sample_errors}
    print_step_result(res)
    return res
