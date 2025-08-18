# 서버 실행 명령어
# python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload

# server.py
from fastapi import FastAPI, HTTPException, Query, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Dict
import time
import random
from jose import jwt, JWTError

app = FastAPI(title="Reliability & Auth Test Server", version="2.0.0")

# --- JWT 설정 ---
# 실제 환경에서는 환경 변수로 관리해야 합니다.
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"

# 토큰을 가져올 의존성 객체
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# --- 서버 상태 (신뢰성 테스트용) ---
STATE: Dict[str, float | bool] = {
    "overloaded": False,
    "failure_rate": 0.0,
    "extra_latency_ms": 0.0,
}

# --- 데이터 모델 ---
class LoginReq(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --- 유틸리티 함수 ---
def get_user(username: str):
    """더미 사용자 정보"""
    if username == "admin":
        return {"username": "admin", "role": "admin"}
    if username == "user":
        return {"username": "user", "role": "user"}
    return None

def apply_chaos():
    """혼란 주입 (지연, 실패)"""
    extra = float(STATE["extra_latency_ms"])
    if extra > 0:
        time.sleep(extra / 1000.0)
    
    if STATE["overloaded"] and random.random() < max(0.2, float(STATE["failure_rate"])):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="temporary overload")

def create_jwt_token(data: dict):
    """JWT 토큰 생성"""
    to_encode = data.copy()
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_role(token: str = Depends(oauth2_scheme)):
    """JWT 토큰을 검증하고 사용자 역할을 추출"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role: str = payload.get("role")
        if role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return role
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

def get_admin_user(role: str = Depends(get_current_user_role)):
    """관리자 권한 확인"""
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an administrator")
    return role

# --- 엔드포인트 ---
@app.get("/health")
def health():
    """헬스체크"""
    if STATE["overloaded"]:
        time.sleep(0.3)
        return {"status": "degraded"}
    return {"status": "ok"}

@app.post("/api/login", response_model=Token)
def login(req: LoginReq):
    """
    로그인 API. 사용자 정보에 따라 JWT 토큰 발급.
    - `admin`: 관리자 권한 토큰
    - `user`: 일반 사용자 권한 토큰
    """
    user = get_user(req.username)
    if not user or req.password != "pass":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    token_data = {"sub": user["username"], "role": user["role"]}
    access_token = create_jwt_token(token_data)
    
    return {"access_token": access_token}

@app.get("/api/echo")
def echo(msg: str = "hello"):
    """
    가벼운 에코 엔드포인트 (신뢰성 테스트용).
    """
    apply_chaos()
    return {"ok": True, "msg": msg}

@app.get("/api/user_data")
def user_data(role: str = Depends(get_current_user_role)):
    """
    로그인한 사용자만 접근 가능한 엔드포인트.
    """
    return {"ok": True, "msg": f"Hello, your role is '{role}'"}

# -------- 관리자 전용 (권한 테스트 대상) --------
@app.post("/admin/toggle_overload")
def toggle_overload(
    admin_role: str = Depends(get_admin_user),
    overloaded: bool = Query(...),
    failure_rate: float = Query(0.5, ge=0.0, le=1.0),
    extra_latency_ms: int = Query(0, ge=0),
):
    """
    과부하/지연/실패율 상태를 토글. **관리자만 접근 가능**.
    """
    STATE["overloaded"] = overloaded
    STATE["failure_rate"] = failure_rate
    STATE["extra_latency_ms"] = float(extra_latency_ms)
    return {"ok": True, **STATE}

@app.post("/admin/recover")
def recover(admin_role: str = Depends(get_admin_user)):
    """
    정상 상태로 복구. **관리자만 접근 가능**.
    """
    STATE["overloaded"] = False
    STATE["failure_rate"] = 0.0
    STATE["extra_latency_ms"] = 0.0
    return {"ok": True, "msg": "recovered", **STATE}

@app.get("/")
def root():
    return {
        "service": "Reliability & Auth Test Server",
        "state": STATE,
    }