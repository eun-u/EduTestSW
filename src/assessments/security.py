"""
========== 보안성 Security ==========
* 수정 필요!!!

| 기밀성 | Confidentiality |
- check_https_certificate :         https 통신 적용 확인
- check_file_encryption_static :    파일 암호화 저장 여부 확인 (llm 프롬프트 기반 정적 코드 리뷰)
+ print_https_result :              https 인증서 검사 결과 출력

| 무결성 | Integrity |
- report_hash_verify :              보고서 해시(SHA-256) 검증 확인
- download_integrity :              파일 다운로드 무결성 확인
- input_validation :                잘못된 입력 거부/정규화 확인

| 부인방지 | Non-Repudiation |
- report_audit_trail :              보고서 생성 시 사용자/타임스탬프 기록 확인
- report_lock_immutable :           제출 이후 보고서 변경 불가 확인

| 책임성 | Accountability |
- action_logging :                  주요 행위 로그/감사 기록 존재 확인
- admin_audit_view :                관리자 모드에서 활동 이력 조회 가능 여부

| 인증성 | Authenticity |
- auth_login :                      인증 후 보호 리소스 접근 가능 확인
- login_rate_limit :                로그인 실패 시도 제한 확인
- token_expiry :                    인증 토큰 만료 처리 확인
====================================
"""
# ---------------------------------------------------------------------
# 모듈 임포트
# ---------------------------------------------------------------------
import ssl
import socket
from urllib.parse import urlparse
from datetime import datetime as dt, timezone
import os
from typing import Any, Dict, List, Optional, Tuple
from src.llm_clients.file_encryption_client import analyze_code_for_encryption
import io, zipfile
import hashlib
import json

# 선택적: LLM 클라이언트가 있을 때만 사용
try:
    from llm_client import review_code  # type: ignore
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False


# ---------------------------------------------------------------------
# 공용 유틸
# ---------------------------------------------------------------------
def is_playwright(driver: Any, mode: Optional[str]) -> Tuple[bool, str]:
    """
    driver/page 존재로 playwright 여부를 추정.
    """
    if mode:
        return (mode == "playwright"), mode
    is_pw = (driver is not None and hasattr(driver, "page"))
    return is_pw, ("playwright" if is_pw else "backend")

def now_iso() -> str:
    return dt.now(timezone.utc).isoformat()

def result(name: str, status: str, details: Optional[Dict[str, Any]] = None,
            evidence: Optional[List[str]] = None, error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,   # PASS | FAIL | WARN | NA | ERROR
        "time": now_iso(),
        "details": details or {},
        "evidence": evidence or [],
        "error": error,
    }

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def detect_magic(b: bytes) -> str:
    """아주 얕은 매직넘버 감지."""
    if b.startswith(b"%PDF-"): return "pdf"
    if b.startswith(b"\x89PNG\r\n\x1a\n"): return "png"
    if b.startswith(b"\xff\xd8\xff"): return "jpg"
    if b.startswith(b"GIF8"): return "gif"
    if b.startswith(b"PK\x03\x04") or b.startswith(b"PK\x05\x06"): return "zip"
    return "unknown"

def print_res(res: Dict[str, Any], str):
        print("\n" + str)
        print(f"  • 상태            : {res.get('status')}")
        if res.get("error"):
            print(f"  • 오류            : {res.get('error')}")
        if res.get("details"):
            print("  • 상세")
            print(json.dumps(res["details"], ensure_ascii=False, indent=2))
        if res.get("evidence"):
            print("  • 근거")
            for e in res["evidence"]:
                print(f"    - {e}")

def format_name(name_tuple) -> str:
    """
    ssl.getpeercert()의 issuer/subject는 튜플의 튜플 형태입니다.
    예: ((('countryName', 'US'),), (('organizationName', "Let's Encrypt"),), ...)
    사람이 읽기 쉬운 문자열로 변환합니다.
    어떤 형태가 와도 인덱스 에러 없이 안전하게 처리합니다.
    """
    try:
        parts = []
        # name_tuple이 None/빈 값/예상과 다른 타입이어도 안전하게 처리
        for rdn in name_tuple or []:
            # rdn: (('key','val'), ('key2','val2'), ...)
            try:
                for k, v in rdn:
                    parts.append(f"{k}={v}")
            except Exception:
                # 예외적으로 rdn이 2중 튜플이 아닐 수도 있으므로 문자열로 강제
                parts.append(str(rdn))
        return ", ".join(parts) if parts else "N/A"
    except Exception:
        return str(name_tuple) if name_tuple is not None else "N/A"
    

