
# EduTestSW 🧪  
**교육용 소프트웨어 품질 검사 자동화 도구**

## 📌 소개
EduTestSW는 **교육 소프트웨어(LMS/EBS 등)** 의 품질을 자동으로 평가하기 위한 오픈소스 프로젝트입니다.  
ISO/IEC 25010 품질 특성을 기반으로 **기능성, 신뢰성, 성능, 보안성, 사용성, 유지보수성, 이식성** 등을 자동 검사할 수 있도록 설계되었습니다.  


---

## ⚙️ 설치 방법

### 1. 가상환경 생성 및 활성화

```bash
# 가상환경 생성
python -m venv venv

# Windows
venv/Scripts/activate

# macOS/Linux
source venv/bin/activate
```

### 2. 필요 패키지 설치

```bash
pip install -r requirements.txt
```
```bash
npm install playwright
npx playwright install
```
---

## ▶️ 실행 방법

```bash
python run_routine.py
```

---

## 📂 프로젝트 구조

```plaintext
EduTestSW/
├── run_routine.py         # 실행 스크립트
├── src/
│   ├── assessments/       # 품질 특성별 검사 모듈
│   ├── core/              # 파서, 드라이버, 러너
│   └── routines/          # JSON 테스트 시나리오
├── requirements.txt       # 의존성 패키지
└── README.md              # 프로젝트 설명 문서
```


---

## 📊 아키텍처 다이어그램
<p align="center">
  <img src="assets/EduSW.drawio.png" alt="EduTestSW 구조" width="700"/>
</p>

---


