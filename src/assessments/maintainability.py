"""
========== 유지보수성 Maintainability ==========

- 분석성(Analyzability)
  - check_log_level           : 로그 레벨 정책 검증
  - check_log_trace_fields    : 로그에 trace_id/request_id 등 필수 필드 포함 여부

- 수정가능성(Modifiability)
  - check_feature_flag        : 피처 플래그 토글 검증(ENV)
  - check_config_separation   : 설정/코드 분리 검증(ENV 값 기대치 확인)

- 시험가능성(Testability)
  - check_test_coverage       : 테스트/커버리지 실행(간이)
  - check_smoke_script        : 스모크 스크립트 실행(반환코드)

- 모듈성(Modularity)
  - check_circular_imports    : 순환 의존성 탐지(AST 기반)

- 재사용성(Reusability)
  - check_duplicate_functions : 중복 함수 본문 탐지(AST 기반, end_lineno 이용)

(선택) 정적복잡도:
  - check_cyclomatic_complexity : radon cc JSON 출력 파싱(설치된 경우)
================================================
"""
from typing import Dict, Any, List, Tuple
import os, re, json, subprocess, sys, ast, hashlib
from pathlib import Path

def print_result(name: str, ok: bool, reason: str):
    status = "PASS" if ok else "FAIL"
    print(f"[MAINTAINABILITY] {name:25s} [{status}] {reason}")

def check(_driver, step: Dict[str, Any]):
    t = step["type"]
    mapping = {
        # 분석성
        "check_log_level":           check_log_level,
        "check_log_trace_fields":    check_log_trace_fields,
        # 수정가능성
        "check_feature_flag":        check_feature_flag,
        "check_config_separation":   check_config_separation,
        # 시험가능성
        "check_test_coverage":       check_test_coverage,
        "check_smoke_script":        check_smoke_script,
        # 모듈성
        "check_circular_imports":    check_circular_imports,
        # 재사용성
        "check_duplicate_functions": check_duplicate_functions,
        # 선택: 복잡도
        "check_cyclomatic_complexity": check_cyclomatic_complexity,
    }
    fn = mapping.get(t)
    if not fn:
        raise ValueError(f"[MAINTAINABILITY] 알 수 없는 검사 유형: {t}")
    return fn(step)

# -------------------------------
# 분석성
# -------------------------------
def check_log_level(step: Dict[str, Any]):
    log_path = step.get("log_path")
    allowed = set(step.get("allowed_levels", ["INFO", "WARN", "ERROR"]))
    if not log_path or not os.path.exists(log_path):
        print_result("check_log_level", False, "log_path 없음")
        return {"pass": False, "reason": "missing log_path"}
    pat = re.compile(r"^\s*([A-Z]+)\s*[:|\-]")
    bad = 0
    bad_lines = []
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for i, ln in enumerate(f, 1):
            m = pat.match(ln)
            if not m:
                # 레벨 표기가 없다면 정책 위반으로 간주(옵션: step.get('allow_no_level'))
                bad += 1; bad_lines.append((i, ln.strip())); continue
            lvl = m.group(1).strip()
            if lvl not in allowed:
                bad += 1; bad_lines.append((i, ln.strip()))
    ok = (bad == 0)
    print_result("check_log_level", ok, f"bad={bad}")
    return {"pass": ok, "bad_count": bad, "bad_lines": bad_lines[:20]}

def check_log_trace_fields(step: Dict[str, Any]):
    """로그에 trace_id/request_id 등 필수 키가 포함되는지 샘플링 확인"""
    log_path = step.get("log_path")
    required = step.get("required_fields", ["trace_id", "request_id"])
    sample = int(step.get("sample", 2000))  # 앞 n바이트만 스캔
    if not log_path or not os.path.exists(log_path):
        print_result("check_log_trace_fields", False, "log_path 없음")
        return {"pass": False, "reason": "missing log_path"}
    with open(log_path, "rb") as f:
        chunk = f.read(sample).decode("utf-8", errors="ignore")
    miss = [k for k in required if k not in chunk]
    ok = (len(miss) == 0)
    print_result("check_log_trace_fields", ok, f"missing={miss}" if miss else "ok")
    return {"pass": ok, "missing": miss}

