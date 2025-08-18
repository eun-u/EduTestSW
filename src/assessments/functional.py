#윤수영

# src/assessments/functional.py
# 정리된 요약 블록으로 결과 출력하는 기능성 테스트
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

UA = {"User-Agent": "FunctionalFeatureCheck/1.0"}

# ───────────── 출력 유틸 ─────────────
def _box(title: str, lines: List[str]) -> None:
    width = max([len(title) + 2] + [len(l) for l in lines]) + 2
    top = "┏" + "━" * (width - 2) + "┓"
    mid = "┗" + "━" * (width - 2) + "┛"
    print(top)
    print(f"┃ {title}".ljust(width - 1) + "┃")
    for l in lines:
        print(("┃ " + l).ljust(width - 1) + "┃")
    print(mid)

def _line(k: str, v: str) -> str:
    return f"{k:<9}: {v}"

def _bullets(items: List[str]) -> List[str]:
    return [f"• {it}" for it in items]

# ───────────── 공통 헬퍼 ─────────────
def _texts(el) -> str:
    return el.get_text(separator=" ", strip=True) if el else ""

def _any_button_has_text(soup: BeautifulSoup, texts: List[str]) -> bool:
    cand = [t.lower() for t in texts]
    for b in soup.find_all(["button", "a", "input"]):
        label = _texts(b) or (b.get("value") or "")
        if label and label.lower() in cand:
            return True
    return False

def _exist_input_types_or_hints(soup: BeautifulSoup, types: List[str], hints: List[str]) -> bool:
    """
    type이 정확히 없어도 name/placeholder/id에 hint가 있으면 인정 (관대 모드)
    """
    types_need = set(t.lower() for t in types)
    types_have = set()
    hint_low = [h.lower() for h in hints]
    hinted = False

    for inp in soup.find_all("input"):
        it = (inp.get("type") or "").lower()
        nm = (inp.get("name") or "").lower()
        ph = (inp.get("placeholder") or "").lower()
        iid = (inp.get("id") or "").lower()
        if it in types_need:
            types_have.add(it)
        blob = " ".join([nm, ph, iid])
        if any(h in blob for h in hint_low):
            hinted = True

    # 타입이 다 있어도 OK, 아니면 hint라도 있으면 OK
    return types_need.issubset(types_have) or hinted

def _exists_field_by_hint(soup: BeautifulSoup, hints: List[str]) -> bool:
    h = [x.lower() for x in hints]
    for el in soup.find_all(["input", "textarea", "select"]):
        name = (el.get("name") or "").lower()
        iid = (el.get("id") or "").lower()
        ph = (el.get("placeholder") or "").lower()
        val = " ".join([name, iid, ph])
        if any(k in val for k in h):
            return True
    return False

def _textarea_hint(soup: BeautifulSoup, hints: List[str]) -> bool:
    hint_low = [h.lower() for h in hints]
    for ta in soup.find_all("textarea"):
        ph = (ta.get("placeholder") or "").lower()
        nm = (ta.get("name") or "").lower()
        iid = (ta.get("id") or "").lower()
        blob = " ".join([ph, nm, iid])
        if any(h in blob for h in hint_low):
            return True
    return False

# ───────────── 기능별 플랜 ─────────────
def _plan_for_feature(feature: str) -> List[Dict[str, Any]]:
    f = (feature or "").lower()
    btn_signup = ["sign up", "signup", "register", "create account", "sign me up"]
    btn_checkout = ["continue to checkout", "continue", "pay", "place order", "checkout"]
    btn_send = ["send", "submit"]
    btn_subscribe = ["subscribe", "sign up", "join"]

    if f in ("signup", "register"):
        return [
            {"name": "email field", "kind": "email", "args": [["email"], ["email"]]},
            {"name": "password field", "kind": "password", "args": [["password", "passwd", "pwd"], ["password"]]},
            {"name": "username hint", "kind": "hint", "args": [["username", "user", "name"]]},
            {"name": "submit button", "kind": "btn", "args": [btn_signup]},
        ]
    if f == "checkout":
        return [
            {"name": "name hint", "kind": "hint", "args": [["firstname", "lastname", "name"]]},
            {"name": "address hint", "kind": "hint", "args": [["address", "street"]]},
            {"name": "city/state/zip hint", "kind": "hint", "args": [["city", "state", "zip", "postcode"]]},
            {"name": "card hint", "kind": "hint", "args": [["card", "credit", "cc", "exp", "cvv"]]},
            {"name": "checkout button", "kind": "btn", "args": [btn_checkout]},
        ]
    if f == "contact":
        return [
            {"name": "name hint", "kind": "hint", "args": [["name"]]},
            {"name": "email field", "kind": "email", "args": [["email"], ["email"]]},
            {"name": "message textarea", "kind": "textarea", "args": [["message", "subject", "comments"]]},
            {"name": "send button", "kind": "btn", "args": [btn_send]},
        ]
    if f == "social_login":
        return [
            {"name": "social buttons", "kind": "btn", "args": [["google", "facebook", "github", "twitter", "kakao", "naver"]]}
        ]
    if f == "newsletter":
        return [
            {"name": "email field", "kind": "email", "args": [["email"], ["email", "newsletter"]]},
            {"name": "subscribe button", "kind": "btn", "args": [btn_subscribe]},
        ]
    # fallback
    return [{"name": "feature hint", "kind": "hint", "args": [[f]]}]