# ---------------------------------------------------------------------
# 엔트리 포인트: 보안 검사 라우팅
# ---------------------------------------------------------------------
def check(driver, step):
    if not isinstance(step, dict):
        raise ValueError("[SECURITY] step는 dict여야 합니다.")
    
    assessment_type = step.get("type") or step.get("name")
    if not assessment_type:
        raise ValueError("[SECURITY] step에는 'type' 또는 'name' 키가 필요합니다.")
    
    if assessment_type == "check_https_certificate":
        return check_https_certificate_step(step)
    
    elif assessment_type == "check_file_encryption_static":
        check_file_encryption_static(step, driver)
        
    # 스켈레톤 라우팅 (아직 미구현 – 실행해도 실패로 터지지 않음)
    elif assessment_type == "report_hash_verify":
        return report_hash_verify(step, driver)

    elif assessment_type == "download_integrity":
        return download_integrity(step, driver)

    elif assessment_type == "input_validation":
        return input_validation(step, driver)

    elif assessment_type == "report_audit_trail":
        return report_audit_trail(step, driver)

    elif assessment_type == "action_logging":
        return action_logging(step, driver)

    elif assessment_type == "report_lock_immutable":
        return report_lock_immutable(step, driver)

    elif assessment_type == "admin_audit_view":
        return admin_audit_view(step, driver)

    elif assessment_type == "auth_login":
        return auth_login(step, driver)

    elif assessment_type == "login_rate_limit":
        return login_rate_limit(step, driver)

    elif assessment_type == "token_expiry":
        return token_expiry(step, driver)

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
    from datetime import datetime as _dt, timezone as _tz
    
    parsed = urlparse(url)
    if (parsed.scheme or "").lower() != "https":
        return {"https_supported": False, "error": "URL scheme must be https"}

    hostname = parsed.hostname
    if not hostname:
        return {"https_supported": False, "error": "Invalid URL (hostname missing)"}

    port = parsed.port or 443
    context = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert() or {}

                valid_from = cert.get("notBefore")
                valid_to   = cert.get("notAfter")

                # notAfter 예: 'Aug 19 23:59:59 2025 GMT'
                expire_dt = None
                if valid_to:
                    try:
                        expire_dt = _dt.strptime(valid_to, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=_tz.utc)
                    except Exception:
                        # 드문 포맷 차이 대응: 실패 시 만료 판단 불가로 처리
                        expire_dt = None

                now_utc = _dt.now(_tz.utc)
                is_valid = bool(expire_dt and expire_dt > now_utc)

                issuer_str  = format_name(cert.get("issuer"))
                subject_str = format_name(cert.get("subject"))

                return {
                    "https_supported": True,
                    "issuer": issuer_str,
                    "subject": subject_str,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "is_valid": is_valid,
                }

    except Exception as e:
        return {"https_supported": False, "error": str(e)}


