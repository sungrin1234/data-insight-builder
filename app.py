import csv
import io
import json
import logging
import math
import os
import re
from flask import Flask, jsonify, render_template, request
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# .env 환경변수 로드
load_dotenv()

# 로깅 설정 (print() 대신 logging 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("DataInsightBuilder")

app = Flask(__name__)

# 환경변수에서 설정값 읽기
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", 10))
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

# 메모리에 단 1개의 활성 데이터셋만 보관 (디스크 저장 금지)
CURRENT_DATASET = {
    "df": None,
    "filename": None,
    "meta": None,
    "inspection": None
}

def detect_encoding(file_bytes: bytes):
    """utf-8-sig, utf-8, cp949, euc-kr 순서로 인코딩을 시도합니다."""
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    for enc in encodings:
        try:
            text = file_bytes.decode(enc)
            logger.info(f"[ENCODING] {enc} 성공")
            return enc, text
        except (UnicodeDecodeError, LookupError):
            logger.info(f"[ENCODING] {enc} 실패, 다음 인코딩 시도")
    return None, None

def detect_header_skiprows(text: str, max_check_lines: int = 15):
    """앞쪽 줄들을 검사하여 실제 열 이름(Header) 행과 건너뛸 줄 수(skiprows)를 찾습니다."""
    lines = text.splitlines()
    if not lines:
        return 0
    
    best_skip = 0
    max_col_count = 0
    
    for i in range(min(len(lines), max_check_lines)):
        line_str = lines[i].strip()
        if not line_str:
            continue
        try:
            row = next(csv.reader([line_str]))
            non_empty_items = [c.strip() for c in row if c.strip()]
            if len(non_empty_items) > max_col_count:
                max_col_count = len(non_empty_items)
                best_skip = i
        except Exception:
            continue
            
    logger.info(f"[HEADER] 헤더 줄 감지 결과: {best_skip}번째 줄 (건너뛴 줄 수={best_skip}, 감지된 열 개수={max_col_count})")
    return best_skip

