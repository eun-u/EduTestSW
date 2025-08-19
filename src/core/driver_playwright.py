import os
import time
import hashlib
from typing import Optional, List, Dict, Any, Union

# 이 드라이버는 Playwright의 sync API에 의존합니다.
# 미설치/미설치-브라우저 상황에서 친절한 에러를 내도록 초기화 로직을 안전하게 감쌉니다.


class PlaywrightDriver:
    """
    Playwright 기반 UI 드라이버 (요청 컨텍스트 지원)
    - 기존 코드를 최대한 건드리지 않으면서, 초기화 안전성만 강화하고
      security.py에서 필요로 하는 선택적 백엔드형 메서드를 추가/보완했습니다.
    - API_BASE 환경 변수가 설정되어 있으면 RequestContext를 생성하여
      파일/레인지 다운로드, 간단한 API 호출 등을 수행할 수 있습니다.
    """

    def __init__(self, headless: bool = True):
        self.api_base: Optional[str] = os.environ.get("API_BASE")  # 예: http://127.0.0.1:8000
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.api = None
        self._started = False
        self._headless = headless

        # 안전한 초기화
        self._ensure_started()

    # ------------------------------------------------------------------
    # 초기화/종료
    # ------------------------------------------------------------------
    def _ensure_started(self):
        """sync_playwright().start() 및 브라우저 런치/컨텍스트 생성(안전 버전)"""
        if self._started:
            return

        # 1) 모듈 로딩
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(
                "[Playwright] 패키지가 설치되어 있지 않습니다.\n"
                "  → pip install playwright\n"
                "  → python -m playwright install  (브라우저 설치)"
            ) from e

        # 2) 런타임 시작 (중복 start 방지)
        try:
            self._pw = sync_playwright().start()
        except Exception as e:
            raise RuntimeError(
                "[Playwright] 런타임 시작 실패. 기존 Playwright 인스턴스가 stop되지 않았을 수 있습니다.\n"
                "테스트를 다시 시작하거나, 드라이버 close()가 정상 호출되는지 확인해주세요."
            ) from e

        # 3) RequestContext (API_BASE가 있으면 브라우저와 무관하게 API 호출 가능)
        try:
            if self.api_base:
                self.api = self._pw.request.new_context(base_url=self.api_base)
        except Exception:
            self.api = None  # 없어도 나머지 동작에는 영향 없음

        # 4) 브라우저 런치 (Chromium → Firefox → WebKit 순서 폴백)
        #    CI/컨테이너에서는 --no-sandbox / --disable-dev-shm-usage가 유용
        launch_args_chromium = {
            "headless": self._headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        last_err = None
        for engine in ("chromium", "firefox", "webkit"):
            try:
                browser_type = getattr(self._pw, engine)
                if engine == "chromium":
                    self.browser = browser_type.launch(**launch_args_chromium)
                else:
                    self.browser = browser_type.launch(headless=self._headless)
                break
            except Exception as e:
                last_err = e
                continue

        if not self.browser:
            # 브라우저 미설치 또는 OS 의존성 누락
            raise RuntimeError(
                "[Playwright] 브라우저 실행 실패.\n"
                "  1) python -m playwright install\n"
                "  2) (리눅스) python -m playwright install-deps  또는  playwright install --with-deps\n"
                "  3) CI/컨테이너 환경이라면 '--no-sandbox' 옵션 유지"
            ) from last_err

        # 5) 컨텍스트/페이지
        try:
            self.context = self.browser.new_context(accept_downloads=True)
            self.page = self.context.new_page()
        except Exception as e:
            # 컨텍스트 생성 실패 시 브라우저 종료 및 친절한 에러
            try:
                self.browser.close()
            except Exception:
                pass
            try:
                self._pw.stop()
            except Exception:
                pass
            self._started = False
            raise RuntimeError("[Playwright] 브라우저 컨텍스트 생성 실패") from e

        self._started = True

    def close(self):
        """브라우저/컨텍스트/런타임 안전 종료"""
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._started = False

    # ------------------------------------------------------------------
    # 기본 UI 동작 (기존 코드 최대한 유지 가정)
    # ------------------------------------------------------------------
    def visit(self, url: str) -> int:
        """
        페이지 이동. 반환값은 HTTP 상태코드(있을 때) 또는 0.
        Playwright의 page.goto()는 Response를 반환할 수 있습니다.
        """
        resp = self.page.goto(url, wait_until="load")
        try:
            return int(resp.status) if resp is not None else 0
        except Exception:
            return 0

    def measure_load_time(self, url: str) -> int:
        """URL 로딩 시간을 ms 단위로 측정"""
        t0 = time.time()
        self.visit(url)
        t1 = time.time()
        return int((t1 - t0) * 1000)

    def get_text(self, selector: str) -> str:
        loc = self.page.locator(selector).first
        try:
            return loc.inner_text().strip()
        except Exception:
            return ""

    def click(self, selector: str):
        self.page.locator(selector).first.click()

    def fill(self, selector: str, value: str):
        self.page.locator(selector).first.fill(value)

    def wait_for_selector(self, selector: str, timeout: int = 5000):
        self.page.wait_for_selector(selector, timeout=timeout)

    # ------------------------------------------------------------------
    # security.py가 "선택적으로" 사용하는 백엔드형 메서드들
    # (API_BASE 설정 시 동작, 없으면 제한적으로 NA 유발해도 무방)
    # ------------------------------------------------------------------
    # 보고서 관련
    def create_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api:
            return {"id": None}
        r = self.api.post("/api/reports", data=payload or {})
        try:
            return r.json()
        except Exception:
            return {"id": None}

    def get_report_hash(self, report_id: str) -> Optional[str]:
        if not self.api:
            return None
        r = self.api.get(f"/api/reports/{report_id}/hash")
        try:
            js = r.json()
            return js.get("hash")
        except Exception:
            return None

    def get_report_bytes(self, report_id: str) -> Optional[bytes]:
        if not self.api:
            return None
        r = self.api.get(f"/api/reports/{report_id}/download")
        return r.body() if 200 <= r.status < 300 else None

    def submit_report(self, report_id: str) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501}
        r = self.api.post(f"/api/reports/{report_id}/submit")
        return {"status": r.status}

    def update_report(self, report_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501}
        r = self.api.patch(f"/api/reports/{report_id}", data=payload or {})
        return {"status": r.status}

    def fetch_audit(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.api:
            return []
        r = self.api.get("/api/audit", params=query or {})
        try:
            return r.json() or []
        except Exception:
            return []

    def fetch_admin_logs(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.api:
            return []
        r = self.api.get("/api/admin/logs", params=query or {})
        try:
            return r.json() or []
        except Exception:
            return []

    # 파일 다운로드/메타/레인지
    def download_file(self, file_id: str) -> Optional[bytes]:
        """
        우선순위:
          1) API_BASE가 있으면 /api/files/{id}/download로 직접 호출
          2) (선택) UI 경로가 있다면 self.api_base/files/{id} 접근 후 expect_download 사용
        """
        if self.api:
            r = self.api.get(f"/api/files/{file_id}/download")
            return r.body() if 200 <= r.status < 300 else None

        # API가 없는 환경에서는 UI를 통해 다운받아야 하며,
        # 실제 페이지 구조/링크 셀렉터에 맞춘 구현이 필요합니다.
        if self.api_base:
            try:
                # 직접 URL 접근으로 다운로드를 트리거하는 페이지라면:
                self.page.goto(f"{self.api_base}/files/{file_id}")
                with self.page.expect_download() as dl_info:
                    # 필요 시 다운로드 버튼 클릭 로직을 추가하세요.
                    pass
                download = dl_info.value
                path = download.path()
                return open(path, "rb").read() if path else None
            except Exception:
                return None
        return None

    def get_file_hash(self, file_id: str) -> Optional[str]:
        b = self.download_file(file_id)
        if not b:
            return None
        h = hashlib.sha256()
        h.update(b)
        return h.hexdigest()

    def get_file_meta(self, file_id: str) -> Optional[Dict[str, Union[int, str]]]:
        if not self.api:
            return None
        r = self.api.head(f"/api/files/{file_id}")
        try:
            length = int(r.headers.get("content-length") or 0) or None
        except Exception:
            length = None
        ctype = r.headers.get("content-type")
        return {"content_length": length, "content_type": ctype} if (length or ctype) else None

    def download_range(self, file_id: str, start: int, end: int) -> Optional[bytes]:
        if not self.api:
            return None
        # Range 사양: bytes=start-end  (end는 inclusive. security.py에서는 end-1로 전달함)
        r = self.api.get(f"/api/files/{file_id}/download", headers={"Range": f"bytes={start}-{end-1}"})
        return r.body() if 200 <= r.status < 300 else None

    def get_file_signature(self, file_id: str) -> Optional[Dict[str, Any]]:
        if not self.api:
            return None
        r = self.api.get(f"/api/files/{file_id}/signature")
        try:
            return r.json()
        except Exception:
            return None

    def verify_signature(self, blob: bytes, sig_info: Dict[str, Any]) -> bool:
        """
        서버가 검증 API를 제공하면 그쪽을 호출하는 게 더 정확합니다.
        여기서는 데모로 'hash prefix 일치' 정도만 확인합니다.
        """
        if not blob or not sig_info:
            return False
        hh = hashlib.sha256()
        hh.update(blob)
        return hh.hexdigest().startswith((sig_info or {}).get("signature", ""))

    # 입력값 검증/인증
    def post_json(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api:
            # security.py는 Playwright 모드에서 이 경우 NA 처리하므로 501로 반환
            return {"status": 501, "text": "api not configured"}
        r = self.api.post(endpoint, data=payload or {})
        body = r.text()
        try:
            js = r.json()
        except Exception:
            js = None
        return {"status": r.status, "json": js, "text": body}

    def get(self, endpoint: str) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501, "text": "api not configured"}
        r = self.api.get(endpoint)
        return {"status": r.status, "text": r.text()}

    def login(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501, "text": "api not configured"}
        r = self.api.post("/api/login", data=credentials or {})
        return {"status": r.status, "text": r.text()}

    def get_authenticated(self, endpoint: str) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501, "text": "api not configured"}
        r = self.api.get(endpoint)
        return {"status": r.status, "text": r.text()}

    def get_with_token(self, endpoint: str, token: str) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501, "text": "api not configured"}
        r = self.api.get(endpoint, headers={"Authorization": f"Bearer {token}"})
        return {"status": r.status, "text": r.text()}

    def refresh_token(self, old_token: str) -> Dict[str, Any]:
        if not self.api:
            return {"status": 501, "token": None}
        r = self.api.post("/api/refresh", data={"token": old_token})
        try:
            js = r.json()
        except Exception:
            js = {}
        return {"status": r.status, "token": js.get("token")}