# src/core/driver_backend.py

# class BackendDriver:
#    def visit(self, url):
#        print(f"[DRIVER] (가상) 방문: {url}")
#    # 다른 메서드들도 여기에 추가하여 BackendDriver가 PlaywrightDriver와 동일한 인터페이스를 가지도록 합니다.
#    # 예를 들어, click, fill, get_text, measure_load_time, close 등

# BackendDriver를 PlaywrightDriver와 동일한 인터페이스를 가지도록 수정
class BackendDriver:
    def __init__(self):
        print("[DRIVER] (가상) 백엔드 드라이버 초기화")

    def visit(self, url):
        print(f"[DRIVER] (가상) 방문: {url}")

    def click(self, selector):
        print(f"[DRIVER] (가상) 클릭: {selector}")

    def fill(self, selector, value):
        print(f"[DRIVER] (가상) 채우기: {selector}, 값: {value}")

    def get_text(self, selector):
        print(f"[DRIVER] (가상) 텍스트 가져오기: {selector}")
        return f"가상 텍스트: {selector}" # 가상 텍스트 반환

    def measure_load_time(self, url):
        print(f"[DRIVER] (가상) 로드 시간 측정: {url}")
        return 1000 # 가상 로드 시간 (1초)

    def run(self): # PlaywrightDriver의 run과 동일한 인터페이스 유지
        print("[DRIVER] (가상) 백엔드 드라이버 종료")
