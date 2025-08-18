#서버 실행 명령어
#python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload



# server.py
from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Dict
import time
import random

app = FastAPI(title="Local Reliability Test Server", version="1.0.0")

# 인메모리 상태 (과부하/지연/실패율 시뮬레이션)
STATE: Dict[str, float | bool] = {
    "overloaded": False,      # True면 장애(복구 전)
    "failure_rate": 0.0,      # 0.0~1.0, 요청 실패 확률
    "extra_latency_ms": 0.0,  # 모든 요청에 추가 지연(ms)
}

class LoginReq(BaseModel):
    username: str
    password: str

@app.get("/health")
def health():
    """
    헬스체크 엔드포인트.
    과부하 상태에선 일부러 느리거나 'degraded'를 반환해서 복구 테스트에 활용.
    """
    if STATE["overloaded"]:
        time.sleep(0.3)  # 복구 SLA 검사용(300ms)
        return {"status": "degraded", "latency_ms": 300}
    return {"status": "ok"}

@app.post("/api/login")
def login(req: LoginReq):
    """
    간단한 로그인 API (토큰 발급 흉내)
    - extra_latency_ms: 모든 요청에 지연 주입
    - overloaded/failure_rate: 장애 시 실패 확률적으로 반환
    """
    # 전역 지연 주입
    extra = float(STATE["extra_latency_ms"])
    if extra > 0:
        time.sleep(extra / 1000.0)

    # 장애/실패율 주입
    if STATE["overloaded"]:
        fail_p = max(0.2, float(STATE["failure_rate"]))  # 최소 20%는 실패하게
        if random.random() < fail_p:
            return {"ok": False, "error": "temporary overload"}

    # 아주 단순한 검증 로직
    if req.username == "user" and req.password == "pass":
        return {"ok": True, "token": "dummy-token"}
    return {"ok": False, "error": "invalid credentials"}

@app.get("/api/echo")
def echo(msg: str = "hello"):
    """
    가벼운 핑/에코 엔드포인트. 부하 테스트 대상 다양화용.
    """
    extra = float(STATE["extra_latency_ms"])
    if extra > 0:
        time.sleep(extra / 1000.0)
    if STATE["overloaded"] and random.random() < max(0.2, float(STATE["failure_rate"])):
        return {"ok": False, "error": "temporary overload"}
    return {"ok": True, "msg": msg}

# -------- Admin (테스트 제어용) --------

@app.post("/admin/toggle_overload")
def toggle_overload(
    overloaded: bool = Query(..., description="과부하 플래그 on/off"),
    failure_rate: float = Query(0.5, ge=0.0, le=1.0, description="요청 실패 확률(0~1)"),
    extra_latency_ms: int = Query(0, ge=0, description="추가 지연(ms)"),
):
    """
    과부하/지연/실패율 상태를 한 번에 토글.
    예) /admin/toggle_overload?overloaded=true&failure_rate=0.7&extra_latency_ms=200
    """
    STATE["overloaded"] = overloaded
    STATE["failure_rate"] = failure_rate
    STATE["extra_latency_ms"] = float(extra_latency_ms)
    return {"ok": True, **STATE}

@app.post("/admin/recover")
def recover():
    """
    정상 상태로 복구.
    """
    STATE["overloaded"] = False
    STATE["failure_rate"] = 0.0
    STATE["extra_latency_ms"] = 0.0
    return {"ok": True, "msg": "recovered", **STATE}

@app.get("/")
def root():
    return {
        "service": "Local Reliability Test Server",
        "endpoints": ["/health", "/api/login", "/api/echo", "/admin/toggle_overload", "/admin/recover"],
        "state": STATE,
    }
