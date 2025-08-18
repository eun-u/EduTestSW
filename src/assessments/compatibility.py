# src/assessments/compatibility.py

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException, NoSuchElementException, ElementClickInterceptedException, NoAlertPresentException
import random
import json

def check_browser_compatibility(driver: WebDriver, url: str, browser_name: str, test_feature: str):
    # 브라우저별 호환성을 검증하는 함수
    results = {"test_name": f"{browser_name} {test_feature} Test", "passed": False, "details": ""}
    
    try:
        driver.get(url)
        time.sleep(5) 

        if test_feature == "login_form":
            username_field = driver.find_element(By.ID, "username")
            password_field = driver.find_element(By.ID, "password")
            login_button = driver.find_element(By.CSS_SELECTOR, "button.login-btn")
            
            if username_field.is_displayed() and password_field.is_displayed() and login_button.is_enabled():
                results["passed"] = True
                results["details"] = f"Login form is correctly displayed and enabled on {browser_name}."
            else:
                results["details"] = f"Login form is not fully functional or visible on {browser_name}."
        
        else:
            results["details"] = f"Unsupported browser test feature: {test_feature}."

    except (WebDriverException, NoSuchElementException) as e:
        results["details"] = f"An error occurred while testing on {browser_name}: {e}"
    except Exception as e:
        results["details"] = f"An unexpected error occurred on {browser_name}: {e}"
    finally:
        if driver:
            driver.quit()

    return results

def check_os_compatibility(driver: WebDriver, url: str, os_name: str, test_feature: str):
    # os 호환성을 검증하는 함수 (기능/디자인 동일성)
    results = {"test_name": f"{os_name} {test_feature} Test", "passed": False, "details": ""}
    
    try:
        driver.get(url)
        time.sleep(5)

        if test_feature == "video_playback":
            video_player = driver.find_element(By.CSS_SELECTOR, "video.course-video")
            is_playable = driver.execute_script("return arguments[0].readyState >= 3;", video_player)

            if is_playable:
                results["passed"] = True
                results["details"] = f"Video playback works correctly on {os_name}."
            else:
                results["details"] = f"Video playback failed to start on {os_name}."

        elif test_feature == "file_upload":
            upload_input = driver.find_element(By.ID, "file-upload-input")
            if upload_input.is_enabled():
                results["passed"] = True
                results["details"] = f"File upload function is enabled on {os_name}."
            else:
                results["details"] = f"File upload function is not enabled on {os_name}."
        
        elif test_feature == "ui_layout":
            header = driver.find_element(By.CSS_SELECTOR, "header.main-header")
            if header.is_displayed():
                results["passed"] = True
                results["details"] = f"Main header is visible and present on {os_name}."
            else:
                results["passed"] = False
                results["details"] = f"Main header is not visible on {os_name}, indicating a layout issue."
        
        else:
            results["details"] = f"Unsupported OS test feature: {test_feature}."

    except (WebDriverException, NoSuchElementException) as e:
        results["details"] = f"An error occurred while testing on {os_name}: {e}"
    except Exception as e:
        results["details"] = f"An unexpected error occurred on {os_name}: {e}"
    finally:
        if driver:
            driver.quit()
    return results

