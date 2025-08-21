# src/assessments/functional.py
# 웹 페이지의 기능적 요소를 확인하는 테스트 모듈입니다.
# 특정 기능(예: 회원가입, 결제)에 필요한 UI 요소들이 웹 페이지에 정상적으로 존재하는지 검사합니다.
# 요청된 파일 구조에 맞게 정리 및 주석을 추가했습니다.

from __future__ import annotations
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import sys
from colorama import Fore, Style

# (선택) Playwright를 사용할 수 없으면 임포트 오류를 무시합니다.
try:
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:
    sync_playwright = None  # type: ignore


UA = {"User-Agent": "FunctionalFeatureCheck/1.0"}

# =====================================================================
# 엔트리 포인트: 기능성 테스트 라우팅
# =====================================================================


def check(driver: Any, step: Dict[str, Any]) -> Dict[str, Any]:
    """
    두 가지 형태의 테스트를 지원합니다.
    A) 기능(feature) 기반:
      { "assessment":"functional", "feature":"signup|checkout|contact|social_login|newsletter", "url":"..." }
    B) 단일 요소(element) 기반:
      { "assessment":"functional", "url":"...", "element":"button", "expected_text":"Login" }
    """
    url = step.get("url")
    feature = step.get("feature")
    element = step.get("element")
    expected_text = (step.get("expected_text") or "").strip()

    if not url:
        result = {"status": "SKIP", "reason": "URL is empty"}
        print_step_result(result, name="functional")
        return result

    # 1) 페이지 로드 (드라이버 타입 자동 감지)
    try:
        soup = _load_page_content(driver, url)
    except requests.RequestException as e:
        result = {"status": "FAIL",
                  "reason": f"Request error: {e.__class__.__name__}", "url": url}
        print_step_result(result, name="functional")
        return result
    except Exception:
        # Playwright 로딩 실패 시 백엔드 경로로 폴백하므로 여기서 에러가 발생하면 심각한 경우
        result = {"status": "FAIL",
                  "reason": "Failed to load page content", "url": url}
        print_step_result(result, name="functional")
        return result

    # 2) 검사 실행
    if feature:
        res = _run_feature_checks(soup, feature)
        res["name"] = "feature_check"
        res["url"] = url
        res["feature"] = feature
    else:
        res = _run_element_check(soup, element or "", expected_text)
        res["name"] = "element_check"
        res["url"] = url
        res["element"] = element
        res["expected_text"] = expected_text

    print_step_result(res)
    return res


# =====================================================================
# 출력 유틸리티
# =====================================================================
'''def print_step_result(res: Dict[str, Any], name: Optional[str] = None) -> None:
    """단일 테스트 스텝의 요약 결과를 보기 좋게 출력합니다."""
    name = name or res.get("name", "(unknown)")
    status = res.get("status", "FAIL").upper()
    print(f"[{name.upper()}] STATUS: {status}")
    
    if res.get("url"):
        print(f"  - URL: {res['url']}")
        
    if "reason" in res:
        print(f"  - Reason: {res['reason']}")
    
    if "feature" in res:
        print(f"  - Feature: {res['feature']}")
        print(f"  - Checks: {res.get('passed', 0)} passed / {res.get('failed', 0)} failed")
        print("  - Details:")
        for detail in res.get("details", []):
            print(f"    • {detail}")
            
    if "element" in res:
        print(f"  - Element: {res['element']}")
        if res.get("expected_text"):
            print(f"  - Expected Text: '{res['expected_text']}'")
        if "details" in res:
            print(f"  - Details: {res['details'][0]}")
    
    print("-" * 30)'''


def color_status(status: str) -> str:
    if status == "PASS":
        return Fore.GREEN + status + Style.RESET_ALL
    elif status == "FAIL":
        return Fore.RED + status + Style.RESET_ALL
    elif status == "WARN":
        return Fore.YELLOW + status + Style.RESET_ALL
    elif status == "ERROR":
        return Fore.MAGENTA + status + Style.RESET_ALL
    return status or "N/A"


