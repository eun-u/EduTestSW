# src/assessments/reliability.py
"""
========== 신뢰성 테스트 Reliability ==========

| 스트레스/부하 테스트 | Stress / Load Test |
- `stress_test`:              높은 동시성(concurrency)과 요청 속도(RPS)로
                             서비스의 최대 처리량과 응답 지연(latency)을 측정합니다.

| 복구 테스트 | Recovery Test |
- `recovery_check`:            서비스 장애 후 지정된 시간 내에 정상 상태로
                             복구되는지 확인합니다.

| 리소스 모니터링 | Resource Monitoring |
- `resource_monitor`:          테스트 중 시스템 및 프로세스(CPU, 메모리, 네트워크)의
                             사용량을 실시간으로 수집합니다.
                             
====================================
"""
import asyncio
import time
import json
import statistics
import sys
from typing import Dict, Any, List, Tuple, Optional
import httpx
import psutil
import threading
from datetime import datetime
from colorama import Fore, Style


TITLE_MAP = {
    "stress_result":   "스트레스/부하 테스트 결과",
    "recovery_result": "복구 테스트 결과",
    "resources":       "리소스 모니터링 스냅샷",
}

# =====================================================================
# 출력 모듈
# =====================================================================
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
                 title_key: str,
                 status: str,
                 reason: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None,
                 evidence: Optional[List[str]] = None,
                 width: int = 70) -> None:
    title = TITLE_MAP.get(title_key, title_key)
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


# =====================================================================
# 엔트리 포인트: 신뢰성 테스트 라우팅
# =====================================================================
def check(driver: Any, step: Dict[str, Any]) -> None:
    """
    테스트 러너에 의해 호출되는 메인 진입점 함수입니다.
    `mode` 값에 따라 스트레스/부하 테스트를 실행합니다.
    """
    mode = step.get("mode")
    if mode not in {"stress", "load"}:
        print("[RELIABILITY] Error: mode must be 'stress' or 'load'.")
        return

    print("[RELIABILITY] 스트레스 테스트 시작")
    try:
        metrics = asyncio.run(_stress_phase(step))
    except Exception as e:
        print(f"[RELIABILITY] Stress test failed: {e}", file=sys.stderr)
        return

    '''# 기존 상세 JSON 출력
    print(json.dumps({"phase": "stress", **metrics}, ensure_ascii=False, indent=2))

    # 기존 SLA 판정 로그
    sla_p95 = float(step.get("sla_ms_p95", 0))
    max_err = float(step.get("max_error_rate", 1.0))
    pass_latency = (metrics["latency_p95_ms"] <= sla_p95) if sla_p95 > 0 else True
    pass_error = (metrics["error_rate"] <= max_err)

    if pass_latency and pass_error:
        print(
            f"[PASS][reliability] p95={metrics['latency_p95_ms']:.1f}ms <= {sla_p95:.1f}ms, "
            f"error_rate={metrics['error_rate']:.3f} <= {max_err:.3f}"
        )
    else:
        print(
            f"[FAIL][reliability] p95={metrics['latency_p95_ms']:.1f}ms (SLA {sla_p95:.1f}ms), "
            f"error_rate={metrics['error_rate']:.3f} (max {max_err:.3f})"
        )'''

    # 요약 박스 출력
    emit_stress_block(metrics, step)
    emit_resource_block(metrics.get("resources"))

    # 복구 테스트 단계
    if step.get("recovery"):
        print("[RELIABILITY] 복구 확인 단계 시작")
        try:
            rec = asyncio.run(_recover_phase(step))
        except Exception as e:
            print(f"[RELIABILITY] Recovery phase failed: {e}", file=sys.stderr)
            rec = {"recovery_checked": True, "within_sla": False, "last_latency_ms": None, "seconds_waited": 0}

        # 기존 상세 JSON 출력
        #print(json.dumps({"phase": "recovery", **rec}, ensure_ascii=False, indent=2))
        
        '''if rec.get("recovery_checked") and rec.get("within_sla") is True:
            print("[PASS][recovery] 헬스체크가 SLA 이내로 회복되었습니다.")
        elif rec.get("recovery_checked"):
            print("[FAIL][recovery] 설정된 시간 내 SLA 이내로 회복하지 못했습니다.")'''

        # 복구 요약 박스
        emit_recovery_block(rec, step)


