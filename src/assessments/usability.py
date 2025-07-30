# src/assessments/usability.py
def check(driver, step):
    url = step["target"]
    selector = step["params"]["check_selector"]

    print(f"[USABILITY] 방문: {url}")
    driver.visit(url)

    try:
        text = driver.get_text(selector)
        print(f"[USABILITY] 요소 '{selector}' 텍스트: {text}")
    except Exception as e:
        print(f"[USABILITY] 요소 '{selector}' 찾기 실패: {e}")