def print_step_result(res: Dict[str, Any], name: Optional[str] = None) -> None:
    title = res.get("feature")
    status = (res.get("status", "fail") or "fail").upper()

    detail_keys_order: List[str] = [
        "url",
        "element",
        "expected_text",
        "passed",
        "failed",
    ]
    details: Dict[str, Any] = {}
    for k in detail_keys_order:
        if k in res and res[k] not in (None, ""):
            details[k] = res[k]

    evidence: List[str] = []

    def sample(obj: Any, n: int = 3) -> str:
        if isinstance(obj, list):
            return str(obj[:n])
        if isinstance(obj, dict):
            return str(list(obj.items())[:n])
        s = str(obj)
        return s if len(s) <= 300 else s[:300]

    if res.get("details"):
        evidence.append(f"details(sample): {sample(res['details'])}")
    if res.get("issues"):
        evidence.append(f"issues(sample): {sample(res['issues'])}")
    if res.get("mismatches"):
        evidence.append(f"mismatches(sample): {sample(res['mismatches'])}")

    line_w = 70
    print("\n" + "=" * line_w)
    print(f"[FUNCTIONAL] {title}")
    print("-" * line_w)

    try:
        colored = color_status(status)
    except NameError:
        colored = status
    print(f"  • 상태       : {colored}")

    if res.get("error"):
        print(f"  • 오류       : {res['error']}")
    if res.get("reason"):
        print(f"  • 이유       : {res['reason']}")

    if details:
        print("  • 상세")
        for k, v in details.items():
            print(f"     - {k:<15}: {v}")

    if evidence:
        print("  • 근거")
        for e in evidence:
            print(f"     - {e}")

    print("=" * line_w)

# =====================================================================
# 페이지 로더
# =====================================================================


def _is_playwright_driver(driver: Any) -> bool:
    """전달된 드라이버 객체가 Playwright 기반인지 휴리스틱으로 판단합니다."""
    # 클래스 이름 확인
    cls_name = driver.__class__.__name__.lower()
    if "playwright" in cls_name or "browser" in cls_name or "context" in cls_name or "page" in cls_name:
        return True

    # 속성 기반 휴리스틱
    return any([
        hasattr(driver, "page"),
        hasattr(driver, "context"),
        hasattr(driver, "browser"),
    ])


def _load_page_content(driver: Any, url: str) -> BeautifulSoup:
    """
    드라이버 종류에 따라 페이지 콘텐츠를 로드합니다.
    Playwright 드라이버가 감지되면 동적 로딩을 시도하고, 아니면 requests로 정적 로딩합니다.
    """
    if _is_playwright_driver(driver):
        return _load_soup_playwright(driver, url)
    else:
        return _load_soup_backend(url)