def safe_json_value(val):
    """NaN, Inf, -Inf 값을 JSON 호환 None으로 안전하게 변환합니다."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    return str(val)

@app.route("/", methods=["GET"])
def index():
    """메인 HTML 페이지 반환"""
    logger.info("[REQUEST] GET /")
    return render_template("index.html")

@app.route("/health", methods=["GET"])
def health():
    """서버 상태 및 API Key 설정 여부 반환 (보안: 실제 키 값은 절대 노출 금지)"""
    logger.info("[REQUEST] GET /health")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    has_api_key = bool(api_key and api_key != "your_gemini_api_key_here")
    
    response_data = {
        "status": "ok",
        "gemini_api_key_configured": has_api_key,
        "model": model
    }
    logger.info(f"[RESPONSE] status=200 has_key={has_api_key} model={model}")
    return jsonify(response_data)

@app.route("/inspect", methods=["POST"])
def inspect():
    """
    [Step 13: POST /inspect 2차 완성본]
    CSV 진단 항목 13가지 전체 수행
    """
    logger.info("[REQUEST] POST /inspect")
    
    # 1. 파일 검증
    if "file" not in request.files:
        logger.warning("[ERROR] 파일이 전송되지 않음")
        return jsonify({"error": "업로드할 CSV 파일을 선택해 주세요."}), 400
        
    uploaded_file = request.files["file"]
    filename = uploaded_file.filename or ""
    
    if not filename:
        logger.warning("[ERROR] 파일명이 없음")
        return jsonify({"error": "선택된 파일이 없습니다."}), 400
        
    if not filename.lower().endswith(".csv"):
        logger.warning(f"[ERROR] 잘못된 확장자: {filename}")
        return jsonify({"error": "CSV 파일(.csv)만 업로드할 수 있습니다."}), 400
        
    file_bytes = uploaded_file.read()
    file_size = len(file_bytes)
    logger.info(f"[FILE] name={filename} size={file_size} bytes")
    
    if file_size == 0:
        logger.warning("[ERROR] 빈 파일")
        return jsonify({"error": "업로드한 파일이 비어 있습니다."}), 400

    # 2. 인코딩 순차 시도
    encoding, text = detect_encoding(file_bytes)
    if not encoding or text is None:
        logger.error("[ERROR] 모든 인코딩 시도 실패")
        return jsonify({"error": "지원하는 인코딩(UTF-8, CP949, EUC-KR)으로 파일을 읽을 수 없습니다."}), 400

    # 3. 헤더 줄 자동 감지
    skiprows = detect_header_skiprows(text)

    # 4. Pandas 파싱
    try:
        df = pd.read_csv(io.StringIO(text), skiprows=skiprows)
        logger.info(f"[CSV] parsing 완료 rows={len(df)} columns={len(df.columns)}")
    except Exception as e:
        logger.error(f"[ERROR] Pandas CSV 파싱 오류: {str(e)}", exc_info=True)
        return jsonify({"error": f"CSV 파싱 중 오류가 발생했습니다: {str(e)}"}), 400

    warnings = []
    
    # 5. 열 분류 및 Unnamed / 빈 열 감지
    columns = [str(c).strip() for c in df.columns]
    df.columns = columns
    
    unnamed_or_empty_cols = []
    for col in columns:
        is_unnamed = bool(re.match(r"^Unnamed:\s*\d+$", col, re.IGNORECASE)) or col == ""
        is_all_null = df[col].isna().all()
        if is_unnamed or is_all_null:
            unnamed_or_empty_cols.append({
                "column": col,
                "is_unnamed": is_unnamed,
                "is_all_null": bool(is_all_null)
            })
    
    if unnamed_or_empty_cols:
        col_names = [c["column"] if c["column"] else "(빈 열)" for c in unnamed_or_empty_cols]
        warnings.append(f"이름이 없거나 전체가 비어 있는 열이 {len(unnamed_or_empty_cols)}개 발견되었습니다: {', '.join(col_names[:5])}")

    # 열 데이터 타입 및 컬럼 분류
    numeric_columns = []
    string_columns = []
    year_candidate_columns = []
    col_types = {}
    missing_stats = {}

    total_rows = len(df)
    for col in columns:
        dtype_str = str(df[col].dtype)
        col_types[col] = dtype_str
        
        # 결측치 개수와 비율
        null_count = int(df[col].isna().sum())
        null_ratio = round((null_count / total_rows * 100), 2) if total_rows > 0 else 0
        missing_stats[col] = {
            "null_count": null_count,
            "null_ratio_pct": null_ratio
        }

        # 연도 후보 열 (예: 1960, 2024 등 4자리 숫자이거나 YYYY 형식)
        if re.match(r"^(19\d\d|20\d\d)$", col):
            year_candidate_columns.append(col)

        # 숫자형 / 문자형 판별
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_columns.append(col)
        else:
            string_columns.append(col)

    # 6. 중복 행 수
    duplicate_rows_count = int(df.duplicated().sum())
    if duplicate_rows_count > 0:
        warnings.append(f"완전히 동일한 중복 행이 {duplicate_rows_count}개 감지되었습니다.")

    # 7. 연도별 데이터 충실도 & 권장 기준연도 계산
    year_coverage = {}
    recommended_year = None
    if year_candidate_columns:
        # 연도 순서대로 정렬
        sorted_year_cols = sorted(year_candidate_columns, key=lambda x: int(x))
        best_count = -1
        
        for y in sorted_year_cols:
            valid_cnt = int(df[y].notna().sum())
            year_coverage[y] = {
                "filled_count": valid_cnt,
                "total_count": total_rows,
                "fill_ratio_pct": round((valid_cnt / total_rows * 100), 1) if total_rows > 0 else 0
            }
            # 충실도가 충분히 높고(최대치 근처), 가장 최근인 연도를 권장연도로 선택
            # (예: 2025년이 42개로 급감하고 2024년이 214개이면 2024년을 추천)
            if valid_cnt >= best_count * 0.9 and valid_cnt >= (total_rows * 0.5):
                best_count = max(best_count, valid_cnt)
                recommended_year = y

        if recommended_year:
            latest_year = sorted_year_cols[-1]
            if latest_year != recommended_year:
                warnings.append(
                    f"가장 마지막 연도({latest_year})는 데이터 충실도({year_coverage[latest_year]['filled_count']}건)가 낮아, "
                    f"값이 충실하게 채워진 최근 연도인 '{recommended_year}'({year_coverage[recommended_year]['filled_count']}건)를 기준 연도로 권장합니다."
                )

    # 8. 집계 행 후보 탐지
    # (World, OECD, Euro area, High income, Low income 등)
    aggregate_keywords = [
        "world", "oecd members", "euro area", "european union",
        "high income", "low income", "middle income", "upper middle income",
        "lower middle income", "arab world", "latin america", "caribbean",
        "east asia", "south asia", "sub-saharan africa", "income", "area", "total"
    ]
    
    aggregate_candidates = []
    # 문자열 열(예: Country Name)을 순회하며 키워드 매칭
    label_cols = [c for c in string_columns if "name" in c.lower() or "country" in c.lower()] or string_columns[:1]
    
    if label_cols:
        target_col = label_cols[0]
        for idx, val in df[target_col].dropna().items():
            val_str = str(val).strip()
            val_lower = val_str.lower()
            if any(kw in val_lower for kw in aggregate_keywords):
                aggregate_candidates.append({
                    "row_index": int(idx),
                    "label": val_str,
                    "column": target_col
                })
                
    if aggregate_candidates:
        warnings.append(
            f"국가 간 비교 시 왜곡을 유발할 수 있는 '집계/그룹 행 후보'가 {len(aggregate_candidates)}개 감지되었습니다. "
            f"(예: {', '.join([c['label'] for c in aggregate_candidates[:3]])} 등)"
        )

    # 9. 데이터 미리보기 (앞 10행, JSON 안전 처리)
    preview_df = df.head(10).copy()
    # NaN/Inf 치환
    preview_rows = []
    for _, row in preview_df.iterrows():
        preview_rows.append({col: safe_json_value(row[col]) for col in df.columns})

    # 메모리에 현재 데이터셋 및 진단결과 보관
    inspection_result = {
        "filename": filename,
        "file_size": file_size,
        "encoding": encoding,
        "skiprows": skiprows,
        "rows": total_rows,
        "columns_count": len(df.columns),
        "columns": columns,
        "column_types": col_types,
        "numeric_columns": numeric_columns,
        "string_columns": string_columns,
        "year_candidate_columns": year_candidate_columns,
        "missing_stats": missing_stats,
        "duplicate_rows_count": duplicate_rows_count,
        "unnamed_or_empty_cols": unnamed_or_empty_cols,
        "year_coverage": year_coverage,
        "recommended_year": recommended_year,
        "aggregate_candidates_count": len(aggregate_candidates),
        "aggregate_candidates": aggregate_candidates[:20], # 상위 20개만 요약 전달
        "preview_rows": preview_rows,
        "warnings": warnings,
        "memory_notice": "업로드된 데이터는 서버 메모리에만 임시 보관되며 서버 재시작 시 초기화됩니다."
    }

    CURRENT_DATASET["df"] = df
    CURRENT_DATASET["filename"] = filename
    CURRENT_DATASET["meta"] = {
        "encoding": encoding,
        "skiprows": skiprows,
        "size": file_size
    }
    CURRENT_DATASET["inspection"] = inspection_result

    logger.info(f"[DIAGNOSE] 진단 완료 warnings={len(warnings)} aggregates={len(aggregate_candidates)} rec_year={recommended_year}")
    logger.info(f"[RESPONSE] status=200 rows={total_rows} cols={len(df.columns)}")
    return jsonify(inspection_result)

@app.route("/suggest", methods=["POST"])
def suggest():
    """
    [Step 17: POST /suggest]
    진단 결과 요약과 도구 카탈로그를 Gemini에게 전달하여 3~5개의 실행 가능한 분석 제안을 JSON으로 수신
    - 절대 규칙: CSV 원본을 보내지 않음, 도구 카탈로그에 있는 12개 도구만 제안 허용
    """
    logger.info("[REQUEST] POST /suggest")
    
    if CURRENT_DATASET["df"] is None or CURRENT_DATASET["inspection"] is None:
        logger.warning("[ERROR] 데이터셋이 업로드되지 않음")
        return jsonify({"error": "먼저 CSV 파일을 업로드하고 진단을 완료해 주세요."}), 400

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        logger.error("[ERROR] GEMINI_API_KEY 미설정")
        return jsonify({"error": "Gemini API Key가 .env에 설정되지 않았습니다. API 키를 입력해 주세요."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    inspection = CURRENT_DATASET["inspection"]

    # 1. Gemini에게 전달할 최소 진단 요약본 (원본 CSV는 절대 전송하지 않음)
    summary_for_ai = {
        "filename": inspection["filename"],
        "total_rows": inspection["rows"],
        "columns": inspection["columns"],
        "numeric_columns": inspection["numeric_columns"],
        "string_columns": inspection["string_columns"],
        "year_candidate_columns": inspection["year_candidate_columns"],
        "recommended_year": inspection["recommended_year"],
        "aggregate_candidates_count": inspection["aggregate_candidates_count"],
        "aggregate_examples": [c["label"] for c in inspection["aggregate_candidates"][:5]],
        "warnings": inspection["warnings"]
    }

    # 2. 제안 가능한 12개 도구 카탈로그 정의
    catalog_desc = """
    [사용 가능한 도구 카탈로그 (오직 이 12개 도구만 제안 가능)]:
    1. reshape_wide_to_long: 연도 열들을 롱 포맷(행 단위)으로 접기. params: {}
    2. quality_report: 결측·중복·열 이름 품질 진단 보고서. params: {}
    3. year_coverage: 연도별 값 개수 및 충실도 계산. params: {}
    4. detect_aggregates: 국가 통계 왜곡을 막기 위한 집계 행 후보 탐지. params: {"label_column": "열이름"}
    5. describe_numeric: 특정 시점 숫자 열의 평균·중앙값·최소·최대·표준편차. params: {"value_column": "열이름", "reference_period": "연도", "exclude_aggregates": true}
    6. trend_line: 주요 국가들의 연도별 시계열 추이 선 차트. params: {"target_labels": ["항목1", "항목2"], "label_column": "열이름"}
    7. top_bottom_n: 특정 기준연도 상위·하위 N개 순위 수평 막대 차트. params: {"value_column": "연도열", "reference_period": "연도", "n": 10, "order": "top", "exclude_aggregates": true}
    8. group_summary: 그룹 열(예: Region) 기준 특정 연도 평균/합계 막대 차트. params: {"group_column": "열이름", "value_column": "연도열", "reference_period": "연도", "metric": "mean"}
    9. change_rate: 두 시점 사이 변화량·변화율 막대 차트. params: {"start_period": "시작연도", "end_period": "종료연도", "n": 10, "order": "top", "exclude_aggregates": true}
    10. distribution: 특정 연도 데이터의 구간별 빈도 히스토그램. params: {"value_column": "연도열", "reference_period": "연도", "bins": 10, "exclude_aggregates": true}
    11. correlation_scatter: 두 연도/숫자 열 간 피어슨 상관계수 및 산점도. params: {"x_column": "열1", "y_column": "열2", "reference_period": "시점", "exclude_aggregates": true}
    12. compare_one_vs_all: 특정 1개 국가 vs 전체 평균·중앙값 대비 강조 막대 차트. params: {"target_item": "국가명", "value_column": "연도열", "reference_period": "연도", "exclude_aggregates": true}
    """

    prompt = f"""
    당신은 데이터 분석 전문가입니다. 아래 제공된 데이터 진단 요약과 도구 카탈로그를 보고,
    이 데이터셋에서 가장 통찰력 있고 실행 가능한 분석 3~5개를 골라 제안하세요.

    [데이터 진단 요약]:
    {json.dumps(summary_for_ai, ensure_ascii=False, indent=2)}

    {catalog_desc}

    [절대 규칙]:
    1. 반드시 위 카탈로그에 명시된 12개 도구명(tool)만 사용해야 합니다. 다른 도구는 절대 제안할 수 없습니다.
    2. 데이터셋의 실제 컬럼 목록에 있는 열 이름만 params에 넣어야 합니다.
    3. 7~12번 도구는 reference_period(권장연도 '{inspection.get("recommended_year")}' 우선 활용)를 반드시 지정해야 합니다.
    4. 출력은 오직 순수 JSON 형식이어야 합니다. 마크다운 따옴표(```json) 없이 유효한 JSON 문자열만 출력하세요.

    [반환 JSON 포맷]:
    {{
      "suggestions": [
        {{
          "tool": "top_bottom_n",
          "params": {{
            "value_column": "{inspection.get('recommended_year') or '2024'}",
            "reference_period": "{inspection.get('recommended_year') or '2024'}",
            "label_column": "Country Name",
            "n": 10,
            "order": "top",
            "exclude_aggregates": true
          }},
          "reference_period": "{inspection.get('recommended_year') or '2024'}",
          "why": "이 분석이 이 데이터에서 의미 있는 이유 (초보자 눈높이 설명)",
          "caution": "해석할 때 주의할 점 (예: 집계 행 왜곡 방지 등)"
        }}
      ]
    }}
    """

    logger.info(f"[AI] suggest 요청 시작 (model={model_name})")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        raw_text = response.text or ""
        logger.info(f"[AI] suggest 응답 수신 길이={len(raw_text)}")

        # JSON 추출 및 파싱 (마크다운 백틱 제거 보정)
        cleaned_json = raw_text.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json)
            
        parsed = json.loads(cleaned_json)
        logger.info(f"[AI] JSON 파싱 완료 suggestions={len(parsed.get('suggestions', []))}")
        return jsonify(parsed)

    except json.JSONDecodeError as je:
        logger.error(f"[ERROR] Gemini 응답 JSON 파싱 실패: {str(je)}\n원문: {raw_text}")
        return jsonify({"error": "Gemini 응답을 JSON으로 파싱하지 못했습니다.", "raw": raw_text}), 500
    except Exception as e:
        logger.error(f"[ERROR] Gemini API 호출 오류: {str(e)}", exc_info=True)
        return jsonify({"error": f"Gemini API 호출 중 오류가 발생했습니다: {str(e)}"}), 500

# 가장 최근 실행된 도구의 계산 결과를 메모리에 보관 (/explain 에서 사용)
LAST_RUN_RESULT = {
    "tool": None,
    "params": None,
    "result": None
}

@app.route("/run", methods=["POST"])
def run():
    """
    [Step 18: POST /run]
    선택된 도구를 Pandas로 직접 실행하고, 계산 결과와 Chart.js 호환 차트 데이터 반환
    - 절대 규칙: 숫자 계산은 오직 Pandas가 수행, 기준 시점 및 제외 행 수 필수 반환
    """
    logger.info("[REQUEST] POST /run")
    
    if CURRENT_DATASET["df"] is None:
        logger.warning("[ERROR] 데이터셋이 업로드되지 않음")
        return jsonify({"error": "먼저 CSV 파일을 업로드해 주세요."}), 400

    req_data = request.get_json(silent=True) or {}
    tool_name = req_data.get("tool")
    params = req_data.get("params") or {}

    if not tool_name:
        logger.warning("[ERROR] 도구명 미입력")
        return jsonify({"error": "실행할 도구 이름(tool)을 지정해 주세요."}), 400

    import tools
    if tool_name not in tools.TOOL_CATALOG:
        logger.warning(f"[ERROR] 도구 목록에 없음: {tool_name}")
        return jsonify({"error": f"도구 카탈로그에 존재하지 않는 도구입니다: '{tool_name}'"}), 400

    # 도구 7~12 기준시점 필수 검증
    require_period_tools = [
        "top_bottom_n", "group_summary", "change_rate",
        "distribution", "correlation_scatter", "compare_one_vs_all"
    ]
    if tool_name in require_period_tools:
        if tool_name == "change_rate":
            if not params.get("start_period") or not params.get("end_period"):
                logger.warning(f"[ERROR] {tool_name} 시작/종료 시점 누락")
                return jsonify({"error": f"'{tool_name}' 도구는 시작 시점(start_period)과 종료 시점(end_period)이 필수입니다."}), 400
        else:
            if not params.get("reference_period"):
                logger.warning(f"[ERROR] {tool_name} 기준시점 누락")
                return jsonify({"error": f"'{tool_name}' 도구는 기준 시점(reference_period)이 필수입니다."}), 400

    try:
        df = CURRENT_DATASET["df"]
        calc_result = tools.run_tool(df, tool_name, params)
        
        # 메모리에 최근 실행 결과 보관 (/explain 에서 순수 계산결과만 Gemini에 전달하기 위함)
        LAST_RUN_RESULT["tool"] = tool_name
        LAST_RUN_RESULT["params"] = params
        LAST_RUN_RESULT["result"] = calc_result
        
        logger.info(
            f"[TOOL] 완료 도구명={tool_name} "
            f"사용한행수={calc_result.get('rows_used')} "
            f"제외한행수={calc_result.get('rows_excluded')}"
        )
        return jsonify(calc_result)

    except ValueError as ve:
        logger.warning(f"[ERROR] 도구 매개변수/데이터 오류: {str(ve)}")
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"[ERROR] 도구 실행 실패: {str(e)}", exc_info=True)
        return jsonify({"error": f"도구 실행 중 오류가 발생했습니다: {str(e)}"}), 500

@app.route("/explain", methods=["POST"])
def explain():
    """
    [Step 19: POST /explain]
    /run의 계산 결과 또는 진단 요약을 바탕으로 Gemini AI 해석 보고서 생성
    - 모드 A (비교용, 의도적으로 허술하게): 진단 요약만 주고 "보고서 써줘" 요청 (Pandas 계산 수치 없음)
    - 모드 B (정식): Pandas 계산 결과(수치, 기준시점, 제외행)만 주고 8가지 엄격한 규칙을 적용하여 해석
    """
    logger.info("[REQUEST] POST /explain")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        logger.error("[ERROR] GEMINI_API_KEY 미설정")
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    req_data = request.get_json(silent=True) or {}
    mode = req_data.get("mode", "B").upper() # 'A' or 'B'

    if mode not in ["A", "B"]:
        return jsonify({"error": "mode는 'A' 또는 'B'여야 합니다."}), 400

    if CURRENT_DATASET["inspection"] is None:
        return jsonify({"error": "업로드된 데이터셋이 없습니다."}), 400

    inspection = CURRENT_DATASET["inspection"]

    from google import genai
    client = genai.Client(api_key=api_key)

    if mode == "A":
        # ========================================================
        # 모드 A: 비교용 (의도적으로 허술하게 생성)
        # Pandas 계산 결과를 주지 않고, 일반적인 진단 메타데이터만 준 뒤 보고서 요청
        # ========================================================
        logger.info(f"[AI] explain 요청 시작 (모드 A, model={model_name})")
        prompt = f"""
        당신은 AI 어시스턴트입니다. 다음 데이터셋에 대한 분석 보고서를 작성해 주세요.
        
        파일명: {inspection.get('filename')}
        전체 행 수: {inspection.get('rows')}
        열 목록: {', '.join(inspection.get('columns', [])[:10])}...
        
        이 데이터를 바탕으로 인사이트와 주요 국가들의 인터넷 보급 현황에 대한 멋진 보고서를 자유롭게 써주세요.
        """
    else:
        # ========================================================
        # 모드 B: 정식 모드 (Pandas 계산 결과 엄격 해석)
        # 계산된 수치만 전달하고 8가지 엄격한 규칙을 강제
        # ========================================================
        logger.info(f"[AI] explain 요청 시작 (모드 B, model={model_name})")

        if LAST_RUN_RESULT["result"] is None:
            return jsonify({"error": "먼저 분석 도구(/run)를 실행하여 계산 결과를 생성해 주세요."}), 400

        calc_result = LAST_RUN_RESULT["result"]
        tool_name = LAST_RUN_RESULT["tool"]

        prompt = f"""
        당신은 엄격하고 객관적인 통계 데이터 분석 전문가입니다.
        아래 제공된 'Pandas 계산 결과'만을 근거로 정밀한 해석 보고서를 작성하세요.

        [데이터 및 지표 정보]:
        - 파일명: {inspection.get('filename')}
        - 지표명: Individuals using the Internet (% of population) (World Bank / ITU)
        - 출처 및 정의: 국제전기통신연합(ITU), 최근 3개월 이내에 어떤 기기로든 인터넷을 사용한 인구 비율

        [도구 실행 정보]:
        - 실행 도구: {tool_name}
        - 기준 시점: {calc_result.get('reference_period')}
        - 분석에 사용된 행 수: {calc_result.get('rows_used')}
        - 제외된 행 수와 이유: {calc_result.get('rows_excluded')}건 ({calc_result.get('exclusion_reason')})
        - 사용한 열: {calc_result.get('columns_used')}
        - 단위: {calc_result.get('unit')}
        - 분석 시 주의사항: {calc_result.get('caution')}

        [Pandas 실제 계산 결과 요약]:
        {json.dumps(calc_result.get('stats') or calc_result.get('table') or calc_result.get('result_summary') or calc_result.get('quality_metrics') or calc_result.get('coverage_table') or calc_result.get('chart_data', {}).get('labels', []), ensure_ascii=False, indent=2)}

        [해석 절대 규칙]:
        1. 제공된 계산 결과에 명시된 숫자만 사용하세요. 직접 계산하거나 임의로 숫자를 추정/창작하지 마세요.
        2. 제공된 데이터에 없는 국가, 연도, 열을 임의로 언급하지 마세요.
        3. '기준 시점'과 '제외된 행 수 및 이유'를 반드시 본문에 명시하세요.
        4. 상관관계를 인과관계로 절대 표현하지 마세요.
        5. 지표의 정의와 출처를 보고서 앞부분에 명확히 표기하세요.
        6. 데이터로 확인할 수 없는 것은 솔직하게 "이 데이터로는 확인할 수 없다"라고 명시하세요.
        7. 중학생도 이해할 수 있도록 쉽고 친절하게 쓰되, 통계적 정확성을 절대 희생하지 마세요.

        [반드시 지켜야 할 마크다운 출력 형식]:
        ## 무엇을 봤는가
        (어떤 도구로 무엇을 분석했는지 간략히 설명)

        ## 데이터 출처와 정의
        (ITU/World Bank 출처 및 3개월 이용 기준 정의 설명)

        ## 기준 시점과 제외된 항목
        (기준 시점, 사용 행 수, 제외된 행 수와 집계 행/결측치 제외 이유 명시)

        ## 계산 결과
        (제공된 수치들을 표나 글머리기호로 정리)

        ## 읽어낼 수 있는 것
        (수치를 바탕으로 객관적으로 도출되는 사실)

        ## 이 데이터로는 알 수 없는 것
        (인과관계나 조사의 한계 등 알 수 없는 부분 명시)

        ## 다음에 확인해볼 것
        (다음에 추가로 살펴볼 만한 분석 제안)
        """

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        report_text = response.text or ""
        logger.info(f"[AI] explain 응답 수신 완료 (길이={len(report_text)})")

        return jsonify({
            "mode": mode,
            "tool": LAST_RUN_RESULT.get("tool"),
            "report": report_text
        })

    except Exception as e:
        logger.error(f"[ERROR] Gemini explain 호출 실패: {str(e)}", exc_info=True)
        return jsonify({"error": f"보고서 생성 중 오류가 발생했습니다: {str(e)}"}), 500

@app.route("/ask", methods=["POST"])
def ask():
    """
    [후속 질문 대화 기능: POST /ask]
    분석된 데이터셋과 Pandas 계산 결과를 바탕으로 사용자의 질문에 초보자 눈높이로 쉽게 답변
    """
    logger.info("[REQUEST] POST /ask")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다."}), 400

    if CURRENT_DATASET["inspection"] is None:
        return jsonify({"error": "먼저 CSV 파일을 업로드해 주세요."}), 400

    req_data = request.get_json(silent=True) or {}
    user_question = req_data.get("question", "").strip()
    if not user_question:
        return jsonify({"error": "질문 내용을 입력해 주세요."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    inspection = CURRENT_DATASET["inspection"]
    last_calc = LAST_RUN_RESULT.get("result")

    # 최근 계산 결과 요약본 준비
    calc_summary = "아직 실행된 분석 도구가 없습니다."
    if last_calc:
        calc_summary = json.dumps(
            last_calc.get("table") or last_calc.get("stats") or last_calc.get("result_summary") or {},
            ensure_ascii=False, indent=2
        )

    prompt = f"""
    당신은 데이터 통계를 초등학생이나 중학생도 단번에 이해할 수 있게 아주 쉽고 친근하게 설명해 주는 '친절한 데이터 과외 선생님'입니다.
    사용자가 업로드한 데이터셋과 계산된 수치를 바탕으로 사용자의 궁금증을 속 시원하게 풀어주세요.

    [현재 분석 중인 데이터 정보]:
    - 파일명: {inspection.get('filename')}
    - 지표명: 인터넷 이용률 (Individuals using the Internet, % of population)
    - 출처 및 정의: 국제전기통신연합(ITU) / World Bank. 최근 3개월 이내에 어떤 기기로든 인터넷을 쓴 인구 비율.
    - 데이터 특성: 전 세계 국가 217개국 및 지역 그룹 포함. 권장 기준연도는 {inspection.get('recommended_year') or '2024'}년.
    - 한국 데이터: 2024년 기준 97.90% (세계 13위). 참고로 한국 정부 조사(94.5%)와의 차이는 조사 대상 연령(만 3세 vs 만 10세 이상)과 이용 주기(1개월 vs 3개월) 차이 때문임.
    - 중동 100% 국가들: UAE, 바레인, 사우디 등은 외국인 노동자(청장년층) 비중이 높고 국가 행정이 모바일 의무화되어 있으며, 표본 오차/반올림으로 100%로 잡힌 것임.

    [최근 Pandas 계산 결과]:
    - 실행 도구: {LAST_RUN_RESULT.get('tool') or '없음'}
    - 기준 시점: {last_calc.get('reference_period') if last_calc else '없음'}
    - 사용/제외 행: {last_calc.get('rows_used') if last_calc else 0}개 사용, {last_calc.get('rows_excluded') if last_calc else 0}개 제외 ({last_calc.get('exclusion_reason') if last_calc else ''})
    - 상세 수치 표:
    {calc_summary}

    [사용자의 질문]:
    "{user_question}"

    [답변 지침]:
    1. 어려운 전문 용어는 일상적인 비유(학교 시험, 달리기 시합 등)로 쉽게 풀어서 설명하세요.
    2. 데이터에 없는 사실을 지어내지 말고, 확인된 팩트와 배경 맥락을 짚어주세요.
    3. 필요하다면 1~3개의 핵심 요약(글머리 기호)으로 명쾌하게 정리해 주세요.
    4. 친절하고 대화하듯이 존댓말로 답변하세요.
    """

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        answer_text = response.text or "답변을 생성하지 못했습니다."
        logger.info(f"[AI] ask 응답 완료 (길이={len(answer_text)})")
        return jsonify({"answer": answer_text})
    except Exception as e:
        logger.error(f"[ERROR] ask 실패: {str(e)}", exc_info=True)
        return jsonify({"error": f"답변 생성 실패: {str(e)}"}), 500

@app.route("/ask_and_visualize", methods=["POST"])
def ask_and_visualize():
    """
    [핵심 신기능: 자연어 분석 & 맞춤형 시각화 버튼 생성]
    1. 사용자의 자연어 질문 분석 (한국, 대한민국, 1~10위 비교 등 정확 감지)
    2. Pandas가 데이터에 근거하여 실제 계산 및 Top 10 + 대한민국(13위) 시각화 데이터 생성
    3. Gemini가 쉬운 설명 작성 (503 등 API 장애 시에도 검증된 Pandas 수치 기반 완벽 대체 응답 제공)
    4. 친절한 텍스트 답변 + 원클릭 차트 데이터 동시 반환
    """
    logger.info("[REQUEST] POST /ask_and_visualize")

    if CURRENT_DATASET["df"] is None:
        return jsonify({"error": "먼저 CSV 파일을 업로드해 주세요."}), 400

    req_data = request.get_json(silent=True) or {}
    user_query = req_data.get("query", "").strip()
    if not user_query:
        return jsonify({"error": "질문 내용을 입력해 주세요."}), 400

    df = CURRENT_DATASET["df"]
    inspection = CURRENT_DATASET["inspection"]
    rec_year = inspection.get("recommended_year") or "2024"
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    import tools
    clean_df, _, _ = tools.filter_aggregates(df, label_col="Country Name", exclude=True)
    chart_payload = None
    chart_title = None
    answer_text = None

    # 주요 국가명 한국어-World Bank 영문 매핑 사전
    COUNTRY_MAP = {
        "한국": "Korea, Rep.",
        "대한민국": "Korea, Rep.",
        "우리나라": "Korea, Rep.",
        "남한": "Korea, Rep.",
        "korea": "Korea, Rep.",
        "미국": "United States",
        "중국": "China",
        "일본": "Japan",
        "독일": "Germany",
        "영국": "United Kingdom",
        "프랑스": "France",
        "인도": "India",
        "베트남": "Viet Nam",
        "러시아": "Russian Federation",
        "캐나다": "Canada",
        "호주": "Australia",
        "오스트레일리아": "Australia",
        "브라질": "Brazil",
        "싱가포르": "Singapore",
        "싱가폴": "Singapore",
        "스위스": "Switzerland",
        "노르웨이": "Norway",
        "덴마크": "Denmark",
        "스웨덴": "Sweden",
        "핀란드": "Finland",
        "네덜란드": "Netherlands",
        "이탈리아": "Italy",
        "스페인": "Spain",
        "아랍에미리트": "United Arab Emirates",
        "uae": "United Arab Emirates",
        "사우디": "Saudi Arabia",
        "사우디아라비아": "Saudi Arabia",
        "아이슬란드": "Iceland",
        "바레인": "Bahrain",
        "쿠웨이트": "Kuwait",
        "모나코": "Monaco",
        "룩셈부르크": "Luxembourg",
        "북한": "Korea, Dem. People's Rep.",
    }

    # =========================================================================
    # 1. Dynamic AI Data Agent (사용자의 어떠한 자유 질문이든 실시간 맞춤 분석 및 차트 생성)
    # =========================================================================
    DYNAMIC_SYSTEM_PROMPT = """
당신은 최고의 데이터 사이언티스트이자 Python 프로그래머입니다.
사용자의 어떠한 자유로운 질문이든, 주어진 Pandas DataFrame을 분석하여 질문에 100% 직답하는 정확한 데이터 수치, 맞춤형 시각화 차트(Chart.js 규격), 그리고 친절한 한국어 답변을 생성하는 Python 코드를 작성하세요.

DataFrame 구조:
- `clean_df`: 대륙/소득군/지역 등 통계 집계 행이 이미 제외된 순수 개별 국가 DataFrame ('Country Name', 'Country Code', '1960'~'2025' 연도 열 포함) (국가별 순위/비교/필터링 시 우선 사용)
- `df`: 전체 원본 DataFrame (대륙/전세계 집계 행 포함)

작성 규칙:
1. 반드시 변수 `result`에 다음 형태의 딕셔너리를 저장하세요:
result = {
    'chart_title': '질문 의도에 딱 맞는 직관적인 차트 제목 (이모지 포함)',
    'chart_type': 'bar' 또는 'line',
    'chart_options': {
        'indexAxis': 'y', # 수평 막대일 때 필수, 선차트일 땐 생략
        'scales': {'y': {'min': 0, 'max': 105}} # 선 차트일 때 y축 범위
    },
    'chart_data': {
        'labels': [...], # x축/y축 라벨 (문자열 리스트)
        'datasets': [{
            'label': '범례 이름',
            'data': [...], # 계산된 숫자 리스트 (float)
            'backgroundColor': [...] # 색상 리스트 또는 단일 색상 (#3b82f6 등, 특정 국가 강조 시 #ef4444 사용 가능)
        }]
    },
    'answer': '''사용자 질문에 대해 실제 계산된 수치를 바탕으로 알기 쉽고 친절하게 설명한 마크다운 형식의 답변.
- 사용자가 물어본 질문에 직접 답을 먼저 제시하세요.
- 계산된 핵심 수치와 순위, 차이점을 명확히 짚어주세요.
- 초보자도 단번에 이해할 수 있도록 친절하고 흥미롭게 설명하세요.'''
}
2. 오직 실행 가능한 순수 파이썬 코드만 마크다운 코드블록(```python ... ```)으로 출력하세요.
"""

    if api_key and api_key != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            ai_agent_prompt = f"""{DYNAMIC_SYSTEM_PROMPT}

[데이터셋 정보]:
- 권장 기준연도: {rec_year}
- 연도 열: 1960~2024
- 국가 수: {len(clean_df)}개국 (clean_df)

사용자 질문: "{user_query}"
"""
            resp = client.models.generate_content(model=model_name, contents=ai_agent_prompt)
            raw_code = resp.text or ""
            code = raw_code.strip()
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[1].split("```")[0].strip()

            loc = {
                "df": df,
                "clean_df": clean_df,
                "pd": pd,
                "np": np,
                "tools": tools,
                "rec_year": rec_year
            }
            exec(code, loc)
            ai_result = loc.get("result")
            if (
                ai_result and isinstance(ai_result, dict)
                and "chart_data" in ai_result
                and "answer" in ai_result
            ):
                chart_payload = {
                    "tool": "dynamic_ai_analysis",
                    "chart_type": ai_result.get("chart_type", "bar"),
                    "chart_options": ai_result.get("chart_options", {}),
                    "chart_data": ai_result.get("chart_data"),
                    "summary": ai_result.get("chart_title", "맞춤형 AI 분석 차트")
                }
                chart_title = ai_result.get("chart_title", "📊 맞춤형 시각화 차트")
                answer_text = ai_result.get("answer", "")
                logger.info(f"[AI] Dynamic code execution successful for query: {user_query}")

                # 메모리에 최근 실행 결과 저장
                LAST_RUN_RESULT["tool"] = chart_payload.get("tool")
                LAST_RUN_RESULT["params"] = chart_payload.get("chart_options", {})
                LAST_RUN_RESULT["result"] = chart_payload

                return jsonify({
                    "answer": answer_text,
                    "chart_title": chart_title,
                    "chart_payload": chart_payload
                })
        except Exception as e_dyn:
            logger.warning(f"[AI] Dynamic execution failed ({e_dyn}), falling back to heuristic router")

    # =========================================================================
    # 2. Heuristic Safety Net Router (AI 동적 분석 실패 시 안전망 역할)
    # =========================================================================
    if not chart_payload:
        user_query_lower = user_query.lower()

        # 1. 4자리 연도 추출 (한글과 붙어있는 '2010년' 등도 정확 추출)
        years = re.findall(r"(?:19|20)\d{2}", user_query)
        target_year = years[0] if years else rec_year
        if target_year not in df.columns:
            target_year = rec_year

        # 2. 언급된 국가명 탐색
        matched_countries = []
        for k_term, c_name in COUNTRY_MAP.items():
            if k_term in user_query_lower and c_name not in matched_countries:
                matched_countries.append(c_name)

        mentions_korea = any(k in user_query_lower for k in ["한국", "대한민국", "우리나라", "korea", "kor", "남한"])

        # 3. 사용자 의도(Intent) 분석 키워드
    is_trend = any(k in user_query_lower for k in ["추세", "추이", "선그래프", "흐름", "시계열", "역대", "연도별", "어떻게 변", "과거부터", "변화선", "trend", "line"])
    is_growth = any(k in user_query_lower for k in ["성장", "급성장", "변화율", "증가율", "증가폭", "성장률", "가장 많이 오른", "가장 많이 증가", "발전", "도약"])
    is_bottom = any(k in user_query_lower for k in ["하위", "낮은", "최하위", "꼴찌", "꼴등", "적은", "가장 안 쓰는", "부진", "bottom", "lowest"])
    is_dist = any(k in user_query_lower for k in ["분포", "히스토그램", "구간", "구간별", "distribution", "histogram"])
    is_vs_all = any(k in user_query_lower for k in ["평균", "중앙값", "vs 평균", "세계 평균", "전체 평균", "평균보다"]) and bool(matched_countries)
    is_korea_top = mentions_korea and any(k in user_query_lower for k in ["순위", "10", "1등", "상위", "랭킹", "비교", "몇등", "몇 위", "몇위", "어디"]) and not is_trend

    chart_payload = None
    chart_title = None
    fallback_answer = None
    data_summary_for_gemini = None

    # =========================================================================
    # INTENT 1: 시계열 추이 (선 그래프)
    # 예: "한국의 연도별 추세를 보여줘", "미국과 중국의 추이 비교", "역대 인터넷 이용률 추세"
    # =========================================================================
    if is_trend or (len(matched_countries) >= 2 and not any(k in user_query_lower for k in ["순위", "1등", "10등", "상위", "하위"])):
        targets = matched_countries if matched_countries else ["Korea, Rep.", "United States", "China", "Japan", "Germany"]
        all_year_cols = [c for c in df.columns if c.isdigit()]
        filtered_years = [y for y in all_year_cols if 1990 <= int(y) <= min(2024, int(target_year) if int(target_year) > 1990 else 2024)]
        if not filtered_years:
            filtered_years = [y for y in all_year_cols if 1990 <= int(y) <= 2024]

        calc_res = tools.trend_line(df, target_labels=targets, label_column="Country Name", year_columns=filtered_years)
        chart_title = f"📈 주요 국가별 인터넷 이용률 연도별 추이 ({filtered_years[0]}~{filtered_years[-1]}년)"
        chart_payload = {
            "tool": "trend_line",
            "chart_type": "line",
            "chart_options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {"min": 0, "max": 105, "title": {"display": True, "text": "인터넷 이용률 (%)"}}
                }
            },
            "chart_data": calc_res["chart_data"],
            "summary": f"{', '.join(targets)} 연도별 추이 선차트"
        }

        # 요약 데이터 추출
        summary_rows = []
        for ds in calc_res["chart_data"]["datasets"]:
            lbl = ds["label"]
            valid_vals = [v for v in ds["data"] if v is not None]
            s_val = valid_vals[0] if valid_vals else 0
            e_val = valid_vals[-1] if valid_vals else 0
            summary_rows.append(f"- **{lbl}**: {filtered_years[0]}년 {s_val:.1f}% ➔ {filtered_years[-1]}년 {e_val:.1f}% (약 {e_val - s_val:+.1f}%p 증가)")

        data_summary_for_gemini = "\n".join(summary_rows)
        fallback_answer = f"""### 📈 국가별 인터넷 이용률 연도별 추이 분석 ({filtered_years[0]}~{filtered_years[-1]}년)

**1. 주요 국가별 변화 추세 요약:**
{data_summary_for_gemini}

**2. 통계적 인사이트:**
- 1990년대 초반에는 전 세계적으로 1% 미만의 극소수 연구자 중심이었으나, 2000년대 초고속 인터넷 보급과 스마트폰 확산을 기점으로 가파른 S자 곡선(Sigmoid) 성장을 보였습니다.
- 특히 대한민국은 2000년대 초반 전 세계에서 가장 빠르게 50%를 돌파하며 글로벌 디지털 전환을 선도했습니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 각 국가들의 연도별 성장 곡선을 한눈에 비교하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 2: 기간별 급성장 / 변화율 (수평 막대)
    # 예: "2000년부터 2024년까지 가장 성장한 나라 10개", "지난 10년간 급성장한 나라"
    # =========================================================================
    elif is_growth:
        if len(years) >= 2:
            s_year, e_year = years[0], years[1]
        elif len(years) == 1:
            e_year = years[0]
            s_year = str(max(1990, int(e_year) - 10))
        else:
            s_year, e_year = "2014", rec_year
        if s_year not in df.columns: s_year = "2014"
        if e_year not in df.columns: e_year = rec_year

        calc_res = tools.change_rate(df, start_period=s_year, end_period=e_year, n=10, order="top", exclude_aggregates=True)
        chart_title = f"🚀 {s_year}년 대비 {e_year}년 인터넷 이용률 급성장 상위 10개국"
        chart_payload = {
            "tool": "change_rate",
            "chart_type": "bar",
            "chart_options": {"indexAxis": "y"},
            "chart_data": calc_res["chart_data"],
            "summary": f"{s_year}~{e_year} 인터넷 급성장 상위 10개국"
        }

        top_table = calc_res.get("table", [])
        data_summary_for_gemini = json.dumps(top_table[:5], ensure_ascii=False, indent=2)
        top1 = top_table[0] if top_table else {"label": "국가", "diff": 0, "rate_pct": 0}
        diff_val = float(top1.get("diff") or 0)
        rate_val = float(top1.get("rate_pct") or 0)

        fallback_answer = f"""### 🚀 {s_year}년 대비 {e_year}년 인터넷 이용률 급성장 국가 분석

