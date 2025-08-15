# src/core/runner.py
<<<<<<< HEAD
=======
# -*- coding: utf-8 -*-

>>>>>>> 1de53cc (feat : 서버 과부화 자동화, 모든 테스트 케이스 자동화 기능 추가)
from assessments import performance, usability, functional, reliability, security

assessments_map = {
    "functional": functional,
    "reliability": reliability,
    "performance": performance,
    "security": security,
    "usability": usability,
}

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
<<<<<<< HEAD
=======
        except AssertionError as e:
            print(f"[FAIL] step {idx} 검사 실패: {e}")
>>>>>>> 1de53cc (feat : 서버 과부화 자동화, 모든 테스트 케이스 자동화 기능 추가)
        except Exception as e:
            print(f"[ERROR] step {idx} 처리 중 예외 발생: {e}")