# =====================================================================
# 테스트 코어: 스트레스, 복구 로직
# =====================================================================
async def _shoot_once(client: httpx.AsyncClient, step: Dict[str, Any]) -> Tuple[bool, float, int, str]:
    """
    단일 요청을 실행하고 결과를 반환합니다.
    (성공 여부, 지연 시간(ms), HTTP 상태 코드, 오류 메시지)
    """
    url = step["target_url"]
    method = step.get("method", "GET").upper()
    headers = step.get("headers") or {}
    timeout_ms = step.get("timeout_ms", 2000)
    success_codes = set(step.get("success_statuses", [200]))

    data = None
    json_payload = None
    if "payload" in step and step["payload"] is not None:
        ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
        if "application/json" in ct or ct == "":
            json_payload = step["payload"]
        else:
            data = step["payload"]

    t0 = time.perf_counter()
    try:
        resp = await client.request(
            method, url, headers=headers, json=json_payload, data=data, timeout=timeout_ms / 1000.0
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        ok = resp.status_code in success_codes
        return ok, latency_ms, resp.status_code, ""
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return False, latency_ms, 0, str(e)

async def _warmup(client: httpx.AsyncClient, step: Dict[str, Any], warmup_sec: int) -> None:
    """테스트 시작 전 워밍업 요청을 보냅니다."""
    if warmup_sec and warmup_sec > 0:
        end = time.perf_counter() + warmup_sec
        while time.perf_counter() < end:
            await _shoot_once(client, step)
            await asyncio.sleep(0.05)

async def _stress_phase(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    주어진 설정(RPS, 동시성, 기간)에 따라 스트레스 테스트를 실행하고 통계를 반환합니다.
    이 함수는 리소스 모니터링 스레드를 시작하고 종료하는 역할을 포함합니다.
    """
    concurrency = int(step.get("concurrency", 10))
    rps = int(step.get("rps", 50))
    duration_sec = int(step.get("duration_sec", 10))

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    latencies: List[float] = []
    errors = 0
    total = 0

    # 리소스 모니터링 스레드 설정 및 시작
    monitor_conf = step.get("monitor") or {}
    mon_series: Dict[str, List[float]] = {}
    stop_evt = threading.Event()
    mon_thread = None
    if monitor_conf.get("enabled", True):
        mon_thread = threading.Thread(target=_sample_resources_loop, args=(stop_evt, monitor_conf, mon_series), daemon=True)
        mon_thread.start()

    async with httpx.AsyncClient(limits=limits, timeout=None) as client:
        await _warmup(client, step, int(step.get("warmup_sec", 0)))

        start = time.perf_counter()
        end = start + duration_sec

        while time.perf_counter() < end:
            tasks: List[asyncio.Task] = []
            for _ in range(rps):
                tasks.append(asyncio.create_task(_shoot_once(client, step)))
                await asyncio.sleep(1.0 / max(1, rps))
                
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for ok, latency_ms, _, _ in results:
                total += 1
                if not ok:
                    errors += 1
                latencies.append(latency_ms)

    # 모니터링 스레드 중지 및 집계
    if mon_thread is not None:
        stop_evt.set()
        mon_thread.join(timeout=1.0)
    
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)
    avg = statistics.mean(latencies) if latencies else 0.0
    err_rate = (errors / total) if total else 0.0

    resource_stats = _aggregate_mon(mon_series) if mon_series else {}

    return {
        "total": total,
        "errors": errors,
        "error_rate": err_rate,
        "latency_avg_ms": avg,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "latency_p99_ms": p99,
        "resources": resource_stats,
    }

async def _recover_phase(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    복구 테스트를 실행합니다.
    복구 API를 호출한 후, 헬스체크 URL을 주기적으로 폴링하여
    서비스가 지정된 SLA 이내로 복구되었는지 확인합니다.
    """
    recovery = step.get("recovery") or {}
    health_url = recovery.get("health_url")
    poll_interval = int(recovery.get("poll_interval_sec", 2))
    max_recovery_sec = int(recovery.get("max_recovery_sec", 60))
    sla_ms = int(recovery.get("recovery_sla_ms", 300))

    if not health_url:
        return {"recovery_checked": False, "within_sla": None, "last_latency_ms": None, "seconds_waited": 0}

    async with httpx.AsyncClient() as client:
        try:
            # 복구 API 호출 (서버 재시작 등)
            await client.post("http://127.0.0.1:8000/admin/recover", timeout=5.0)
        except Exception:
            pass

        waited = 0
        last_latency = None
        while waited <= max_recovery_sec:
            t0 = time.perf_counter()
            try:
                resp = await client.get(health_url, timeout=5.0)
                last_latency = (time.perf_counter() - t0) * 1000.0
                ok = (resp.status_code == 200)
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                status_str = data.get("status")
                
                # 복구 성공 조건: 200 OK + 'ok' 상태 + SLA 만족
                if ok and status_str == "ok" and last_latency is not None and last_latency <= sla_ms:
                    return {
                        "recovery_checked": True,
                        "within_sla": True,
                        "last_latency_ms": last_latency,
                        "seconds_waited": waited,
                    }
            except Exception:
                last_latency = None

            await asyncio.sleep(poll_interval)
            waited += poll_interval

        # 타임아웃
        return {
            "recovery_checked": True,
            "within_sla": False,
            "last_latency_ms": last_latency,
            "seconds_waited": waited,
        }

# =====================================================================
# 리소스 모니터링: 백그라운드 스레드
# =====================================================================
def _find_process_for_monitor(monitor: Dict[str, Any]) -> Optional[psutil.Process]:
    """
    모니터링 대상 프로세스를 찾습니다. pid, port, name_contains 순으로 탐색합니다.
    """
    pid = monitor.get("pid")
    port = monitor.get("port")
    name_contains = (monitor.get("name_contains") or "uvicorn").lower()

    try:
        if pid:
            return psutil.Process(int(pid))
    except Exception:
        pass

    if port:
        try:
            target_port = int(port)
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    conns = p.connections(kind="inet")
                    for c in conns:
                        if c.laddr and hasattr(c.laddr, "port") and c.laddr.port == target_port:
                            return p
                except Exception:
                    continue
        except Exception:
            pass

    if name_contains:
        try:
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                nm = (p.info.get("name") or "").lower()
                cl = " ".join(p.info.get("cmdline") or []).lower()
                if name_contains in nm or name_contains in cl:
                    return p
        except Exception:
            pass

    return None

def _sample_resources_loop(stop_evt: threading.Event, mon_conf: Dict[str, Any], out: Dict[str, List[float]]):
    """
    별도 스레드에서 주기적으로 시스템 및 프로세스 리소스를 샘플링합니다.
    `stop_evt`가 설정될 때까지 반복됩니다.
    """
    interval = float(mon_conf.get("interval_ms", 500)) / 1000.0
    series_limit = int(mon_conf.get("series_limit", 5 * 60 * 1000 / max(1, mon_conf.get("interval_ms", 500))))

    try:
        psutil.cpu_percent(None) # 첫 호출은 0을 반환하므로 미리 호출
    except Exception:
        pass

    proc = _find_process_for_monitor(mon_conf)
    last_net = psutil.net_io_counters() if hasattr(psutil, "net_io_counters") else None

    while not stop_evt.is_set():
        try:
            sys_cpu = psutil.cpu_percent(None)
            
            p_cpu = None
            p_mem_mb = None
            p_threads = None
            if proc and proc.is_running():
                p_cpu = proc.cpu_percent(None)
                mem = proc.memory_info().rss
                p_mem_mb = mem / (1024 * 1024)
                p_threads = proc.num_threads()
            else:
                proc = _find_process_for_monitor(mon_conf) # 프로세스 사망 시 재탐색 시도

            sent_kb = recv_kb = None
            now_net = psutil.net_io_counters()
            if last_net:
                sent_kb = max(0.0, (now_net.bytes_sent - last_net.bytes_sent) / 1024.0 / max(interval, 1e-6))
                recv_kb = max(0.0, (now_net.bytes_recv - last_net.bytes_recv) / 1024.0 / max(interval, 1e-6))
            last_net = now_net
            
            def push(key: str, val: Optional[float]):
                if val is not None:
                    arr = out.setdefault(key, [])
                    arr.append(float(val))
                    if len(arr) > series_limit:
                        del arr[: len(arr) - series_limit]

            push("system_cpu_pct", sys_cpu)
            push("process_cpu_pct", p_cpu)
            push("process_mem_mb", p_mem_mb)
            push("process_threads", p_threads)
            push("net_sent_kb", sent_kb)
            push("net_recv_kb", recv_kb)

        except Exception:
            pass
        
        stop_evt.wait(interval)

# =====================================================================
# 출력 유틸리티
# =====================================================================
def _box(title: str, lines: List[str]) -> None:
    """테스트 결과를 시각적으로 정리된 박스 형태로 출력합니다."""
    width = max([len(title) + 2] + [len(l) for l in lines]) + 2
    top = "┏" + "━" * (width - 2) + "┓"
    bot = "┗" + "━" * (width - 2) + "┛"
    print(top)
    print(f"┃ {title}".ljust(width - 1) + "┃")
    for l in lines:
        print(("┃ " + l).ljust(width - 1) + "┃")
    print(bot)

def _kv(k: str, v: str) -> str:
    """키-값 쌍의 포맷팅을 위한 헬퍼 함수입니다."""
    return f"{k:<16}: {v}"

def _fmt_triplet(stat: dict, unit: str = "", as_pct: bool = False) -> str:
    """평균, p95, 최대값을 포맷팅하여 반환합니다."""
    if not stat:
        return f"avg - / p95 - / max -{unit}"
    a = stat.get("avg")
    p = stat.get("p95")
    m = stat.get("max")
    if as_pct:
        def pct(x: Optional[float]) -> str: return "-" if x is None else f"{x:.1f}%"
        return f"avg {pct(a)} / p95 {pct(p)} / max {pct(m)}"
    else:
        def num(x: Optional[float]) -> str: return "-" if x is None else f"{x:.1f}{unit}"
        return f"avg {num(a)} / p95 {num(p)} / max {num(m)}"

def _fmt_ms(v: Optional[float]) -> str:
    """밀리초 단위를 포맷팅합니다."""
    return "-" if v is None else f"{v:.1f} ms"

def _fmt_pct(v: Optional[float]) -> str:
    """백분율을 포맷팅합니다."""
    if v is None:
        return "-"
    return f"{(v*100):.1f}%"

def _percentile(values: List[float], p: float) -> float:
    """값 리스트에서 지정된 백분위수를 계산합니다."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[k]

def _aggregate_series(values: List[float]) -> Dict[str, float]:
    """값 시리즈의 통계(평균, p95, 최대)를 집계합니다."""
    if not values:
        return {"avg": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "avg": statistics.mean(values),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }

def _aggregate_mon(mon: Dict[str, List[float]]) -> Dict[str, Any]:
    """모니터링된 모든 리소스 시리즈를 집계합니다."""
    return {
        "system_cpu_pct": _aggregate_series(mon.get("system_cpu_pct", [])),
        "process_cpu_pct": _aggregate_series(mon.get("process_cpu_pct", [])),
        "process_mem_mb": _aggregate_series(mon.get("process_mem_mb", [])),
        "process_threads": _aggregate_series(mon.get("process_threads", [])),
        "net_sent_kb": _aggregate_series(mon.get("net_sent_kb", [])),
        "net_recv_kb": _aggregate_series(mon.get("net_recv_kb", [])),
        "samples": len(mon.get("system_cpu_pct", [])),
    }

def emit_stress_block(metrics: Dict[str, Any], step: Dict[str, Any]) -> None:
    sla_p95 = float(step.get("sla_ms_p95", 0))
    max_err = float(step.get("max_error_rate", 1.0))
    pass_latency = (metrics["latency_p95_ms"] <= sla_p95) if sla_p95 > 0 else True
    pass_error = (metrics["error_rate"] <= max_err)
    status = "PASS" if (pass_latency and pass_error) else "FAIL"

    details = {
        "requests":        f"{metrics['total']} (errors {metrics['errors']})",
        "error_rate":      f"{metrics['error_rate']*100:.1f}%",
        "latency_p50":     f"{metrics['latency_p50_ms']:.1f} ms",
        "latency_p95":     f"{metrics['latency_p95_ms']:.1f} ms",
        "latency_p99":     f"{metrics['latency_p99_ms']:.1f} ms",
        "latency_avg":     f"{metrics['latency_avg_ms']:.1f} ms",
        "SLA_p95":         ("-" if sla_p95 <= 0 else f"{sla_p95:.1f} ms"),
        "err_threshold":   f"{max_err:.3f}",
    }
    print_block("RELIABILITY", "stress_result", status, details=details)

def emit_recovery_block(rec: Dict[str, Any], step: Dict[str, Any]) -> None:
    sla_ms = int((step.get("recovery") or {}).get("recovery_sla_ms", 300))
    checked = rec.get("recovery_checked")
    within = rec.get("within_sla")
    if not checked:
        status, reason = "SKIP", "recovery_checked=False"
    else:
        status = "PASS" if within is True else "FAIL"
        reason = None

    details = {
        "within_sla":   str(within),
        "last_latency": ("-" if rec.get("last_latency_ms") is None else f"{rec['last_latency_ms']:.1f} ms"),
        "waited":       f"{rec.get('seconds_waited', 0)} s",
        "SLA(health)":  f"{sla_ms:.1f} ms",
    }
    print_block("RELIABILITY", "recovery_result", status, reason=reason, details=details)

def emit_resource_block(resources: Optional[dict]) -> None:
    if not resources or resources.get("samples", 0) == 0:
        print_block("RELIABILITY", "resources", "SKIP",
                     reason="No resource samples collected",
                     details={"samples": 0})
        return

    def _triplet(d: dict, unit: str = "", pct=False):
        if not d: return "avg - / p95 - / max -"
        a, p, m = d.get("avg"), d.get("p95"), d.get("max")
        if pct:
            fmt = lambda x: "-" if x is None else f"{x:.1f}%"
        else:
            fmt = lambda x: "-" if x is None else f"{x:.1f}{unit}"
        return f"avg {fmt(a)} / p95 {fmt(p)} / max {fmt(m)}"

    details = {
        "samples":       resources.get("samples", 0),
        "system_cpu":    _triplet(resources.get("system_cpu_pct") or {}, pct=True),
        "proc_cpu":      _triplet(resources.get("process_cpu_pct") or {}, pct=True),
        "proc_mem":      _triplet(resources.get("process_mem_mb") or {}, unit=" MB"),
        "threads":       _triplet(resources.get("process_threads") or {}, unit=""),
        "net_tx":        _triplet(resources.get("net_sent_kb") or {}, unit=" KB/s"),
        "net_rx":        _triplet(resources.get("net_recv_kb") or {}, unit=" KB/s"),
    }
    print_block("RELIABILITY", "resources", "PASS", details=details)