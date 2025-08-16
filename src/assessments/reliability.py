# src/assessments/reliability.py
import asyncio
import time
import json
import statistics
from typing import Dict, Any, List, Tuple, Optional
import httpx

# === New: resource monitoring ===
import psutil
import threading
from datetime import datetime

# ───────────── resource pretty box (추가) ─────────────
def _fmt_triplet(stat: dict, unit: str = "", as_pct: bool = False) -> str:
    if not stat:
        return f"avg - / p95 - / max -{unit}"
    a = stat.get("avg")
    p = stat.get("p95")
    m = stat.get("max")
    if as_pct:
        def pct(x): return "-" if x is None else f"{x:.1f}%"
        return f"avg {pct(a)} / p95 {pct(p)} / max {pct(m)}"
    else:
        def num(x): return "-" if x is None else f"{x:.1f}{unit}"
        return f"avg {num(a)} / p95 {num(p)} / max {num(m)}"

def _print_resource_snapshot(resources: Optional[dict]) -> None:
    if not resources or resources.get("samples", 0) == 0:
        _box("Reliability - Resources", [
            _kv("Samples", "0"),
            _kv("Note", "No resource samples collected"),
        ])
        return

    sc = resources.get("system_cpu_pct") or {}
    pc = resources.get("process_cpu_pct") or {}
    pm = resources.get("process_mem_mb") or {}
    pt = resources.get("process_threads") or {}
    ns = resources.get("net_sent_kb") or {}
    nr = resources.get("net_recv_kb") or {}

    lines = [
        _kv("Samples", str(resources.get("samples", 0))),
        _kv("System CPU", _fmt_triplet(sc, as_pct=True)),
        _kv("Proc CPU",   _fmt_triplet(pc, as_pct=True)),
        _kv("Proc Mem",   _fmt_triplet(pm, unit=" MB")),
        _kv("Threads",    _fmt_triplet(pt, unit="")),
        _kv("Net TX",     _fmt_triplet(ns, unit=" KB/s")),
        _kv("Net RX",     _fmt_triplet(nr, unit=" KB/s")),
    ]
    _box("Reliability - Resources", lines)

# ───────────── pretty print helpers (출력만 추가) ─────────────
def _box(title: str, lines: List[str]) -> None:
    width = max([len(title) + 2] + [len(l) for l in lines]) + 2
    top = "┏" + "━" * (width - 2) + "┓"
    bot = "┗" + "━" * (width - 2) + "┛"
    print(top)
    print(f"┃ {title}".ljust(width - 1) + "┃")
    for l in lines:
        print(("┃ " + l).ljust(width - 1) + "┃")
    print(bot)

def _kv(k: str, v: str) -> str:
    return f"{k:<16}: {v}"

def _fmt_ms(v: Optional[float]) -> str:
    return "-" if v is None else f"{v:.1f} ms"

def _fmt_pct(v: Optional[float], scale_1=False) -> str:
    if v is None:
        return "-"
    return f"{(v*100 if not scale_1 else v):.1f}%"

def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[k]

async def _shoot_once(client: httpx.AsyncClient, step: Dict[str, Any]) -> Tuple[bool, float, int, str]:
    """One request shot: return (ok, latency_ms, status_code, err_msg)."""
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
    if warmup_sec and warmup_sec > 0:
        end = time.perf_counter() + warmup_sec
        while time.perf_counter() < end:
            await _shoot_once(client, step)
            await asyncio.sleep(0.05)

# ─────────────────────────────────────────────────────────
#            Resource monitor (system / process)
# ─────────────────────────────────────────────────────────
def _find_process_for_monitor(monitor: Dict[str, Any]) -> Optional[psutil.Process]:
    """
    우선순위: pid -> port -> name_contains
    """
    pid = monitor.get("pid")
    port = monitor.get("port")
    name_contains = (monitor.get("name_contains") or "uvicorn").lower()

    try:
        if pid:
            return psutil.Process(int(pid))
    except Exception:
        pass

    # by port
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

    # by name contains (uvicorn 등)
    try:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            nm = (p.info.get("name") or "").lower()
            cl = " ".join(p.info.get("cmdline") or []).lower()
            if name_contains in nm or name_contains in cl:
                return p
    except Exception:
        pass

    return None

def _aggregate_series(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"avg": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "avg": statistics.mean(values),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }

def _aggregate_mon(mon: Dict[str, List[float]]) -> Dict[str, Any]:
    """values 시리즈의 통계를 각 항목별로 계산"""
    return {
        "system_cpu_pct": _aggregate_series(mon.get("system_cpu_pct", [])),
        "process_cpu_pct": _aggregate_series(mon.get("process_cpu_pct", [])),
        "process_mem_mb": _aggregate_series(mon.get("process_mem_mb", [])),
        "process_threads": _aggregate_series(mon.get("process_threads", [])),
        "net_sent_kb": _aggregate_series(mon.get("net_sent_kb", [])),
        "net_recv_kb": _aggregate_series(mon.get("net_recv_kb", [])),
        "samples": len(mon.get("system_cpu_pct", [])),
    }

