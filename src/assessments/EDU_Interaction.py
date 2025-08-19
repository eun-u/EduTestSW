# src/assessments/interaction.py
# 교육용 LMS/EBS 상호작용 품질 검사 모듈 (완성본)
# - 메시징 전달 지연
# - 읽음(리드 레시트) 반영 지연
# - 대량 방송(팬아웃) 성공률/지연
# - 교차기기 동기화(웹/모바일) 일관성
# - 중복/폭주 알림 제어(아이덤포턴시)
# - 실시간 채팅(WebSocket) 왕복 지연(선택)
# - 접근성 라벨/대체텍스트 & 읽음 공개 범위(UI, Playwright)

from __future__ import annotations
import time, math, uuid, json
from typing import Any, Dict, List, Optional
import requests

try:
    # 선택 의존성: 실시간 채팅 테스트에만 사용
    import websockets  # type: ignore
except Exception:  # noqa: E722
    websockets = None

# performance 유틸 재사용(있으면 사용)
try:
    from assessments.performance import summarize, judge, percentile
except Exception:
    # 안전장치(직접 실행 시 의존성 없을 때 최소 동작 보장)
    def percentile(values: List[float], p: float) -> float:
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
        xs = [x for x in samples if isinstance(x, (int, float)) and math.isfinite(x)]
        xs.sort()
        return {
            "count": len(samples),
            "finite_count": len(xs),
            "errors": len(samples) - len(xs),
            "avg": (sum(xs) / len(xs)) if xs else float("inf"),
            "p90": percentile(xs, 90) if xs else float("inf"),
            "p95": percentile(xs, 95) if xs else float("inf"),
            "p99": percentile(xs, 99) if xs else float("inf"),
            "min": xs[0] if xs else float("inf"),
            "max": xs[-1] if xs else float("inf"),
        }

    def judge(stats: Dict[str, float], threshold_s: float, rule: str = "p95<=threshold"):
        metric = rule.split("<=")[0].strip()
        val = stats.get(metric)
        ok = (val is not None) and (val <= threshold_s)
        reason = f"{metric}={val:.4f}s, threshold={threshold_s:.4f}s → {'PASS' if ok else 'FAIL'}"
        return ok, reason


# ------------------------------------------------------------
# 공통 유틸
# ------------------------------------------------------------
def _get_by_path(obj: Any, path: Optional[str]) -> Any:
    """JSON에서 'a.b.c' 경로 값 안전 추출 (없으면 None)"""
    if not path:
        return None
    cur = obj
    for key in path.split('.'):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list):
            try:
                idx = int(key)
                cur = cur[idx]
            except Exception:
                return None
        else:
            return None
    return cur

