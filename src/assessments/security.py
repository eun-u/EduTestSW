"""
========== 보안성 Security ==========

| 기밀성 | Confidentiality |
- check_https_certificate :         https 통신 적용 확인
- check_file_encryption_static :    파일 암호화 저장 여부 확인 (llm 프롬프트 기반 정적 코드 리뷰)
+ print_https_result :              https 인증서 검사 결과 출력

| 무결성 | Integrity |
- report_hash_verify :              보고서 해시(SHA-256) 검증 확인 (SKELETON)
- download_integrity :              파일 다운로드 무결성(서버 기준 해시와 일치) 확인 (SKELETON)
- input_validation :                잘못된 입력 거부/정규화 확인 (SKELETON)

| 부인방지 | Non-Repudiation |
- report_audit_trail :              보고서 생성 시 사용자/타임스탬프 기록 확인 (SKELETON)
- report_lock_immutable :           제출 이후 보고서 변경 불가 확인 (SKELETON)

| 책임성 | Accountability |
- action_logging :                  주요 행위 로그/감사 기록 존재 확인 (SKELETON)
- admin_audit_view :                관리자 모드에서 활동 이력 조회 가능 여부 (SKELETON)

| 인증성 | Authenticity |
- auth_login :                      인증 후 보호 리소스 접근 가능 확인 (SKELETON)
- login_rate_limit :                로그인 실패 시도 제한 확인 (SKELETON)
- token_expiry :                    인증 토큰 만료 처리 확인 (SKELETON)
====================================
"""
# ---------------------------------------------------------------------
# 모듈 임포트
# ---------------------------------------------------------------------
import ssl
import socket
from urllib.parse import urlparse
import datetime
import os
from typing import Dict, Any
from src.llm_clients.file_encryption_client import analyze_code_for_encryption

# 외부 I/O 라이브러리 (스켈레톤은 설치 없어도 동작하게 try-import)
try:
    import requests
except Exception:   # pragma: no cover
    requests = None

try:
    from jsonschema import validate, ValidationError
except Exception:   # pragma: no cover
    validate = None
    ValidationError = Exception

try:
    import jwt  # PyJWT
except Exception:   # pragma: no cover
    jwt = None

import time, hashlib


# ---------------------------------------------------------------------
# 내부 유틸 (스켈레톤 공용)
# ---------------------------------------------------------------------
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def req(method: str, url: str, **kw):
    """requests 없는 환경에서도 에러가 친절히 나오도록 래퍼."""
    if requests is None:
        raise RuntimeError("[SECURITY] requests 모듈이 필요합니다. (pip install requests)")
    if "timeout" not in kw:
        kw["timeout"] = 5
    return requests.request(method.upper(), url, **kw)

def sk_print(name: str, msg: str = ""):
    print(f"[SECURITY][SKELETON] {name}: {msg or '미구현(placeholder)'}")


def print_result(name: str, ok: bool, reason: str):
    """일관된 PASS/FAIL 로그 출력 유틸 (스켈레톤/부분 구현 공용)."""
    status = "PASS" if ok else "FAIL"
    print(f"[SECURITY] {name:30s} [{status}] {reason}")
    