def _sample_resources_loop(stop_evt: threading.Event, mon_conf: Dict[str, Any], out: Dict[str, List[float]]):
    """
    별도 스레드에서 동작. stop_evt.set() 될 때까지 주기적으로 샘플링.
    out에 시리즈 누적.
    """
    interval = float(mon_conf.get("interval_ms", 500)) / 1000.0
    series_limit = int(mon_conf.get("series_limit", 5 * 60 * 1000 / max(1, mon_conf.get("interval_ms", 500))))  # 기본 5분 분량

    # system priming
    try:
        psutil.cpu_percent(None)
    except Exception:
        pass

    proc = _find_process_for_monitor(mon_conf)
    last_net = psutil.net_io_counters() if hasattr(psutil, "net_io_counters") else None

    while not stop_evt.is_set():
        try:
            # system
            sys_cpu = psutil.cpu_percent(None)

            # process
            p_cpu = None
            p_mem_mb = None
            p_threads = None
            if proc and proc.is_running():
                try:
                    p_cpu = proc.cpu_percent(None)
                    mem = proc.memory_info().rss
                    p_mem_mb = mem / (1024 * 1024)
                    p_threads = proc.num_threads()
                except Exception:
                    proc = _find_process_for_monitor(mon_conf)  # 재탐색 시도

            # network (system-level deltas)
            sent_kb = recv_kb = None
            try:
                now_net = psutil.net_io_counters()
                if last_net:
                    sent_kb = max(0.0, (now_net.bytes_sent - last_net.bytes_sent) / 1024.0 / max(interval, 1e-6))
                    recv_kb = max(0.0, (now_net.bytes_recv - last_net.bytes_recv) / 1024.0 / max(interval, 1e-6))
                last_net = now_net
            except Exception:
                pass

            # append
            def push(key: str, val: Optional[float]):
                if val is None:
                    return
                arr = out.setdefault(key, [])
                arr.append(float(val))
                # trim
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

async def _stress_phase(step: Dict[str, Any]) -> Dict[str, Any]:
    """Run stress for duration_sec with given RPS & concurrency; return stats + resource monitor stats."""
    concurrency = int(step.get("concurrency", 10))
    rps = int(step.get("rps", 50))
    duration_sec = int(step.get("duration_sec", 10))

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    latencies: List[float] = []
    errors = 0
    total = 0

    # --- resource monitor setup ---
    monitor_conf = step.get("monitor") or {}  # {"pid":..., "port":8000, "name_contains":"uvicorn", "interval_ms":500, "series_limit":600}
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
            second_end = min(end, time.perf_counter() + 1.0)

            tasks: List[asyncio.Task] = []
            for _ in range(rps):
                tasks.append(asyncio.create_task(_shoot_once(client, step)))
                await asyncio.sleep(1.0 / max(1, rps))

            results = await asyncio.gather(*tasks, return_exceptions=False)
            for ok, latency_ms, status, err in results:
                total += 1
                if not ok:
                    errors += 1
                latencies.append(latency_ms)

            remain = second_end - time.perf_counter()
            if remain > 0:
                await asyncio.sleep(remain)

    # stop monitor
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
    """Call /admin/recover then poll health_url until SLA or timeout."""
    recovery = step.get("recovery") or {}
    health_url = recovery.get("health_url")
    poll_interval = int(recovery.get("poll_interval_sec", 2))
    max_recovery_sec = int(recovery.get("max_recovery_sec", 60))
    sla_ms = int(recovery.get("recovery_sla_ms", 300))

    if not health_url:
        return {"recovery_checked": False, "within_sla": None, "last_latency_ms": None, "seconds_waited": 0}

    async with httpx.AsyncClient() as client:
        try:
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

        return {
            "recovery_checked": True,
            "within_sla": False,
            "last_latency_ms": last_latency,
            "seconds_waited": waited,
        }