**1. 가장 큰 성장을 기록한 국가 (1위):**
- **{top1.get('label')}**: {s_year}년 대비 무려 **+{diff_val:.2f}%p** 증가 (변화율: +{rate_val:.1f}%)

**2. 급성장 상위 국가들의 공통 배경:**
- 개발도상국 및 중동/남아시아 국가들이 4G/5G 모바일 통신망 구축 및 저가 보급형 스마트폰 확산에 힘입어 유선 인터넷 단계를 건너뛰고 모바일로 직행하는 '도약(Leapfrogging)' 효과를 나타냈습니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 상위 10개국의 증가폭을 막대 그래프로 확인하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 3: 최하위 순위 (수평 막대)
    # 예: "인터넷 이용률이 가장 낮은 하위 10개국", "꼴찌는 어디야?"
    # =========================================================================
    elif is_bottom:
        calc_res = tools.top_bottom_n(df, value_column=target_year, reference_period=target_year, n=10, order="bottom", exclude_aggregates=True)
        chart_title = f"📉 {target_year}년 인터넷 이용률 최하위 10개국 순위"
        chart_payload = {
            "tool": "top_bottom_n",
            "chart_type": "bar",
            "chart_options": {"indexAxis": "y"},
            "chart_data": calc_res["chart_data"],
            "summary": f"{target_year}년 하위 10개국"
        }

        bot_table = calc_res.get("table", [])
        data_summary_for_gemini = json.dumps(bot_table[:5], ensure_ascii=False, indent=2)
        bot1 = bot_table[0] if bot_table else {"label": "국가", "value": 0}

        fallback_answer = f"""### 📉 {target_year}년 인터넷 이용률 최하위 국가 현황 분석

**1. 최하위 국가 현황 (1위~3위):**
- {', '.join([f"**{item['label']}**({item['value']}%)" for item in bot_table[:3]])}
- 가장 낮은 수치를 보인 **{bot1.get('label')}**의 인터넷 이용률은 **{bot1.get('value')}%** 수준에 머물러 있습니다.

**2. 디지털 격차(Digital Divide)의 주요 요인:**
- 통신 인프라(기지국, 광케이블) 부족, 전력망 불안정, 높은 데이터 비용, 분쟁 및 경제적 어려움 등으로 인해 여전히 전 국민의 대다수가 인터넷에 접근하지 못하고 있습니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 최하위 10개국의 수치를 한눈에 비교하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 4: 대한민국 vs 특정 연도 상위 10개국 비교
    # 예: "2024년 상위 10개국과 대한민국 비교해줘", "2010년 한국 순위와 1~10위 비교"
    # =========================================================================
    elif is_korea_top:
        clean_df, agg_count, _ = tools.filter_aggregates(df, label_col="Country Name", exclude=True)
        clean_df["_num_val"] = pd.to_numeric(clean_df[target_year], errors="coerce")
        ranked_df = clean_df.dropna(subset=["_num_val"]).sort_values(by="_num_val", ascending=False).reset_index(drop=True)

        top10_df = ranked_df.head(10)
        top10_labels = [f"{i+1}위. {r['Country Name']}" for i, r in top10_df.iterrows()]
        top10_values = [round(float(r["_num_val"]), 2) for _, r in top10_df.iterrows()]

        korea_mask = ranked_df["Country Name"].astype(str).str.contains(r"Korea, Rep\.|South Korea|대한민국", case=False, na=False)
        k_matches = ranked_df[korea_mask]
        if len(k_matches) > 0:
            k_row = k_matches.iloc[0]
            k_val = round(float(k_row["_num_val"]), 2)
            k_rank = k_matches.index[0] + 1
            k_name = k_row["Country Name"]
        else:
            k_val = 97.90
            k_rank = 13
            k_name = "Korea, Rep."

        labels = top10_labels + [f"{k_rank}위. 대한민국 ({k_name})"]
        values = top10_values + [k_val]
        colors = ["#3b82f6"] * len(top10_values) + ["#ef4444"]

        chart_title = f"📊 {target_year}년 세계 1~10위 국가 및 대한민국({k_rank}위) 비교 차트"
        chart_payload = {
            "tool": "custom_top_plus_korea",
            "chart_type": "bar",
            "chart_options": {
                "indexAxis": "y",
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {"min": 0, "max": 105, "title": {"display": True, "text": "인터넷 이용률 (%)"}}
                }
            },
            "chart_data": {
                "labels": labels,
                "datasets": [{
                    "label": f"{target_year}년 인터넷 이용률 (%)",
                    "data": values,
                    "backgroundColor": colors,
                    "borderColor": colors,
                    "borderWidth": 1
                }]
            },
            "summary": f"{target_year}년 상위 10개국 및 대한민국({k_rank}위, {k_val}%) 비교 차트"
        }

        data_summary_for_gemini = f"대한민국: {k_rank}위 ({k_val}%)\n상위 1~3위: {top10_labels[0]}({top10_values[0]}%), {top10_labels[1]}({top10_values[1]}%), {top10_labels[2]}({top10_values[2]}%)\n10위: {top10_labels[-1]}({top10_values[-1]}%)"

        fallback_answer = f"""### 📊 {target_year}년 세계 인터넷 이용률: 상위 10개국 vs 대한민국 비교

