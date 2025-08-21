"""
========== 실행효율성 Performance ==========

| 시간효율성 | Time Efficiency |
- report_response_time :        주요 기능 응답 시간 측정
- compare_processing_time :     보고서 기반 기능별 처리 시간 비교
- warn_timeout :                시간 초과 경고 탐지
+ measure_func :                특정 함수 실행 시간을 측정하는 공통 유틸
+ summarize :                   응답 시간 통계 요약
+ judge :                       통계 결과와 기준값 비교 후 PASS/FAIL 판정
+ print_report :                응답 시간 측정 결과를 보기 좋게 출력
+ percentile :                  분위수 계산 유틸(단순 선형보간)
+ median :                      중앙값 계산(강건 통계용)
+ mad :                         중앙값 절대편차(Median Absolute Deviation) 계산
+ robust_zscores :              중앙값/MAD 기반 강건 z-score 계산

============================================
"""
# ---------------------------------------------------------------------
# 모듈 임포트
# ---------------------------------------------------------------------
from __future__ import annotations
import time
import statistics
from typing import Dict, Any, List, Callable, Tuple, Optional
import requests
import time
import statistics
import math
from colorama import Fore, Style


# ---------------------------------------------------------------------
# 엔트리 포인트: 실행효율성 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    assessment_type = step["type"]

    if assessment_type == "report_response_time":
        return report_response_time(step, driver)

    elif assessment_type == "compare_processing_time":
        return compare_processing_time(step, driver)

    elif assessment_type == "warn_timeout":
        return warn_timeout(step, driver)

    else:
        raise ValueError(f"[PERFORMANCE] 알 수 없는 검사 유형: {assessment_type}")


# ---------------------------------------------------------------------
# 공통 유틸: 계측/통계/판정/리포트
# ---------------------------------------------------------------------
def measure_func(func: Callable[[], Any]) -> float:
    """콜러블 실행 시간을 초 단위로 반환"""
    t0 = time.perf_counter()
    func()
    return time.perf_counter() - t0


def percentile(values: List[float], p: float) -> float:
    """단순 분위수(0~100)"""
    if not values:
        return 0.0
    xs = sorted(values)
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] * (c - k) + xs[c] * (k - f)


def summarize(samples: List[float]) -> Dict[str, float]:
    """샘플(초) 리스트에서 핵심 통계량 산출. 비유한값(inf/NaN)은 제외."""
    xs_all = list(samples)
    xs = [x for x in xs_all if isinstance(
        x, (int, float)) and math.isfinite(x)]
    err_cnt = len(xs_all) - len(xs)
    xs.sort()
    stats = {
        "count": len(xs_all),
        "finite_count": len(xs),
        "errors": err_cnt,
        "avg": (sum(xs) / len(xs)) if xs else float("inf"),
        "median": (statistics.median(xs) if xs else float("inf")),
        "p90": (percentile(xs, 90) if xs else float("inf")),
        "p95": (percentile(xs, 95) if xs else float("inf")),
        "p99": (percentile(xs, 99) if xs else float("inf")),
        "min": (xs[0] if xs else float("inf")),
        "max": (xs[-1] if xs else float("inf")),
    }
    return stats


def judge(stats: Dict[str, float], threshold_s: float, rule: str = "p95<=threshold") -> Tuple[bool, str]:
    """
    임계치 판정 규칙(기본: p95 <= threshold 이면 PASS).
    rule 예: "avg<=threshold", "p90<=threshold"
    """
    metric = rule.split("<=")[0].strip()
    val = stats.get(metric)
    ok = (val is not None) and (val <= threshold_s)
    reason = f"{metric}={val:.4f}s, threshold={threshold_s:.4f}s → {'PASS' if ok else 'FAIL'}"
    return ok, reason


# ---------------------------------------------------------------------
# 출력 포맷 유틸 (다른 모듈과 통일)
# ---------------------------------------------------------------------
def color_status(status: str) -> str:
    if status == "PASS":
        return Fore.GREEN + status + Style.RESET_ALL
    elif status == "FAIL":
        return Fore.RED + status + Style.RESET_ALL
    elif status == "WARN":
        return Fore.YELLOW + status + Style.RESET_ALL
    elif status == "ERROR":
        return Fore.MAGENTA + status + Style.RESET_ALL
    return status or "N/A"


