# src/assessments/performance.py
def check(driver, step):
    url = step["target"]
    load_time = driver.measure_load_time(url)
    print(f"[PERFORMANCE] '{url}' 로드 시간: {load_time}ms")
    # 여기에 성능 기준을 체크하는 로직 추가 가능
    if load_time > 2000: # 예시: 2초 이상이면 경고
        print(f"[PERFORMANCE] 경고: '{url}' 로드 시간이 너무 깁니다. ({load_time}ms)")
    