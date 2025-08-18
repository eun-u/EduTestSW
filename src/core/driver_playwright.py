# src/core/driver_playwright.py

from playwright.sync_api import sync_playwright  # 동기식 Playwright API 불러오기
import time

# Playwright 기반 UI 테스트 드라이버 클래스
class PlaywrightDriver:
    def __init__(self):
        # Playwright 실행 시작 (크로미움, 파이어폭스, 웹킷 중 선택 가능)
        self.playwright = sync_playwright().start()
        # 브라우저 인스턴스 시작 (headless=True는 실제 브라우저 창을 띄우지 않음)
        self.browser = self.playwright.chromium.launch(headless=True)
        # 새 브라우저 탭 열기
        self.page = self.browser.new_page()

    def visit(self, url):
        """웹 페이지로 이동"""
        self.page.goto(url)

    def click(self, selector):
        """CSS 선택자로 지정된 요소 클릭"""
        self.page.click(selector)

    def fill(self, selector, value):
        """입력 필드(selector)에 값(value) 입력"""
        self.page.fill(selector, value)

    def get_text(self, selector):
        """요소의 텍스트(innerText)를 반환"""
        return self.page.inner_text(selector)

    def measure_load_time(self, url):
        """페이지 로딩 시간을 ms 단위로 측정"""
        start = time.time()                   # 시작 시간 기록
        self.page.goto(url)                   # 페이지 이동
        return int((time.time() - start) * 1000)  # 걸린 시간(ms) 반환

    def run(self):
        """브라우저 및 Playwright 종료 (사용 후 반드시 호출!)"""
        self.browser.close()          # 브라우저 닫기
        self.playwright.stop()        # Playwright 프로세스 종료

# 사용이 끝난후 반드시 종료
