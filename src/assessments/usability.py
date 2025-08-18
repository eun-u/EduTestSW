# src/assessments/usability.py
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import WebDriverException, NoSuchElementException, ElementClickInterceptedException, NoAlertPresentException

def check_ease_of_use(driver: WebDriver, url: str):
    #이해용이성: UI의 직관성 및 명확성 검증
    results = {"test_name": "이해용이성 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(3)
        login_button = driver.find_element(By.CSS_SELECTOR, "a.login-link, button.login-btn")
        if login_button:
            results["details"].append("로그인 버튼이 명확하게 존재합니다.")
            results["passed"] = True
    except NoSuchElementException:
        results["details"].append("주요 탐색 요소(로그인 버튼)를 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    finally:
        if driver: driver.quit()
    return results

def check_learnability(driver: WebDriver, url: str):
    #새로운 사용자가 기능을 쉽게 배울 수 있는지 검증
    results = {"test_name": "학습성 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(3)
        help_button = driver.find_element(By.CSS_SELECTOR, "a.help-link, button.help-btn")
        if help_button.is_displayed():
            results["details"].append("도움말/튜토리얼 버튼이 존재하여 학습을 돕습니다.")
            results["passed"] = True
        else:
            results["details"].append("도움말/튜토리얼 버튼을 찾을 수 없습니다.")
            results["passed"] = False
    except NoSuchElementException:
        results["details"].append("도움말/튜토리얼 버튼을 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    finally:
        if driver: driver.quit()
    return results

def check_operability(driver: WebDriver, url: str):
    #사용자가 기능을 효과적으로 조작할 수 있는지 검증
    results = {"test_name": "운영성 테스트", "passed": False, "details": []}
    try:
        driver.get(url)
        time.sleep(3)
        course_button = driver.find_element(By.CSS_SELECTOR, "button.register-course-btn")
        if course_button.is_enabled():
            results["details"].append("강의 등록 버튼이 활성화되어 정상적으로 조작 가능합니다.")
            results["passed"] = True
        else:
            results["details"].append("강의 등록 버튼이 비활성화 상태입니다.")
            results["passed"] = False
    except NoSuchElementException:
        results["details"].append("강의 등록 버튼을 찾을 수 없습니다.")
        results["passed"] = False
    except Exception as e:
        results["details"].append(f"예상치 못한 오류 발생: {e}")
        results["passed"] = False
    finally:
        if driver: driver.quit()
    return results

def check_user_error_protection(driver: WebDriver, url: str, protection_type: str):
    #적절한 보호 기능을 검증
    results = {"test_name": f"사용자 오류 보호 테스트 ({protection_type})", "passed": False, "details": ""}
    
    try:
        driver.get(url)
        time.sleep(3)
        
        if protection_type == "password_confirmation":
            # 회원가입 시 비밀번호 확인 필드 존재 여부 확인
            try:
                confirm_password = driver.find_element(By.ID, "confirm_password")
                if confirm_password.is_displayed():
                    results["passed"] = True
                    results["details"] = "비밀번호 확인 필드가 있어 사용자 오류를 줄여줍니다."
                else:
                    results["passed"] = False
                    results["details"] = "비밀번호 확인 필드가 화면에 표시되지 않습니다."
            except NoSuchElementException:
                results["passed"] = False
                results["details"] = "비밀번호 확인 필드를 찾을 수 없어 사용자 오류 보호가 부족합니다."

        elif protection_type == "data_deletion":
            # 데이터 삭제 시 경고 팝업 존재 여부 확인
            try:
                delete_button = driver.find_element(By.CSS_SELECTOR, "button.delete-data-btn")
                delete_button.click()
                time.sleep(1)
                
                alert = driver.switch_to.alert
                if "정말로 삭제하시겠습니까?" in alert.text or "삭제하면 복구할 수 없습니다" in alert.text:
                    results["passed"] = True
                    results["details"] = "데이터 삭제 시 경고 팝업이 표시되어 사용자 실수를 방지합니다."
                else:
                    results["passed"] = False
                    results["details"] = "데이터 삭제 시 예상치 못한 팝업이 표시되거나, 경고 메시지가 명확하지 않습니다."
                alert.dismiss()
            except NoSuchElementException:
                results["passed"] = False
                results["details"] = "데이터 삭제 버튼을 찾을 수 없어 테스트를 진행할 수 없습니다."
            except NoAlertPresentException:
                results["passed"] = False
                results["details"] = "데이터 삭제 버튼 클릭 후 경고 팝업이 표시되지 않습니다."
        
        else:
            results["passed"] = False
            results["details"] = f"알 수 없는 보호 유형: {protection_type}"
            
    except Exception as e:
        results["passed"] = False
        results["details"] = f"예상치 못한 오류 발생: {e}"
    finally:
        if driver: driver.quit()
    return results

def check(driver: WebDriver, step: dict):
    #메인 함수
    test_type = step.get("test_type")

    if test_type == "ease_of_use":
        return check_ease_of_use(driver, step.get("url"))
    elif test_type == "learnability":
        return check_learnability(driver, step.get("url"))
    elif test_type == "operability":
        return check_operability(driver, step.get("url"))
    elif test_type == "error_protection":
        protection_type = step.get("protection_type")
        return check_user_error_protection(driver, step.get("url"), protection_type)
    else:
        return {"test_name": "사용성 테스트", "passed": False, "details": f"알 수 없는 테스트 유형: {test_type}"}