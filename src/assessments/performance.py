"""
========== 실행효율성 Performance ==========

| 시간효율성 | Time Efficiency |
- report_response_time :        주요 기능 응답 시간 측정
- compare_processing_time :     보고서 기반 기능별 처리 시간 비교
- warn_timeout :                시간 초과 경고 탐지
+ measure_func :                특정 함수 실행 시간을 측정하는 공통 유틸
+ summarize :                   응답 시간 통계 요약 (평균, p90, p95, 최소/최대 등)
+ judge :                       통계 결과와 기준값 비교 후 PASS/FAIL 판정
+ print_report :                응답 시간 측정 결과를 보기 좋게 출력

| 자원활용성 | Resource Utilization |

============================================
"""
# ---------------------------------------------------------------------
# 모듈 임포트
# ---------------------------------------------------------------------
from __future__ import annotations
import time, statistics
from typing import Dict, Any, List, Callable, Tuple, Optional
import requests
import time, statistics, math


# ---------------------------------------------------------------------
# 엔트리 포인트: 실행효율성 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    assessment_type = step["type"]
    
    if assessment_type == "report_response_time":
        return report_response_time(step, driver)
    
    elif assessment_type == "compare_processing_time":
        return compare_processing_time(step, driver)
    
        '''elif assessment_type == "warn_timeout":
        return warn_timeout(step, driver)'''
    
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
    xs = [x for x in xs_all if isinstance(x, (int, float)) and math.isfinite(x)]
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

def print_report(results: Dict[str, Any]):
    print("\n[PERFORMANCE > 응답시간 리포트]")
    for name, data in results.items():
        stats = data["stats"]
        print(f"\n기능: {name}")
        print(f"  - 측정 횟수 : {stats['count']}")
        print(f"  - 평균 시간 : {stats['avg']:.4f}s")
        print(f"  - 90% 구간 최대값(p90) : {stats['p90']:.4f}s")
        print(f"  - 95% 구간 최대값(p95) : {stats['p95']:.4f}s")
        print(f"  - 99% 구간 최대값(p99) : {stats['p99']:.4f}s")
        print(f"  - 최소 / 최대 : {stats['min']:.4f}s / {stats['max']:.4f}s")
        print(f"  - 기준값(rule) : {data['rule']} / {data['threshold']:.4f}s")
        print(f"  => 판정 : {'PASS' if data['pass'] else 'FAIL'} ({data['reason']})")


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

    med = median(values)           # 항상 먼저 계산
    mad_val = mad(values, med)     # 항상 먼저 계산

    if mad_val == 0:
        # 모든 값이 같거나 변동이 너무 작음 → 나누기 방지
        return [0.0] * len(values), med, float("inf")

    denom = mad_val * 1.4826        # 정규분포 보정 상수
    z = [(v - med) / denom for v in values]
    return z, med, denom


# ---------------------------------------------------------------------
# 주요 기능 응답 시간 측정 
# ---------------------------------------------------------------------
def report_response_time(step: Dict[str, Any], driver) -> Dict[str, Any]:
    """
    주요 기능들의 응답 시간을 측정하는 함수
    """
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
    thresholds: Dict[str, float] = step.get("thresholds", {"*": 0.300 if driver == "backend" else 1.200})

    results: Dict[str, Any] = {}
    
    items: List[Dict[str, Any]] = []

    # 실행 함수 정의
    # playwright인 경우
    if is_playwright:
        if driver is None or not hasattr(driver, "page"):
            raise RuntimeError("[PERFORMANCE] Playwright 모드에는 driver.page가 필요합니다.")
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
            raise ValueError("[PERFORMANCE] playwright 모드에서는 'actions'가 필요합니다.")
    
    # 백엔드인 경우
    else:
        def run_target(t: Dict[str, Any]):
            method = t.get("method", "GET").upper()
            url = t["url"]
            req_kwargs = {k: v for k, v in t.items() if k not in ("name", "method", "url")}
            # 기본 timeout 부여
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
            raise ValueError("[PERFORMANCE > TIME EFFICIENCY] backend 모드에서는 'targets'가 필요합니다.")

    # 각 대상(백엔드 타겟 or 플레이라이트 액션)별 측정
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
        ok, reason = (True, "no-threshold") if thr is None else judge(stats, thr, rule=rule)
        results[name] = {
            "stats": stats,
            "threshold": thr,
            "rule": rule,
            "pass": ok,
            "reason": reason
        }

    print_report(results)
    return results


