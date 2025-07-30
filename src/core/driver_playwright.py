# src/core/driver_playwright.py

from playwright.sync_api import sync_playwright
import time
#import mock # PlaywrightDriver에서는 mock이 필요 없을 수 있으니 주석 처리

class PlaywrightDriver:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True) # headless=True로 변경
        self.page = self.browser.new_page()

    def visit(self, url):
        self.page.goto(url)

    def click(self, selector):
        self.page.click(selector)

    def fill(self, selector, value):
        self.page.fill(selector, value)

    def get_text(self, selector):
        return self.page.inner_text(selector)

    def measure_load_time(self, url):
        start = time.time()
        self.page.goto(url)
        return int((time.time() - start) * 1000)

    def run(self): # run이라는 이름은 좀 모호하니 close_driver 등으로 바꾸는게 좋습니다.
        self.browser.close()
        self.playwright.stop()

#드라이버 사용후 반드시 종료