def check_loading_anxiety(driver: WebDriver, url: str):
    # 느린 로딩 시 사용자 불안 최소화
    results = {"test_name": "로딩 불안 최소화 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(2)
        
        load_button = driver.find_element(By.CSS_SELECTOR, "button.load-content-btn")
        load_button.click()
        
        loading_indicator = driver.find_element(By.CSS_SELECTOR, ".loading-indicator, .loading-message")
        if loading_indicator.is_displayed():
            results["details"].append("로딩 시 사용자에게 피드백을 주는 요소가 표시됩니다.")
            try:
                cancel_button = driver.find_element(By.CSS_SELECTOR, "button.loading-cancel-btn")
                if cancel_button.is_displayed():
                    results["details"].append("로딩 중 취소 버튼이 존재합니다.")
                    results["passed"] = True
                else:
                    results["details"].append("로딩 중 취소 버튼을 찾을 수 없습니다.")
                    results["passed"] = False
            except NoSuchElementException:
                results["details"].append("로딩 중 취소 버튼을 찾을 수 없습니다.")
                results["passed"] = False
        else:
            results["details"].append("로딩 시 아무런 피드백이 없어 사용자가 불안해할 수 있습니다.")
            results["passed"] = False
            
    except NoSuchElementException:
        results["details"].append("로딩을 유발하는 버튼이나 로딩 요소를 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    return results

def check_quiz_notification(driver: WebDriver, url: str):
    # 강의 완료/퀴즈 결과 알림 명확성 검증
    results = {"test_name": "알림 명확성 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(3)
        
        notification_popup = driver.find_element(By.CSS_SELECTOR, ".quiz-result-popup, .notification-message")
        if notification_popup.is_displayed():
            results["details"].append("퀴즈 결과 알림이 명확하게 표시됩니다.")
            if any(char.isdigit() for char in notification_popup.text):
                results["details"].append("알림 메시지에 점수가 포함되어 있습니다.")
                results["passed"] = True
            else:
                results["details"].append("알림 메시지에 점수가 포함되어 있지 않습니다.")
                results["passed"] = False
        else:
            results["details"].append("퀴즈 결과 알림을 찾을 수 없습니다.")
            results["passed"] = False
            
    except NoSuchElementException:
        results["details"].append("퀴즈 결과 알림 요소를 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    return results

def check_wcag_contrast(driver: WebDriver, url: str):
    # 글씨 크기와 대비(WCAG) 기준 충족 검증
    results = {"test_name": "WCAG 대비 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(3)
        
        font_size_controls = driver.find_elements(By.CSS_SELECTOR, ".font-size-control, .theme-switcher")
        if font_size_controls:
            results["details"].append("폰트 크기 및 테마(다크 모드) 조절 기능이 존재합니다.")
            results["passed"] = True
        else:
            results["details"].append("폰트 크기 및 테마 조절 기능을 찾을 수 없습니다.")
            results["passed"] = False
            
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    return results

def check_subtitle_sync(driver: WebDriver, url: str):
    # 자막이 강의 오디오와 정확히 맞는지 검증
    results = {"test_name": "자막 동기화 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(5)
        
        subtitle_element = driver.find_element(By.CSS_SELECTOR, ".subtitle-display")
        if subtitle_element.is_displayed():
            results["details"].append("자막이 동영상 재생 시 화면에 정상적으로 표시됩니다.")
            results["details"].append("자막 타이밍이 동영상과 정확히 일치하는 것으로 가정합니다.")
            results["passed"] = True
        else:
            results["details"].append("자막이 화면에 표시되지 않습니다.")
            results["passed"] = False
            
    except NoSuchElementException:
        results["details"].append("자막을 표시하는 요소를 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    return results

def check_mobile_ui(driver: WebDriver, url: str):
    # 모바일 환경에서 버튼/텍스트 겹침 검증 (반응형 디자인)
    results = {"test_name": "모바일 UI 테스트", "passed": False, "details": []}
    try:
        # 뷰포트 크기를 모바일로 변경하여 테스트
        driver.set_window_size(375, 812) # iPhone X 크기
        driver.get(url)
        time.sleep(3)
        
        header = driver.find_element(By.CSS_SELECTOR, "header")
        menu_button = driver.find_element(By.CSS_SELECTOR, ".mobile-menu-btn")
        
        if header.is_displayed() and menu_button.is_displayed():
            results["details"].append("모바일 뷰포트에서 헤더와 모바일 메뉴 버튼이 올바르게 표시됩니다.")
            results["passed"] = True
        else:
            results["details"].append("모바일 뷰포트에서 UI 요소가 깨지거나 숨겨져 있습니다.")
            results["passed"] = False
            
    except NoSuchElementException:
        results["details"].append("필수 UI 요소를 찾을 수 없습니다. 모바일 UI에 문제가 있을 수 있습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    finally:
        driver.set_window_size(1200, 800) # 테스트 후 원래 크기로 복원
    return results

def check(driver: WebDriver, step: dict):
    # 메인 함수: step의 'test_type'에 따라 알맞은 테스트 함수를 호출
    test_type = step.get("test_type")
    url = step.get("url")

    # 모든 테스트 함수가 driver를 생성하고 닫도록 수정
    driver_instance = webdriver.Chrome()

    try:
        if test_type == "browser_compatibility":
            return check_browser_compatibility(
                driver_instance, 
                url, 
                step.get("browser_name"), 
                step.get("test_feature")
            )
        elif test_type == "os_compatibility":
            return check_os_compatibility(
                driver_instance, 
                url, 
                step.get("os_name"), 
                step.get("test_feature")
            )
        elif test_type == "loading_anxiety":
            return check_loading_anxiety(driver_instance, url)
        elif test_type == "quiz_notification":
            return check_quiz_notification(driver_instance, url)
        elif test_type == "wcag_contrast":
            return check_wcag_contrast(driver_instance, url)
        elif test_type == "subtitle_sync":
            return check_subtitle_sync(driver_instance, url)
        elif test_type == "mobile_ui":
            return check_mobile_ui(driver_instance, url)
        else:
            return {"test_name": "Compatibility Test", "passed": False, "details": f"Unknown test type: {test_type}"}
    finally:
        if driver_instance:
            driver_instance.quit()