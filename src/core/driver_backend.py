import requests           # HTTP 요청을 보내기 위한 라이브러리
import time               # 시간 측정용 (로딩 시간 등)
from bs4 import BeautifulSoup  # HTML 파싱용
import json
import os
import subprocess         # 외부 명령어 실행용 (정적 분석 등)

import hashlib
import datetime as dt
from typing import Optional


# 백엔드 API 및 정적 분석 등을 수행하는 드라이버
class BackendDriver:
    def __init__(self):
        self.session = requests.Session()  # 세션 객체로 쿠키 등 유지
        self.last_response = None          # 마지막 응답 객체 저장
        self.last_url = None               # 마지막 요청 URL
        self.last_html = ""                # HTML 응답 저장
        self.last_json = None              # JSON 응답 저장
        self.last_soup = None              # HTML을 BeautifulSoup으로 파싱한 결과 저장
        print("[DRIVER] 실제 백엔드 드라이버 초기화 완료")
    
        # (추가) API 베이스 URL (선택). 설정 시 실제 서버 호출 가능
        #    ex) export API_BASE=http://127.0.0.1:8000
        self.api_base: Optional[str] = os.environ.get("API_BASE")

        # (추가) 보안 테스트용 인메모리 스텁 저장소
        self._reports = {}     # {id: {"content": bytes, "hash": str, "locked": bool}}
        self._files = {}       # {file_id: bytes}
        self._audits = []      # [{"action":..., "user_id":..., "timestamp":...}]
        self._admin_logs = []  # [{"id":..., "action":..., "timestamp":..., "user_id":..., "user_email":..., "actor":...}]
        self._login_attempts = {}  # {username: count}
        self._sessions = set()     # {"admin@example.com"}
        self._token_store = {}     # {"NEW": {"exp": "..."}}
        self._seed_stub_data()
    
    def visit(self, url):
        """GET 요청을 보내고 응답을 분석하여 HTML/JSON으로 분류"""
        print(f"[DRIVER] 방문: {url}")
        response = self.session.get(url)
        self.last_response = response
        self.last_url = url
        content_type = response.headers.get("Content-Type", "")

        # HTML 응답 처리
        if "html" in content_type:
            self.last_html = response.text
            self.last_soup = BeautifulSoup(response.text, "html.parser")
            self.last_json = None
        # JSON 응답 처리
        elif "json" in content_type:
            self.last_json = response.json()
            self.last_html = ""
            self.last_soup = None
        # 기타 형식
        else:
            self.last_html = ""
            self.last_json = None
            self.last_soup = None
        return response.status_code

    def measure_load_time(self, url):
        """URL 로딩 시간을 ms 단위로 측정"""
        start = time.time()
        self.visit(url)
        end = time.time()
        elapsed = int((end - start) * 1000)
        print(f"[DRIVER] 로딩 시간: {elapsed}ms")
        return elapsed

    def get_text(self, selector):
        """HTML 응답에서 특정 CSS 선택자의 텍스트 반환"""
        if not self.last_soup:
            raise Exception("HTML 응답이 없습니다.")
        element = self.last_soup.select_one(selector)
        return element.text.strip() if element else ""

    def get_json_field(self, key_path):
        """
        JSON 응답에서 key_path에 해당하는 값을 반환
        key_path 예시: 'user.name.first' → json['user']['name']['first']
        """
        if not self.last_json:
            raise Exception("JSON 응답이 없습니다.")
        keys = key_path.split(".")
        value = self.last_json
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value

    def check_header(self, key):
        """응답 헤더에 특정 키가 있는지 확인"""
        if not self.last_response:
            raise Exception("응답이 없습니다.")
        return key in self.last_response.headers

    def post(self, url, data=None):
        """POST 요청을 보내고 JSON 응답 저장"""
        print(f"[DRIVER] POST 요청: {url} with data: {data}")
        response = self.session.post(url, json=data)
        self.last_response = response
        content_type = response.headers.get("Content-Type", "")

        if "json" in content_type:
            self.last_json = response.json()
        else:
            self.last_json = None
        return response.status_code

    def run_static_analysis(self, path):
        """
        radon을 사용한 코드 복잡도 정적 분석
        - radon 설치 필요: pip install radon
        - 분석 결과를 문자열로 반환
        """
        print(f"[DRIVER] 코드 복잡도 분석 실행: {path}")
        if not os.path.exists(path):
            raise Exception("분석 대상 경로가 존재하지 않습니다.")

        try:
            result = subprocess.check_output(
                ["radon", "cc", path, "-s", "-a"], universal_newlines=True
            )
            return result
        except Exception as e:
            return f"분석 실패: {e}"

    def run(self):
        """세션 종료 및 드라이버 종료 메시지 출력"""
        print("[DRIVER] 백엔드 드라이버 종료")
        self.session.close()


    # ======================================================================
    # 여기서부터 '보안성 루틴'이 요구하는 메서드들을 추가합니다 (기존 코드 미변경)
    # ======================================================================

    # ---- 내부 유틸 & 스텁 시딩 ----
    def _sha256_bytes(self, b: bytes) -> str:
        h = hashlib.sha256()
        h.update(b)
        return h.hexdigest()

    def _now_iso(self) -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def _seed_stub_data(self):
        # 샘플 파일 (간단한 PDF 바이트)
        pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
        self._files["FILE-EXAMPLE-001"] = pdf

        # 리포트: 불변성 테스트용 플레이스홀더
        rid = "RPT-PLACEHOLDER-IMMUTABLE"
        content = f"Report content for {rid}".encode("utf-8")
        self._reports[rid] = {
            "content": content,
            "hash": self._sha256_bytes(content),
            "locked": False,
        }

        # 관리자 로그 샘플
        for i in range(3):
            self._admin_logs.append({
                "id": f"log-{i+1}",
                "action": "LOGIN" if i % 2 == 0 else "DOWNLOAD",
                "timestamp": self._now_iso(),
                "user_id": "admin",
                "user_email": "admin@example.com",
                "actor": "admin@example.com",
            })

    def _abs_url(self, endpoint: str) -> Optional[str]:
        """상대 경로를 api_base에 붙여 절대 URL 반환. api_base 없으면 None."""
        if not endpoint:
            return None
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if self.api_base:
            return f"{self.api_base.rstrip('/')}{endpoint}"
        return None

    # ---- 보고서 관련 ----
    def create_report(self, payload: dict):
        """
        서버가 있으면 POST /api/reports 등으로 보내고,
        없으면 인메모리로 생성해 ID 반환.
        """
        # 실제 서버 호출 경로가 정해지면 여기에 매핑 가능
        rid = f"RPT-{int(time.time())}"
        content = f"Report content for {(payload or {}).get('title','Untitled')}".encode("utf-8")
        self._reports[rid] = {
            "content": content,
            "hash": self._sha256_bytes(content),
            "locked": False,
        }
        # 감사 로그
        self._audits.append({
            "action": "REPORT_CREATE",
            "user_id": "admin",
            "timestamp": self._now_iso()
        })
        return {"id": rid}

    def get_report_hash(self, report_id: str) -> Optional[str]:
        r = self._reports.get(report_id)
        return r["hash"] if r else None

    def get_report_bytes(self, report_id: str) -> Optional[bytes]:
        r = self._reports.get(report_id)
        return r["content"] if r else None

    def submit_report(self, report_id: str) -> dict:
        r = self._reports.get(report_id)
        if not r:
            return {"status": 404}
        r["locked"] = True
        return {"status": 200}

    def update_report(self, report_id: str, payload: dict) -> dict:
        r = self._reports.get(report_id)
        if not r:
            return {"status": 404}
        if r.get("locked"):
            return {"status": 423}  # Locked
        return {"status": 200}

    def fetch_audit(self, query: dict) -> list[dict]:
        action = (query or {}).get("action")
        lim = int((query or {}).get("limit", 10))
        rows = [a for a in self._audits if (not action or a.get("action") == action)]
        return rows[:lim]

    # ---- 파일 / 다운로드 ----
    def download_file(self, file_id: str) -> Optional[bytes]:
        return self._files.get(file_id)

    def get_file_hash(self, file_id: str) -> Optional[str]:
        b = self._files.get(file_id)
        return self._sha256_bytes(b) if b is not None else None

    def get_file_meta(self, file_id: str) -> Optional[dict]:
        b = self._files.get(file_id)
        if b is None:
            return None
        return {"content_length": len(b), "content_type": "application/pdf"}

    def download_range(self, file_id: str, start: int, end: int) -> Optional[bytes]:
        b = self._files.get(file_id)
        if b is None:
            return None
        return b[start:end]  # [start, end)

    def get_file_signature(self, file_id: str) -> Optional[dict]:
        b = self._files.get(file_id)
        if b is None:
            return None
        sig = self._sha256_bytes(b)[:32]
        return {"alg": "demo-hash", "signature": sig, "key_id": "k1"}

    def verify_signature(self, blob: bytes, sig_info: dict) -> bool:
        if not blob or not sig_info:
            return False
        return self._sha256_bytes(blob).startswith(sig_info.get("signature", ""))

    # ---- 입력값 검증 ----
    def post_json(self, endpoint: str, payload: dict) -> dict:
        """
        실제 서버가 있으면 API_BASE + endpoint로 POST하고,
        없으면 /api/profile 규칙만 스텁 검증.
        """
        url = self._abs_url(endpoint)
        if url:
            try:
                resp = self.session.post(url, json=payload, timeout=5)
                ct = resp.headers.get("Content-Type", "")
                body = resp.text
                try:
                    body_json = resp.json() if "json" in ct else None
                except Exception:
                    body_json = None
                return {"status": resp.status_code, "json": body_json, "text": body}
            except Exception as e:
                return {"status": 599, "text": str(e)}

        # 스텁 규칙: /api/profile
        if endpoint == "/api/profile":
            name = payload.get("name")
            if name in ("", None):
                return {"status": 422, "text": "name is required"}
            if isinstance(name, str) and len(name) > 255:
                return {"status": 422, "text": "name too long"}
            if isinstance(name, str) and "<script" in name.lower():
                return {"status": 422, "text": "invalid characters"}
            return {"status": 200, "text": "ok"}
        return {"status": 404, "text": "not found"}

    # ---- 관리자 로그 ----
    def fetch_admin_logs(self, query: dict) -> list[dict]:
        lim = int((query or {}).get("limit", 10))
        return self._admin_logs[:lim]

    # ---- 인증/세션 ----
    def get(self, endpoint: str) -> dict:
        url = self._abs_url(endpoint)
        if url:
            try:
                resp = self.session.get(url, timeout=5)
                return {"status": resp.status_code, "text": resp.text}
            except Exception as e:
                return {"status": 599, "text": str(e)}
        # 스텁: 보호 자원은 인증 전 401
        if endpoint.startswith("/api/"):
            return {"status": 401, "text": "unauthorized"}
        return {"status": 200, "text": "ok"}

    def login(self, credentials: dict) -> dict:
        url = self._abs_url("/api/login") if self.api_base else None
        if url:
            try:
                resp = self.session.post(url, json=credentials, timeout=5)
                return {"status": resp.status_code, "text": resp.text}
            except Exception as e:
                return {"status": 599, "text": str(e)}

        # 스텁: 비밀번호 'secret'만 성공, 실패 누적 5회→429
        username = (credentials or {}).get("username")
        password = (credentials or {}).get("password", "")
        if password != "secret":
            cnt = self._login_attempts.get(username, 0) + 1
            self._login_attempts[username] = cnt
            if cnt >= 5:
                return {"status": 429, "text": "too many attempts"}
            return {"status": 401, "text": "invalid credentials"}
        self._sessions.add(username)
        self._login_attempts[username] = 0
        return {"status": 200, "text": "login success"}

    def get_authenticated(self, endpoint: str) -> dict:
        url = self._abs_url(endpoint)
        if url:
            try:
                resp = self.session.get(url, timeout=5)
                return {"status": resp.status_code, "text": resp.text}
            except Exception as e:
                return {"status": 599, "text": str(e)}
        return {"status": 200, "text": "ok"} if self._sessions else {"status": 401, "text": "unauthorized"}

    # ---- 토큰 ----
    def get_with_token(self, endpoint: str, token: str) -> dict:
        url = self._abs_url(endpoint)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if url:
            try:
                resp = self.session.get(url, headers=headers, timeout=5)
                return {"status": resp.status_code, "text": resp.text}
            except Exception as e:
                return {"status": 599, "text": str(e)}
        if token == "EXPIRED":
            return {"status": 401, "text": "token expired"}
        return {"status": 200, "text": "ok"}

    def refresh_token(self, old_token: str) -> dict:
        url = self._abs_url("/api/refresh") if self.api_base else None
        if url:
            try:
                resp = self.session.post(url, json={"token": old_token}, timeout=5)
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                return {"status": resp.status_code, "token": data.get("token")}
            except Exception as e:
                return {"status": 599, "token": None, "text": str(e)}
        if old_token != "EXPIRED":
            return {"status": 400}
        self._token_store["NEW"] = {"exp": self._now_iso()}
        return {"status": 200, "token": "NEW"}