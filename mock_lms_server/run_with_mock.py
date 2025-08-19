# run_with_mock.py
import argparse, subprocess, sys, time, socket, requests, os

def tcp_ping(host: str, port: int, timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        try: s.close()
        except: pass

def wait_health(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=0.5)
            if r.ok:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="mock_lms_server/mock_lms_server.py",
                    help="모의 서버 스크립트 경로")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--routine", default="src/routines/EDU_Interaction_backend_local.json",
                    help="실행할 루틴 JSON 경로")
    args = ap.parse_args()

    server_up = tcp_ping(args.host, args.port)
    proc = None
    try:
        if not server_up:
            print(f"[INFO] 서버가 안 떠있음 → 모의 서버 실행: {args.server}")
            # mock_lms_server.py가 기본 8000으로 뜨도록 작성됨
            proc = subprocess.Popen([sys.executable, args.server])
            ok = wait_health(f"http://{args.host}:{args.port}/health", timeout=12)
            if not ok:
                raise RuntimeError("모의 서버 /health 응답 대기 타임아웃")

        # 루틴 실행 (run_routine.py가 인자로 받은 JSON을 후보에 포함)
        cmd = [sys.executable, "run_routine.py", args.routine]
        print(f"[INFO] 실행: {' '.join(cmd)}")
        subprocess.run(cmd, check=False)
    finally:
        if proc:
            print("[INFO] 모의 서버 종료")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

if __name__ == "__main__":
    main()