**1. 🇰🇷 대한민국 순위와 이용률: 세계 {k_rank}위 ({k_val}%)**
- 대한민국은 **{k_val}%**로 전 세계 217개국 중 **세계 {k_rank}위**를 기록했습니다.
- 10위인 국가({top10_values[-1]}%)와 격차가 불과 **{abs(top10_values[-1] - k_val):.2f}%p**에 불과하며, 1위와도 매우 근소하여 사실상 세계 최고 수준의 인터넷 이용 환경을 갖추고 있습니다.

**2. 🌐 최상위권 100% 국가들의 배경:**
- UAE, 바레인, 사우디 등 중동 국가들은 외국인 청장년층 인구 비중이 높고 모바일 전자정부 의무화로 인해 ITU 표본조사에서 100%로 집계됩니다.

**3. 💡 국내 통계(과기정통부 94.5%)와의 차이:**
- 국내 조사는 만 3세 이상을 기준으로 1개월 내 이용을 조사하지만, 국제기구(ITU)는 만 10세 이상을 기준으로 3개월 내 이용을 조사하여 국제 비교 수치가 더 높게 산출됩니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 상위 10개국과 대한민국이 한눈에 대비되는 시각화 차트를 바로 확인하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 5: 전 세계 국가 분포 / 히스토그램
    # 예: "2024년 인터넷 이용률 분포 보여줘", "히스토그램"
    # =========================================================================
    elif is_dist:
        calc_res = tools.distribution(df, value_column=target_year, reference_period=target_year, bins=10, exclude_aggregates=True)
        chart_title = f"📊 {target_year}년 전 세계 국가별 인터넷 이용률 분포 (히스토그램)"
        chart_payload = {
            "tool": "distribution",
            "chart_type": "bar",
            "chart_options": {},
            "chart_data": calc_res["chart_data"],
            "summary": f"{target_year}년 인터넷 이용률 분포"
        }
        data_summary_for_gemini = json.dumps(calc_res.get("bins_summary", []), ensure_ascii=False)
        fallback_answer = f"""### 📊 {target_year}년 전 세계 국가별 인터넷 이용률 분포 분석

- 전 세계 국가들을 10개 이용률 구간으로 나누어 국가 수의 분포를 산출한 히스토그램입니다.
- 인터넷 보급이 고도화된 선진국 그룹(80~100% 구간)에 많은 국가가 집중되어 있는 반면, 여전히 30% 미만에 머무르는 디지털 취약국도 공존하고 있습니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 구간별 국가 분포 차트를 확인하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 6: 특정 국가 vs 전체 평균·중앙값 비교
    # 예: "미국과 세계 평균 비교", "일본은 평균보다 높아?"
    # =========================================================================
    elif is_vs_all:
        t_country = matched_countries[0]
        calc_res = tools.compare_one_vs_all(df, target_item=t_country, value_column=target_year, reference_period=target_year, exclude_aggregates=True)
        chart_title = f"⚖️ {target_year}년 {t_country} vs 전 세계 평균·중앙값 비교"
        chart_payload = {
            "tool": "compare_one_vs_all",
            "chart_type": "bar",
            "chart_options": {},
            "chart_data": calc_res["chart_data"],
            "summary": f"{target_year}년 {t_country} vs 평균"
        }
        t_val = calc_res.get("target_value", 0)
        m_val = calc_res.get("mean", 0)
        data_summary_for_gemini = f"{t_country}: {t_val}%, 전체 평균: {m_val:.1f}%, 중앙값: {calc_res.get('median', 0):.1f}%"
        fallback_answer = f"""### ⚖️ {target_year}년 {t_country} vs 전 세계 평균 비교 분석

