"""
========== 학습 데이터 관리 LearningData ==========

| 이력 | History |
- history_presence :          사용자별 학습 활동 로그 존재/커버리지 확인

| 진도율 | Progress |
- progress_completeness :     진도율 결측/범위외/전부 0% 사용자 감지(신선도 옵션)

| 활동로그 | Activity Log |
- activity_log_adequacy :     필수 이벤트 존재 여부 + (선택) 이상치 탐지

| 완료 | Completion |
- completion_rule_check :     완료 규칙(진도/과제/시험) 충족 여부 판정

====================================
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
import math
import re
import statistics
from datetime import datetime, timedelta

# (선택) scikit-learn이 있으면 IsolationForest 사용
try:
    from sklearn.ensemble import IsolationForest
except Exception:
    IsolationForest = None


# ---------------------------------------------------------------------
# 엔트리 포인트: 학습 데이터 관리 라우팅
# ---------------------------------------------------------------------
def check(driver, step: Dict[str, Any]) -> Dict[str, Any]:
    assessment_type = step.get("type")

    if assessment_type == "history_presence":
        return history_presence(step)

    elif assessment_type == "progress_completeness":
        return progress_completeness(step)

    elif assessment_type == "activity_log_adequacy":
        return activity_log_adequacy(step)

    elif assessment_type == "completion_rule_check":
        return completion_rule_check(step)

    elif assessment_type == "run_all":
        results = [
            history_presence(step),
            progress_completeness(step),
            activity_log_adequacy(step),
            completion_rule_check(step),
        ]

        final = "pass"
        if any(r["status"] == "fail" for r in results):
            final = "fail"
        elif any(r["status"] == "warn" for r in results):
            final = "warn"

        out = {"module": "learning_data", "status": final, "results": results}
        print_module_result(out)
        return out
    else:
        raise ValueError(f"[LEARNING_DATA] 알 수 없는 검사 유형: {assessment_type}")


# -------------------------
# 공용 유틸
# -------------------------
def print_module_result(result: Dict[str, Any]):
    status = result.get("status", "pass").upper()
    print(f"[LEARNING_DATA] MODULE STATUS: {status}")
    for r in result.get("results", []):
        name = r.get("name")
        st = r.get("status", "pass").upper()
        print(f"  - {name:24s} [{st}]")


def print_step_result(res: Dict[str, Any]) -> None:
    """각 함수 내부에서 즉시 호출되는 단일 스텝 요약 + 짧은 설명."""
    name = res.get("name", "(unknown)")
    st = res.get("status", "pass").upper()
    line = f"[LEARNING_DATA][STEP] {name:24s} [{st}]"

    for k in ("coverage", "missing_users", "invalid_count", "zero_only_users",
              "anomaly_count", "completion_rate"):
        if k in res:
            line += f" {k}={res[k]}"
    print(line)
    note = brief_explain(res)
    if note:
        print(f"    note: {note}")
    for key in ("issues", "details", "missing_map", "anomalies", "fails"):
        if res.get(key):
            print(f"    {key}(sample): {str(res[key])[:300]}")
    print()


def brief_explain(res: Dict[str, Any]) -> str:
    name, st = res.get("name"), res.get("status")
    if name == "history_presence":
        if st == "pass":
            return "모든 대상 사용자에 대해 학습 이력이 존재합니다."
        return "일부 사용자에 대한 학습 이력이 누락되어 있습니다."
    if name == "progress_completeness":
        if st == "pass":
            return "진도율 데이터가 정상이며 추적 가능합니다."
        return "결측/범위외/0%만 존재하는 진도율이 확인되었습니다."
    if name == "activity_log_adequacy":
        if st == "pass":
            return "필수 활동 로그가 충족되며 이상치가 없습니다."
        return "필수 이벤트 누락 또는 이상치 패턴이 감지되었습니다."
    if name == "completion_rule_check":
        if st == "pass":
            return "정의된 완료 규칙이 모두 충족됩니다."
        return "일부 사용자가 완료 조건을 만족하지 못했습니다."
    return ""


def to_dt(x) -> Optional[datetime]:
    if not x:
        return None
    if isinstance(x, (int, float)):  # epoch seconds
        try:
            return datetime.fromtimestamp(x)
        except Exception:
            return None
    if isinstance(x, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%dT%H:%M:%S"):
            try:
                return datetime.strptime(x, fmt)
            except Exception:
                continue
    return None


def group_by_user(logs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    g = defaultdict(list)
    for ev in logs:
        uid = str(ev.get("user_id") or ev.get("uid") or "")
        if uid:
            g[uid].append(ev)
    return g


# ------------------------------------
# 학습 데이터 관리: 학습 이력 저장 여부
# ------------------------------------
def history_presence(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력:
      - logs: [{user_id, event_type, ts, ...}, ...]
      - users: ["u1","u2",...] (선택)
    """
    logs: List[Dict[str, Any]] = step.get("logs", []) or []
    users: List[str] = step.get("users", []) or []
    g = group_by_user(logs)
    target_users = users or list(g.keys())
    missing = [u for u in target_users if u not in g or len(g[u]) == 0]
    ok = len(target_users) - len(missing)
    coverage = round(ok / max(1, len(target_users)), 3)
    status = "pass" if len(missing) == 0 else (
        "warn" if coverage >= 0.9 else "fail")
    res = {
        "name": "history_presence",
        "status": status,
        "coverage": coverage,
        "missing_users": len(missing),
        "details": missing[:20],
    }
    print_step_result(res)
    return res


