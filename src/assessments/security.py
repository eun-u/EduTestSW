"""
========== 보안성 Security ==========

| 기밀성 | Confidentiality |
- check_https_certificate : https 통신 적용 확인
- check_file_encryption_static : 파일 암호화 저장 여부 확인
                                 (llm 프롬프트 기반 정적 코드 리뷰)
+ print_https_result : https 인증서 검사 결과 출력

| 무결성 | Integrity |
- hash_integrity :
- input_validation : 

| 부인방지 | Non-Reputation |

| 책임성 | Accountability |

| 인증성 | Authenticity |

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