# src/core/runner.py
# 1 from assessments import performance # 이 줄을 아래와 같이 수정!
from assessments import performance
from assessments import usability # usability.py가 있다면 함께 임포트
from assessments import security


def run_routine(routine, driver):
    for step in routine:
        assessment = step["assessment"]
        # yujin 25.08.07 Traceback 문구 출력 피하기 위해 try~except 블록으로 감쌈
        try:
            if assessment == "performance":
                performance.check(driver, step)
            elif assessment == "usability": # usability 추가
                usability.check(driver, step)
            # 25.08.07 Security 추가
            elif assessment == "security":
                security.check(driver, step)
            else:
                print(f"[SKIP] 지원하지 않는 assessment: {assessment}")
        except AssertionError as e:
            print(f"[FAIL] 검사 실패: {e}")
        except Exception as e:
            print(f"[ERROR] 예기치 않은 오류 발생: {e}")