def print_block(tag: str,
                title: str,
                status: str,
                reason: Optional[str] = None,
                details: Optional[Dict[str, Any]] = None,
                evidence: Optional[List[str]] = None,
                width: int = 70) -> None:
    print("\n" + "=" * width)
    print(f"[{tag}] {title}")
    print("-" * width)
    print(f"  • 상태       : {color_status(status)}")
    if reason:
        print(f"  • 이유       : {reason}")
    if details:
        print("  • 상세")
        for k, v in details.items():
            print(f"     - {k:<15}: {v}")
    if evidence:
        print("  • 근거")
        for e in evidence:
            print(f"     - {e}")
    print("=" * width)


# ---------------------------------------------------------------------
# 강건 통계 유틸: median / MAD / 강건 z-score
# ---------------------------------------------------------------------
def median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    m = n // 2
    return s[m] if n % 2 else (s[m-1] + s[m]) / 2.0


def mad(xs: List[float], med: Optional[float] = None) -> float:
    if not xs:
        return 0.0
    if med is None:
        med = median(xs)
    abs_dev = [abs(x - med) for x in xs]
    return median(abs_dev)


def robust_zscores(values: List[float]) -> Tuple[List[float], float, float]:
    """
    values: 비교 대상 값들(예: 기능별 평균 응답시간)
    반환: (각 값의 강건 z 리스트, 중앙값, 분모(MAD*1.4826 또는 inf))
    - 값이 비었으면 z=[], median=0.0, denom=1.0
    - 모든 값이 동일하거나 MAD=0이면 z=0, denom=inf (나누기 방지)
    """
    if not values:
        return [], 0.0, 1.0

    med = median(values)
    mad_val = mad(values, med)

    if mad_val == 0:
        return [0.0] * len(values), med, float("inf")

    denom = mad_val * 1.4826        # 정규분포 보정 상수
    z = [(v - med) / denom for v in values]
    return z, med, denom


