# 윤수영

# src/assessments/functional.py

def check(driver, step):
    """
    기능성 검사:
    - 특정 페이지(URL)에 접속한 후
    - 특정 요소(element)의 텍스트가 기대값(expected_text)과 일치하는지 확인

    step 예시:
    {
        "url": "https://example.com/login",
        "element": "#login-button",
        "expected_text": "로그인"
    }
    """
    url = step["url"]
    element = step["element"]
    expected_text = step["expected_text"]

    # 드라이버로 페이지 방문
    driver.visit(url)

    # 요소의 텍스트 가져오기
    text = driver.get_text(element)

    print(f"[Functional] {url} - 요소 '{element}' 텍스트: '{text}'")

    if expected_text not in text:
        raise AssertionError(
            f"기능 오류: '{element}'에 '{expected_text}' 문구가 없음"
        )

    print("[Functional] 기능성 검사 통과")

