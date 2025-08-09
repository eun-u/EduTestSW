# run_routine.py
import os
import sys

# 프로젝트 루트 (EduTest)의 'src' 디렉토리를 Python 모듈 검색 경로에 추가합니다.
# 이렇게 하면 'src'를 기준으로 'core'나 'assessments'와 같은 패키지를 찾을 수 있습니다.
# 이 설정은 'from core.parser import ...' 와 같은 임포트 구문과 일치합니다.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


# 필요한 모듈들을 임포트합니다.
from core.parser import parse_routine
from core.runner import run_routine
from core.driver_backend import BackendDriver # 목업 드라이버
from core.driver_playwright import PlaywrightDriver # Playwright 드라이버

if __name__ == "__main__":
    # example_routine.json 파일 파싱
    #routine = parse_routine("example_routine.json")
    
    # yujin 25.08.07 구현 내용 테스트용
    routine = parse_routine("src/routines/performance_compare_processing_time_backend.json")

    # 사용할 드라이버 선택
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

    # 선택된 드라이버로 루틴 실행
    if driver:
        try:
            run_routine(routine, driver)
        finally:
            # 드라이버 사용이 끝난 후 반드시 종료 메서드를 호출합니다.
            # PlaywrightDriver는 브라우저를 닫고 세션을 종료해야 합니다.
            # BackendDriver도 일관성을 위해 run 메서드를 호출합니다.
            if hasattr(driver, 'run') and callable(driver.run):
                driver.run()
            else:
                print("경고: 선택된 드라이버에 'run' 메서드가 없습니다.")
    else:
        print("드라이버 선택에 실패했습니다. 프로그램을 종료합니다.")