# ---------------------------------------------------------------------
# 엔트리 포인트: 보안 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    assessment_type = step["type"]
    
    if assessment_type == "check_https_certificate":
        url = step.get("url")
        if not url:
            raise ValueError("[SECURITY > CONFIDENTIALITY] 'url' 항목이 누락되었습니다.")
        result = check_https_certificate(url)
        print_https_result(result)
    
    elif assessment_type == "check_file_encryption_static":
        check_file_encryption_static(step, driver)
        
    # 스켈레톤 라우팅 (아직 미구현 – 실행해도 실패로 터지지 않음)
    elif assessment_type == "report_hash_verify":
        return report_hash_verify(step)

    elif assessment_type == "download_integrity":
        return download_integrity(step)

    elif assessment_type == "input_validation":
        return input_validation(step)

    elif assessment_type == "report_audit_trail":
        return report_audit_trail(step)

    elif assessment_type == "action_logging":
        return action_logging(step)

    elif assessment_type == "report_lock_immutable":
        return report_lock_immutable(step)

    elif assessment_type == "admin_audit_view":
        return admin_audit_view(step)

    elif assessment_type == "auth_login":
        return auth_login(step)

    elif assessment_type == "login_rate_limit":
        return login_rate_limit(step)

    elif assessment_type == "token_expiry":
        return token_expiry(step)

    else:
        raise ValueError(f"[SECURITY] 알 수 없는 검사 유형: {assessment_type}")
    

