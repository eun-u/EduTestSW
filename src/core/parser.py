import json

def parse_routine(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
<<<<<<< HEAD
    return data
=======
        # yujin 디버딩용
        print("✅ routine data type:", type(data))
        print("✅ routine content:", data)
    # yujin 25.08.07 json 읽기 오류로 수정
    return data["steps"]
>>>>>>> 1de53cc (feat : 서버 과부화 자동화, 모든 테스트 케이스 자동화 기능 추가)
