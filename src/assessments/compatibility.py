# src/assessments/compatibility.py
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException, NoSuchElementException

def check_browser_compatibility(driver: WebDriver, url: str, browser_name: str, test_feature: str):
    #브라우저별 호환성을 검증하는 함수
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
    #os 호환성을 검증하는 함수 (기능/디자인 동일성)
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

def check(driver: WebDriver, step: dict):
    #메인 함수
    test_type = step.get("test_type")
    
    if test_type == "browser_compatibility":
        return check_browser_compatibility(
            driver, 
            step.get("url"), 
            step.get("browser_name"), 
            step.get("test_feature")
        )
    elif test_type == "os_compatibility":
        return check_os_compatibility(
            driver, 
            step.get("url"), 
            step.get("os_name"), 
            step.get("test_feature")
        )
    else:
        return {"test_name": "Compatibility Test", "passed": False, "details": f"Unknown test type: {test_type}"}