# ---------------------------------------------------------------------
# (러너 호환) step/driver 시그니처용 래퍼 + 안전 출력
# ---------------------------------------------------------------------
def check_https_certificate_step(step):
    """
    러너가 security.check(driver, step)에서 호출할 수 있도록 만든 래퍼.
    - step["url"]에서 URL을 꺼내 핵심 함수를 호출
    - 결과를 표준 포맷으로 출력(문자열 인덱스 접근 없이 안전)
    """
    url = (step or {}).get("url")
    res = check_https_certificate(url or "")

    # 안전 출력: 키 미존재/None도 안전하게 처리
    https_supported = res.get("https_supported")
    error           = res.get("error")
    issuer          = res.get("issuer") or "N/A"
    subject         = res.get("subject") or "N/A"
    valid_from      = res.get("valid_from") or "N/A"
    valid_to        = res.get("valid_to") or "N/A"
    is_valid        = res.get("is_valid")

    print("\n[HTTPS 인증서 검사 결과]")
    if https_supported:
        print("  • HTTPS 적용 여부     : 적용")
        print(f"  • 유효한 인증서       : {'예' if is_valid else '아니오/판단불가'}")
        print(f"  • 발급자(issuer)      : {issuer}")
        print(f"  • 주체(subject)       : {subject}")
        print(f"  • 유효기간            : {valid_from}  ~  {valid_to}")
    else:
        print("  • HTTPS 적용 여부     : 미적용 또는 실패")
        if error:
            print(f"  • 오류 내용           : {error}")

    return res


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
# 기밀성: 보고서 해시 검증 확인 (+ 선택적 LLM 정적 리뷰)
# ---------------------------------------------------------------------
def report_hash_verify(step: Dict[str, Any], driver):
    """
    서버가 리포트 해시를 제공/보관하고, 다운로드한 리포트의 SHA-256과 일치하는지 확인.
    step:
      - create: {method,url,json/...}  # 보고서 생성
      - fetch:  {method,url}           # 보고서 본문 다운로드
      - gethash:{method,url}           # 저장된 해시 조회
      - payload_path(optional):  생성 응답에서 report_id를 꺼낼 경로 ["data","id"] 등
    """
    name = "report_hash_verify"
    label = "[보고서 해시 검증 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))
    
    try:
        # 1) report_id 확보
        report_id = step.get("report_id")
        if not report_id and not is_pw and hasattr(driver, "create_report"):
            payload = step.get("create_report", {})
            resp = driver.create_report(payload)  # 사용자 환경에 맞춰 구현되어 있어야 함
            report_id = resp.get("id") if isinstance(resp, dict) else None

        if not report_id:
            res = result(name, "NA", {"reason": "report_id 없음 또는 생성 불가(드라이버 미지원)"})
            print_res(res, label); return res

        # 2) 서버 해시 조회
        server_hash = None
        if not is_pw and hasattr(driver, "get_report_hash"):
            server_hash = driver.get_report_hash(report_id)

        # 3) 리포트 바이트 다운로드 후 SHA-256 계산
        client_hash = None
        if not is_pw and hasattr(driver, "get_report_bytes"):
            blob = driver.get_report_bytes(report_id)
            if isinstance(blob, (bytes, bytearray)):
                client_hash = sha256_bytes(bytes(blob))

        details = {"report_id": report_id, "server_hash": server_hash, "client_hash": client_hash}

        if server_hash and client_hash:
            if server_hash == client_hash:
                status = "PASS"
                evidence = [f"서버 해시와 클라이언트 계산 해시 일치: {server_hash[:8]}..."]
            else:
                status = "FAIL"
                evidence = [f"서버({server_hash[:8]}...) ≠ 클라이언트({client_hash[:8]}...)"]
        elif client_hash and not server_hash:
            status = "WARN"
            evidence = ["서버 해시 미노출. 클라이언트 재계산만 성공(동일성 보장은 제한적)."]
        else:
            status = "NA"
            evidence = ["드라이버가 보고서 다운로드/해시 API를 지원하지 않음."]

        # (선택) LLM 정적 리뷰 훅
        if step.get("use_llm") and LLM_AVAILABLE and hasattr(review_code, "__call__"):
            # 예: 특정 경로의 코드에서 SHA-256 사용/저장 여부를 점검
            llm_summary = review_code(
                prompt="Check if the codebase properly computes and persists SHA-256 for reports.",
                context={"topic": "report_hash_verify"}
            )
            details["llm_review"] = llm_summary

        res = result(name, status, details, evidence)
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res
    