# ---------------------------------------------------------------------
# 보고서 기반 기능별 처리 시간 비교 + 이상치 탐지
# ---------------------------------------------------------------------
def compare_processing_time(step: Dict[str, Any], driver) -> Dict[str, Any]:
    """
    보고서 기반 기능별 처리 시간 비교
    - 입력:
        1) step["results"]가 있으면 그 결과( report_response_time 반환값 )를 그대로 사용
        2) 없으면 내부적으로 report_response_time을 실행하여 결과 생성
    - 이상치 탐지:
        기본: 강건 z-score(중앙값/MAD) 기준
        옵션: factor(배수) 규칙 병행, Isolation Forest(데이터 충분 시)
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

    # 1) 결과 확보
    base_results = step.get("results")
    if not base_results:
        # 같은 step 내용을 이용해 측정까지 수행
        base_results = report_response_time(step, driver)

    # 2) 기능별 통계 추출
    features: List[str] = []
    values: List[float] = []
    counts: List[int] = []
    stds: List[float] = []

    for name, data in base_results.items():
        if not isinstance(data, dict) or "stats" not in data:
            # report_response_time 이외의 필드가 섞여 있을 수 있으니 스킵
            continue
        s = data["stats"]
        # 샘플 수/표준편차는 참고용
        features.append(name)
        values.append(float(s.get(metric, 0.0)))
        counts.append(int(s.get("count", 0)))
        # 표준편차는 전달된 통계에 없으므로 대체(간단 계산)
        # 여기서는 p50 근처 분산을 가늠하기 어려워 0으로 두되 출력만 참고용
        stds.append(0.0)

    if not features:
        raise ValueError("[PERFORMANCE > TIME EFFICIENCY] 비교할 대상이 없습니다. report_response_time 결과를 확인하세요.")

    # 3) 이상치 탐지
    is_anomaly = [False] * len(features)
    reasons = ["normal"] * len(features)
    score = [0.0] * len(features)

    # 3-1) robust z-score (유한값만 사용)
    # 비유한값(Inf/NaN) 체크
    nonfinite = [not math.isfinite(v) for v in values]

    # 유한값만 뽑아서 z-score 계산
    finite_vals = [v for v in values if math.isfinite(v)]
    z_map: Dict[int, float] = {}
    med = 0.0
    denom = float("inf")

    if finite_vals:
        # robust z-score 계산 함수 이름이 _robust_zscores/robust_zscores 중 무엇인지에 맞춰 호출하세요.
        z_list, med, denom = robust_zscores(finite_vals)  # 또는 robust_zscores(finite_vals)
        # 유한값 위치에만 z-score 매핑
        fi = 0
        for i, v in enumerate(values):
            if math.isfinite(v):
                z_map[i] = z_list[fi]
                fi += 1

    # 3-1') 이상치 판정 루프
    for i in range(len(features)):
        # 샘플 수 그레이스
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

    # 3-2) Isolation Forest(옵션, 데이터/환경 충분 시)
    if method == "iforest":
        try:
            from sklearn.ensemble import IsolationForest
            # 표본이 너무 적으면 과적합/무의미, 최소 5개 이상일 때만
            if len(values) >= 5:
                iso = IsolationForest(contamination=contamination, random_state=42)
                pred = iso.fit_predict([[v] for v in values])  # -1: 이상
                df_score = iso.decision_function([[v] for v in values])  # 낮을수록 이상
                for i in range(len(features)):
                    if counts[i] < min_samples:
                        continue
                    if pred[i] == -1:
                        is_anomaly[i] = True
                        tag = f"iforest(cont={contamination})"
                        reasons[i] = tag if reasons[i] == "normal" else (reasons[i] + " & " + tag)
                    # 점수는 참고용으로 덮지 않고 평균(간단 병합)
                    score[i] = (score[i] + (-df_score[i])) / 2.0
        except Exception as e:
            # sklearn 없는 환경도 고려해 조용히 넘어감
            pass

    # 4) 리포트 출력
    print("\n[PERFORMANCE > 기능별 처리시간 비교/이상 탐지]")
    print(f"  - 기준 metric: {metric}")
    print(f"  - 중앙값(median): {med:.6f}s")
    if not math.isinf(denom):
        print(f"  - 강건 z 보정분모(MAD*1.4826): {denom:.6f}")
    print("----------------------------------------------------------------")
    for i in range(len(features)):
        flag = "ANOMALY" if is_anomaly[i] else "OK"
        print(f"{features[i]:<30s} {values[i]:>10.6f}s  "
              f"(count={counts[i]:>2d})  [{flag}]  reason={reasons[i]}  score={score[i]:+.3f}")

    # 5) 반환 오브젝트
    out = {
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
    return out