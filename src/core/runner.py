# src/core/runner.py
# -*- coding: utf-8 -*-

from assessments import performance, usability, functional, reliability, security
# 1 from assessments import performance # 이 줄을 아래와 같이 수정!
from assessments import performance
from assessments import usability # usability.py가 있다면 함께 임포트
from assessments import security
from src.assessments import EDU_TestDesign, EDU_LearningData

assessments_map = {
    "functional": functional,
    "reliability": reliability,
    "performance": performance,
    "security": security,
    "usability": usability,
    "test_design" : EDU_TestDesign,
    "learning_data" : EDU_LearningData
}
'''
def run_routine(routine: dict, driver):
    steps = routine.get("steps", [])
    if not isinstance(steps, list):
        print("[ERROR] routine['steps']가 리스트가 아닙니다. JSON 구조를 확인하세요.")
        return

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            print(f"[SKIP] 잘못된 step 형식 (index {idx}): {step!r}")
            continue

        assessment = step.get("assessment")
        handler = assessments_map.get(assessment)
        if not handler:
            print(f"[SKIP] 지원하지 않는 assessment: {assessment}")
            continue

        try:
            handler.check(driver, step)
        except AssertionError as e:
            print(f"[FAIL] step {idx} 검사 실패: {e}")
        except Exception as e:
            print(f"[ERROR] step {idx} 처리 중 예외 발생: {e}")
'''

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
                
            elif assessment == "test_design":
                EDU_TestDesign.check(driver, step)
                
            elif assessment == "learning_data":
                EDU_LearningData.check(driver, step)
                
            else:
                print(f"[SKIP] 지원하지 않는 assessment: {assessment}")
        except AssertionError as e:
            print(f"[FAIL] 검사 실패: {e}")
        except Exception as e:
            print(f"[ERROR] 예기치 않은 오류 발생: {e}")
