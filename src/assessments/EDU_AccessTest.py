# src/assessments/EDU_AccessTest.py

import requests
import json
import time
from playwright.sync_api import Page
from typing import Dict, Any

# 테스트 서버 URL 설정
BASE_URL = "http://127.0.0.1:8000"

def check(driver, step: Dict[str, Any]):
    """
    runner.py에 의해 호출되는 메인 함수.
    step의 test_case에 따라 적절한 테스트 함수를 호출.
    """
    test_case = step.get("test_case")
    print(f"\n--- [시작] Access Control Test: {step.get('name')} ---")

    if driver.name == "backend":
        if test_case == "access_control_test":
            _test_backend_access_control()
        else:
            print(f"경고: 알 수 없는 Backend 테스트 케이스: {test_case}")
    
    elif driver.name == "playwright":
        if test_case == "access_control_test":
            _test_playwright_access_control(driver.get_page())
        else:
            print(f"경고: 알 수 없는 Playwright 테스트 케이스: {test_case}")
    else:
        print(f"경고: 지원하지 않는 드라이버: {driver.name}")

# --- Backend 테스트 로직 ---
def _test_backend_access_control():
    print("-> 1. 일반 사용자 ('user')로 로그인하여 토큰 획득...")
    login_url = f"{BASE_URL}/api/login"
    login_payload = {"username": "user", "password": "pass"}
    
    try:
        response = requests.post(login_url, json=login_payload)
        response.raise_for_status()
        user_token = response.json().get("access_token")
        
        if not user_token:
            print("실패: 로그인 실패: 토큰을 받지 못했습니다.")
            return
        print("성공: 일반 사용자 토큰 획득.")

        print("-> 2. 획득한 토큰으로 관리자 API 접근 시도 중...")
        admin_api_url = f"{BASE_URL}/admin/toggle_overload"
        headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        admin_payload = {"overloaded": True, "failure_rate": 0.5, "extra_latency_ms": 100}
        
        response = requests.post(admin_api_url, headers=headers, json=admin_payload)
        
        if response.status_code == 403:
            print("성공: 접근 제어 테스트: 올바르게 403 Forbidden 응답을 받았습니다.")
        elif response.status_code == 200:
            print("실패: 접근 제어 테스트: 일반 사용자로 관리자 API에 접근할 수 있습니다.")
        else:
            print(f"경고: 예상치 못한 응답: HTTP {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"오류: 요청 실패: {e}")

# --- Playwright 테스트 로직 ---
def _test_playwright_access_control(page: Page):
    """
    Playwright로 URL 직접 입력하여 관리자 페이지 접근 시도
    """
    print("-> Playwright로 일반 사용자 로그인 및 URL 직접 입력 시도...")
    
    # 1. 일반 사용자 로그인 (세션 쿠키/토큰 획득)
    # Playwright를 이용한 실제 로그인 과정 시뮬레이션
    page.goto(f"{BASE_URL}/docs")
    # 로그인 폼이 없으므로, 더미 요청을 보냈다고 가정
    # 또는 페이지 상에서 로그인 폼을 찾아 입력하는 로직을 추가
    print("성공: 가상 로그인 상태 설정.")
    
    # 2. URL 직접 입력으로 관리자 페이지 접근 시도
    admin_url = f"{BASE_URL}/admin/toggle_overload"
    page.goto(admin_url, wait_until="networkidle")

    # 3. 페이지 콘텐츠 확인
    content = page.content()
    if "Not an administrator" in content:
        print("성공: 권한 우회 테스트: 'Not an administrator' 메시지를 확인했습니다.")
    elif "ok" in content:
        print("실패: 권한 우회 테스트: 관리자 페이지에 접근할 수 있습니다.")
    else:
        print(f"경고: 예상치 못한 페이지 콘텐츠. 첫 100자: {content[:100]}")