# ---------------------------------------------------------------------
# 무결성: 파일 다운로드 시 무결성 체크 (멀티 전략 지원)
# ---------------------------------------------------------------------
def download_integrity(step: Dict[str, Any], driver):
    """
    파일 무결성을 여러 기준으로 점검한다.
        strategy:
            - "hash" (기본값): 기존 동작(서버 해시 비교 또는 2회 다운로드 동일성)
            - "size_mime_magic": Content-Length/Type/매직넘버와 실제 바이트 일치 여부
            - "format_basic": 포맷 인지형 얕은 검증(PDF/ZIP 등)
            - "range_consistency": Range 다운로드 재조합이 전체와 동일한지
            - "server_signature": 서버가 제공하는 서명 검증(드라이버 지원 필요)

    멀티 전략 확장:
      - 기존과 호환: "strategy": "hash"  (문자열 1개)
      - 확장:       "strategy": ["hash", "size_mime_magic", ...]  (여러 개를 한 번에 실행)

    기대 입력 예:
      {
        "file_id": "FILE-1",
        "strategy": ["size_mime_magic","format_basic"],   # ← 멀티 전략
        "expected": {"content_type": "application/pdf"}   # 선택
      }
    드라이버 기대(전략별 필요 메서드):
      - common: download_file(file_id) -> bytes
      - size_mime_magic: get_file_meta(file_id) -> {"content_length": int, "content_type": str}
      - range_consistency: download_range(file_id, start, end) -> bytes
      - server_signature: get_file_signature(file_id)->dict, verify_signature(blob, sig_info)->bool
    """
    name = "file_download_integrity_check"
    label = "[파일 다운로드 무결성 검사 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        file_id = step.get("file_id")
        if not file_id:
            res = result(name, "NA", {"reason": "file_id 미제공"})
            print_res(res, label); return res

        # strategy를 문자열 또는 리스트로 받도록 정규화
        raw_strategy = step.get("strategy", "hash")
        strategies = list(raw_strategy) if isinstance(raw_strategy, (list, tuple, set)) else [raw_strategy]

        if is_pw:
            res = result(name, "NA", {"reason": "Playwright 모드에서는 바이트 단위 검증 미지원"})
            print_res(res, label); return res

        if not hasattr(driver, "download_file"):
            res = result(name, "NA", {"reason": "driver.download_file 미구현"})
            print_res(res, label); return res

        blob = driver.download_file(file_id)
        if not isinstance(blob, (bytes, bytearray)):
            res = result(name, "NA", {"reason": "다운로드 바이트 획득 실패"})
            print_res(res, label); return res
        blob = bytes(blob)  # 공통 바이트

        # (옵션) 메타는 1회만 조회해 공유
        meta = {}
        if hasattr(driver, "get_file_meta"):
            try:
                meta = driver.get_file_meta(file_id) or {}
            except Exception:
                meta = {}

        # --- 단일 전략 실행기 ---
        def run_one(st: str) -> Dict[str, Any]:
            if st == "size_mime_magic":
                details = {"file_id": file_id}
                expected = step.get("expected", {})
                content_length = meta.get("content_length") or expected.get("content_length")
                content_type   = meta.get("content_type") or expected.get("content_type")

                actual_len = len(blob)
                detected_magic = detect_magic(blob)
                details.update({
                    "content_length_srv": content_length,
                    "content_type_srv": content_type,
                    "actual_length": actual_len,
                    "detected_magic": detected_magic
                })

                evid = []
                ok_len  = (content_length is None) or (int(content_length) == actual_len)
                ok_type = True
                if content_type:
                    # 아주 얕게: magic과 MIME의 상식적 매칭만 확인
                    mapping = {"pdf": "pdf", "png": "png", "jpg": "jpeg", "gif": "gif", "zip": "zip"}
                    hint = mapping.get(detected_magic, "")
                    ok_type = (hint in content_type.lower())
                if ok_len: evid.append("Content-Length 일치 또는 미제공")
                else:      evid.append(f"Content-Length 불일치: srv={content_length}, actual={actual_len}")
                if ok_type: evid.append("Content-Type ↔ magic 상식적 일치")
                else:       evid.append(f"Content-Type 불일치 가능성: type={content_type}, magic={detected_magic}")

                status = "PASS" if (ok_len and ok_type) else ("WARN" if ok_len or ok_type else "FAIL")
                return result(name, status, details, evid)

            elif st == "format_basic":
                details = {"file_id": file_id}
                evid = []
                magic = detect_magic(blob)
                details["detected_magic"] = magic

                if magic == "pdf":
                    # 시작/종단 간단 확인
                    ok_start = blob.startswith(b"%PDF-")
                    ok_end   = blob.rstrip().endswith(b"%%EOF")
                    status = "PASS" if (ok_start and ok_end) else ("WARN" if ok_start or ok_end else "FAIL")
                    evid.append(f"PDF 서명/EOF: start={ok_start}, eof={ok_end}")
                    return result(name, status, details, evid)

                if magic == "zip":
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(blob))
                        bad = zf.testzip()
                        details["zip_bad_entry"] = bad
                        if bad is None:
                            return result(name, "PASS", details, ["ZIP 구조/CRC 정상"])
                        return result(name, "FAIL", details, [f"ZIP 손상 항목: {bad}"])
                    except Exception as ex:
                        return result(name, "FAIL", details, [f"ZIP 열기 실패: {ex}"])

                # 기타 포맷: 최소한 길이>0 정도만
                status = "PASS" if len(blob) > 0 else "FAIL"
                evid.append("알 수 없는 포맷: 최소 바이트 존재 여부만 확인")
                return result(name, status, details, evid)

            elif st == "range_consistency":
                if not hasattr(driver, "download_range"):
                    return result(name, "NA", {"reason": "driver.download_range 미구현"})
                total = len(blob)
                mid = total // 2
                part1 = driver.download_range(file_id, 0, mid)          # [0, mid)
                part2 = driver.download_range(file_id, mid, total)      # [mid, total)
                if not isinstance(part1, (bytes, bytearray)) or not isinstance(part2, (bytes, bytearray)):
                    return result(name, "NA", {"reason": "range 바이트 획득 실패"})
                reassembled = bytes(part1) + bytes(part2)
                if reassembled == blob:
                    return result(name, "PASS", {"file_id": file_id, "size": total}, ["Range 재조합 == 전체 바이트"])
                return result(name, "FAIL", {"file_id": file_id, "size": total}, ["Range 재조합 ≠ 전체 바이트"])

            elif st == "server_signature":
                # 서버가 서명/검증 API를 제공하는 경우(해시가 아니라 '서명'으로 무결성+출처 보증)
                if not (hasattr(driver, "get_file_signature") and hasattr(driver, "verify_signature")):
                    return result(name, "NA", {"reason": "서명 검증 API 미구현"})
                sig_info = driver.get_file_signature(file_id)
                ok = bool(sig_info) and bool(driver.verify_signature(blob, sig_info))
                if ok:
                    return result(name, "PASS", {"file_id": file_id, "sig_alg": (sig_info or {}).get("alg")}, ["서명 검증 성공"])
                return result(name, "FAIL", {"file_id": file_id, "sig_alg": (sig_info or {}).get("alg")}, ["서명 검증 실패"])

            else:  # "hash" (기본)
                if step.get("use_server_hash") and hasattr(driver, "get_file_hash"):
                    server_hash = driver.get_file_hash(file_id)
                    h1 = sha256_bytes(blob)
                    details = {"file_id": file_id, "client_hash": h1, "server_hash": server_hash}
                    if server_hash and server_hash == h1:
                        return result(name, "PASS", details, [f"서버 해시 일치: {h1[:8]}..."])
                    else:
                        return result(name, "FAIL", details, ["서버 해시 불일치 또는 미노출"])
                else:
                    # 대체: 2회 다운로드 동일성 (바이트 비교, 해시 불필요)
                    blob2 = driver.download_file(file_id)
                    same = isinstance(blob2, (bytes, bytearray)) and (bytes(blob2) == blob)
                    details = {"file_id": file_id, "size": len(blob)}
                    if same:
                        return result(name, "PASS", details, ["2회 다운로드 바이트 동일성 확인 PASS"])
                    return result(name, "WARN", details, ["서버 해시 미제공 + 2회 동일성 검증 실패"])

        # --- 실행 ---
        if len(strategies) == 1:
            st = str(strategies[0])
            res = run_one(st)
            # 기존 포맷 그대로 출력
            print_res(res, label)
            return res

        # 멀티 전략: 각 전략별 결과를 개별 라벨로 출력 + 요약 1회 추가 출력
        results = []
        for st in strategies:
            res = run_one(str(st))
            print_res(res, f"{label} ({st})")
            results.append({"strategy": str(st), **res})

        # 최종 집계(가장 나쁜 상태를 선택: ERROR/FAIL > WARN > PASS > NA)
        rank = {"ERROR": 0, "FAIL": 0, "WARN": 1, "PASS": 2, "NA": 3}
        worst = min((rank.get(r.get("status", "NA"), 3) for r in results), default=3)
        overall = {v: k for k, v in rank.items()}[worst]

        summary = result(
            name,
            overall,
            {"file_id": file_id, "strategies": list(map(str, strategies)), "results": results}
        )
        print_res(summary, f"{label} [summary]")
        return summary

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res


