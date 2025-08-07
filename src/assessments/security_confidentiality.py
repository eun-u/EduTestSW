"""
==== SECURITY > CONFIDENTIALITY ====

[Major Functions]
- check_https_certificate() : https 통신 적용 확인
- file_encryption() : 파일 암호화 저장 여부 확인

[Additional Functions]
- print_https_result() : https 인증서 검사 결과 출력

====================================
"""
import ssl
import socket
from urllib.parse import urlparse
import datetime


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
    port = 443 # https 기본 포트
    
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