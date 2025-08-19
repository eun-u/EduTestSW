"""
========== 이식성 Portability ==========

- check_env_variable     : 환경변수 적용 가능 여부
- check_multi_env        : 다중 환경 호환성 검증
- check_platform_matrix  : 플랫폼(OS/Python) 지원 매트릭스 검증
- check_install_script   : 원클릭 설치 확인
- check_rollback         : 설치 롤백 절차 검증
- check_upgrade          : 업그레이드/다운그레이드 지원 여부(간이)
- check_service_replace  : 서비스 대체 가능성(간이)
- check_data_format      : 데이터 포맷 호환성(json/xml/csv 간이)
- check_functional_equal : 치환 후 결과 동일성 비교
=======================================
"""
from typing import Dict, Any, List
import os, subprocess, platform, json, requests
from io import StringIO
import csv
import xml.etree.ElementTree as ET

def print_result(name: str, ok: bool, reason: str):
    status = "PASS" if ok else "FAIL"
    print(f"[PORTABILITY] {name:25s} [{status}] {reason}")

def check(_driver, step: Dict[str, Any]):
    t = step["type"]
    mapping = {
        "check_env_variable":     check_env_variable,
        "check_multi_env":        check_multi_env,
        "check_platform_matrix":  check_platform_matrix,
        "check_install_script":   check_install_script,
        "check_rollback":         check_rollback,
        "check_upgrade":          check_upgrade,
        "check_service_replace":  check_service_replace,
        "check_data_format":      check_data_format,
        "check_functional_equal": check_functional_equal,
    }
    func = mapping.get(t)
    if not func:
        raise ValueError(f"[PORTABILITY] 알 수 없는 검사 유형: {t}")
    return func(step)

# ---------------------------
# Helpers
# ---------------------------
def _run_script(script_path: str):
    if not os.path.exists(script_path):
        return False, "script not found", "", ""

    try:
        if os.name == "nt":
            # Windows: .bat/.cmd는 shell=True, 그 외는 그대로 시도
            if script_path.lower().endswith((".bat", ".cmd")):
                result = subprocess.run(script_path, capture_output=True, text=True, shell=True)
            else:
                result = subprocess.run([script_path], capture_output=True, text=True, shell=False)
        else:
            # Unix: 실행권한 없으면 bash로 시도
            if os.access(script_path, os.X_OK):
                result = subprocess.run([script_path], capture_output=True, text=True, shell=False)
            else:
                result = subprocess.run(["bash", script_path], capture_output=True, text=True, shell=False)

        ok = (result.returncode == 0)
        return ok, f"return={result.returncode}", result.stdout, result.stderr
    except Exception as e:
        return False, str(e), "", ""

# ---------------------------
# 환경적용성
# ---------------------------
def check_env_variable(step: Dict[str, Any]):
    key = step.get("env_key")
    set_value = step.get("set_value")
    if not key:
        print_result("check_env_variable", False, "env_key 누락")
        return {"pass": False, "reason": "missing env_key"}
    os.environ[key] = str(set_value)
    val = os.environ.get(key)
    ok = (val == str(set_value))
    print_result("check_env_variable", ok, f"{key}={val}")
    return {"pass": ok, "key": key, "value": val}

def check_multi_env(step: Dict[str, Any]):
    urls: List[str] = step.get("urls", [])
    if not urls:
        print_result("check_multi_env", False, "urls 비어있음")
        return {"pass": False, "codes": []}
    codes = []
    for u in urls:
        try:
            r = requests.get(u, timeout=5)
            codes.append(r.status_code)
        except Exception:
            codes.append(None)
    finite = [c for c in codes if c is not None]
    ok = (len(finite) > 0) and all(c == finite[0] for c in finite)
    print_result("check_multi_env", ok, f"codes={codes}")
    return {"pass": ok, "codes": codes}

def check_platform_matrix(step: Dict[str, Any]):
    os_name = platform.system()               # e.g., 'Windows', 'Linux', 'Darwin'
    py_ver  = platform.python_version()       # e.g., '3.11.6'
    expected = step.get("expected", [])
    def match(item):
        os_expect = item.get("os")
        py_expect = item.get("python")  # '3.11'처럼 prefix 매칭
        os_ok = (os_name == os_expect) if isinstance(os_expect, str) else (os_name in (os_expect or []))
        py_ok = str(py_ver).startswith(str(py_expect)) if py_expect else True
        return os_ok and py_ok
    ok = any(match(e) for e in expected) if expected else True
    print_result("check_platform_matrix", ok, f"OS={os_name}, Python={py_ver}")
    return {"pass": ok, "os": os_name, "python": py_ver}