# ---------------------------------------------------------------------
# 시간효율성: 주요 기능 응답 시간 측정
# ---------------------------------------------------------------------
def report_response_time(step: Dict[str, Any], driver) -> Dict[str, Any]:
    """
    주요 기능들의 응답 시간을 측정하는 함수
    """
    emit = bool(step.get("emit", True))

    mode = step.get("mode")
    if not mode:
        is_playwright = (driver is not None and hasattr(driver, "page"))
        mode = "playwright" if is_playwright else "backend"
    else:
        is_playwright = (mode == "playwright")

    # 공통 파라미터
    repeats = int(step.get("repeats", 5 if is_playwright else 3))
    warmups = int(step.get("warmups", 1))
    rule = step.get("rule", "p95<=threshold")
    thresholds: Dict[str, float] = step.get(
        "thresholds", {"*": 0.300 if driver == "backend" else 1.200})

    results: Dict[str, Any] = {}

    items: List[Dict[str, Any]] = []

    # 실행 함수 정의
    # playwright인 경우
    if is_playwright:
        if driver is None or not hasattr(driver, "page"):
            raise RuntimeError(
                "[PERFORMANCE] Playwright 모드에는 driver.page가 필요합니다.")
        page = driver.page

        def run_target(act: Dict[str, Any]):
            op = act["op"]
            if op == "goto":
                return measure_func(lambda: page.goto(act["url"]))
            elif op == "click":
                return measure_func(lambda: page.click(act["selector"]))
            elif op == "fill":
                return measure_func(lambda: page.fill(act["selector"], act["value"]))
            elif op == "press":
                return measure_func(lambda: page.press(act["selector"], act["key"]))
            else:
                raise ValueError(f"[PERFORMANCE] 지원하지 않는 action op: {op}")

        items = step.get("actions") or []
        if not items:
            raise ValueError(
                "[PERFORMANCE] playwright 모드에서는 'actions'가 필요합니다.")

    # 백엔드인 경우
    else:
        def run_target(t: Dict[str, Any]):
            method = t.get("method", "GET").upper()
            url = t["url"]
            req_kwargs = {k: v for k, v in t.items(
            ) if k not in ("name", "method", "url")}

            if "timeout" not in req_kwargs:
                req_kwargs["timeout"] = 5

            def call():
                try:
                    return requests.request(method, url, **req_kwargs)
                except Exception:
                    time.sleep(0.2)  # 1회 재시도
                    return requests.request(method, url, **req_kwargs)
            return measure_func(call)

        items = step.get("targets") or []
        if not items:
            raise ValueError(
                "[PERFORMANCE > TIME EFFICIENCY] backend 모드에서는 'targets'가 필요합니다.")

    # 각 대상별 측정
    for t in items:
        name = t["name"]

        # 워밍업
        for _ in range(warmups):
            try:
                _ = run_target(t)
            except Exception:
                pass

        # 측정
        samples: List[float] = []
        for _ in range(repeats):
            try:
                dur = run_target(t)
                samples.append(dur)
            except Exception:
                samples.append(float("inf"))

        stats = summarize(samples)
        thr = thresholds.get(name, thresholds.get("*", None))
        ok, reason = (
            True, "no-threshold") if thr is None else judge(stats, thr, rule=rule)
        results[name] = {
            "stats": stats,
            "threshold": thr,
            "rule": rule,
            "pass": ok,
            "reason": reason,
            "samples": samples
        }

        if emit:
            status = "PASS" if ok else "FAIL"
            details = {
                "count": stats["count"],
                "avg": f"{stats['avg']:.4f}s",
                "p90": f"{stats['p90']:.4f}s",
                "p95": f"{stats['p95']:.4f}s",
                "p99": f"{stats['p99']:.4f}s",
                "min": f"{stats['min']:.4f}s",
                "max": f"{stats['max']:.4f}s",
                "rule": rule,
                "threshold": ("None" if thr is None else f"{thr:.4f}s"),
            }
            ev = None
            if samples:
                ev = [f"samples(top3): {[round(x, 4) for x in samples[:3]]}"]
            print_block("PERFORMANCE", f"주요 기능 응답 시간 측정: {name}", status, reason=reason,
                        details=details, evidence=ev)

    return results