# ---------------------------------------------------------------------
# 무결성: 입력값 검증 처리 확인 (+ 선택적 LLM/룰 설명)
# ---------------------------------------------------------------------
def input_validation(step: Dict[str, Any], driver):
    """
    비정상 페이로드 전송 시 4xx 및 명확한 에러 메시지로 거부되는지 확인.
    기대 입력(예시):
      step = {
        "endpoint": "/api/reports",
        "invalid_payloads": [
          {"title": ""},                       # 빈 필수값
          {"title": "A"*10000},                # 과도한 길이
          {"title": "<script>alert(1)</script>"} # 금지문자
        ],
        "expect_status": [400, 422]
      }
    driver 기대:
      - driver.post_json(endpoint, payload) -> {"status": int, "json": {...}, "text": "..."}
    """
    name = "input_validation_check"
    label = "[입력값 검증 처리 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw or not hasattr(driver, "post_json"):
            res = result(name, "NA", {"reason": "백엔드 드라이버 post_json 필요"})
            print_res(res, label); return res

        endpoint = step.get("endpoint")
        invalids = step.get("invalid_payloads", [])
        expect = set(step.get("expect_status", [400, 422]))
        if not endpoint or not invalids:
            res = result(name, "NA", {"reason": "endpoint/invalid_payloads 미지정"})
            print_res(res, label); return res

        fails = []
        passes = 0
        evid = []
        for i, payload in enumerate(invalids, 1):
            resp = driver.post_json(endpoint, payload)
            status = int(resp.get("status", 0))
            if status in expect:
                passes += 1
                evid.append(f"[{i}] invalid→{status} 거부 OK")
            else:
                fails.append({"idx": i, "status": status, "body": resp.get("text")})

        status_final = "PASS" if passes == len(invalids) else ("WARN" if passes > 0 else "FAIL")
        details = {"tested": len(invalids), "passed": passes, "failed_cases": fails}
        res = result(name, status_final, details, evid)
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res
    

