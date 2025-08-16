# src/assessments/reliability.py
import asyncio
import time
import json
import statistics
from typing import Dict, Any, List, Tuple
import httpx

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

async def _stress_phase(step: Dict[str, Any]) -> Dict[str, Any]:
    """Run stress for duration_sec with given RPS & concurrency; return stats."""
    concurrency = int(step.get("concurrency", 10))
    rps = int(step.get("rps", 50))
    duration_sec = int(step.get("duration_sec", 10))

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    latencies: List[float] = []
    errors = 0
    total = 0

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

    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)
    avg = statistics.mean(latencies) if latencies else 0.0
    err_rate = (errors / total) if total else 0.0

    return {
        "total": total,
        "errors": errors,
        "error_rate": err_rate,
        "latency_avg_ms": avg,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "latency_p99_ms": p99,
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

def check(driver, step: Dict[str, Any]):
    """Entry point called by runner."""
    if step.get("mode") not in {"stress", "load"}:
        print("[reliability] 지원하지 않는 mode입니다. mode=stress|load")
        return

    print("[reliability] 스트레스 테스트 시작")
    metrics = asyncio.run(_stress_phase(step))
    print(json.dumps({"phase": "stress", **metrics}, ensure_ascii=False, indent=2))

    # Evaluate against SLA (ASCII only; no fancy symbols)
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

    # Recovery check
    if step.get("recovery"):
        print("[reliability] 복구 확인 단계 시작")
        rec = asyncio.run(_recover_phase(step))
        print(json.dumps({"phase": "recovery", **rec}, ensure_ascii=False, indent=2))
        if rec.get("recovery_checked") and rec.get("within_sla") is True:
            print("[PASS][recovery] 헬스체크가 SLA 이내로 회복되었습니다.")
        elif rec.get("recovery_checked"):
            print("[FAIL][recovery] 설정된 시간 내 SLA 이내로 회복하지 못했습니다.")