# ---------------------------
# 설치용이성
# ---------------------------
def check_install_script(step: Dict[str, Any]):
    script = step.get("script")
    if not script:
        print_result("check_install_script", False, "script 경로 누락")
        return {"pass": False, "reason": "missing script"}
    ok, info, stdout, stderr = _run_script(script)
    print_result("check_install_script", ok, info)
    return {"pass": ok, "stdout": stdout, "stderr": stderr, "info": info}

def check_rollback(step: Dict[str, Any]):
    script = step.get("rollback_script")
    if not script:
        print_result("check_rollback", False, "rollback_script 누락")
        return {"pass": False, "reason": "missing rollback_script"}
    ok, info, stdout, stderr = _run_script(script)
    print_result("check_rollback", ok, info)
    return {"pass": ok, "stdout": stdout, "stderr": stderr, "info": info}

def check_upgrade(step: Dict[str, Any]):
    old_ver = str(step.get("old_version", "")).strip()
    new_ver = str(step.get("new_version", "")).strip()
    if not old_ver or not new_ver:
        print_result("check_upgrade", False, "old/new_version 누락")
        return {"pass": False, "reason": "missing version"}
    ok = (old_ver != new_ver)  # 실제 업그레이드 수행 대신 버전 변경 가능성 간이 확인
    print_result("check_upgrade", ok, f"{old_ver} -> {new_ver}")
    return {"pass": ok, "old": old_ver, "new": new_ver}

# ---------------------------
# 치환성
# ---------------------------
def check_service_replace(step: Dict[str, Any]):
    envs = step.get("environments", [])
    # 간이 규칙: 대체 후보가 2개 이상이면 일단 치환 가능성 OK
    ok = isinstance(envs, list) and len(envs) >= 2
    print_result("check_service_replace", ok, f"envs={envs}")
    return {"pass": ok, "envs": envs}

def check_data_format(step: Dict[str, Any]):
    fmt = (step.get("format") or "json").lower()
    sample = step.get("sample")
    ok = True
    reason = "ok"
    try:
        if fmt == "json":
            json.dumps(sample)
        elif fmt == "xml":
            # 아주 간단한 dict -> XML 변환(1-depth)
            root = ET.Element("root")
            if isinstance(sample, dict):
                for k, v in sample.items():
                    child = ET.SubElement(root, str(k))
                    child.text = "" if v is None else str(v)
            else:
                # 리스트/스칼라도 허용
                child = ET.SubElement(root, "value")
                child.text = "" if sample is None else str(sample)
            ET.tostring(root, encoding="utf-8")
        elif fmt == "csv":
            # dict 리스트 또는 dict 1개를 csv로 직렬화 테스트
            buf = StringIO()
            if isinstance(sample, list) and sample and isinstance(sample[0], dict):
                w = csv.DictWriter(buf, fieldnames=list(sample[0].keys()))
                w.writeheader()
                for row in sample:
                    w.writerow(row)
            elif isinstance(sample, dict):
                w = csv.DictWriter(buf, fieldnames=list(sample.keys()))
                w.writeheader()
                w.writerow(sample)
            else:
                # 스칼라/리스트 스칼라 → 1컬럼로 직렬
                w = csv.writer(buf)
                if isinstance(sample, list):
                    for item in sample:
                        w.writerow([item])
                else:
                    w.writerow([sample])
            _ = buf.getvalue()
        else:
            ok, reason = False, f"unsupported format: {fmt}"
    except Exception as e:
        ok, reason = False, str(e)

    print_result("check_data_format", ok, f"format={fmt} ({reason})")
    return {"pass": ok, "format": fmt, "reason": reason}

def check_functional_equal(step: Dict[str, Any]):
    base = step.get("base_result")
    alt  = step.get("alt_result")
    ok = (base == alt)
    print_result("check_functional_equal", ok, f"equal={ok}")
    return {"pass": ok, "equal": ok, "base": base, "alt": alt}