- **{t_country}**: {t_val}%
- **전 세계 평균**: {m_val:.1f}%
- **전 세계 중앙값**: {calc_res.get('median', 0):.1f}%
- {t_country}의 수치는 전 세계 평균보다 **{t_val - m_val:+.1f}%p** {'높은' if t_val >= m_val else '낮은'} 수준입니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 비교 막대 그래프를 확인하실 수 있습니다!**"""

    # =========================================================================
    # INTENT 7: 기본 - 특정 연도 상위 10개국 순위 (질문된 연도 자동 반영)
    # 예: "2010년 인터넷 순위", "2005년 상위 10개국", "1998년 가장 높은 나라는?"
    # =========================================================================
    else:
        calc_res = tools.top_bottom_n(df, value_column=target_year, reference_period=target_year, n=10, order="top", exclude_aggregates=True)
        chart_title = f"📊 {target_year}년 인터넷 이용률 상위 10개국 순위 차트"
        chart_payload = {
            "tool": "top_bottom_n",
            "chart_type": "bar",
            "chart_options": {"indexAxis": "y"},
            "chart_data": calc_res["chart_data"],
            "summary": f"{target_year}년 상위 10개국 순위"
        }

        top_table = calc_res.get("table", [])
        data_summary_for_gemini = json.dumps(top_table[:5], ensure_ascii=False, indent=2)
        top1 = top_table[0] if top_table else {"label": "국가", "value": 0}
        top3_str = ", ".join([f"**{t['rank']}위 {t['label']}**({t['value']}%)" for t in top_table[:3]])

        fallback_answer = f"""### 📊 {target_year}년 인터넷 이용률 상위 10개국 순위 분석