# ---------------------------------------------------------------------
# 무결성: 보고서 생성 시 타임스탬프/사용자 기록 남기기
# ---------------------------------------------------------------------
def report_audit_trail(step: Dict[str, Any], driver):
    """
    기대 입력(예시):
      step = {
        "create_report": {...},
        "fetch_audit": {"action": "REPORT_CREATE", "limit": 5}
      }
    driver 기대:
      - driver.create_report(payload) -> {"id": "..."}
      - driver.fetch_audit(query) -> List[Dict]
    """
    name = "report_audit_trail_check"
    label = "[감사 로그 기록 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw:
            res = result(name, "NA", {"reason": "감사 로그 API 확인은 백엔드 드라이버 필요"})
            print_res(res, label); return res

        if not hasattr(driver, "create_report") or not hasattr(driver, "fetch_audit"):
            res = result(name, "NA", {"reason": "driver.create_report/fetch_audit 미구현"})
            print_res(res, label); return res

        create_payload = step.get("create_report", {})
        report = driver.create_report(create_payload)
        _ = report.get("id") if isinstance(report, dict) else None

        audits = driver.fetch_audit(step.get("fetch_audit", {"action": "REPORT_CREATE", "limit": 10}))
        found = False
        for item in audits or []:
            if item.get("action") == "REPORT_CREATE" and item.get("user_id") and item.get("timestamp"):
                found = True
                break

        if found:
            res = result(name, "PASS", {"audit_count": len(audits or [])}, ["user_id,timestamp 포함 로그 발견"])
        else:
            res = result(name, "FAIL", {"audit_count": len(audits or [])}, ["필수 필드(user_id,timestamp) 누락"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res
    

# ---------------------------------------------------------------------
# 무결성: 리포트 제출 이후 내용 변경 불가 확인
# ---------------------------------------------------------------------
def report_lock_immutable(step: Dict[str, Any], driver):
    """
    제출 후 수정이 403/차단되는지 확인.
    
    기대 입력(예시):
      step = {
        "report_id": "r123",
        "submit": True,
        "edit_attempt": {"title": "changed"}
      }
    driver 기대:
      - driver.submit_report(report_id) -> {"status": 200, ...}
      - driver.update_report(report_id, payload) -> {"status": int, ...}
    """
    name = "report_submission_immutability_check"
    label = "[리포트 불변성(제출 후 수정 불가) 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw:
            res = result(name, "NA", {"reason": "제출/수정 차단 확인은 백엔드 드라이버 필요"})
            print_res(res, label); return res

        if not hasattr(driver, "update_report"):
            res = result(name, "NA", {"reason": "driver.update_report 미구현"})
            print_res(res, label); return res

        rid = step.get("report_id")
        if not rid:
            res = result(name, "NA", {"reason": "report_id 미지정"})
            print_res(res, label); return res

        if step.get("submit") and hasattr(driver, "submit_report"):
            driver.submit_report(rid)

        resp = driver.update_report(rid, step.get("edit_attempt", {"title": "x"}))
        status_code = int(resp.get("status", 0))
        if status_code in (401, 403, 423):
            res = result(name, "PASS", {"update_status": status_code}, ["제출 이후 수정 차단 확인"])
        elif 200 <= status_code < 300:
            res = result(name, "FAIL", {"update_status": status_code}, ["제출 이후에도 수정 성공"])
        else:
            res = result(name, "WARN", {"update_status": status_code}, ["명확한 차단 코드 아님"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res
    
    
# ---------------------------------------------------------------------
# 무결성: 관리자 모드에서 사용자 활동 이력 확인
# ---------------------------------------------------------------------
def admin_audit_view(step: Dict[str, Any], driver):
    """
    관리자 로그 조회/필터/페이징 등 기본 동작 확인.
    
    기대 입력(예시):
      step = {
        "query": {"limit": 10, "action": "LOGIN"},
        "require_fields": ["id", "action", "timestamp"]
      }
    driver 기대:
      - driver.fetch_admin_logs(query) -> List[Dict]
    """
    name = "admin_activity_log_view_check"
    label = "[관리자 활동 이력 조회 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw:
            res = result(name, "NA", {"reason": "로그 API 확인은 백엔드 드라이버 필요"})
            print_res(res, label); return res

        if not hasattr(driver, "fetch_admin_logs"):
            res = result(name, "NA", {"reason": "driver.fetch_admin_logs 미구현"})
            print_res(res, label); return res

        logs = driver.fetch_admin_logs(step.get("query", {"limit": 10}))
        req = set(step.get("require_fields", ["id", "action", "timestamp"]))
        ok = False
        if isinstance(logs, list) and logs:
            sample = logs[0]
            ok = all(k in sample for k in req)

        if ok:
            res = result(name, "PASS", {"count": len(logs)}, ["필수 필드 포함 로그 조회 성공"])
        elif isinstance(logs, list):
            res = result(name, "WARN", {"count": len(logs)}, ["로그는 있으나 필수 필드 누락"])
        else:
            res = result(name, "FAIL", {}, ["로그 조회 실패 또는 빈 결과"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res


# ---------------------------------------------------------------------
# 무결성: 각 작업별 로그 주체 기록 여부 확인(액터 필드)
# ---------------------------------------------------------------------
def action_logging(step: Dict[str, Any], driver):
    """
    로그 항목에 user_id/email 등 주체 식별자가 항상 포함되는지 확인.

    기대 입력(예시):
      step = {
        "query": {"limit": 20},
        "actor_keys": ["user_id", "user_email"]
      }
    driver 기대:
      - driver.fetch_admin_logs(query) -> List[Dict]
    """
    name = "log_actor_presence_check"
    label = "[로그 주체 기록 여부 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw or not hasattr(driver, "fetch_admin_logs"):
            res = result(name, "NA", {"reason": "백엔드 드라이버 필요"})
            print_res(res, label); return res

        actor_keys = step.get("actor_keys", ["user_id", "user_email", "actor"])
        logs = driver.fetch_admin_logs(step.get("query", {"limit": 20})) or []
        missing = 0
        for item in logs:
            if not any(k in item and item.get(k) for k in actor_keys):
                missing += 1

        if not logs:
            res = result(name, "FAIL", {"count": 0}, ["로그가 비어 있음"]); print_res(res, label); return res
        if missing == 0:
            res = result(name, "PASS", {"count": len(logs)}, ["모든 로그에 주체 식별 포함"]); print_res(res, label); return res
        ratio = missing / max(1, len(logs))
        status = "WARN" if ratio < 0.2 else "FAIL"
        res = result(name, status, {"count": len(logs), "missing": missing}, [f"주체 누락 비율 {ratio:.0%}"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res


# ---------------------------------------------------------------------
# 무결성: 로그인 기능 인증 처리 확인
# ---------------------------------------------------------------------
def auth_login(step: Dict[str, Any], driver):
    """
    비로그인 보호자원 접근 차단, 로그인 후 접근 허용 여부 확인.
    
    기대 입력(예시):
      step = {
        "protected_endpoint": "/api/me",
        "credentials": {"username": "u", "password": "p"}
      }
    driver 기대:
      - driver.get(endpoint) -> {"status": int, ...}
      - driver.login(credentials) -> {"status": int, ...}
      - driver.get_authenticated(endpoint) -> {"status": int, ...}
    """
    name = "login_authentication_check"
    label = "[로그인 인증 처리 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw:
            res = result(name, "NA", {"reason": "백엔드 드라이버 기반 확인 필요"})
            print_res(res, label); return res

        if not all(hasattr(driver, m) for m in ("get", "login", "get_authenticated")):
            res = result(name, "NA", {"reason": "driver.get/login/get_authenticated 필요"})
            print_res(res, label); return res

        protected = step.get("protected_endpoint")
        creds = step.get("credentials")
        if not protected or not creds:
            res = result(name, "NA", {"reason": "protected_endpoint/credentials 미설정"})
            print_res(res, label); return res

        r1 = driver.get(protected)
        s1 = int(r1.get("status", 0))
        blocked_ok = (s1 in (401, 403)) or (300 <= s1 < 400)

        r2 = driver.login(creds)
        s2 = int(r2.get("status", 0))
        if not (200 <= s2 < 300):
            res = result(name, "FAIL", {"pre_status": s1, "login_status": s2}, ["로그인 실패"])
            print_res(res, label); return res

        r3 = driver.get_authenticated(protected)
        s3 = int(r3.get("status", 0))
        if blocked_ok and (200 <= s3 < 300):
            res = result(name, "PASS", {"pre_status": s1, "auth_status": s3}, ["인증 흐름 정상"])
        else:
            res = result(name, "FAIL", {"pre_status": s1, "auth_status": s3}, ["인증 흐름 비정상"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res
    

# ---------------------------------------------------------------------
# 무결성 로그인 실패 시도 제한 기능 확인(브루트포스 방어)
# ---------------------------------------------------------------------
def login_rate_limit(step: Dict[str, Any], driver):
    """
    연속된 실패 후 임시 차단/지연이 적용되는지 확인.
    
    기대 입력(예시):
      step = {
        "username": "test_user",
        "wrong_password": "x",
        "attempts": 7,
        "block_expected_after": 5
      }
    driver 기대:
      - driver.login({"username":..., "password":...}) -> {"status": int, "text": "..."}
    """
    name = "login_rate_limit_check"
    label = "[로그인 실패 시도 제한 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw or not hasattr(driver, "login"):
            res = result(name, "NA", {"reason": "백엔드 드라이버 login 필요"})
            print_res(res, label); return res

        user = step.get("username")
        wrong = step.get("wrong_password", "invalid")
        attempts = int(step.get("attempts", 7))
        cutoff = int(step.get("block_expected_after", 5))
        if not user:
            res = result(name, "NA", {"reason": "username 미설정"})
            print_res(res, label); return res

        blocked = False
        statuses: List[int] = []
        for i in range(attempts):
            resp = driver.login({"username": user, "password": wrong})
            statuses.append(int(resp.get("status", 0)))
            # 차단 시나리오 판단(429/423/403 등, 또는 'too many attempts' 메시지)
            text = (resp.get("text") or "").lower()
            if statuses[-1] in (429, 423) or "too many" in text or "locked" in text:
                blocked = True
                break

        details = {"attempts": len(statuses), "statuses": statuses}
        if blocked and len(statuses) >= cutoff:
            res = result(name, "PASS", details, ["실패 누적 후 차단/지연 동작 확인"])
        elif blocked:
            res = result(name, "WARN", details, ["차단 동작은 있으나 기대 횟수 이전에 발동"])
        else:
            res = result(name, "FAIL", details, ["무제한 실패 허용 또는 차단 미동작"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res


# ---------------------------------------------------------------------
# 무결성: 인증 토큰 만료 처리 확인(JWT exp 등)
# ---------------------------------------------------------------------
def token_expiry(step: Dict[str, Any], driver):
    """
    만료된 토큰으로 보호자원 접근 시 401/재인증 요구되는지 확인.
    refresh 플로우가 있으면 만료→리프레시→재시도도 점검 가능.
    
    기대 입력(예시):
      step = {
        "protected_endpoint": "/api/me",
        "expired_token": "eyJhbGciOiJI...",  # (선택) 테스트용 만료 토큰
        "check_refresh": False
      }
    driver 기대:
      - driver.get_with_token(endpoint, token) -> {"status": int, ...}
      - (선택) driver.refresh_token(old_token) -> {"status": int, "token": "..."}
    """
    name = "token_expiry_handling_check"
    label = "[인증 토큰 만료 처리 결과]"
    is_pw, mode = is_playwright(driver, step.get("mode"))

    try:
        if is_pw:
            res = result(name, "NA", {"reason": "백엔드 드라이버 필요"})
            print_res(res, label); return res

        if not hasattr(driver, "get_with_token"):
            res = result(name, "NA", {"reason": "driver.get_with_token 미구현"})
            print_res(res, label); return res

        endpoint = step.get("protected_endpoint")
        expired = step.get("expired_token")
        if not endpoint or not expired:
            res = result(name, "NA", {"reason": "protected_endpoint/expired_token 미지정"})
            print_res(res, label); return res

        r1 = driver.get_with_token(endpoint, expired)
        s1 = int(r1.get("status", 0))
        if s1 in (401, 419, 440):
            evid = ["만료 토큰 접근 거부 확인"]
            details = {"expired_status": s1}

            if step.get("check_refresh") and hasattr(driver, "refresh_token"):
                rr = driver.refresh_token(expired)
                rs = int(rr.get("status", 0))
                new_t = rr.get("token")
                details["refresh_status"] = rs
                details["has_new_token"] = bool(new_t)
                if 200 <= rs < 300 and new_t:
                    r2 = driver.get_with_token(endpoint, new_t)
                    s2 = int(r2.get("status", 0))
                    details["post_refresh_status"] = s2
                    if 200 <= s2 < 300:
                        evid.append("리프레시 후 재접근 성공")
                        res = result(name, "PASS", details, evid); print_res(res, label); return res
                    else:
                        res = result(name, "WARN", details, evid + ["리프레시 후에도 접근 불가"]); print_res(res, label); return res
            res = result(name, "PASS", details, evid); print_res(res, label); return res

        res = result(name, "FAIL", {"expired_status": s1}, ["만료 토큰으로 접근 허용됨"])
        print_res(res, label); return res

    except Exception as e:
        res = result(name, "ERROR", error=str(e))
        print_res(res, label); return res