# run_routine.py
import os
import sys
import time
import subprocess
import requests
import re
import argparse
from typing import List, Dict, Any

# src 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from core.parser import parse_routine
from core.runner import run_routine
from core.driver_backend import BackendDriver

# Playwright 드라이버는 선택적 임포트
try:
    from core.driver_playwright import PlaywrightDriver
    HAS_PLAYWRIGHT = True
except Exception:
    PlaywrightDriver = None  # type: ignore
    HAS_PLAYWRIGHT = False


def list_json_files(base_dir="src/routines"):
    paths = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".json"):
                paths.append(os.path.join(root, f))
    return sorted(paths)

def normalize_routines(obj):
    """
    parse_routine() 결과가 dict 또는 list일 수 있으므로
    항상 [ { name, driver, steps }, ... ] 리스트로 정규화
    """
    if obj is None:
        return []
    if isinstance(obj, dict):
        return [obj] if "steps" in obj else []
    if isinstance(obj, list):
        # 이미 루틴 dict들의 리스트
        if obj and isinstance(obj[0], dict) and "steps" in obj[0]:
            return obj
        # steps 리스트만 온 경우( [{assessment:...}, ...] )
        if obj and all(isinstance(s, dict) and "assessment" in s for s in obj):
            drv = "playwright" if any(s.get("assessment") == "performance" for s in obj) else "backend"
            return [{"name": "ad-hoc routine", "driver": drv, "steps": obj}]
    return []

def load_all_from_dir(dir_path="src/routines"):
    routines = []
    files = list_json_files(dir_path)
    print(f"[INFO] routines 폴더에서 JSON {len(files)}개 발견")  # ★ 이 줄 중요
    for p in files:
        try:
            data = parse_routine(p)
        except Exception as e:
            print(f"[WARN] '{p}' 로드 실패: {e}")
            continue
        rts = normalize_routines(data)
        if not rts:
            print(f"[WARN] '{p}'는 유효한 루틴 형식이 아닙니다(steps 없음)")
        # 파일 경로를 기록(검색용)
        for r in rts:
            r["_source"] = p
        routines.extend(rts)
    return routines

def includes_reliability(routines) -> bool:
    for r in routines:
        for s in r.get("steps", []):
            if s.get("assessment") == "reliability":
                return True
    return False

def wait_health(url="http://127.0.0.1:8000/health", timeout=15) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

# -------------------------------
# 선택/필터 유틸
# -------------------------------
def summarize_routine(idx: int, r: Dict[str, Any]) -> str:
    drv = r.get("driver", "") or "(auto)"
    name = r.get("name", "(noname)")
    # 대표 assessment 3개 미리보기
    kinds = [s.get("assessment") for s in r.get("steps", []) if isinstance(s, dict)][:3]
    kinds_s = ",".join([k for k in kinds if k]) or "-"
    return f"[{idx}] {name} | driver={drv} | assessments={kinds_s} | src={os.path.basename(r.get('_source','-'))}"

def print_routine_table(routines: List[Dict[str, Any]]):
    print("\n=== 실행 가능한 루틴 목록 ===")
    for i, r in enumerate(routines, 1):
        print(summarize_routine(i, r))
    print("============================\n")

def parse_index_ranges(expr: str, n: int) -> List[int]:
    """
    '1,3-5,8' -> [1,3,4,5,8] (1-based 인덱스)
    범위를 벗어나면 무시.
    """
    result = set()
    for token in expr.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if lo <= hi:
                    for k in range(lo, hi + 1):
                        if 1 <= k <= n:
                            result.add(k)
        else:
            if token.isdigit():
                k = int(token)
                if 1 <= k <= n:
                    result.add(k)
    return sorted(result)

def filter_by_keyword(routines: List[Dict[str, Any]], keyword: str) -> List[Dict[str, Any]]:
    kw = keyword.lower()
    out = []
    for r in routines:
        if kw in (r.get("name","") or "").lower():
            out.append(r); continue
        if kw in (r.get("_source","") or "").lower():
            out.append(r); continue
        # steps 내 url/assessment 검색
        for s in r.get("steps", []):
            if isinstance(s, dict):
                if kw in (s.get("url","") or "").lower(): out.append(r); break
                if kw in (s.get("assessment","") or "").lower(): out.append(r); break
    return out

def filter_by_assessment(routines: List[Dict[str, Any]], kinds: List[str]) -> List[Dict[str, Any]]:
    want = set(k.strip().lower() for k in kinds if k.strip())
    out = []
    for r in routines:
        kinds_in = { (s.get("assessment","") or "").lower() for s in r.get("steps", []) if isinstance(s, dict) }
        if kinds_in & want:
            out.append(r)
    return out