def _run_feature_checks(soup: BeautifulSoup, feature: str) -> Dict[str, Any]:
    checks = _plan_for_feature(feature)
    passed, failed, details = 0, 0, []
    for c in checks:
        kind = c["kind"]
        nm = c["name"]
        args = c["args"]
        ok = False

        if kind == "btn":
            ok = _any_button_has_text(soup, args[0])
        elif kind == "hint":
            ok = _exists_field_by_hint(soup, args[0])
        elif kind == "textarea":
            ok = _textarea_hint(soup, args[0])
        elif kind == "email":
            # types=["email"] OR hints in name/placeholder (관대)
            ok = _exist_input_types_or_hints(soup, ["email"], args[1])
        elif kind == "password":
            ok = _exist_input_types_or_hints(soup, ["password"], args[1])
        else:
            ok = False

        if ok:
            passed += 1
            details.append(f"{nm} OK")
        else:
            failed += 1
            details.append(f"{nm} MISSING")

    status = "PASS" if failed == 0 else ("WARN" if passed > 0 else "FAIL")
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "details": details
    }

# ───────────── 요소 단일 검사(호환) ─────────────
def _run_element_check(soup: BeautifulSoup, element: str, expected_text: str) -> Dict[str, Any]:
    found = soup.find_all(element)
    if not found:
        return {"status": "FAIL", "passed": 0, "failed": 1, "details": [f"'{element}' not found"]}

    if expected_text:
        has = any((el.get_text(strip=True) == expected_text) for el in found)
        if has:
            return {"status": "PASS", "passed": 1, "failed": 0, "details": [f"{element} text == '{expected_text}'"]}
        else:
            cands = [el.get_text(strip=True) for el in found if el.get_text(strip=True)]
            cands = cands[:5]
            return {"status": "FAIL", "passed": 0, "failed": 1, "details": [f"text mismatch (candidates={cands})"]}
    else:
        return {"status": "PASS", "passed": 1, "failed": 0, "details": [f"{element} exists"]}

# ───────────── 페이지 로더 ─────────────
def _load_soup_backend(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=UA, timeout=12)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def _load_soup_playwright(driver, url: str) -> BeautifulSoup:
    """
    PlaywrightDriver의 형태가 서로 다를 수 있어 최대한 관대한 탐색:
    - driver.page 가 있으면 그대로 사용
    - driver.context 가 있으면 new_page()
    - driver.browser 가 있으면 새 context/page 생성
    - 어떤 것도 없으면 Backend 로더로 폴백
    """
    try:
        page = getattr(driver, "page", None)

        context = getattr(driver, "context", None)
        browser = getattr(driver, "browser", None)

        if page is None and context is not None and hasattr(context, "new_page"):
            page = context.new_page()

        if page is None and browser is not None:
            # 일부 래퍼는 browser만 노출
            context = browser.new_context()
            page = context.new_page()

        if page is None:
            # 드라이버 래퍼가 페이지 인터페이스를 안 노출했다면 백엔드 경로로 폴백
            return _load_soup_backend(url)

        page.goto(url, wait_until="load", timeout=15000)
        html = page.content()
        return BeautifulSoup(html, "html.parser")
    except Exception:
        # 실패 시에도 백엔드 경로로 폴백하여 테스트를 이어간다.
        return _load_soup_backend(url)

def _is_playwright_driver(driver) -> bool:
    cls = driver.__class__.__name__.lower()
    if "playwright" in cls:
        return True
    # 속성 기반 휴리스틱
    return any([
        hasattr(driver, "page"),
        hasattr(driver, "context"),
        hasattr(driver, "browser"),
    ])

# ───────────── 메인 엔트리 ─────────────
def check(driver, step):
    """
    두 형태 모두 지원
    A) feature 기반:
      { "assessment":"functional", "feature":"signup|checkout|contact|social_login|register|newsletter", "url":"..." }
    B) 단일 요소 기반(레거시):
      { "assessment":"functional", "url":"...", "element":"button", "expected_text":"Login" }
    """
    url = step.get("url")
    feature = step.get("feature")
    element = step.get("element")
    expected_text = (step.get("expected_text") or "").strip()

    if not url:
        _box("Functional Result", [_line("Status", "SKIP"), _line("Reason", "url is empty")])
        return

    # 1) 페이지 로드 (드라이버 타입 자동 감지)
    is_pw = _is_playwright_driver(driver)
    try:
        soup = _load_soup_playwright(driver, url) if is_pw else _load_soup_backend(url)
    except Exception as e:
        _box("Functional Result", [
            _line("Status", "FAIL"),
            _line("URL", url),
            _line("Reason", f"request error: {e.__class__.__name__}")
        ])
        return

    # 2) 검사 실행 (로직은 공통)
    if feature:
        res = _run_feature_checks(soup, feature)
        title = "Functional Result"
        lines = [
            _line("Status", res["status"]),
            _line("Feature", feature),
            _line("URL", url),
            _line("Checks", f"{res['passed']} passed / {res['failed']} failed"),
            "Details",
        ] + _bullets(res["details"])
        _box(title, lines)
    else:
        res = _run_element_check(soup, element or "", expected_text)
        title = "Functional Result"
        lines = [
            _line("Status", res["status"]),
            _line("Element", element or "-"),
            _line("URL", url),
            "Details",
        ] + _bullets(res["details"])
        _box(title, lines)