def _load_soup_backend(url: str) -> BeautifulSoup:
    """requests 라이브러리를 사용해 페이지의 HTML을 정적으로 로드합니다."""
    resp = requests.get(url, headers=UA, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _load_soup_playwright(driver: Any, url: str) -> BeautifulSoup:
    """
    Playwright를 사용해 페이지를 로드하고 동적으로 생성된 HTML 콘텐츠를 반환합니다.
    다양한 Playwright 래퍼 형태에 대응합니다.
    """
    try:
        page = getattr(driver, "page", None)
        context = getattr(driver, "context", None)
        browser = getattr(driver, "browser", None)

        if not page:
            if context and hasattr(context, "new_page"):
                page = context.new_page()
            elif browser and hasattr(browser, "new_context"):
                context = browser.new_context()
                if hasattr(context, "new_page"):
                    page = context.new_page()

        if page:
            page.goto(url, wait_until="load", timeout=20000)
            html = page.content()
            return BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(
            f"[FUNCTIONAL] Playwright loading failed, falling back to backend: {e}", file=sys.stderr)

    # Playwright 로딩 실패 시 requests로 폴백
    return _load_soup_backend(url)

# =====================================================================
# 테스트 로직
# =====================================================================


def _plan_for_feature(feature: str) -> List[Dict[str, Any]]:
    """
    주어진 기능에 대한 테스트 계획(필요한 요소와 검사 방식)을 반환합니다.
    """
    f = (feature or "").lower()
    btn_signup = ["sign up", "signup", "register",
                  "create account", "sign me up"]
    btn_checkout = ["continue to checkout",
                    "continue", "pay", "place order", "checkout"]
    btn_send = ["send", "submit"]
    btn_subscribe = ["subscribe", "sign up", "join"]

    if f in ("signup", "register"):
        return [
            {"name": "email field", "kind": "email",
                "args": [["email"], ["email"]]},
            {"name": "password field", "kind": "password", "args": [
                ["password", "passwd", "pwd"], ["password"]]},
            {"name": "username hint", "kind": "hint",
                "args": [["username", "user", "name"]]},
            {"name": "submit button", "kind": "btn", "args": [btn_signup]},
        ]
    if f == "checkout":
        return [
            {"name": "name hint", "kind": "hint", "args": [
                ["firstname", "lastname", "name"]]},
            {"name": "address hint", "kind": "hint",
                "args": [["address", "street"]]},
            {"name": "city/state/zip hint", "kind": "hint",
                "args": [["city", "state", "zip", "postcode"]]},
            {"name": "card hint", "kind": "hint", "args": [
                ["card", "credit", "cc", "exp", "cvv"]]},
            {"name": "checkout button", "kind": "btn", "args": [btn_checkout]},
        ]
    if f == "contact":
        return [
            {"name": "name hint", "kind": "hint", "args": [["name"]]},
            {"name": "email field", "kind": "email",
                "args": [["email"], ["email"]]},
            {"name": "message textarea", "kind": "textarea",
                "args": [["message", "subject", "comments"]]},
            {"name": "send button", "kind": "btn", "args": [btn_send]},
        ]
    if f == "social_login":
        return [
            {"name": "social buttons", "kind": "btn", "args": [
                ["google", "facebook", "github", "twitter", "kakao", "naver"]]}
        ]
    if f == "newsletter":
        return [
            {"name": "email field", "kind": "email", "args": [
                ["email"], ["email", "newsletter"]]},
            {"name": "subscribe button", "kind": "btn",
                "args": [btn_subscribe]},
        ]
    # 폴백: 특정 기능명 자체가 힌트로 사용될 수 있습니다.
    return [{"name": "feature hint", "kind": "hint", "args": [[f]]}]


def _run_feature_checks(soup: BeautifulSoup, feature: str) -> Dict[str, Any]:
    """
    미리 정의된 테스트 계획(_plan_for_feature)에 따라 페이지 요소를 검사합니다.
    """
    checks = _plan_for_feature(feature)
    passed, failed, details = 0, 0, []

    for c in checks:
        kind, nm, args = c["kind"], c["name"], c["args"]
        ok = False

        if kind == "btn":
            ok = _any_button_has_text(soup, args[0])
        elif kind == "hint":
            ok = _exists_field_by_hint(soup, args[0])
        elif kind == "textarea":
            ok = _textarea_hint(soup, args[0])
        elif kind == "email":
            ok = _exist_input_types_or_hints(soup, ["email"], args[1])
        elif kind == "password":
            ok = _exist_input_types_or_hints(soup, ["password"], args[1])

        if ok:
            passed += 1
            details.append(f"{nm} OK")
        else:
            failed += 1
            details.append(f"{nm} MISSING")

    status = "pass" if failed == 0 else ("warn" if passed > 0 else "fail")
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "details": details
    }


def _run_element_check(soup: BeautifulSoup, element: str, expected_text: str) -> Dict[str, Any]:
    """
    단일 HTML 요소의 존재 여부와 텍스트 일치 여부를 검사합니다.
    """
    found = soup.find_all(element)

    if not found:
        return {"status": "FAIL", "passed": 0, "failed": 1, "details": [f"'{element}' not found"]}

    if expected_text:
        has = any((el.get_text(strip=True) == expected_text) for el in found)
        if has:
            return {"status": "PASS", "passed": 1, "failed": 0, "details": [f"{element} text == '{expected_text}'"]}
        else:
            cands = [el.get_text(strip=True)
                     for el in found if el.get_text(strip=True)]
            return {"status": "FAIL", "passed": 0, "failed": 1, "details": [f"Text mismatch (candidates: {cands[:5]})"]}
    else:
        return {"status": "PASS", "passed": 1, "failed": 0, "details": [f"{element} exists"]}