def _print_stress_summary(metrics: Dict[str, Any], step: Dict[str, Any]) -> None:
    """예쁜 요약 박스 (기존 출력은 그대로 유지 + 추가 요약)"""
    sla_p95 = float(step.get("sla_ms_p95", 0))
    max_err = float(step.get("max_error_rate", 1.0))
    pass_latency = (metrics["latency_p95_ms"] <= sla_p95) if sla_p95 > 0 else True
    pass_error = (metrics["error_rate"] <= max_err)
    overall = "PASS" if (pass_latency and pass_error) else "FAIL"

    lines = [
        _kv("Status", overall),
        _kv("Requests", f"{metrics['total']} (errors {metrics['errors']})"),
        _kv("Error Rate", _fmt_pct(metrics['error_rate'])),
        _kv("Latency p50", _fmt_ms(metrics['latency_p50_ms'])),
        _kv("Latency p95", _fmt_ms(metrics['latency_p95_ms'])),
        _kv("Latency p99", _fmt_ms(metrics['latency_p99_ms'])),
        _kv("Avg Latency", _fmt_ms(metrics['latency_avg_ms'])),
    ]
    if sla_p95 > 0:
        lines.append(_kv("SLA p95", _fmt_ms(sla_p95)))
    lines.append(_kv("Err threshold", f"{max_err:.3f}"))

    # Resource summary (있을 때만)
    res = metrics.get("resources") or {}
    if res and res.get("samples", 0) > 0:
        sc = res.get("system_cpu_pct") or {}
        pc = res.get("process_cpu_pct") or {}
        pm = res.get("process_mem_mb") or {}
        lines += [
            "",
            _kv("Res samples", str(res.get("samples", 0))),
            _kv("System CPU p95", f"{sc.get('p95', 0.0):.1f}%"),
            _kv("Proc CPU p95", f"{pc.get('p95', 0.0):.1f}%"),
            _kv("Proc Mem p95", f"{pm.get('p95', 0.0):.1f} MB"),
        ]

    _box("Reliability - Stress Summary", lines)

def _print_recovery_summary(rec: Dict[str, Any], step: Dict[str, Any]) -> None:
    sla_ms = int((step.get("recovery") or {}).get("recovery_sla_ms", 300))
    checked = rec.get("recovery_checked")
    within = rec.get("within_sla")
    status = "SKIP"
    if checked:
        status = "PASS" if within is True else "FAIL"
    lines = [
        _kv("Status", status),
        _kv("Within SLA", str(within)),
        _kv("Last latency", _fmt_ms(rec.get("last_latency_ms"))),
        _kv("Waited", f"{rec.get('seconds_waited', 0)} s"),
        _kv("SLA (health)", _fmt_ms(sla_ms)),
    ]
    _box("Reliability - Recovery Summary", lines)

def check(driver, step: Dict[str, Any]):
    """Entry point called by runner."""
    if step.get("mode") not in {"stress", "load"}:
        print("[reliability] 지원하지 않는 mode입니다. mode=stress|load")
        return

    print("[reliability] 스트레스 테스트 시작")
    metrics = asyncio.run(_stress_phase(step))

    # 기존 상세 JSON 출력(유지)
    print(json.dumps({"phase": "stress", **metrics}, ensure_ascii=False, indent=2))

    # 기존 SLA 판정 로그(유지)
    sla_p95 = float(step.get("sla_ms_p95", 0))
    max_err = float(step.get("max_error_rate", 1.0))
    pass_latency = (metrics["latency_p95_ms"] <= sla_p95) if sla_p95 > 0 else True
    pass_error = (metrics["error_rate"] <= max_err)

    if pass_latency and pass_error:
        print(
            "[PASS][reliability] p95={:.1f}ms <= {:.1f}ms, error_rate={:.3f} <= {:.3f}".format(
                metrics["latency_p95_ms"], sla_p95, metrics["error_rate"], max_err
            )
        )
    else:
        print(
            "[FAIL][reliability] p95={:.1f}ms (SLA {:.1f}ms), error_rate={:.3f} (max {:.3f})".format(
                metrics["latency_p95_ms"], sla_p95, metrics["error_rate"], max_err
            )
        )

    # ✅ 새로 추가: 요약 박스
    _print_stress_summary(metrics, step)

    # Recovery check
    if step.get("recovery"):
        print("[reliability] 복구 확인 단계 시작")
        rec = asyncio.run(_recover_phase(step))

        # 기존 상세 JSON 출력(유지)
        print(json.dumps({"phase": "recovery", **rec}, ensure_ascii=False, indent=2))
        if rec.get("recovery_checked") and rec.get("within_sla") is True:
            print("[PASS][recovery] 헬스체크가 SLA 이내로 회복되었습니다.")
        elif rec.get("recovery_checked"):
            print("[FAIL][recovery] 설정된 시간 내 SLA 이내로 회복하지 못했습니다.")

        # ✅ 새로 추가: 복구 요약 박스
        _print_recovery_summary(rec, step)
        
            # ✅ 새로 추가: 요약 박스
        _print_stress_summary(metrics, step)

        # ✅ 새로 추가: 리소스 스냅샷 박스
        _print_resource_snapshot(metrics.get("resources"))

        # Recovery check
        if step.get("recovery"):
            ...
            # ✅ 새로 추가: 복구 요약 박스
            _print_recovery_summary(rec, step)