def select_routines_interactive(all_target: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    print_routine_table(all_target)
    print("실행할 테스트를 선택하세요:")
    print("  A) 모든 테스트 실행")
    print("  N) 번호로 선택 (예: 1,3-5)")
    print("  K) 키워드로 필터 (이름/URL/assessment/파일명)")
    print("  T) assessment 타입으로 필터 (예: functional,reliability,performance)")
    sel = input("선택 (A/N/K/T): ").strip().lower()

    if sel == "a":
        return all_target

    if sel == "n":
        expr = input("번호(쉼표/범위): ").strip()
        idxs = parse_index_ranges(expr, len(all_target))
        if not idxs:
            print("[INFO] 유효한 번호가 없습니다. 전체 실행으로 대체합니다.")
            return all_target
        return [all_target[i-1] for i in idxs]

    if sel == "k":
        kw = input("키워드: ").strip()
        picked = filter_by_keyword(all_target, kw)
        if not picked:
            print("[INFO] 키워드 매칭 결과가 없습니다. 전체 실행으로 대체합니다.")
            return all_target
        print_routine_table(picked)
        return picked

    if sel == "t":
        kinds = input("assessment 타입들 (예: functional,reliability): ").strip().split(",")
        picked = filter_by_assessment(all_target, kinds)
        if not picked:
            print("[INFO] 타입 매칭 결과가 없습니다. 전체 실행으로 대체합니다.")
            return all_target
        print_routine_table(picked)
        return picked

    print("[INFO] 알 수 없는 입력입니다. 전체 실행으로 진행합니다.")
    return all_target

def select_routines_cli(all_target: List[Dict[str, Any]], args) -> List[Dict[str, Any]]:
    """비대화형 선택: --run/--pick/--filter/--assessment"""
    if args.run == "all":
        return all_target

    picked = all_target

    if args.filter:
        picked = filter_by_keyword(picked, args.filter)

    if args.assessment:
        kinds = [k.strip() for k in args.assessment.split(",") if k.strip()]
        picked = filter_by_assessment(picked, kinds)

    if args.pick:
        idxs = parse_index_ranges(args.pick, len(picked))
        picked = [picked[i-1] for i in idxs] if idxs else []

    if not picked:
        print("[INFO] 선택 결과가 비었습니다. 전체 실행으로 대체합니다.")
        return all_target
    return picked

# -------------------------------
# 메인
# -------------------------------
if __name__ == "__main__":

    # CLI 인자 (비대화형 선택 가능)
    parser = argparse.ArgumentParser(description="Run routines with driver/test selection.")
    parser.add_argument("--run", choices=["all"], help="모든 테스트 실행")
    parser.add_argument("--pick", help="번호로 선택 (예: '1,3-5') — 필터 적용 후의 인덱스 기준")
    parser.add_argument("--filter", help="키워드 필터(이름/URL/assessment/파일명)")
    parser.add_argument("--assessment", help="assessment 타입 필터. 예: 'functional,reliability'")
    args, unknown = parser.parse_known_args()

    # 1) 모든 루틴 로드
    routines = load_all_from_dir("src/routines")
    print(f"[INFO] 로드된 루틴 수: {len(routines)}")


    # 2) 드라이버 선택
    print("사용할 드라이버를 선택하세요:")
    print("1. BackendDriver (가상 드라이버 - 콘솔 출력)")
    if HAS_PLAYWRIGHT:
        print("2. PlaywrightDriver (실제 웹 브라우저 제어)")
    choice = input("선택 (1" + (" 또는 2" if HAS_PLAYWRIGHT else "") + "): ").strip()

    if choice == "2" and HAS_PLAYWRIGHT:
        driver = PlaywrightDriver()
        selected_driver = "playwright"
        print("PlaywrightDriver를 선택했습니다.")
    else:
        driver = BackendDriver()
        selected_driver = "backend"
        print("BackendDriver를 선택했습니다.")

    # 3) 드라이버에 맞는 루틴만 필터( driver 키가 비어있으면 현재 드라이버로 간주 )
    all_target = [r for r in routines if r.get("driver", "").lower() in ("", selected_driver)]
    print(f"[INFO] '{selected_driver}' 대상 루틴: {len(all_target)}개")
    if not all_target:
        print(f"[INFO] '{selected_driver}'용 루틴이 없습니다. 종료합니다.")
        sys.exit(0)

    # 3.5) 어떤 테스트를 실행할지 선택 (CLI 우선, 없으면 인터랙티브)
    if args.run or args.pick or args.filter or args.assessment:
        target = select_routines_cli(all_target, args)
    else:
        target = select_routines_interactive(all_target)

    print(f"[INFO] 실제 실행 루틴 수: {len(target)}개")
    if not target:
        print("[INFO] 실행할 루틴이 없습니다. 종료합니다.")
        sys.exit(0)

    # 4) reliability 포함 시 서버 자동 기동(venv 파이썬 사용), 이미 떠 있으면 생략
    server = None
    try:
        if selected_driver == "backend" and includes_reliability(target):
            if wait_health():
                print("[INFO] 기존 서버 감지. 재기동 생략합니다.")
            else:
                server = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "server:app",
                     "--host", "127.0.0.1", "--port", "8000", "--reload"]
                )
                print("[INFO] 서버 부팅 대기…")
                if not wait_health():
                    print("[WARN] /health 응답 대기 초과. 그래도 진행합니다.")

        # 5) 루틴 순차 실행
        for r in target:
            print(f"\n[RUN] {r.get('name')}")
            run_routine(r, driver)

    finally:
        # 드라이버 종료
        if hasattr(driver, "close") and callable(driver.close):
            try:
                driver.close()
            except Exception:
                pass
        # 서버 종료
        if server is not None:
            print("[INFO] 서버 종료")
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()