# -------------------------------
# 수정가능성
# -------------------------------
def check_feature_flag(step: Dict[str, Any]):
    key = step.get("env_key")
    on_value = str(step.get("on_value", "ON"))
    if not key:
        print_result("check_feature_flag", False, "env_key 없음")
        return {"pass": False, "reason": "missing env_key"}
    before = os.environ.get(key, "")
    os.environ[key] = on_value
    after = os.environ.get(key, "")
    ok = (after == on_value)
    print_result("check_feature_flag", ok, f"{key}={after} (before={before})")
    return {"pass": ok, "before": before, "after": after}

def check_config_separation(step: Dict[str, Any]):
    key = step.get("env_key")
    expect = step.get("expect")
    if not key:
        print_result("check_config_separation", False, "env_key 없음")
        return {"pass": False, "reason": "missing env_key"}
    val = os.environ.get(key)
    ok = (val == expect)
    print_result("check_config_separation", ok, f"{key}={val}, expect={expect}")
    return {"pass": ok, "value": val}

# -------------------------------
# 시험가능성
# -------------------------------
def _which(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None

def check_test_coverage(step: Dict[str, Any]):
    """
    - prefer: coverage + pytest
    - fallback: pytest만
    """
    workdir = step.get("workdir", ".")
    cov = step.get("min_coverage", 0)  # 0이면 커버리지 임계 미적용
    use_cov = _which("coverage") and _which("pytest")
    use_pytest_only = (not use_cov) and _which("pytest")

    try:
        if use_cov:
            # coverage run -m pytest && coverage report --json
            r1 = subprocess.run(["coverage", "run", "-m", "pytest", "-q"], cwd=workdir,
                                capture_output=True, text=True)
            r2 = subprocess.run(["coverage", "report", "--format=json"], cwd=workdir,
                                capture_output=True, text=True)
            ok = (r1.returncode == 0)
            cov_pct = None
            try:
                data = json.loads(r2.stdout or "{}")
                cov_pct = float(data.get("totals", {}).get("percent_covered", 0.0))
                if cov and cov_pct is not None:
                    ok = ok and (cov_pct >= float(cov))
            except Exception:
                pass
            print_result("check_test_coverage", ok, f"pytest_rc={r1.returncode}, coverage={cov_pct}")
            return {"pass": ok, "pytest_rc": r1.returncode, "coverage": cov_pct,
                    "stdout": (r1.stdout + "\n" + r2.stdout)[-2000:], "stderr": (r1.stderr + "\n" + r2.stderr)[-2000:]}
        elif use_pytest_only:
            r = subprocess.run(["pytest", "-q"], cwd=workdir, capture_output=True, text=True)
            ok = (r.returncode == 0)
            print_result("check_test_coverage", ok, f"pytest_rc={r.returncode} (coverage 미사용)")
            return {"pass": ok, "pytest_rc": r.returncode, "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]}
        else:
            print_result("check_test_coverage", False, "pytest/coverage 미설치")
            return {"pass": False, "reason": "pytest/coverage not available"}
    except Exception as e:
        print_result("check_test_coverage", False, str(e))
        return {"pass": False, "reason": str(e)}

def check_smoke_script(step: Dict[str, Any]):
    script = step.get("script")
    if not script or not os.path.exists(script):
        print_result("check_smoke_script", False, "script 없음")
        return {"pass": False, "reason": "missing script"}
    r = subprocess.run([script], capture_output=True, text=True, shell=os.name=="nt" and script.lower().endswith((".bat",".cmd")))
    ok = (r.returncode == 0)
    print_result("check_smoke_script", ok, f"return={r.returncode}")
    return {"pass": ok, "returncode": r.returncode, "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]}

# -------------------------------
# 모듈성
# -------------------------------
def _iter_py_files(root: str) -> List[Path]:
    p = Path(root)
    return [x for x in p.rglob("*.py") if x.is_file() and ("venv" not in x.parts and ".venv" not in x.parts)]

def check_circular_imports(step: Dict[str, Any]):
    src = step.get("src", "src")
    files = _iter_py_files(src)
    # module name = path relative to src without .py, with dots
    def mod_name(path: Path) -> str:
        rel = path.relative_to(src).with_suffix("")
        return ".".join(rel.parts)
    modules = {mod_name(f): f for f in files}
    graph = {m: set() for m in modules}
    # build edges
    for m, f in modules.items():
        try:
            code = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(code, filename=str(f))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        top = n.name.split(".")[0]
                        # 전체 이름 중 우리 모듈 prefix와 맞는 것만 연결
                        for cand in modules:
                            if cand == n.name or cand.startswith(n.name + ".") or n.name.startswith(cand + ".") or cand.split(".")[0]==top:
                                graph[m].add(cand)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for cand in modules:
                            if cand == node.module or cand.startswith(node.module + ".") or node.module.startswith(cand + "."):
                                graph[m].add(cand)
        except Exception:
            pass
    # detect cycles (DFS)
    visited, stack = set(), set()
    cycles: List[List[str]] = []
    def dfs(u: str, path: List[str]):
        visited.add(u); stack.add(u); path.append(u)
        for v in graph.get(u, []):
            if v not in modules: 
                continue
            if v not in visited:
                dfs(v, path)
            elif v in stack:
                # cycle found
                if v in path:
                    idx = path.index(v)
                    cyc = path[idx:] + [v]
                    if cyc not in cycles:
                        cycles.append(cyc)
        path.pop(); stack.discard(u)
    for m in list(graph.keys()):
        if m not in visited:
            dfs(m, [])
    ok = (len(cycles) == 0)
    print_result("check_circular_imports", ok, f"cycles={len(cycles)}")
    return {"pass": ok, "cycles": cycles}

# -------------------------------
# 재사용성
# -------------------------------
def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def check_duplicate_functions(step: Dict[str, Any]):
    src = step.get("src", "src")
    min_len = int(step.get("min_chars", 80))  # 너무 짧은 건 무시
    funcs = {}  # hash -> [(module, name, start,end)]
    for f in _iter_py_files(src):
        try:
            code = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(code, filename=str(f))
            lines = code.splitlines()
            for node in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                if not hasattr(node, "end_lineno"):
                    continue
                body = "\n".join(lines[node.lineno-1: node.end_lineno])
                norm = re.sub(r"\s+", " ", body).strip()
                if len(norm) < min_len:
                    continue
                h = _hash_text(norm)
                funcs.setdefault(h, []).append((str(f), node.name, node.lineno, node.end_lineno))
        except Exception:
            pass
    dups = {h: v for h, v in funcs.items() if len(v) > 1}
    ok = (len(dups) == 0)
    print_result("check_duplicate_functions", ok, f"duplicates={len(dups)}")
    # 상위 몇 개만 리포트
    sample = []
    for v in dups.values():
        sample.extend(v)
        if len(sample) > 20:
            break
    return {"pass": ok, "duplicates": sample}

# -------------------------------
# 선택: 복잡도 (radon)
# -------------------------------
def check_cyclomatic_complexity(step: Dict[str, Any]):
    """
    radon cc -s -j <path>
    - max_avg: 평균 복잡도 상한(없으면 미적용)
    - max_any: 단일 함수 최고 복잡도 상한(없으면 미적용)
    """
    path = step.get("path", "src")
    max_avg = step.get("max_avg")
    max_any = step.get("max_any")
    if not _which("radon"):
        print_result("check_cyclomatic_complexity", False, "radon 미설치")
        return {"pass": False, "reason": "radon not available"}

    r = subprocess.run(["radon", "cc", "-s", "-j", path], capture_output=True, text=True)
    if r.returncode != 0:
        print_result("check_cyclomatic_complexity", False, f"radon rc={r.returncode}")
        return {"pass": False, "reason": "radon failed", "stderr": r.stderr[-1000:]}
    try:
        data = json.loads(r.stdout or "{}")  # {file: [{complexity: int, ...}, ...]}
        counts, total = 0, 0
        worst = 0
        for v in data.values():
            for item in v:
                c = int(item.get("complexity", 0))
                total += c; counts += 1
                worst = max(worst, c)
        avg = (total / counts) if counts else 0.0
        ok = True
        reasons = []
        if max_avg is not None and avg > float(max_avg):
            ok = False; reasons.append(f"avg {avg:.2f}>{float(max_avg)}")
        if max_any is not None and worst > int(max_any):
            ok = False; reasons.append(f"worst {worst}>{int(max_any)}")
        print_result("check_cyclomatic_complexity", ok, f"avg={avg:.2f}, worst={worst}" + ("" if not reasons else f" ({', '.join(reasons)})"))
        return {"pass": ok, "avg": avg, "worst": worst, "files": list(data.keys())[:20]}
    except Exception as e:
        print_result("check_cyclomatic_complexity", False, str(e))
        return {"pass": False, "reason": str(e)}