def _headers(token: Optional[str] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra:
        h.update(extra)
    return h

def _post(url: str, payload: Dict[str, Any], token: Optional[str] = None, timeout: float = 10.0, headers: Optional[Dict[str,str]] = None) -> requests.Response:
    h = _headers(token)
    if headers:
        h.update(headers)
    return requests.post(url, headers=h, json=payload, timeout=timeout)

def _get(url: str, token: Optional[str] = None, timeout: float = 10.0, headers: Optional[Dict[str,str]] = None) -> requests.Response:
    h = _headers(token)
    if headers:
        h.update(headers)
    return requests.get(url, headers=h, timeout=timeout)


# ------------------------------------------------------------
# 엔트리 포인트
# ------------------------------------------------------------
def check(driver, step: Dict[str, Any]):
    t = step.get("type")
    if t == "messaging_latency":
        return _messaging_latency(step)
    elif t == "read_receipt_latency":
        return _read_receipt_latency(step)
    elif t == "broadcast_fanout":
        return _broadcast_fanout(step)
    elif t == "cross_device_sync":
        return _cross_device_sync(step)
    elif t == "dedup_guard":
        return _dedup_guard(step)
    elif t == "realtime_chat_latency_ws":
        return _realtime_chat_latency_ws(step)
    elif t == "accessibility_labels":
        return _accessibility_labels(step, driver)
    elif t == "privacy_scope_check_ui":
        return _privacy_scope_check_ui(step, driver)
    else:
        raise ValueError(f"[INTERACTION] 알 수 없는 type: {t}")


# ------------------------------------------------------------
# 1) 메시징 전달 지연 (교원→학생 1:1 쪽지)  p95 ≤ 3s
# ------------------------------------------------------------
def _messaging_latency(step: Dict[str, Any]) -> Dict[str, Any]:
    send_url: str = step["send_url"]
    inbox_url: str = step["inbox_url"]
    auth = step.get("auth", {})
    sender_token = auth.get("sender_token")
    receiver_token = auth.get("receiver_token")
    headers = step.get("headers")  # 선택: 맞춤 헤더

    message_tmpl: Dict[str, Any] = step.get("message", {"text": "[test] {i}"})
    id_field: str = step.get("id_field", "client_msg_id")
    list_path: str = step.get("list_path", "items")
    id_path: str = step.get("id_path", id_field)

    repeats: int = int(step.get("repeats", 10))
    poll_interval_s: float = float(step.get("poll_interval_s", 0.2))
    timeout_s: float = float(step.get("timeout_s", 10.0))

    threshold_s: float = float(step.get("threshold_s", 3.0))
    rule: str = step.get("rule", "p95<=threshold")

    samples: List[float] = []

    print("\n[INTERACTION > 메시징 전달 지연]")
    for i in range(repeats):
        msg_id = str(uuid.uuid4())
        payload = json.loads(json.dumps(message_tmpl).replace("{i}", str(i)))
        payload[id_field] = msg_id

        t0 = time.perf_counter()
        try:
            r = _post(send_url, payload, token=sender_token, headers=headers)
            r.raise_for_status()
        except Exception as e:
            print(f"  - 전송 실패: {e}")
            samples.append(float("inf"))
            continue

        # 수신함 폴링: msg_id가 나타날 때까지 대기
        found = False
        deadline = t0 + timeout_s
        while time.perf_counter() < deadline:
            try:
                ir = _get(inbox_url, token=receiver_token, headers=headers)
                data = ir.json()
                items = _get_by_path(data, list_path) or []
                for it in items:
                    if _get_by_path(it, id_path) == msg_id:
                        found = True
                        break
                if found:
                    break
            except Exception:
                pass
            time.sleep(poll_interval_s)

        dt = time.perf_counter() - t0
        samples.append(dt if found else float("inf"))
        print(f"  - #{i+1:02d} 지연 = {dt:.3f}s {'(FOUND)' if found else '(TIMEOUT)'}")

    stats = summarize(samples)
    ok, reason = judge(stats, threshold_s, rule)

    print("\n  * 결과:")
    print(f"    - count={stats['count']}, avg={stats['avg']:.3f}s, p95={stats['p95']:.3f}s")
    print(f"    - 기준: {rule} / threshold={threshold_s:.3f}s -> {'PASS' if ok else 'FAIL'} ({reason})")

    return {"stats": stats, "pass": ok, "reason": reason, "samples": samples}


# ------------------------------------------------------------
# 2) 읽음(리드 레시트) 반영 지연 (학생 열람 → 강사 화면 갱신) 60s 이내
# ------------------------------------------------------------
def _read_receipt_latency(step: Dict[str, Any]) -> Dict[str, Any]:
    mark_read_url: str = step["mark_read_url"]          # 학생 측 호출
    sender_thread_url: str = step["sender_thread_url"]  # 강사 측 스레드 조회
    headers = step.get("headers")

    auth = step.get("auth", {})
    sender_token = auth.get("sender_token")     # 강사
    receiver_token = auth.get("receiver_token") # 학생

    thread_id: Optional[str] = step.get("thread_id")
    thread_id_path: Optional[str] = step.get("thread_id_path")
    read_flag_path: str = step.get("read_flag_path", "last_message.read")

    repeats: int = int(step.get("repeats", 5))
    threshold_s: float = float(step.get("threshold_s", 60.0))

    samples: List[float] = []

    print("\n[INTERACTION > 읽음 반영 지연]")
    for i in range(repeats):
        # 1) 강사 스레드 조회 → thread_id 확보
        try:
            tr = _get(sender_thread_url, token=sender_token, headers=headers)
            tr.raise_for_status()
            tdata = tr.json()
            tid = thread_id or _get_by_path(tdata, thread_id_path)
        except Exception as e:
            print(f"  - 스레드 조회 실패: {e}")
            samples.append(float("inf"))
            continue

        # 2) 학생: 읽음 표시
        payload = {"thread_id": tid}
        t0 = time.perf_counter()
        try:
            rr = _post(mark_read_url, payload, token=receiver_token, headers=headers)
            rr.raise_for_status()
        except Exception as e:
            print(f"  - 읽음 마킹 실패: {e}")
            samples.append(float("inf"))
            continue

        # 3) 강사 화면 폴링 → read_flag true 확인
        found = False
        while time.perf_counter() - t0 < threshold_s:
            try:
                tr2 = _get(sender_thread_url, token=sender_token, headers=headers)
                data2 = tr2.json()
                flag = _get_by_path(data2, read_flag_path)
                if bool(flag):
                    found = True
                    break
            except Exception:
                pass
            time.sleep(0.5)

        dt = time.perf_counter() - t0
        samples.append(dt if found else float("inf"))
        print(f"  - #{i+1:02d} 반영지연 = {dt:.3f}s {'(OK)' if found else '(TIMEOUT)'}")

    stats = summarize(samples)
    ok, reason = judge(stats, threshold_s, rule="p95<=threshold")
    print(f"\n  * 결과: avg={stats['avg']:.3f}s, p95={stats['p95']:.3f}s → {'PASS' if ok else 'FAIL'} ({reason})")
    return {"stats": stats, "pass": ok, "reason": reason, "samples": samples}


# ------------------------------------------------------------
# 3) 대량 방송(팬아웃) 안정성: 성공률 ≥ 99%, 평균 지연 ≤ 5s
# ------------------------------------------------------------
def _broadcast_fanout(step: Dict[str, Any]) -> Dict[str, Any]:
    broadcast_url: str = step["broadcast_url"]
    status_url_tpl: str = step["status_url"]  # 예: ".../status?broadcast_id={broadcast_id}"
    headers = step.get("headers")
    sender_token: Optional[str] = step.get("auth", {}).get("sender_token")

    recipients: int = int(step.get("recipients", 300))
    success_rate_threshold: float = float(step.get("success_rate_threshold", 0.99))
    avg_delay_threshold_s: float = float(step.get("avg_delay_threshold_s", 5.0))
    poll_interval_s: float = float(step.get("poll_interval_s", 0.5))
    timeout_s: float = float(step.get("timeout_s", 30.0))

    print("\n[INTERACTION > 팬아웃 방송]")

    # 1) 방송 전송
    req_id = str(uuid.uuid4())
    payload = {"title": "[test] notice", "body": "fanout test", "recipients": recipients, "request_id": req_id}

    try:
        br = _post(broadcast_url, payload, token=sender_token, headers=headers)
        br.raise_for_status()
        brobj = br.json()
        broadcast_id = _get_by_path(brobj, "broadcast_id") or brobj.get("id") or req_id
    except Exception as e:
        print(f"  - 방송 전송 실패: {e}")
        return {"pass": False, "reason": "send_failed", "stats": {}}

    # 2) 상태 폴링
    t0 = time.perf_counter()
    delays = []
    last_rate = 0.0
    while time.perf_counter() - t0 < timeout_s:
        try:
            surl = status_url_tpl.format(broadcast_id=broadcast_id)
            sr = _get(surl, token=sender_token, headers=headers)
            data = sr.json()
            delivered = int(_get_by_path(data, "delivered") or 0)
            total = int(_get_by_path(data, "total") or recipients)
            rate = delivered / max(1, total)
            last_rate = rate
            if rate >= success_rate_threshold:
                delays.append(time.perf_counter() - t0)
                break
        except Exception:
            pass
        time.sleep(poll_interval_s)

    if not delays:
        print(f"  - 타임아웃(성공률 {last_rate*100:.1f}% 미달)")
        return {"pass": False, "reason": "timeout_or_low_success", "stats": {}}

    stats = summarize(delays)
    ok = (stats["avg"] <= avg_delay_threshold_s)
    reason = f"avg_delay={stats['avg']:.3f}s ≤ {avg_delay_threshold_s:.3f}s and success≥{success_rate_threshold*100:.1f}%"
    print(f"  * 결과: avg_delay={stats['avg']:.3f}s, success_rate≥{success_rate_threshold*100:.1f}% → {'PASS' if ok else 'FAIL'}")
    return {"stats": stats, "pass": ok, "reason": reason}


# ------------------------------------------------------------
# 4) 교차기기 동기화 (웹/모바일 읽음/삭제 상태 5초 내 일치)
# ------------------------------------------------------------
def _cross_device_sync(step: Dict[str, Any]) -> Dict[str, Any]:
    web_state_url: str = step["web_state_url"]
    mobile_state_url: str = step["mobile_state_url"]
    headers = step.get("headers")
    token: Optional[str] = step.get("auth", {}).get("token")

    key_path: str = step.get("key_path", "threads.0.last_message.read")
    threshold_s: float = float(step.get("threshold_s", 5.0))

    t0 = time.perf_counter()
    consistent = False
    while time.perf_counter() - t0 < threshold_s:
        try:
            w = _get(web_state_url, token=token, headers=headers).json()
            m = _get(mobile_state_url, token=token, headers=headers).json()
            if _get_by_path(w, key_path) == _get_by_path(m, key_path):
                consistent = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    print(f"\n[INTERACTION > 교차기기 동기화]  {'PASS' if consistent else 'FAIL'}")
    return {"pass": consistent, "reason": "state_consistent" if consistent else "timeout_mismatch"}


# ------------------------------------------------------------
# 5) 중복/폭주 알림 제어 (아이덤포턴시 키 기반 1회만 노출)
# ------------------------------------------------------------
def _dedup_guard(step: Dict[str, Any]) -> Dict[str, Any]:
    send_url: str = step["send_url"]
    inbox_url: str = step["inbox_url"]
    headers = step.get("headers")
    token: Optional[str] = step.get("auth", {}).get("user_token")

    event_payload: Dict[str, Any] = step.get("event_payload", {"event": "assignment_updated"})
    idempotency_key_path: str = step.get("idempotency_key_path", "idempotency_key")
    list_path: str = step.get("list_path", "items")
    key_path: str = step.get("key_path", "event_key")

    triggers: int = int(step.get("triggers", 3))
    expect_max: int = int(step.get("expect_max_per_user", 1))

    idem = str(uuid.uuid4())

    # 동일 이벤트 트리거 N회
    for _ in range(triggers):
        payload = dict(event_payload)
        payload[idempotency_key_path] = idem
        try:
            _post(send_url, payload, token=token, headers=headers)
        except Exception:
            pass

    # 받은 알림에서 동일 key 개수 카운트
    time.sleep(1.0)
    try:
        inbox = _get(inbox_url, token=token, headers=headers).json()
        items = _get_by_path(inbox, list_path) or []
        count = 0
        for it in items:
            if _get_by_path(it, key_path) == idem:
                count += 1
    except Exception:
        count = triggers

    ok = count <= expect_max
    print(f"\n[INTERACTION > 중복/폭주 알림 제어]  count={count}  expect≤{expect_max} → {'PASS' if ok else 'FAIL'}")
    return {"pass": ok, "found": count, "expect_max": expect_max}


# ------------------------------------------------------------
# 6) 실시간 채팅 왕복 지연 (WebSocket)  평균 ≤ 0.5s, p95 ≤ 1.0s
# ------------------------------------------------------------
def _realtime_chat_latency_ws(step: Dict[str, Any]) -> Dict[str, Any]:
    if websockets is None:
        print("[INTERACTION > 실시간채팅] websockets 미설치 → SKIP")
        return {"pass": False, "reason": "websockets_not_installed"}

    ws_url: str = step["ws_url"]
    auth = step.get("auth", {})
    a_token = auth.get("a_token")
    b_token = auth.get("b_token")
    headers = step.get("headers")
    messages: int = int(step.get("messages", 10))
    thresholds = step.get("thresholds", {"avg": 0.5, "p95": 1.0})

    import asyncio

    async def runner():
        samples: List[float] = []
        # 토큰을 쿼리스트링으로 전달(서비스 구조에 맞게 수정 가능)
        at = f"&token={a_token}" if a_token else ""
        bt = f"&token={b_token}" if b_token else ""
        async with websockets.connect(f"{ws_url}{at}") as A, \
                   websockets.connect(f"{ws_url}{bt}") as B:
            # B는 에코 서버처럼 동작: pong 전송
            async def b_loop():
                while True:
                    msg = await B.recv()
                    if isinstance(msg, bytes):
                        msg = msg.decode()
                    if msg.startswith("ping:"):
                        uid = msg.split(":", 1)[1]
                        await B.send(f"pong:{uid}")

            task_b = asyncio.create_task(b_loop())

            try:
                for _ in range(messages):
                    uid = str(uuid.uuid4())
                    t0 = time.perf_counter()
                    await A.send(f"ping:{uid}")
                    # pong 기다림
                    while True:
                        msg = await A.recv()
                        if isinstance(msg, bytes):
                            msg = msg.decode()
                        if msg == f"pong:{uid}":
                            samples.append(time.perf_counter() - t0)
                            break
            finally:
                task_b.cancel()
        return samples

    try:
        samples = asyncio.get_event_loop().run_until_complete(runner())
    except RuntimeError:
        samples = asyncio.new_event_loop().run_until_complete(runner())

    stats = summarize(samples)
    ok = stats["avg"] <= thresholds.get("avg", 0.5) and stats["p95"] <= thresholds.get("p95", 1.0)
    print(f"\n[INTERACTION > 실시간 채팅]")
    print(f"  - avg={stats['avg']:.3f}s, p95={stats['p95']:.3f}s → {'PASS' if ok else 'FAIL'}")
    return {"stats": stats, "pass": ok, "samples": samples}


# ------------------------------------------------------------
# 7) 접근성(라벨/대체텍스트) + 8) 읽음 공개 범위 UI (Playwright)
# ------------------------------------------------------------
def _require_playwright(driver):
    if driver is None or not hasattr(driver, "page"):
        raise RuntimeError("Playwright driver가 필요합니다.")
    return driver.page

def _accessibility_labels(step: Dict[str, Any], driver) -> Dict[str, Any]:
    page = _require_playwright(driver)
    targets: List[Dict[str, Any]] = step.get("targets", [])

    print("\n[INTERACTION > 접근성 라벨/대체텍스트]")
    results = []
    for t in targets:
        url = t["url"]
        selectors: List[str] = t.get("selectors", ["[aria-label]", "img[alt]"])
        page.goto(url)
        page.wait_for_timeout(300)
        misses = []
        for sel in selectors:
            try:
                _ = page.locator(sel).count()
            except Exception:
                misses.append(sel)
        results.append({"url": url, "misses": misses})
        print(f"  - {url}  misses={len(misses)}")

    ok = all(len(r["misses"]) == 0 for r in results)
    return {"pass": ok, "rows": results}

def _privacy_scope_check_ui(step: Dict[str, Any], driver) -> Dict[str, Any]:
    page = _require_playwright(driver)
    flows: List[Dict[str, Any]] = step.get("flows", [])

    print("\n[INTERACTION > 읽음 공개 범위 UI]")
    all_ok = True
    rows = []
    for f in flows:
        url = f["url"]
        checks: List[Dict[str, Any]] = f.get("checks", [])
        page.goto(url)
        page.wait_for_timeout(300)
        ok = True
        for c in checks:
            sel = c["selector"]
            should_visible = bool(c.get("visible", True))
            try:
                visible = page.is_visible(sel)
            except Exception:
                visible = False
            if visible != should_visible:
                ok = False
                all_ok = False
        rows.append({"url": url, "pass": ok})
        print(f"  - {url} → {'PASS' if ok else 'FAIL'}")

    return {"pass": all_ok, "rows": rows}