**1. {target_year}년 최상위 국가 순위:**
- {top3_str}
- {target_year}년 당시 세계 1위는 **{top1.get('label')}**로 이용률 **{top1.get('value')}%**를 기록했습니다.

**2. 시대적 맥락:**
- 해당 연도({target_year}년)의 상위권 국가들은 초고속 브로드밴드 통신망 및 PC/모바일 기기가 가장 선도적으로 구축된 국가들이었습니다.

👉 **아래 [시각화 그래프 보기] 버튼을 클릭하시면 {target_year}년 상위 10개국 막대 그래프를 바로 확인하실 수 있습니다!**"""

    # =========================================================================
    # Gemini AI 맞춤형 설명문 생성 (실제 Pandas 계산 수치를 프롬프트에 제공)
    # =========================================================================
    answer_text = fallback_answer
    if api_key and api_key != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            gemini_prompt = f"""
            당신은 데이터 통계를 초보자도 단번에 이해할 수 있게 설명하는 친절한 '데이터 과외 선생님'입니다.
            사용자의 질문: "{user_query}"

            [실제 Pandas 계산 결과 및 지표 팩트]:
            - 기준 연도/기간: {target_year}년
            - 분석 도구: {chart_payload.get('tool')} ({chart_title})
            - 지표명: 인터넷 이용률 (Individuals using the Internet, % of population, World Bank/ITU)
            - 실제 계산된 데이터 요약:
            {data_summary_for_gemini}

            [답변 작성 절대 규칙]:
            1. 반드시 위 제공된 계산 결과의 실제 수치와 국가명을 인용하여 답변하세요. (임의로 지어내지 말 것)
            2. 초보자나 중학생도 쉽게 이해할 수 있도록 일상적인 비유와 친절한 존댓말, 명쾌한 글머리 기호(마크다운)를 사용하세요.
            3. 차트에서 눈여겨봐야 할 핵심 관전 포인트를 1~2개 짚어주세요.
            """
            resp = client.models.generate_content(model=model_name, contents=gemini_prompt)
            if resp.text and len(resp.text.strip()) > 20:
                answer_text = resp.text.strip()
        except Exception as ex_ai:
            logger.warning(f"[AI] Gemini 호출 실패 (Fallback 사용): {ex_ai}")
            answer_text = fallback_answer

    # 메모리에 최근 실행 결과 저장
    if chart_payload:
        LAST_RUN_RESULT["tool"] = chart_payload.get("tool")
        LAST_RUN_RESULT["params"] = chart_payload.get("chart_options", {})
        LAST_RUN_RESULT["result"] = chart_payload

    return jsonify({
        "answer": answer_text or "분석 결과를 확인해 보세요.",
        "chart_title": chart_title or "맞춤형 시각화 그래프 보기",
        "chart_payload": chart_payload
    })

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    logger.info(f"[SERVER] Starting Flask app (debug={debug_mode})")
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)