# ------------------------------------
# 학습 데이터 관리: 학습 진도율 누락 감지
# ------------------------------------
def progress_completeness(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력:
      - progress: [{user_id, progress, last_updated}, ...]  # progress: 0~100
      - freshness_days: int (선택, 기본 0=무시; N>0이면 last_updated 경과 N일 초과 시 경고)
    """
    records: List[Dict[str, Any]] = step.get("progress", []) or []
    freshness_days: int = int(step.get("freshness_days", 0))

    invalid = 0
    zero_only_users = set()
    stale_users = set()

    # 사용자별 모든 progress 값 수집
    by_u = defaultdict(list)
    for r in records:
        uid = str(r.get("user_id"))
        p = r.get("progress", None)
        by_u[uid].append(p)

        # 신선도 체크
        if freshness_days > 0:
            dt = to_dt(r.get("last_updated"))
            if not dt or (datetime.now() - dt) > timedelta(days=freshness_days):
                stale_users.add(uid)

        # 범위/결측 체크
        if p is None or (not isinstance(p, (int, float))) or p < 0 or p > 100:
            invalid += 1

    for uid, vals in by_u.items():
        norm = [v for v in vals if isinstance(v, (int, float))]
        if norm and all((v == 0 for v in norm)):
            zero_only_users.add(uid)

    status = "pass"
    issues = []
    if invalid > 0:
        status = "warn"
        issues.append({"issue": "INVALID_PROGRESS_VALUE", "count": invalid})
    if zero_only_users:
        status = "warn"
        issues.append({"issue": "ZERO_ONLY_USERS", "count": len(
            zero_only_users), "ids": list(zero_only_users)[:10]})
    if freshness_days > 0 and stale_users:
        status = "warn"
        issues.append({"issue": "STALE_PROGRESS", "count": len(
            stale_users), "ids": list(stale_users)[:10]})

    res = {
        "name": "progress_completeness",
        "status": status,
        "invalid_count": invalid,
        "zero_only_users": len(zero_only_users),
        "issues": issues,
    }
    print_step_result(res)
    return res


# --------------------------------------------
# 학습 데이터 관리: 학습 활동 로그 적절성 + 이상치 탐지
# --------------------------------------------
REQUIRED_EVENTS_DEFAULT = ["start_course",
                           "progress", "submit_assignment", "take_exam"]


def _ensure_required_map(logs: List[Dict[str, Any]], required: List[str]) -> Dict[str, Dict[str, bool]]:
    g = group_by_user(logs)
    out = {}
    for uid, evs in g.items():
        seen = {k: False for k in required}
        for e in evs:
            et = str(e.get("event_type") or e.get("type") or "").lower()
            # 간단한 동의어 매핑
            if et in ("start", "start_course", "course_start"):
                seen["start_course"] = True
            if et in ("progress", "progress_inc", "learn_step"):
                seen["progress"] = True
            if et in ("submit_assignment", "assignment_submit", "hw_submit"):
                seen["submit_assignment"] = True
            if et in ("take_exam", "exam_start", "exam_submit"):
                seen["take_exam"] = True
        out[uid] = seen
    return out


def build_user_features(logs: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """사용자별 간단 피처(이벤트수, 유형수, progress 비율, 평균 간격(초))"""
    g = group_by_user(logs)
    feats = {}
    for uid, evs in g.items():
        total = len(evs)
        types = set(str(e.get("event_type") or e.get("type") or "").lower()
                    for e in evs)
        progress_cnt = sum(1 for e in evs if str(
            e.get("event_type") or "").lower().startswith("progress"))
        # 시간 간격
        ts = []
        for e in evs:
            dt = to_dt(e.get("ts") or e.get("timestamp"))
            if dt:
                ts.append(dt)
        ts.sort()
        gaps = [(ts[i] - ts[i-1]).total_seconds()
                for i in range(1, len(ts))] if len(ts) >= 2 else [0.0]
        avg_gap = sum(gaps)/len(gaps) if gaps else 0.0
        feats[uid] = [float(total), float(len(types)),
                      float(progress_cnt), float(avg_gap)]
    return feats


def iqr_anomaly_flags(values: List[float]) -> List[bool]:
    if len(values) < 4:
        return [False]*len(values)
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    low = q1 - 1.5*iqr
    high = q3 + 1.5*iqr
    return [(v < low or v > high) for v in values]


def activity_log_adequacy(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력:
      - logs: [{user_id, event_type, ts, ...}, ...]
      - required_events: [str,...] (선택, 기본 REQUIRED_EVENTS_DEFAULT)
      - use_ai: bool (선택, 기본 False)  # 이상치 탐지 시도
    """
    logs: List[Dict[str, Any]] = step.get("logs", []) or []
    required: List[str] = step.get(
        "required_events") or REQUIRED_EVENTS_DEFAULT
    use_ai: bool = bool(step.get("use_ai", False))

    # 필수 이벤트 커버리지
    req_map = _ensure_required_map(logs, required)
    missing_map = {}
    for uid, seen in req_map.items():
        missing = [k for k, v in seen.items() if not v]
        if missing:
            missing_map[uid] = missing

    status = "pass" if not missing_map else ("warn" if len(
        missing_map) <= max(1, len(req_map)//10) else "fail")
    issues = []
    if missing_map:
        issues.append({"issue": "REQUIRED_EVENTS_MISSING",
                      "count_users": len(missing_map)})

    # (선택) 이상치 탐지
    anomalies = []
    if use_ai and logs:
        feats = build_user_features(logs)
        X = list(feats.values())
        uids = list(feats.keys())
        if IsolationForest is not None and len(X) >= 8:
            try:
                model = IsolationForest(
                    n_estimators=100, contamination="auto", random_state=42)
                preds = model.fit_predict(X)  # -1: outlier
                anomalies = [uids[i] for i, p in enumerate(preds) if p == -1]
            except Exception:
                anomalies = []
        else:
            # 간단 IQR 폴백: 각 피처별 이상치가 2개 이상인 사용자만 outlier로 간주
            cols = list(zip(*X)) if X else []
            flags_per_col = [iqr_anomaly_flags(
                list(col)) for col in cols] if cols else []
            for i in range(len(uids)):
                flag_count = sum(1 for col in flags_per_col if col and col[i])
                if flag_count >= 2:
                    anomalies.append(uids[i])

        if anomalies:
            status = "warn" if status == "pass" else status
            issues.append({"issue": "ANOMALY_DETECTED",
                          "count_users": len(anomalies)})

    res = {
        "name": "activity_log_adequacy",
        "status": status,
        "missing_map": dict(list(missing_map.items())[:20]),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:20],
        "issues": issues
    }
    print_step_result(res)
    return res


# ------------------------------------
# 학습 데이터 관리: 완료 규칙 일치 여부
# ------------------------------------
def completion_rule_check(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    입력:
      - progress: [{user_id, progress}, ...]
      - assignment: [{user_id, submitted: bool}, ...]   (선택)
      - exam: [{user_id, taken: bool}, ...]             (선택)
      - completion_rules: {"min_progress": 100, "require_assignment": true, "require_exam": true}
    """
    progress = step.get("progress", []) or []
    assignment = step.get("assignment", []) or []
    exam = step.get("exam", []) or []
    rules = step.get("completion_rules", {}) or {}

    min_progress = int(rules.get("min_progress", 100))
    req_asg = bool(rules.get("require_assignment", True))
    req_exam = bool(rules.get("require_exam", True))

    # dict화
    prog_map = {str(r.get("user_id")): float(r.get("progress", 0))
                for r in progress}
    asg_map = {str(r.get("user_id")): bool(r.get("submitted", False))
               for r in assignment}
    exam_map = {str(r.get("user_id")): bool(r.get("taken", False))
                for r in exam}

    users = set(list(prog_map.keys()) +
                list(asg_map.keys()) + list(exam_map.keys()))
    fails = []
    ok = 0
    for uid in users:
        reasons = []
        if prog_map.get(uid, 0.0) < min_progress:
            reasons.append("progress")
        if req_asg and not asg_map.get(uid, False):
            reasons.append("assignment")
        if req_exam and not exam_map.get(uid, False):
            reasons.append("exam")
        if reasons:
            fails.append({"user_id": uid, "reasons": reasons})
        else:
            ok += 1

    completion_rate = round(ok / max(1, len(users)), 3)
    status = "pass" if not fails else (
        "warn" if completion_rate >= 0.9 else "fail")
    res = {
        "name": "completion_rule_check",
        "status": status,
        "completion_rate": completion_rate,
        "fails": fails[:30]
    }
    print_step_result(res)
    return res
