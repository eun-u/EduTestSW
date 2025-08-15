# src/assessments/reliability.py
import asyncio
import time
import json
from typing import Dict, Any, List, Tuple
import httpx
import statistics

def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = max(0, min(len(values_sorted) - 1, int(round(p * (len(values_sorted) - 1)))))
    return values_sorted[k]

async def _shoot_once(client: httpx.AsyncClient, step: Dict[str, Any]) -> Tuple[bool, float, int, str]:
    """
    ??踰덉쓽 ?붿껌 諛쒖궗. (?깃났?щ?, latency_ms, status_code, ?먮윭硫붿떆吏)
    ?깃났 ?먯젙: status ??success_statuses
    """
    url = step["target_url"]
    method = step.get("method", "GET").upper()
    headers = step.get("headers") or {}
    timeout_ms = step.get("timeout_ms", 2000)
    success_statuses = set(step.get("success_statuses", [200]))

    data = None
    json_payload = None
    if "payload" in step and step["payload"] is not None:
        # Content-Type ?ㅻ뜑???곕씪 ?꾩넚 諛⑹떇 ?좏깮(湲곕낯? JSON)
        ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
        if "application/json" in ct or ct == "":
            json_payload = step["payload"]
        else:
            data = step["payload"]

    t0 = time.perf_counter()
    try:
        resp = await client.request(
            method,
            url,
            headers=headers,
            json=json_payload,
            data=data,
            timeout=timeout_ms / 1000.0,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        ok = resp.status_code in success_statuses
        return ok, latency_ms, resp.status_code, ""
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return False, latency_ms, 0, str(e)

async def _warmup(client: httpx.AsyncClient, step: Dict[str, Any], warmup_sec: int):
    if warmup_sec <= 0:
        return
    end = time.perf_counter() + warmup_sec
    while time.perf_counter() < end:
        await _shoot_once(client, step)
        await asyncio.sleep(0.05)

async def _stress_phase(step: Dict[str, Any]) -> Dict[str, Any]:
    """
    RPS? ?숈떆???쒗븳?쇰줈 duration_sec ?숈븞 ?붿껌???섍퀬 寃곌낵 ?듦퀎瑜?由ы꽩
    """
    concurrency = int(step.get("concurrency", 10))
    rps = int(step.get("rps", 50))
    duration_sec = int(step.get("duration_sec", 10))

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    latencies: List[float] = []
    errors = 0
    total = 0

    async with httpx.AsyncClient(limits=limits, timeout=None) as client:
        # ?뚮컢??
        await _warmup(client, step, int(step.get("warmup_sec", 0)))

        start = time.perf_counter()
        end = start + duration_sec

        # 留?珥덈쭏??rps留뚰겮 ?ㅼ?以?
        while time.perf_counter() < end:
            second_end = min(end, time.perf_counter() + 1.0)
            # ??1珥??숈븞 rps???ㅽ뻾
            batch: List[asyncio.Task] = []
            for _ in range(rps):
                batch.append(asyncio.create_task(_shoot_once(client, step)))
                await asyncio.sleep(1.0 / max(1, rps))  # 媛꾨떒??pace

            # 1珥?諛곗튂 寃곌낵 ?섏쭛
            results = await asyncio.gather(*batch, return_exceptions=False)
            for ok, latency_ms, status, err in results:
                total += 1
                if not ok:
                    errors += 1
                latencies.append(latency_ms)

            # ?⑥? ?쒓컙???덈떎硫??ㅼ쓬 珥덈줈
            remain = second_end - time.perf_counter()
            if remain > 0:
                await asyncio.sleep(remain)

    # ?듦퀎
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
    """
    /admin/recover ?몄텧 ??health_url??二쇨린?곸쑝濡??대쭅?섏뿬
    SLA(recovery_sla_ms) ?대궡濡??뚮났?섎뒗吏 ?뺤씤
    """
    recovery = step.get("recovery") or {}
    health_url = recovery.get("health_url")
    poll_interval = int(recovery.get("poll_interval_sec", 2))
    max_recovery_sec = int(recovery.get("max_recovery_sec", 60))
    sla_ms = int(recovery.get("recovery_sla_ms", 300))

    if not health_url:
        return {"recovery_checked": False, "within_sla": None, "last_latency_ms": None, "seconds_waited": 0}

    async with httpx.AsyncClient() as client:
        # 1) ?곗꽑 ?뺤긽???쒕룄
        try:
            await client.post("http://127.0.0.1:8000/admin/recover", timeout=5.0)
        except Exception:
            pass

        # 2) ?대쭅
        waited = 0
        last_latency = None
        while waited <= max_recovery_sec:
            t0 = time.perf_counter()
            try:
                resp = await client.get(health_url, timeout=5.0)
                last_latency = (time.perf_counter() - t0) * 1000.0
                ok = (resp.status_code == 200)
                # server.py???뺤긽??{"status":"ok"} 瑜?諛섑솚
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                status_str = data.get("status")
                if ok and status_str == "ok" and last_latency <= sla_ms:
                    return {
                        "recovery_checked": True,
                        "within_sla": True,
                        "last_latency_ms": last_latency,
                        "seconds_waited": waited,
                    }
            except Exception:
                # ignore and keep polling
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
    """
    runner?먯꽌 ?몄텧?섎뒗 ?뷀듃由ы룷?명듃
    """
    if step.get("mode") not in {"stress", "load"}:
        print("[reliability] 吏?먰븯吏 ?딅뒗 mode?낅땲?? mode=stress|load")
        return

    print("[reliability] ?ㅽ듃?덉뒪 ?뚯뒪???쒖옉")
    metrics = asyncio.run(_stress_phase(step))
    print(json.dumps({"phase": "stress", **metrics}, ensure_ascii=False, indent=2))

    # ?먯젙
    sla_p95 = float(step.get("sla_ms_p95", 0))
    max_err = float(step.get("max_error_rate", 1.0))
    pass_latency = (metrics["latency_p95_ms"] <= sla_p95) if sla_p95 > 0 else True
    pass_error = (metrics["error_rate"] <= max_err)
    if pass_latency and pass_error:
        print(f"[PASS][reliability] p95??sla_p95}ms, error_rate??max_err}")
    else:
        print(f"[FAIL][reliability] p95={metrics['latency_p95_ms']:.1f}ms (SLA {sla_p95}), "
              f"error_rate={metrics['error_rate']:.3f} (max {max_err})")

    # 蹂듦뎄 ?뺤씤
    if step.get("recovery"):
        print("[reliability] 蹂듦뎄 ?뺤씤 ?④퀎 ?쒖옉")
        rec = asyncio.run(_recover_phase(step))
        print(json.dumps({"phase": "recovery", **rec}, ensure_ascii=False, indent=2))
        if rec.get("recovery_checked") and rec.get("within_sla") is True:
            print("[PASS][recovery] ?ъ뒪泥댄겕媛 SLA ?대궡濡??뚮났?섏뿀?듬땲??")
        elif rec.get("recovery_checked"):
            print("[FAIL][recovery] ?ㅼ젙???쒓컙 ??SLA ?대궡濡??뚮났?섏? 紐삵뻽?듬땲??")

# run_reliability.py
import subprocess, time, os, sys, requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from core.parser import parse_routine
from core.driver_backend import BackendDriver

def wait_health(url="http://127.0.0.1:8000/health", timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

if __name__ == "__main__":
    # 1) ?쒕쾭 湲곕룞
    server = subprocess.Popen(
        ["python", "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    )
    print("[INFO] ?쒕쾭 遺???湲겸?)
    ok = wait_health()
    if not ok:
        print("[WARN] /health ?묐떟 ?湲?珥덇낵. 洹몃옒??吏꾪뻾?⑸땲??")

    try:
        # 2) reliability.json 濡쒕뱶
        routine = parse_routine("src/routines/reliability.json")
        driver = BackendDriver()

        # 3) ?ㅽ뻾
        print("[INFO] 遺???뚯뒪???쒖옉")
        run_routine(routine, driver)

    finally:
        print("[INFO] ?쒕쾭 醫낅즺")
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