# =====================================================================
# 공통 헬퍼 함수 (재사용 가능한 유틸리티)
# =====================================================================
def _texts(el: Any) -> str:
    """주어진 HTML 요소의 텍스트를 추출합니다."""
    return el.get_text(separator=" ", strip=True) if el else ""


def _any_button_has_text(soup: BeautifulSoup, texts: List[str]) -> bool:
    """
    주어진 텍스트를 가진 버튼 또는 링크가 존재하는지 확인합니다.
    """
    candidates = [t.lower() for t in texts]
    for b in soup.find_all(["button", "a", "input"]):
        label = _texts(b) or (b.get("value") or "")
        if label and label.lower() in candidates:
            return True
    return False


def _exist_input_types_or_hints(soup: BeautifulSoup, types: List[str], hints: List[str]) -> bool:
    """
    지정된 'type'을 가진 입력 필드 또는 'name/placeholder/id'에 힌트가 포함된 필드를 찾습니다.
    """
    types_need = set(t.lower() for t in types)
    types_have = set()
    hint_low = [h.lower() for h in hints]
    hinted = False

    for inp in soup.find_all("input"):
        it = (inp.get("type") or "").lower()
        if it in types_need:
            types_have.add(it)

        # 힌트 체크
        blob = " ".join([(inp.get(attr) or "")
                        for attr in ["name", "placeholder", "id"]]).lower()
        if any(h in blob for h in hint_low):
            hinted = True

    # 타입이 다 있거나(정확), 힌트라도 있으면(관대) 통과
    return types_need.issubset(types_have) or hinted


def _exists_field_by_hint(soup: BeautifulSoup, hints: List[str]) -> bool:
    """
    지정된 힌트가 'name/id/placeholder'에 포함된 입력 필드, 텍스트 영역, 셀렉트 박스를 찾습니다.
    """
    h = [x.lower() for x in hints]
    for el in soup.find_all(["input", "textarea", "select"]):
        val_attrs = [(el.get(attr) or "").lower()
                     for attr in ["name", "id", "placeholder"]]
        combined_val = " ".join(val_attrs)
        if any(k in combined_val for k in h):
            return True
    return False


def _textarea_hint(soup: BeautifulSoup, hints: List[str]) -> bool:
    """
    지정된 힌트가 'name/id/placeholder'에 포함된 <textarea>를 찾습니다.
    """
    hint_low = [h.lower() for h in hints]
    for ta in soup.find_all("textarea"):
        attrs = [ta.get("placeholder", ""), ta.get(
            "name", ""), ta.get("id", "")]
        blob = " ".join(a.lower() for a in attrs)
        if any(h in blob for h in hint_low):
            return True
    return False


# =====================================================================
# 메인 실행 블록 (모듈이 직접 실행될 경우)
# =====================================================================
if __name__ == "__main__":
    # 이 모듈은 독립적으로 실행되지 않으며, 다른 모듈에서 호출되어 사용됩니다.
    # 예제 호출을 위한 더미 드라이버와 스텝 데이터입니다.
    class MockDriver:
        pass

    mock_driver = MockDriver()

    print("--- Example: Signup Feature Check ---")
    signup_step = {
        "assessment": "functional",
        "feature": "signup",
        "url": "https://example.com/signup"
    }
    check(mock_driver, signup_step)

    print("\n--- Example: Element Text Check ---")
    element_step = {
        "assessment": "functional",
        "url": "https://example.com",
        "element": "h1",
        "expected_text": "Welcome to Our Site"
    }
    check(mock_driver, element_step)
