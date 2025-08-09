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
import os


# ---------------------------------------------------------------------
# 엔트리 포인트: 실행효율성 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    assessment_type = step["type"]
    
    if assessment_type == "report_response_time":
        return report_response_time(step, driver)
    
        '''elif assessment_type == "compare_processing_time":
        return compare_processing_time(step, driver)
    
    elif assessment_type == "warn_timeout":
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
    """샘플(초) 리스트에서 핵심 통계량 산출"""
    xs = sorted(samples)
    return {
        "count": len(xs),
        "avg": (sum(xs) / len(xs)) if xs else 0.0,
        "median": statistics.median(xs) if xs else 0.0,
        "p90": percentile(xs, 90),
        "p95": percentile(xs, 95),
        "p99": percentile(xs, 99),
        "min": xs[0] if xs else 0.0,
        "max": xs[-1] if xs else 0.0,
    }

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

        items = step.get("actions", [])
        if not items:
            raise ValueError("[PERFORMANCE] playwright 모드에서는 'actions'가 필요합니다.")
    
    # 백엔드인 경우
    else:
        def run_target(t: Dict[str, Any]):
            method = t.get("method", "GET").upper()
            url = t["url"]
            req_kwargs = {k: v for k, v in t.items() if k not in ("name", "method", "url")}
            return measure_func(lambda: requests.request(method, url, **req_kwargs))

        items = step.get("targets", [])
        if not items:
            raise ValueError("[PERFORMANCE] backend 모드에서는 'targets'가 필요합니다.")

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