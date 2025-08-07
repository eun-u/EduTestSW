"""
========== 보안성 Security ==========

| 기밀성 | Confidentiality |
- check_https_certificate() : https 통신 적용 확인
- file_encryption() : 파일 암호화 저장 여부 확인

| 무결성 | Integrity |
- hash_integrity :
- input_validation : 

| 부인방지 | Non-Reputation |

| 책임성 | Accountability |

| 인증성 | Authenticity |

====================================
"""
import requests
from . import security_confidentiality


def check(driver, step):
    assessment_type = step["type"]
    
    if assessment_type == "check_https_certificate":
        url = step.get("url")
        if not url:
            raise ValueError("[SECURITY] 'url' 항목이 누락되었습니다.")
        result = security_confidentiality.check_https_certificate(url)
        security_confidentiality.print_https_result(result)
    
        '''elif assessment_type == "file_encryption_check":
        check_file_encryption(step, driver)'''
    else:
        raise ValueError(f"[SECURITY] 알 수 없는 검사 유형: {assessment_type}")
    

"""
def check_file_encryption(step, driver):
    '''
    - 업로드된 파일이 암호화된 상태로 저장되었는지 확인하는 함수
    - 파일의 일부를 읽었을 때 평문 ASCII 비율이 낮았을 때 암호화된 상태로 판단
    - 평문 ASCII 비율이 높으면 암호화 안 된 것으로 판단
    '''
    file_path = step["file_path"]
    if not file_path:
        raise ValueError("file_path 필드가 없습니다.")
    
    # playwright인 경우
    if hasattr(driver, "page"):
        upload_selector = step["upload_selector"]
        if not upload_selector:
            raise ValueError("upload_selector 필드가 없습니다.")
        driver.page.set_input_files(step["upload_selector"], file_path)
        print(f"[SECURITY > CONFIDENTIALITY] 파일 업로드 완료: {file_path}")
    
    
    print(f"[SECURITY > CONFIDENTIALITY] 파일 암호화 확인 대상: {file_path}")
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read(200)
            if not content:
                print("[SECURITY > CONFIDENTIALITY] 파일 내용이 비어 있습니다.")
                return
            
            ascii_cnt = sum(9 == b or 10 == b or 13 == b or 32 <= b <= 126 for b in content)
            ascii_ratio = ascii_cnt / len(content)
            
            print(f"[DEBUG] ASCII 문자 비율: {ascii_ratio:.2f}")
            
            if ascii_ratio >= 0.95:
                print("[SECURITY > CONFIDENTIALITY] 암호화되지 않은 파일입니다.")
            else:
                print("[SECURITY > CONFIDENTIALITY] 암호화된 파일입니다.")
    except FileNotFoundError:
        raise AssertionError(f"[SECURITY > CONFIDENTIALITY] 파일이 존재하지 않습니다: {file_path}")
    except Exception as e:
        raise AssertionError(f"[SECURITY > CONFIDENTIALITY] 파일 검사 중 오류 발생: {e}")"""