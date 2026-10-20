# 🔬 AI Data Insight Builder

> **공식 데이터 자동 진단 &bull; Pandas 정밀 계산 &bull; Gemini AI 통계 해석 & 동적 자연어 시각화 웹 플랫폼**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Web%20Framework-black?logo=flask)](https://flask.palletsprojects.com/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-2.5--Flash-8E75B2?logo=googlegemini)](https://aistudio.google.com/)
[![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-150458?logo=pandas)](https://pandas.pydata.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📌 프로젝트 소개

**AI Data Insight Builder**는 복잡한 데이터 분석 절차를 누구나 손쉽게 수행할 수 있도록 돕는 웹 애플리케이션입니다.  
사용자가 CSV 파일을 업로드하면 **인코딩 감지, 데이터 정제, 결측치 진단**을 자동으로 수행하며, 사용자의 **자유로운 자연어 질문**을 이해하여 알맞은 시각화 차트와 심층 AI 해석 보고서를 실시간으로 생성합니다.

---

## ✨ 핵심 기능

### 1. 🔒 사이트 보안 잠금 (Security Lock System)
- **4자리 PIN 인증**: 사이트 접속 시 글래스모피즘 오버레이 잠금 화면 적용 (기본 비밀번호: **`7890`**)
- **물리적 인터랙티브 애니메이션**:
  - 비밀번호 일치 시 SVG 자물쇠 고리 회전 및 팝업, 에메랄드 그린 발광 및 리플 파동 효과 후 부드러운 페이드아웃
  - 비밀번호 불일치 시 직관적인 카드 진동(Shake) 효과 및 경고 문구 출력
- **세션 유지 및 다시 잠그기**: 브라우저 세션 동안 인증 상태를 기억하며, 헤더의 `[🔒 잠금]` 버튼으로 언제든 다시 잠금 가능

### 2. 🧠 동적 AI 데이터 에이전트 (Dynamic AI Agent)
- **제약 없는 자유 질의응답**:
  - *"2024년 1등부터 10등까지 한국과 비교해줘"*
  - *"특정 국가/조건의 연도별 추세를 보여줘"*
  - *"상위 5개 그룹의 평균 수치를 비교해줘"*
- **자동 쿼리 해석 및 Pandas 연산**: 질문 의도에 맞추어 컬럼, 필터 조건, 정렬 기준, 비교 대상을 자동 추출 및 계산
- **실시간 반응형 시각화**: Chart.js를 연동하여 막대 차트, 꺾은선 차트, 파이 차트 등을 유연하게 렌더링

### 3. 🔍 스마트 데이터 자동 진단 (Data Inspection)
- **인코딩 자동 판별**: `utf-8-sig`, `utf-8`, `cp949`, `euc-kr` 자동 감지로 한글 깨짐 방지
- **헤더/스킵 행 자동 감지**: 공공데이터 특유의 불필요한 서두 행 자동 제거
- **통계 요약**: 수치형/범주형 컬럼 분류, 결측치율, 기초 통계량(평균, 사분위수, 최빈값 등) 즉시 제공

### 4. 📝 Gemini 맞춤형 통계 리포트 (Insight Generation)
- **수준별 3단계 설명 모드**:
  - 🎒 **초등학생 모드**: 쉬운 비유와 스토리텔링 중심 설명
  - 🏫 **고등학생 모드**: 통계적 개념과 원인-결과 분석 중심
  - 💼 **전문가 모드**: 데이터 신뢰도, 분포 왜곡, 한계점 및 실무 제언 포함

### 5. 🍂 감성 가을 단풍 테마 (Autumn Mode)
- 상단 토글 스위치로 감성적인 가을 단풍 모드 전환
- HTML5 Canvas 기반의 자연스러운 단풍잎 낙하 물리 시뮬레이션
- 눈이 편안한 웜톤 브라운 팔레트 UI 테마

### 6. 📲 PWA (Progressive Web App) & 앱 설치 지원
- **독립형 앱 구동**: 브라우저 주소창 없이 전체 화면 데스크톱/모바일 앱으로 동작
- **원클릭 앱 설치 버튼**: 상단 헤더의 `[📲 앱 설치]` 버튼으로 간편 설치 지원 및 기기별(PC, iOS, Android) 맞춤 설치 가이드 제공
- **오프라인 캐싱**: Service Worker(`sw.js`) 및 `manifest.json` 내장으로 빠른 로딩 속도 및 오프라인 정적 자산 보존

---

## 🛠 기술 스택

| 영역 | 기술 및 도구 |
| :--- | :--- |
| **Backend** | Python 3, Flask, Pandas, NumPy, python-dotenv |
| **AI / LLM** | Google Gemini API (`gemini-2.5-flash`), `google-genai` SDK |
| **Frontend** | Vanilla JavaScript (ES6+), HTML5, CSS3 (Glassmorphism), Chart.js |
| **Deployment** | Vercel, GitHub |

---

## 🚀 빠른 시작 (Getting Started)

### 1. 저장소 클론
```bash
git clone https://github.com/sungrin1234/data-insight-builder.git
cd data-insight-builder
```

### 2. 가상환경 구성 및 패키지 설치
```bash
# 가상환경 생성 (선택)
python -m venv .venv

# 가상환경 활성화 (Windows)
.\.venv\Scripts\activate
# 가상환경 활성화 (Mac/Linux)
source .venv/bin/activate

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 3. 환경 변수 설정
프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 발급받은 Gemini API 키를 입력합니다. ([Google AI Studio에서 발급](https://aistudio.google.com/))
```env
# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# 사용할 Gemini 모델명
GEMINI_MODEL=gemini-2.5-flash

# Flask 디버그 모드
FLASK_DEBUG=true

# 최대 업로드 파일 크기 (단위: MB)
MAX_UPLOAD_MB=10
```

### 4. 서버 실행
```bash
python app.py
```
브라우저에서 `http://127.0.0.1:5000`으로 접속합니다.  
**기본 접속 비밀번호는 `7890` 입니다.**

---

## 📂 프로젝트 구조

```plaintext
data-insight-builder/
├── data/                  # 예제 데이터셋 (행복지수, GDP 등)
├── static/
│   └── style.css          # UI 디자인, 가을 테마, 보안 잠금 애니메이션
├── templates/
│   └── index.html         # 메인 대시보드 템플릿, SVG 자물쇠, Chart.js 로직
├── app.py                 # Flask 서버 및 Pandas 연산, Gemini AI 파이프라인
├── tools.py               # 데이터 분석 보조 유틸리티 모듈
├── requirements.txt       # 의존성 패키지 목록
├── .env.example           # 환경 변수 템플릿
├── .gitignore             # 깃 추적 제외 목록
└── README.md              # 프로젝트 안내 문서
```

---

## 🔌 주요 API 엔드포인트

| Method | Endpoint | 설명 |
| :---: | :--- | :--- |
| `GET` | `/` | 웹 대시보드 메인 화면 |
| `GET` | `/health` | 서버 상태 및 Gemini API 연동 상태 확인 |
| `POST` | `/inspect` | CSV 업로드 및 인코딩/결측치/데이터 구조 자동 진단 |
| `POST` | `/suggest` | 데이터셋 특성 기반 추천 시각화 질문 생성 |
| `POST` | `/run` | 선택한 컬럼 및 집계 방식에 따른 Pandas 연산 및 시각화 데이터 반환 |
| `POST` | `/explain` | 분석 결과에 대한 Gemini AI 맞춤형 통계 해석 리포트 생성 |
| `POST` | `/ask` | 데이터셋 기반 자유 텍스트 질문 및 답변 |
| `POST` | `/ask_and_visualize` | 사용자 임의 질문을 실시간 분석하여 차트 + 인사이트 동시 생성 |

---

## 🔐 사이트 기본 접속 정보
- **기본 비밀번호(PIN)**: `7890`
- 변경을 원할 경우 `templates/index.html` 내 `const SECRET_PIN = "7890";` 값을 수정할 수 있습니다.

---

## 📄 라이선스
This project is licensed under the MIT License.