# ---------------------------------------------------------------------
# 시간효율성: 보고서 기반 기능별 처리 시간 비교 + 이상치 탐지
# ---------------------------------------------------------------------
def compare_processing_time(step: Dict[str, Any], driver) -> Dict[str, Any]:
    """
    보고서 기반 기능별 처리 시간 비교
    - 입력:
        - step["results"]가 있으면 그 결과( report_response_time 반환값 )를 그대로 사용
        - 없으면 내부적으로 report_response_time을 실행하여 결과 생성
    - 이상치 탐지:
        dafault: 강건 z-score(중앙값/MAD) 기준
        option: factor(배수) 규칙 병행, Isolation Forest(데이터 충분 시)
    - 설정(step):
        metric: "avg" | "p90" | "p95" | "p99" 중 비교 기준 (기본 "avg")
        anomaly: {
          "method": "robust_z" | "iforest",
          "z_thresh": 3.0,
          "factor_baseline": 1.6,
          "min_samples": 3,
          "contamination": 0.15   # iforest일 때만
        }
    """
    metric = step.get("metric", "avg")
    an = step.get("anomaly", {}) or {}
    method = an.get("method", "robust_z")
    z_thresh = float(an.get("z_thresh", 3.0))
    factor_baseline = an.get("factor_baseline", 1.6)
    min_samples = int(an.get("min_samples", 3))
    contamination = float(an.get("contamination", 0.15))

    # 결과 확보
    base_results = step.get("results")
    if not base_results:
        inner_step = {**step, "emit": False}
        base_results = report_response_time(inner_step, driver)

    # 기능별 통계 추출
    features: List[str] = []
    values: List[float] = []
    counts: List[int] = []
    stds: List[float] = []

    for name, data in base_results.items():
        if not isinstance(data, dict) or "stats" not in data:
            continue
        s = data["stats"]
        features.append(name)
        values.append(float(s.get(metric, 0.0)))
        counts.append(int(s.get("count", 0)))

        stds.append(0.0)

    if not features:
        raise ValueError(
            "[PERFORMANCE > TIME EFFICIENCY] 비교할 대상이 없습니다. report_response_time 결과를 확인하세요.")

    # 이상치 탐지
    is_anomaly = [False] * len(features)
    reasons = ["normal"] * len(features)
    score = [0.0] * len(features)

    # robust z-score (유한값만 사용)
    nonfinite = [not math.isfinite(v) for v in values]

    # 유한값만 뽑아서 z-score 계산
    finite_vals = [v for v in values if math.isfinite(v)]
    z_map: Dict[int, float] = {}
    med = 0.0
    denom = float("inf")

    if finite_vals:
        z_list, med, denom = robust_zscores(finite_vals)
        # 유한값 위치에만 z-score 매핑
        fi = 0
        for i, v in enumerate(values):
            if math.isfinite(v):
                z_map[i] = z_list[fi]
                fi += 1

    # 이상치 판정 루프
    for i in range(len(features)):
        if counts[i] < min_samples:
            is_anomaly[i] = False
            reasons[i] = f"insufficient_samples(<{min_samples})"
            score[i] = 0.0
            continue

        # 비유한값은 즉시 이상 처리
        if nonfinite[i]:
            is_anomaly[i] = True
            reasons[i] = "non-finite(value=inf/NaN)"
            score[i] = float("inf")
            continue

        rz = z_map.get(i, 0.0)
        flags = []

        # z-score 룰
        if abs(rz) >= z_thresh and not math.isinf(denom):
            flags.append(f"robust_z|z|≥{z_thresh}")

        # 배수 규칙(느린 쪽만): 값이 median보다 크고, factor 이상일 때만 이상
        if factor_baseline and med > 0 and values[i] > med:
            if values[i] >= med * float(factor_baseline):
                flags.append(f"factor≥{factor_baseline}x_median")

        if flags:
            is_anomaly[i] = True
            reasons[i] = " & ".join(flags)
        score[i] = rz

    # Isolation Forest(옵션, 데이터/환경 충분 시)
    if method == "iforest":
        try:
            from sklearn.ensemble import IsolationForest
            # 표본이 너무 적으면 과적합/무의미 -> 최소 5개 이상일 때만
            if len(values) >= 5:
                iso = IsolationForest(
                    contamination=contamination, random_state=42)
                pred = iso.fit_predict([[v] for v in values])  # -1: 이상
                df_score = iso.decision_function(
                    [[v] for v in values])  # 낮을수록 이상
                for i in range(len(features)):
                    if counts[i] < min_samples:
                        continue
                    if pred[i] == -1:
                        is_anomaly[i] = True
                        tag = f"iforest(cont={contamination})"
                        reasons[i] = tag if reasons[i] == "normal" else (
                            reasons[i] + " & " + tag)

                    score[i] = (score[i] + (-df_score[i])) / 2.0
        except Exception as e:
            pass

    # 리포트 출력
    any_anom = any(is_anomaly)
    status = "WARN" if any_anom else "PASS"
    details = {
        "metric": metric,
        "median": f"{med:.6f}s",
        "robust_denom": ("inf" if math.isinf(denom) else f"{denom:.6f}"),
        "anomaly_method": method,
        "z_thresh": z_thresh,
        "factor_baseline": factor_baseline,
        "min_samples": min_samples,
    }
    ev: List[str] = []
    for i in range(len(features)):
        flag = "ANOMALY" if is_anomaly[i] else "OK"
        ev.append(
            f"{features[i]:<18} {values[i]:>10.6f}s  (n={counts[i]:>2d})  "
            f"[{flag}]  reason={reasons[i]}  z={score[i]:+.3f}"
        )

    print_block("PERFORMANCE", "기능별 처리시간 비교/이상 탐지",
                status, details=details, evidence=ev)

    return {
        "metric": metric,
        "median": med,
        "robust_denom": denom,
        "rows": [
            {
                "feature": features[i],
                "value_s": values[i],
                "count": counts[i],
                "is_anomaly": is_anomaly[i],
                "reason": reasons[i],
                "score": score[i],
            }
            for i in range(len(features))
        ]
    }


