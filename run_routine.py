# run_routine.py
import os
import sys

# ✅ 먼저 src를 모듈 경로에 넣고
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# ✅ 그 다음에 core/assessments 임포트
from core.parser import parse_routine
from core.runner import run_routine
from core.driver_backend import BackendDriver
from core.driver_playwright import PlaywrightDriver


if __name__ == "__main__":
    # 1) JSON 로드
    try:
        routine = parse_routine("src/routines/performance_backend.json")
    except Exception as e:
        print(f"[ERROR] 루틴 로딩 실패: {e}")
        sys.exit(1)
    # example_routine.json 파일 파싱
    #routine = parse_routine("example_routine.json")
    
    # yujin 25.08.07 구현 내용 테스트용
    #routine = parse_routine("src/routines/EDU_test_design_backend.json")

    # 2) 드라이버 선택
    print("사용할 드라이버를 선택하세요:")
    print("1. BackendDriver (가상 드라이버 - 콘솔 출력)")
    print("2. PlaywrightDriver (실제 웹 브라우저 제어)")

    driver = None
    while True:
        choice = input("선택 (1 또는 2): ")
        if choice == '1':
            driver = BackendDriver()
            print("BackendDriver를 선택했습니다.")
            break
        elif choice == '2':
            driver = PlaywrightDriver()
            print("PlaywrightDriver를 선택했습니다.")
            break
        else:
            print("잘못된 입력입니다. 1 또는 2를 입력해주세요.")

    # 3) 실행
    if driver:
        try:
            run_routine(routine, driver)
        finally:
            # 드라이버 종료 (있으면)
            if hasattr(driver, "run") and callable(driver.run):
                driver.run()
            elif hasattr(driver, "close") and callable(driver.close):
                driver.close()
            else:
                print("경고: 선택된 드라이버에 종료 메서드가 없습니다.")
