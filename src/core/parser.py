# src/core/parser.py
import json
import os

def parse_routine(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        # yujin 디버딩용
        #print("✅ routine data type:", type(data))
        #print("✅ routine content:", data)
    # yujin 25.08.07 json 읽기 오류로 수정
    return data["steps"]
