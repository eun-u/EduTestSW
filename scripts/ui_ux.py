import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import random

os.environ["TOKENIZERS_PARALLELISM"] = "false"


class QA_TestApp:
    """
    온라인 강의 플랫폼의 UI/UX 품질을 검사하기 위한 테스트 도구
    10가지 테스트 케이스를 시뮬레이션 후 그 결과를 사용자에게 즉시 보여줌
    """

    def __init__(self, root):
        self.root = root
        self.root.title("온라인 강의 QA 테스트 도구 (10가지 항목)")
        self.root.geometry("800x700")

        # 테스트 진행 상황을 기록하는 로그 창
        self.test_log = tk.Text(self.root, height=10,
                                state='disabled', bg='#f0f0f0')
        self.test_log.pack(fill=tk.X, padx=10, pady=(10, 0))
        self.log_message("QA 테스트 도구 시작. 아래 버튼을 눌러 각 항목을 테스트하세요.")

        self.create_widgets()

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(expand=True, fill=tk.BOTH)

        # 10가지 테스트 케이스별 버튼 생성
        self.create_test_button("1. 로그인 과정 직관성 테스트", self.test_login_process)
        self.create_test_button(
            "2. 느린 로딩 시 사용자 불안 최소화 테스트", self.test_loading_anxiety)
        self.create_test_button("3. 재생, 일시정지, 배속 기능 테스트",
                                self.test_player_controls)
        self.create_test_button("4. 콘텐츠 탐색 직관성 테스트", self.test_content_search)
        self.create_test_button(
            "5. 모바일 환경 UI 테스트 (시뮬레이션)", self.test_mobile_ui)
        self.create_test_button("6. 중간 종료 후 이어보기 기능 테스트",
                                self.test_continue_watching)
        self.create_test_button("7. 강의 완료/퀴즈 결과 알림 테스트",
                                self.test_quiz_notification)
        self.create_test_button(
            "8. 글씨 크기와 대비 WCAG 기준 충족 테스트", self.test_wcag_compliance)
        self.create_test_button("9. 불편사항 쉽게 신고 기능 테스트", self.test_report_issue)
        self.create_test_button(
            "10. 자막이 강의 오디오와 정확히 맞는지 테스트", self.test_subtitle_sync)

    def create_test_button(self, text, command):
        # 테스트 버튼을 생성하고 메인 프레임에 추가하는 헬퍼 함수
        btn = ttk.Button(self.main_frame, text=text,
                         command=lambda: self.run_test(text, command))
        btn.pack(fill=tk.X, pady=5)

    def log_message(self, message):
        # 테스트 진행 상황을 로그 텍스트 위젯에 기록하는 함수
        self.test_log.config(state='normal')
        self.test_log.insert(tk.END, f"> {message}\n")
        self.test_log.config(state='disabled')
        self.test_log.see(tk.END)

    def run_test(self, test_name, test_func):
        # 각 테스트 함수를 실행하고 결과를 로그에 기록하는 제네릭 함수
        self.log_message(f"--- '{test_name}' 테스트 시작 ---")
        test_func()
        self.log_message(f"--- '{test_name}' 테스트 완료 ---\n")

    # --- 10가지 개별 테스트 케이스 ---

    # 1. 로그인 과정 직관성 테스트
    def test_login_process(self):
        self.log_message(" - 소셜 로그인 버튼 클릭을 시뮬레이션합니다.")
        messagebox.showinfo("테스트 결과", "로그인 절차가 간편하고 직관적입니다.")
        self.log_message(" - 결과: 로그인 절차 간편성 통과.")

    # 2. 느린 로딩 시 사용자 불안 최소화 테스트
    def test_loading_anxiety(self):
        self.log_message(" - 로딩 바와 취소 버튼이 나타나는지 확인합니다.")
        loading_window = tk.Toplevel(self.root)
        loading_window.title("로딩 테스트")

        progress_bar = ttk.Progressbar(
            loading_window, orient="horizontal", length=250, mode='determinate')
        progress_bar.pack(pady=10)

        cancel_btn = ttk.Button(loading_window, text="취소",
                                command=lambda: loading_window.destroy())
        cancel_btn.pack()

        def simulate_progress():
            for i in range(101):
                if not loading_window.winfo_exists():
                    return
                time.sleep(0.02)
                progress_bar['value'] = i
                loading_window.update_idletasks()
            if loading_window.winfo_exists():
                loading_window.destroy()
                self.log_message("로딩 중 진행률이 명확하게 표시됩니다.")
                messagebox.showinfo("테스트 결과", "로딩 시 사용자 불안 최소화 테스트 통과.")
                self.log_message(" - 결과: 로딩 불안감 최소화 통과.")

        threading.Thread(target=simulate_progress).start()

    # 3. 재생, 일시정지, 배속 기능 테스트
    def test_player_controls(self):
        self.log_message(" - 재생, 일시정지, 배속 기능 버튼 및 메뉴 동작을 시뮬레이션합니다.")
        messagebox.showinfo("테스트 결과", "플레이어 제어 버튼과 배속 메뉴가 정상적으로 작동합니다.")
        self.log_message(" - 결과: 플레이어 제어 기능 통과.")

    # 4. 원하는 콘텐츠 탐색 직관성 테스트
    def test_content_search(self):
        self.log_message(" - 검색어 '파이' 입력 시 관련 강의가 자동 완성되는지 시뮬레이션합니다.")
        contents = ["Python 기초", "자바스크립트 마스터", "PyTorch 튜토리얼"]
        search_query = "Py"
        results = [c for c in contents if search_query.lower() in c.lower()]

        if results:
            self.log_message(f" - 검색어 '{search_query}'에 대한 결과: {results}")
            messagebox.showinfo("테스트 결과", "검색 기능이 직관적으로 작동합니다.")
            self.log_message(" - 결과: 콘텐츠 탐색 직관성 통과.")
        else:
            self.log_message(" - 검색 결과 없음.")
            messagebox.showwarning("테스트 결과", "검색 기능에 문제가 있습니다.")
            self.log_message(" - 결과: 콘텐츠 탐색 직관성 실패.")

    # 5. 모바일 환경 UI 테스트 (시뮬레이션)
    def test_mobile_ui(self):
        self.log_message(" - 모바일 환경에서 버튼과 텍스트가 겹치지 않는지 시뮬레이션합니다.")
        messagebox.showinfo("테스트 결과", "모바일 환경에서 UI가 겹치지 않고 잘 배치되어 있습니다.")
        self.log_message(" - 결과: 모바일 UI 테스트 통과.")

    # 6. 중간 종료 후 이어보기 기능 테스트
    def test_continue_watching(self):
        self.log_message(" - 시청 기록 저장 및 로드 기능을 시뮬레이션합니다.")
        last_watched_time = random.randint(60, 180)

        # 시청 기록 파일 생성
        with open("progress_test.json", "w") as f:
            json.dump({"last_watched_time": last_watched_time}, f)

        try:
            with open("progress_test.json", "r") as f:
                data = json.load(f)
                loaded_time = data.get("last_watched_time")
            self.log_message(f" - 시청 기록 {loaded_time}초가 성공적으로 로드되었습니다.")
            messagebox.showinfo("테스트 결과", "이어보기 기능이 사용자의 흐름을 방해하지 않습니다.")
            self.log_message(" - 결과: 이어보기 기능 통과.")
        except (FileNotFoundError, json.JSONDecodeError):
            self.log_message(" - 시청 기록 파일이 없습니다.")
            messagebox.showwarning("테스트 결과", "이어보기 기능에 문제가 있습니다.")
            self.log_message(" - 결과: 이어보기 기능 실패.")

    # 7. 강의 완료/퀴즈 결과 알림 테스트
    def test_quiz_notification(self):
        self.log_message(" - 퀴즈 결과 알림이 명확한지 시뮬레이션합니다.")
        score = random.randint(50, 100)
        if score > 70:
            messagebox.showinfo("테스트 결과", f"축하합니다! 퀴즈 점수: {score}점")
            self.log_message(" - 결과: 알림 명확성 통과 (성공 케이스).")
        else:
            messagebox.showwarning("테스트 결과", f"아쉽네요. 퀴즈 점수: {score}점")
            self.log_message(" - 결과: 알림 명확성 통과 (실패 케이스).")

    # 8. 글씨 크기와 대비 WCAG 기준 충족 테스트
    def test_wcag_compliance(self):
        self.log_message(" - 글씨와 배경의 대비가 충분한지 시뮬레이션합니다.")
        messagebox.showinfo("테스트 결과", "글씨와 배경의 대비가 충분하며, 글씨 크기 조절 기능이 있습니다.")
        self.log_message(" - 결과: WCAG 기준 준수 통과.")

    # 9. 불편사항 쉽게 신고 기능 테스트
    def test_report_issue(self):
        self.log_message(" - 불편사항 신고 버튼 접근성과 기능이 정상적인지 시뮬레이션합니다.")
        messagebox.showinfo(
            "테스트 결과", "'불편사항 신고' 버튼이 쉽게 찾을 수 있는 곳에 있으며, 정상적으로 작동합니다.")
        self.log_message(" - 결과: 불편사항 신고 기능 통과.")

    # 10. 자막이 강의 오디오와 정확히 맞는지 테스트
    def test_subtitle_sync(self):
        self.log_message(" - 자막이 강의 오디오와 정확히 동기화되는지 시뮬레이션합니다.")
        messagebox.showinfo("테스트 결과", "자막이 강의 오디오와 정확히 동기화됩니다.")
        self.log_message(" - 결과: 자막 동기화 테스트 통과.")


if __name__ == "__main__":
    root = tk.Tk()
    app = QA_TestApp(root)
    root.mainloop()
