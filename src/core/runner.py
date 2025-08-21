# -*- coding: utf-8 -*-

from src.assessments import performance, usability, functional, reliability, security, portability, maintainability, EDU_Interaction, compatibility
from src.assessments import EDU_TestDesign, EDU_LearningData, EDU_AccessTest

assessments_map = {
    "functional": functional,
    "reliability": reliability,
    "performance": performance,
    "security": security,
    "usability": usability,
    "access_control": EDU_AccessTest,
    "portability":     portability,
    "maintainability": maintainability,
    "interaction": EDU_Interaction,
    "test_design": EDU_TestDesign,
    "learning_data": EDU_LearningData,
    "compatibility": compatibility
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
        except Exception as e:

            print(f"[ERROR] step {idx} 처리 중 예외 발생: {e}")
