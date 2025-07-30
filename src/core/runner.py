# src/core/runner.py
# 1 from assessments import performance # 이 줄을 아래와 같이 수정!
from assessments import performance
from assessments import usability # usability.py가 있다면 함께 임포트


def run_routine(routine, driver):
    for step in routine:
        assessment = step["assessment"]
        if assessment == "performance":
            performance.check(driver, step)
        elif assessment == "usability": # usability 추가
            usability.check(driver, step)
        else:
            print(f"[SKIP] 지원하지 않는 assessment: {assessment}")
