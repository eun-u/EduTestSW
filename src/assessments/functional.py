# 윤수영

# src/assessments/functional.py
import requests
from bs4 import BeautifulSoup

def check(driver, step):
    url = step.get("url")
    element = step.get("element")      # 예: "button"
    expected_text = step.get("expected_text", "").strip()

    if not url or not element:
        print("[SKIP][functional] url/element가 비었습니다.")
        return

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    found = soup.find_all(element)

    if not found:
        print(f"[FAIL][functional] '{element}' 요소를 찾지 못했습니다. url={url}")
        return

    # expected_text가 있으면 텍스트 일치 확인
    if expected_text:
        has_match = any((el.get_text(strip=True) == expected_text) for el in found)
        if has_match:
            print(f"[PASS][functional] '{element}' 요소에 텍스트 '{expected_text}' 발견")
        else:
            # 근접 텍스트 후보 보여주기
            candidates = [el.get_text(strip=True) for el in found][:5]
            print(f"[FAIL][functional] '{element}'는 있으나 텍스트 '{expected_text}' 미일치. 후보={candidates}")
    else:
        print(f"[PASS][functional] '{element}' 요소가 존재합니다.")