# ---------------------------------------------------------------------
# 시간효율성: 시간 초과 경고 탐지 - 기준 초과 비율(%) 리포트
# ---------------------------------------------------------------------
def warn_timeout(step: Dict[str, Any], driver) -> Dict[str, Any]:
    """
    시간 초과 경고 탐지
    - 기준(threshold_s)을 초과한 샘플 비율을 계산해 경고
    - 입력:
        1) step["results"]: 기존 report_response_time() 결과를 재사용하거나,
        2) 없으면 report_response_time(step, driver)로 즉시 측정
    - 설정(step):
        percent_limit: 초과 비율 경고 임계치(기본 10%)
        metric: 보고서 표시에 참고로 보여줄 대표 통계(기본 avg)
    """
    percent_limit = float(step.get("percent_limit", 10.0))
    metric = step.get("metric", "avg")

    # 결과 확보
    base_results = step.get("results")
    if not base_results:
        inner_step = {**step, "emit": False}
        base_results = report_response_time(inner_step, driver)

    if not isinstance(base_results, dict):
        raise ValueError("[PERFORMANCE > TIMEOUT] 유효한 results가 아닙니다.")

    # 계산
    rows = []
    for name, data in base_results.items():
        if not isinstance(data, dict) or "stats" not in data:
            continue
        stats = data["stats"]
        samples = data.get("samples", [])
        thr = data.get("threshold")

        # threshold가 없다면 전체 기본값을 step에서 가져오거나 스킵
        if thr is None:
            thr = (step.get("thresholds", {}) or {}).get("*", None)
        if thr is None:
            # 기준이 없으면 의미 있는 초과율을 계산할 수 없음
            rows.append({
                "feature": name,
                "metric_value": float(stats.get(metric, 0.0)),
                "threshold": None,
                "count": len(samples),
                "over_count": 0,
                "percent_over": 0.0,
                "warn": False,
                "reason": "no-threshold"
            })
            continue

        # 초과 판단: sample > thr 또는 비유한값(Inf/NaN) → 초과로 간주
        total = len(samples)
        over = 0
        for x in samples:
            if not isinstance(x, (int, float)) or not math.isfinite(x):
                over += 1
            elif x > thr:
                over += 1

        percent_over = (over / total * 100.0) if total > 0 else 0.0
        warn = percent_over >= percent_limit

        rows.append({
            "feature": name,
            "metric_value": float(stats.get(metric, 0.0)),
            "threshold": thr,
            "count": total,
            "over_count": over,
            "percent_over": percent_over,
            "warn": warn,
            "reason": f"{percent_over:.1f}%≥{percent_limit:.1f}% → {'WARN' if warn else 'OK'}"
        })

    any_warn = any(r["warn"] for r in rows)
    status = "WARN" if any_warn else "PASS"
    details = {
        "percent_limit": f"{percent_limit:.1f}%",
        "metric": metric,
    }
    ev = []
    for r in rows:
        flag = "WARN" if r["warn"] else "OK"
        thr_str = "None" if r["threshold"] is None else f"{r['threshold']:.3f}s"
        ev.append(
            f"{r['feature']:<18} {r['metric_value']:>10.6f}s  "
            f"(count={r['count']:>2d}, over={r['over_count']:>2d}, {r['percent_over']:>5.1f}%)  "
            f"[{flag}]  thr={thr_str}  {r['reason']}"
        )

    print_block("PERFORMANCE", "시간 초과 경고 탐지",
                status, details=details, evidence=ev)

    return {
        "percent_limit": percent_limit,
        "metric": metric,
        "rows": rows
    }