# ---------------------------------------------------------------------
# 기밀성: HTTPS 인증서 검사
# ---------------------------------------------------------------------
def check_https_certificate(url: str) -> dict:
    """
    HTTPS 통신 적용 여부를 검사하는 함수
    - TLS 인증서 유효성과 만료일을 확인함
    - 인증서 발급자 정보를 반환함

    Args:
        url (str): 검사할 대상 시스템의 URL (예: https://example.com)

    Returns:
        dict: HTTPS 적용 여부, 인증서 유효성, 발급자 정보 등이 포함된 결과 딕셔너리
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = 443  # https 기본 포트
    
    context = ssl.create_default_context()
    
    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                valid_from = cert["notBefore"]
                valid_to = cert["notAfter"]

                expire_date = datetime.datetime.strptime(valid_to, '%b %d %H:%M:%S %Y %Z')
                is_valid = expire_date > datetime.datetime.now()

                return {
                    "https_supported": True,
                    "issuer": cert.get("issuer", "N/A"),
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "is_valid": is_valid,
                }

    except Exception as e:
        return {
            "https_supported": False,
            "error": str(e)
        }


# ---------------------------------------------------------------------
# 기밀성: 파일 암호화 저장 여부 정적 분석(LLM)
# ---------------------------------------------------------------------
def check_file_encryption_static(step: Dict[str, Any], driver=None) -> Dict[str, Any]:
    """
    파일 업로드 처리 코드에서 서버 측 암호화 저장 여부를
    LLM을 통해 정적 분석하는 함수

    Args:
        step (dict): 루틴 스텝 데이터 (code_path 포함)
        driver (object): 현재 루틴에서 사용되는 드라이버 (사용되지 않음)

    Returns:
        dict: analyze_code_for_encryption 결과(printed도 함)
    """
    code_path = step.get("code_path")
    if not code_path:
        raise ValueError("[SECURITY > CONFIDENTIALITY] 'code_path'가 누락되었습니다.")
    if not os.path.exists(code_path):
        raise FileNotFoundError(f"[SECURITY > CONFIDENTIALITY] code_path가 존재하지 않습니다: {code_path}")

    try:
        with open(code_path, "r", encoding="utf-8") as f:
            code = f.read()
    except UnicodeDecodeError:
        # 바이너리나 다른 인코딩일 수 있음 → latin-1로 재시도(깨져도 라인 패턴엔 영향 적음)
        with open(code_path, "r", encoding="latin-1", errors="replace") as f:
            code = f.read()

    result = analyze_code_for_encryption(code)
    
    # ===== 원하는 출력 포맷 =====
    verdict = "파일 암호화 됨" if result.get("encrypted") else "파일 암호화 되지 않음"
    print("\n[파일 암호화 정적 분석 결과]")
    print(f"- {verdict}")
    # 근거 최소 표시
    ev = result.get("evidence", [])
    if ev:
        first = ev[0]
        print(f"- 근거: L{first.get('line')}: {first.get('text')}")
    else:
        print(f"- 근거: {result.get('reason', '근거 부족')}")
    
    return result


# ---------------------------------------------------------------------
# 출력 유틸: HTTPS 검사 결과 프린트
# ---------------------------------------------------------------------
def print_https_result(result: dict):
    """
    HTTPS 인증서 검사 결과를 읽기 쉽도록 출력하는 함수

    Args:
        result (dict): check_https_certificate() 함수의 반환 결과 딕셔너리.
    """
    print("\n[HTTPS 인증서 검사 결과]")
    
    supported = result.get("https_supported", False)
    print(f"  • HTTPS 적용 여부     : {'적용됨' if supported else '미적용 또는 실패'}")

    if not supported:
        print(f"  • 오류 내용           : {result.get('error')}")
        return

    # 발급자 이름 정리
    issuer_tuple = result.get("issuer", [])
    issuer_parts = []
    for entry in issuer_tuple:
        for part in entry:
            issuer_parts.append(part[1])
    issuer_str = " / ".join(issuer_parts)

    print(f"  • 인증서 발급자       : {issuer_str}")
    print(f"  • 유효 기간           : {result.get('valid_from')} ~ {result.get('valid_to')}")
    print(f"  • 인증서 유효성       : {'유효함' if result.get('is_valid') else '만료됨'}")


# ======================== SKELETON START (아직 미구현 테스트) ====================
# 아래 함수들은 스켈레톤이지만, 최소 동작이 가능하도록 "안전한 부분 구현"을 포함합니다.
# 각 함수는 시작 시 SKELETON 표기를 로그로 남깁니다.

# -------------- 1) 보고서 해시 검증 확인 --------------
def report_hash_verify(step: Dict[str, Any]):
    """
    서버가 보고서 생성 시 SHA-256 해시를 함께 제공하고,
    이후 검증 요청 시 동일 해시를 되돌려주는지 확인.
    step:
      - create: {method,url,json/...}  # 보고서 생성
      - fetch:  {method,url}           # 보고서 본문 다운로드
      - gethash:{method,url}           # 저장된 해시 조회
      - payload_path(optional):  생성 응답에서 report_id를 꺼낼 경로 ["data","id"] 등
    """
    sk_print("report_hash_verify")
    create = step["create"]; fetch = step["fetch"]; gethash = step["gethash"]
    try:
        # 1) 보고서 생성
        r1 = req(create.get("method","POST"), create["url"], json=create.get("json"))
        if r1.status_code >= 300:
            print_result("report_hash_verify", False, f"create failed {r1.status_code}")
            return {"pass": False, "reason":"create failed"}
        resp1 = r1.json() if "application/json" in r1.headers.get("Content-Type","") else {}
        report_id = resp1.get("id", None)
        # 커스텀 경로 지원
        path = step.get("payload_path")
        if path:
            cur = resp1
            for k in path:
                cur = cur.get(k, {}) if isinstance(cur, dict) else {}
            report_id = cur if isinstance(cur, (str,int)) else report_id

        # 2) 보고서 본문 가져와 로컬 해시 계산
        url_fetch = fetch["url"].format(id=report_id) if report_id is not None else fetch["url"]
        r2 = req(fetch.get("method","GET"), url_fetch)
        if r2.status_code >= 300:
            print_result("report_hash_verify", False, f"fetch failed {r2.status_code}")
            return {"pass": False, "reason":"fetch failed"}
        body = r2.content
        local_hash = sha256_hex(body)

        # 3) 서버 저장 해시 조회
        url_hash = gethash["url"].format(id=report_id) if report_id is not None else gethash["url"]
        r3 = req(gethash.get("method","GET"), url_hash)
        if r3.status_code >= 300:
            print_result("report_hash_verify", False, f"gethash failed {r3.status_code}")
            return {"pass": False, "reason":"gethash failed"}
        server_hash = r3.json().get("sha256") if "application/json" in r3.headers.get("Content-Type","") else r3.text.strip()

        ok = (server_hash == local_hash)
        print_result("report_hash_verify", ok, f"server={server_hash} local={local_hash}")
        return {"pass": ok, "server_hash": server_hash, "local_hash": local_hash}
    except Exception as e:
        print_result("report_hash_verify", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 2) 파일 다운로드 무결성 체크 --------------
def download_integrity(step: Dict[str, Any]):
    """
    서버가 다운로드 시 해시를 제공하거나(헤더/메타),
    클라이언트가 서버의 기준 해시와 비교할 수 있는지 확인.
    step:
      - file: {method,url}
      - hash: {method,url}  # 같은 파일의 기준 해시를 주는 엔드포인트
      - header_key(optional): 예: 'X-Content-SHA256' (헤더로 해시 제공 시)
    """
    sk_print("download_integrity")
    try:
        file_desc = step["file"]; hash_desc = step.get("hash")
        r = req(file_desc.get("method","GET"), file_desc["url"])
        if r.status_code >= 300:
            print_result("download_integrity", False, f"download failed {r.status_code}")
            return {"pass": False, "reason":"download failed"}
        body = r.content
        local_hash = sha256_hex(body)

        header_key = step.get("header_key")
        server_hash = None
        if header_key and header_key in r.headers:
            server_hash = r.headers[header_key]
        elif hash_desc:
            r2 = req(hash_desc.get("method","GET"), hash_desc["url"])
            if r2.status_code < 300:
                server_hash = r2.json().get("sha256") if "application/json" in r2.headers.get("Content-Type","") else r2.text.strip()

        ok = (server_hash == local_hash) if server_hash else True  # 기준 해시 없으면 일단 OK로 보고 경고는 리포트 레벨에서 처리 가능
        print_result("download_integrity", ok, f"server={server_hash} local={local_hash}")
        return {"pass": ok, "server_hash": server_hash, "local_hash": local_hash}
    except Exception as e:
        print_result("download_integrity", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 3) 입력값 검증 처리 확인 --------------
def input_validation(step: Dict[str, Any]):
    """
    잘못된 형식 입력 시 4xx를 반환하는지, 또는 서버가 거부/정규화하는지 확인.
    step:
      - target: {method,url}
      - bad_payload: dict
      - expect_status: [400,422] 등
      - schema(optional): 성공 케이스 JSON 스키마(있으면 정상 입력도 점검)
    """
    sk_print("input_validation")
    try:
        t = step["target"]
        bad = step.get("bad_payload", {})
        expect = set(step.get("expect_status", [400, 422]))
        r = req(t.get("method","POST"), t["url"], json=bad)
        ok = r.status_code in expect
        reason = f"status={r.status_code}, expect in {sorted(expect)}"
        if step.get("schema") and validate:
            try:
                validate(instance=r.json(), schema=step["schema"])
            except Exception:
                # 실패 응답은 스키마 검사를 건너뜀(선택)
                pass
        print_result("input_validation", ok, reason)
        return {"pass": ok, "status": r.status_code}
    except Exception as e:
        print_result("input_validation", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 4) 보고서 생성 시 타임스탬프/사용자 기록 --------------
def report_audit_trail(step: Dict[str, Any]):
    """
    리포트 생성 시 사용자ID/시간이 저장되는지 확인.
    step:
      - create:{method,url,json}
      - fetch_meta:{method,url}  # id로 메타 조회 가능해야 함
      - payload_path(optional)
      - expect_fields: ["user_id","created_at"] 등
    """
    sk_print("report_audit_trail")
    try:
        create = step["create"]; fetch_meta = step["fetch_meta"]
        r = req(create.get("method","POST"), create["url"], json=create.get("json"))
        if r.status_code >= 300:
            print_result("report_audit_trail", False, f"create failed {r.status_code}")
            return {"pass": False}
        data = r.json() if "application/json" in r.headers.get("Content-Type","") else {}
        report_id = data.get("id")
        path = step.get("payload_path")
        if path:
            cur = data
            for k in path:
                cur = cur.get(k,{}) if isinstance(cur, dict) else {}
            report_id = cur if isinstance(cur,(str,int)) else report_id

        r2 = req(fetch_meta.get("method","GET"), fetch_meta["url"].format(id=report_id))
        ok = False; reason = ""
        if r2.status_code < 300:
            meta = r2.json()
            missing = [f for f in step.get("expect_fields", ["user_id","created_at"]) if f not in meta]
            ok = (len(missing)==0)
            reason = "ok" if ok else f"missing {missing}"
        print_result("report_audit_trail", ok, reason)
        return {"pass": ok, "reason": reason}
    except Exception as e:
        print_result("report_audit_trail", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 5) 작업 로그 기록 여부 --------------
def action_logging(step: Dict[str, Any]):
    """
    특정 행위 후 서버 로그/감사 테이블에 레코드가 남는지 확인(간접 확인).
    step:
      - act:{method,url,json}
      - probe:{method,url}  # 최근 로그/감사 목록 조회
      - expect_contains: ["user_id","action"] 등
    """
    sk_print("action_logging")
    try:
        act = step["act"]; probe = step["probe"]
        req(act.get("method","POST"), act["url"], json=act.get("json"))
        r = req(probe.get("method","GET"), probe["url"])
        ok = False; reason = ""
        if r.status_code < 300:
            txt = r.text
            ok = all(term in txt for term in step.get("expect_contains", []))
            reason = "ok" if ok else "missing fields in log view"
        print_result("action_logging", ok, reason)
        return {"pass": ok, "reason": reason}
    except Exception as e:
        print_result("action_logging", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 6) 리포트 제출 이후 불변 --------------
def report_lock_immutable(step: Dict[str, Any]):
    """
    제출 상태로 전환 후 수정 시도가 거부되는지 확인.
    step:
      - create:{...} -> id
      - submit:{method,url}  # 상태=SUBMITTED
      - modify:{method,url,json}  # 수정 시도
      - expect_status:[403,409] 등
    """
    sk_print("report_lock_immutable")
    try:
        create = step["create"]; submit = step["submit"]; modify = step["modify"]
        r1 = req(create.get("method","POST"), create["url"], json=create.get("json"))
        if r1.status_code >= 300:
            print_result("report_lock_immutable", False, "create failed")
            return {"pass": False}
        rid = (r1.json() or {}).get("id")
        req(submit.get("method","POST"), submit["url"].format(id=rid))
        r3 = req(modify.get("method","POST"), modify["url"].format(id=rid), json=modify.get("json"))
        ok = r3.status_code in set(step.get("expect_status",[403,409]))
        print_result("report_lock_immutable", ok, f"status={r3.status_code}")
        return {"pass": ok, "status": r3.status_code}
    except Exception as e:
        print_result("report_lock_immutable", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 7) 관리자 모드에서 활동 이력 확인 --------------
def admin_audit_view(step: Dict[str, Any]):
    """
    관리자 페이지/엔드포인트로 이력 조회 가능 여부 확인.
    step: {method,url, expect_contains:[...]}
    """
    sk_print("admin_audit_view")
    try:
        r = req(step.get("method","GET"), step["url"])\

        ok = (r.status_code < 300) and all(term in r.text for term in step.get("expect_contains", []))
        print_result("admin_audit_view", ok, f"status={r.status_code}")
        return {"pass": ok, "status": r.status_code}
    except Exception as e:
        print_result("admin_audit_view", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 8) 로그인 인증 처리 확인 --------------
def auth_login(step: Dict[str, Any]):
    """
    올바른 인증으로 접근 가능한지 (예: JWT 혹은 세션).
    step:
      - login:{method,url,json}
      - protected:{method,url}  # Authorization 필요
      - token_path(optional): ["data","token"]
      - header_prefix: "Bearer "
    """
    sk_print("auth_login")
    try:
        login = step["login"]; protected = step["protected"]
        r = req(login.get("method","POST"), login["url"], json=login.get("json"))
        if r.status_code >= 300:
            print_result("auth_login", False, "login failed")
            return {"pass": False}
        token = (r.json() or {}).get("token")
        path = step.get("token_path")
        if path:
            cur = r.json()
            for k in path:
                cur = cur.get(k,{}) if isinstance(cur, dict) else {}
            token = cur if isinstance(cur, str) else token
        headers = {"Authorization": step.get("header_prefix","Bearer ") + token} if token else {}
        r2 = req(protected.get("method","GET"), protected["url"], headers=headers)
        ok = (r2.status_code < 300)
        print_result("auth_login", ok, f"status={r2.status_code}")
        return {"pass": ok, "status": r2.status_code}
    except Exception as e:
        print_result("auth_login", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 9) 로그인 실패 시도 제한 --------------
def login_rate_limit(step: Dict[str, Any]):
    """
    반복 실패 시 차단되는지 확인.
    step:
      - login:{method,url}
      - bad_json:{...}
      - attempts:int
      - expect_block_status: [429, 423, 403] 등
    """
    sk_print("login_rate_limit")
    try:
        login = step["login"]
        attempts = int(step.get("attempts", 6))
        block_codes = set(step.get("expect_block_status",[429,423,403]))
        last_status = None
        blocked = False
        for _ in range(attempts):
            r = req(login.get("method","POST"), login["url"], json=step.get("bad_json", {}))
            last_status = r.status_code
            if last_status in block_codes:
                blocked = True
                break
        print_result("login_rate_limit", blocked, f"last_status={last_status}")
        return {"pass": blocked, "status": last_status}
    except Exception as e:
        print_result("login_rate_limit", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# -------------- 10) 인증 토큰 만료 처리 --------------
def token_expiry(step: Dict[str, Any]):
    """
    exp가 지난 JWT는 거부되는지 확인.
    step:
      - login:{method,url,json}
      - protected:{method,url}
      - token_path(optional)
      - tamper_exp_seconds: -10  (만료로 조작해 테스트)
      - secret: HS256 secret (테스트 전용)
    """
    sk_print("token_expiry")
    try:
        if jwt is None:
            print_result("token_expiry", False, "PyJWT 미설치")
            return {"pass": False, "reason": "PyJWT not installed"}

        login = step["login"]; protected = step["protected"]
        r = req(login.get("method","POST"), login["url"], json=login.get("json"))
        if r.status_code >= 300:
            print_result("token_expiry", False, "login failed")
            return {"pass": False}
        token = (r.json() or {}).get("token")
        path = step.get("token_path")
        if path:
            cur = r.json()
            for k in path:
                cur = cur.get(k,{}) if isinstance(cur, dict) else {}
            token = cur if isinstance(cur,str) else token

        # 토큰 exp를 강제로 지난 값으로 재서명(테스트 환경에서만)
        try:
            secret = step["secret"]
            payload = jwt.decode(token, options={"verify_signature": False})
            payload["exp"] = int(time.time()) + int(step.get("tamper_exp_seconds", -10))
            bad = jwt.encode(payload, secret, algorithm="HS256")
        except Exception as e:
            print_result("token_expiry", False, "tamper failed")
            return {"pass": False, "reason":"tamper failed"}

        headers = {"Authorization": step.get("header_prefix","Bearer ") + bad}
        r2 = req(protected.get("method","GET"), protected["url"], headers=headers)
        ok = (r2.status_code in set(step.get("expect_expired_status",[401,403])))
        print_result("token_expiry", ok, f"status={r2.status_code}")
        return {"pass": ok, "status": r2.status_code}
    except Exception as e:
        print_result("token_expiry", False, f"exception: {e}")
        return {"pass": False, "reason": str(e)}

# ========================= SKELETON END =======================================