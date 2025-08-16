# run_routine.py
import os
import sys
import time
import subprocess
import requests

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


if __name__ == "__main__":
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
    target = [r for r in routines if r.get("driver", "").lower() in ("", selected_driver)]
    print(f"[INFO] '{selected_driver}' 대상 루틴: {len(target)}개")
    if not target:
        print(f"[INFO] '{selected_driver}'용 루틴이 없습니다. 종료합니다.")
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
