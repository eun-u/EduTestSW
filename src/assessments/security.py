"""
>> 보안성 Security <<

|기밀성|Confidentiality|
- https_check : https 통신 적용 확인
- file_encryption : 파일 암호화 저장 여부 확인

|무결성|Integrity|
- hash_integrity :
- input_validation : 

|부인방지|Non-Reputation|

|책임성|Accountability|

|인증성|Authenticity|

"""

import requests

def check(driver, step):
    assessment_type = step["type"]
    
    if assessment_type == "https_check":
        check_https_applied(step, driver)
    else:
        raise ValueError(f"[SECURITY] 알 수 없는 검사 유형: {assessment_type}")
    


def check_https_applied(step, driver=None):
    """
    - HTTPS 통신이 적용되었는지 확인하는 함수
    - URL이 https://로 시작하지 않으면 경고
    - 실제 요청 후 상태 코드가 200이 아니면 오류
    """
    # Playwright인 경우
    if hasattr(driver, "page"):
        url = step.get("page")  # Playwright용 JSON에서는 "page" 필드를 사용
        print(f"[SECURITY > CONFIDENTIALITY] 브라우저로 이동할 페이지: {url}")

        if not url:
            raise ValueError("page 필드가 없습니다.")
        if not url.startswith("https://"):
            raise AssertionError(f"[SECURITY > CONFIDENTIALITY] HTTPS 미적용 페이지입니다: {url}")

        driver.visit(url)  # 실제로 브라우저를 띄우고 이동
        print(f"[SECURITY > CONFIDENTIALITY] HTTPS 적용된 페이지 브라우저 이동 완료")

    # 백엔드 드라이버인 경우
    else:
        url = step.get("url")
        print(f"[SECURITY > CONFIDENTIALITY] 요청할 백엔드 URL: {url}")

        if not url:
            raise ValueError("url 필드가 없습니다.")
        if not url.startswith("https://"):
            raise AssertionError(f"[SECURITY > CONFIDENTIALITY] HTTPS가 적용되지 않은 URL입니다: {url}")

        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                raise AssertionError(f"[SECURITY > CONFIDENTIALITY] HTTPS 통신 시 비정상 응답 코드: {response.status_code}")
            print(f"[SECURITY > CONFIDENTIALITY] HTTPS 통신 정상 확인됨: {url}")
        except Exception as e:
            raise AssertionError(f"[SECURITY > CONFIDENTIALITY] HTTPS 요청 중 오류 발생: {e}")