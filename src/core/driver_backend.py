import requests           # HTTP 요청을 보내기 위한 라이브러리
import time               # 시간 측정용 (로딩 시간 등)
from bs4 import BeautifulSoup  # HTML 파싱용
import json
import os
import subprocess         # 외부 명령어 실행용 (정적 분석 등)

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

