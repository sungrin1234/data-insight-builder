import logging
import math
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger("DataInsightBuilder.tools")

def safe_value(val: Any) -> Any:
    """JSON 전송을 위해 NaN, Inf, -Inf 값을 None(null)으로 변환합니다."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    return str(val)

def find_year_columns(df: pd.DataFrame) -> List[str]:
    """YYYY(4자리 숫자) 형태의 연도 열 목록을 찾아 정렬하여 반환합니다."""
    years = [str(c).strip() for c in df.columns if re.match(r"^(19\d\d|20\d\d)$", str(c).strip())]
    return sorted(years, key=lambda x: int(x))

def get_aggregate_keywords() -> List[str]:
    """집계/지역/소득군 행을 식별하는 기본 키워드 목록"""
    return [
        "world", "oecd members", "euro area", "european union",
        "high income", "low income", "middle income", "upper middle income",
        "lower middle income", "arab world", "latin america", "caribbean",
        "east asia", "south asia", "sub-saharan africa", "income", "area", "total",
        "small states", "ida & ibrd", "fragile and conflict"
    ]

def filter_aggregates(df: pd.DataFrame, label_col: str, exclude: bool = True) -> (pd.DataFrame, int, List[str]):
    """
    집계 행 후보를 제외하거나 필터링합니다.
    반환값: (필터링된 df, 제외된 행 수, 제외된 항목 이름 목록)
    """
    if not exclude or label_col not in df.columns:
        return df.copy(), 0, []

    keywords = get_aggregate_keywords()
    mask = df[label_col].astype(str).str.lower().apply(
        lambda x: any(kw in x for kw in keywords)
    )
    
    excluded_names = df[label_col][mask].dropna().tolist()
    filtered_df = df[~mask].copy()
    excluded_count = int(mask.sum())
    
    return filtered_df, excluded_count, excluded_names


# ==========================================
# 도구 1: reshape_wide_to_long (연도 열을 행으로 접기)
# ==========================================
def reshape_wide_to_long(
    df: pd.DataFrame,
    id_vars: Optional[List[str]] = None,
    year_vars: Optional[List[str]] = None,
    var_name: str = "Year",
    value_name: str = "Value"
) -> Dict[str, Any]:
    """
    가로로 펼쳐진 연도 열들을 [식별자, 연도, 값] 형태의 롱 포맷(Long format)으로 변환합니다.
    """
    original_rows = len(df)
    year_cols = year_vars or find_year_columns(df)
    
    if not year_cols:
        raise ValueError("변환할 연도 열(예: 1960~2025)을 찾을 수 없습니다.")

    # id_vars가 지정되지 않은 경우, 연도 열을 제외한 앞쪽 열들을 id_vars로 지정
    if not id_vars:
        id_vars = [c for c in df.columns if c not in year_cols and not c.startswith("Unnamed")]
        if not id_vars:
            id_vars = [df.columns[0]]

    # Wide to Long 변환 (pd.melt)
    melted = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=year_cols,
        var_name=var_name,
        value_name=value_name
    )

    # 결측치 행 제외
    valid_melted = melted.dropna(subset=[value_name]).copy()
    excluded_count = len(melted) - len(valid_melted)

    # 미리보기 10행 생성
    preview = []
    for _, r in valid_melted.head(10).iterrows():
        preview.append({col: safe_value(r[col]) for col in valid_melted.columns})

    return {
        "tool": "reshape_wide_to_long",
        "reference_period": f"{year_cols[0]}~{year_cols[-1]}" if year_cols else "전체",
        "rows_used": len(valid_melted),
        "rows_excluded": excluded_count,
        "exclusion_reason": f"해당 연도에 값이 없는 결측 행({excluded_count}건) 제외",
        "columns_used": id_vars + [var_name, value_name],
        "unit": "행(Row)",
        "caution": "원본 와이드 표의 결측 셀은 변환 후 행 목록에서 제외되었습니다.",
        "result_summary": {
            "original_rows": original_rows,
            "transformed_rows": len(valid_melted),
            "id_columns": id_vars,
            "years_count": len(year_cols)
        },
        "preview": preview
    }


# ==========================================
# 도구 2: quality_report (결측·중복·타입·이상한 열 이름)
# ==========================================
def quality_report(df: pd.DataFrame) -> Dict[str, Any]:
    """
    데이터셋의 전반적인 데이터 품질(결측치, 중복, 열 이름 이상, 비어 있는 열)을 정밀 진단합니다.
    """
    total_rows = len(df)
    total_cols = len(df.columns)
    
    duplicate_rows = int(df.duplicated().sum())
    
    columns_quality = []
    unnamed_cols = []
    empty_cols = []

    for col in df.columns:
        col_str = str(col).strip()
        null_cnt = int(df[col].isna().sum())
        null_pct = round((null_cnt / total_rows * 100), 2) if total_rows > 0 else 0
        dtype_str = str(df[col].dtype)
        
        is_unnamed = bool(re.match(r"^Unnamed:\s*\d+$", col_str, re.IGNORECASE)) or col_str == ""
        is_all_null = (null_cnt == total_rows)

        if is_unnamed:
            unnamed_cols.append(col_str)
        if is_all_null:
            empty_cols.append(col_str)

        columns_quality.append({
            "column": col_str,
            "dtype": dtype_str,
            "null_count": null_cnt,
            "null_ratio_pct": null_pct,
            "is_unnamed": is_unnamed,
            "is_all_null": is_all_null
        })

    return {
        "tool": "quality_report",
        "reference_period": "전체 데이터셋",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": "품질 진단을 위해 전체 행을 검사함",
        "columns_used": [str(c) for c in df.columns],
        "unit": "건 / %",
        "caution": "이름이 없는(Unnamed) 열이나 전체가 빈 열은 후속 분석 전 정리해야 합니다.",
        "quality_metrics": {
            "total_rows": total_rows,
            "total_columns": total_cols,
            "duplicate_rows": duplicate_rows,
            "unnamed_columns_count": len(unnamed_cols),
            "unnamed_columns": unnamed_cols,
            "empty_columns_count": len(empty_cols),
            "empty_columns": empty_cols,
            "column_details": columns_quality
        }
    }


# ==========================================
# 도구 3: year_coverage (연도별 값 개수와 권장 기준연도)
# ==========================================
def year_coverage(df: pd.DataFrame) -> Dict[str, Any]:
    """
    연도별로 값이 존재하는 데이터 개수와 충실도 비율을 계산하고 최적의 권장 기준연도를 제안합니다.
    """
    year_cols = find_year_columns(df)
    if not year_cols:
        raise ValueError("분석할 연도 열(YYYY)이 데이터에 존재하지 않습니다.")

    total_rows = len(df)
    coverage_table = []
    best_count = -1
    recommended_year = year_cols[-1]

    for y in year_cols:
        filled = int(df[y].notna().sum())
        fill_pct = round((filled / total_rows * 100), 2) if total_rows > 0 else 0
        coverage_table.append({
            "year": y,
            "filled_count": filled,
            "total_rows": total_rows,
            "fill_pct": fill_pct
        })
        
        # 유효 개수가 충분하고(전체 50% 이상), 최근 연도 우선 선택
        if filled >= (total_rows * 0.5) and filled >= best_count * 0.9:
            best_count = max(best_count, filled)
            recommended_year = y

    latest_year = year_cols[-1]
    reason = (
        f"최근 연도({latest_year})의 결측치가 많은 경우 데이터가 안정적으로 채워진 {recommended_year}년을 사용하는 것이 바람직합니다."
        if latest_year != recommended_year else "가장 최신 연도에 데이터가 충분히 수집되어 있습니다."
    )

    return {
        "tool": "year_coverage",
        "reference_period": f"{year_cols[0]}~{year_cols[-1]}",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": "전체 행의 연도별 결측 현황을 계산함",
        "columns_used": year_cols,
        "unit": "개국 / 건",
        "caution": reason,
        "recommended_year": recommended_year,
        "coverage_table": coverage_table
    }


# ==========================================
# 도구 4: detect_aggregates (집계 행 후보 탐지)
# ==========================================
def detect_aggregates(
    df: pd.DataFrame,
    label_column: Optional[str] = None
) -> Dict[str, Any]:
    """
    개별 국가가 아닌 대륙, 소득 그룹, 전 세계 평균 등 통계 집계 행 후보를 탐지합니다.
    """
    # 라벨 열 자동 탐색
    if not label_column:
        candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = candidates[0] if candidates else df.columns[0]

    filtered_df, excluded_count, excluded_names = filter_aggregates(df, label_col=label_column, exclude=True)
    
    return {
        "tool": "detect_aggregates",
        "reference_period": "전체",
        "rows_used": len(filtered_df),
        "rows_excluded": excluded_count,
        "exclusion_reason": f"국가 간 비교 시 중복/왜곡을 유발하는 집계/지역/소득군 행({excluded_count}건) 감지",
        "columns_used": [label_column],
        "unit": "행(Row)",
        "caution": "순위 분석이나 상관관계 분석 시에는 반드시 집계 행을 제외해야 올바른 결과가 도출됩니다.",
        "detected_aggregates_count": excluded_count,
        "detected_aggregates": excluded_names[:30],
        "clean_rows_count": len(filtered_df)
    }

# ==========================================
# 도구 5: describe_numeric (개수·평균·중앙값·최소·최대·표준편차)
# ==========================================
def describe_numeric(
    df: pd.DataFrame,
    value_column: str,
    label_column: Optional[str] = None,
    reference_period: Optional[str] = None,
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    특정 기준 시점(또는 숫자 열)의 기초 통계량(개수, 평균, 중앙값, 최소, 최대, 표준편차)을 계산합니다.
    """
    if not value_column or value_column not in df.columns:
        raise ValueError(f"유효한 숫자 열({value_column})을 선택해 주세요.")

    # 라벨 열 자동 감지
    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()
    
    # 집계 행 제외
    agg_excluded_count = 0
    if exclude_aggregates:
        work_df, agg_excluded_count, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    # 숫자 변환 및 결측치 제외
    numeric_series = pd.to_numeric(work_df[value_column], errors="coerce").dropna()
    missing_excluded_count = len(work_df) - len(numeric_series)
    total_excluded = original_rows - len(numeric_series)

    if len(numeric_series) == 0:
        raise ValueError(f"선택한 열({value_column})에 유효한 숫자 데이터가 없습니다.")

    ref_period = reference_period or value_column

    return {
        "tool": "describe_numeric",
        "reference_period": str(ref_period),
        "rows_used": len(numeric_series),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행({agg_excluded_count}건) 및 해당 시점 결측치({missing_excluded_count}건) 제외",
        "columns_used": [label_column, value_column],
        "unit": "수치 단위 (예: % 또는 건수)",
        "caution": "왜도(비대칭도)가 큰 데이터에서는 평균보다 중앙값이 더 대표성을 가집니다.",
        "stats": {
            "count": int(numeric_series.count()),
            "mean": round(float(numeric_series.mean()), 2),
            "median": round(float(numeric_series.median()), 2),
            "std": round(float(numeric_series.std()), 2) if len(numeric_series) > 1 else 0.0,
            "min": round(float(numeric_series.min()), 2),
            "max": round(float(numeric_series.max()), 2),
            "q25": round(float(numeric_series.quantile(0.25)), 2),
            "q75": round(float(numeric_series.quantile(0.75)), 2)
        }
    }


# ==========================================
# 도구 6: trend_line (선택 항목들의 연도별 추이 - 선 차트)
# ==========================================
def trend_line(
    df: pd.DataFrame,
    target_labels: List[str],
    label_column: Optional[str] = None,
    year_columns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    선택한 국가/항목들의 연도별 변화 추이를 추출하여 Chart.js 호환 선 차트(Line Chart) 데이터를 생성합니다.
    """
    if not target_labels:
        raise ValueError("추이를 조회할 항목(국가 등)을 최소 1개 이상 지정해야 합니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    years = year_columns or find_year_columns(df)
    if not years:
        raise ValueError("시계열 추이를 분석할 연도 열을 찾을 수 없습니다.")

    # 대상 항목 필터링
    matched_df = df[df[label_column].astype(str).str.strip().isin([str(t).strip() for t in target_labels])].copy()
    rows_used = len(matched_df)
    rows_excluded = len(df) - rows_used

    # Chart.js 데이터셋 포맷 구성
    datasets = []
    # 구분되는 색상 팔레트
    colors = [
        "#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea",
        "#0891b2", "#ea580c", "#4f46e5", "#059669", "#be123c"
    ]

    for idx, (_, row) in enumerate(matched_df.iterrows()):
        lbl = str(row[label_column])
        values = []
        for y in years:
            val = row.get(y)
            try:
                val_num = float(val) if pd.notna(val) else None
                values.append(safe_value(val_num))
            except (ValueError, TypeError):
                values.append(None)
                
        color = colors[idx % len(colors)]
        datasets.append({
            "label": lbl,
            "data": values,
            "borderColor": color,
            "backgroundColor": color,
            "fill": False,
            "tension": 0.1
        })

    return {
        "tool": "trend_line",
        "reference_period": f"{years[0]}~{years[-1]}",
        "rows_used": rows_used,
        "rows_excluded": rows_excluded,
        "exclusion_reason": f"선택된 {rows_used}개 항목 외 나머지 행 제외",
        "columns_used": [label_column] + years,
        "unit": "수치 (연도별)",
        "caution": "연도별 결측치가 존재하는 경우 선 차트에서 해당 구간이 끊어져 보일 수 있습니다.",
        "chart_type": "line",
        "chart_data": {
            "labels": years,
            "datasets": datasets
        }
    }


# ==========================================
# 도구 7: top_bottom_n (기준연도 기준 상위·하위 N - 수평 막대)
# ==========================================
def top_bottom_n(
    df: pd.DataFrame,
    value_column: str,
    reference_period: str,
    label_column: Optional[str] = None,
    n: int = 10,
    order: str = "top", # "top", "bottom", "both"
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 7: 기준 시점 필수]
    특정 기준 연도의 수치를 기준으로 상위/하위 N개 항목을 추출하여 수평 막대 차트 데이터를 생성합니다.
    """
    if not reference_period:
        raise ValueError("[도구 7 오류] 기준 시점(reference_period)은 필수 입력 항목입니다.")

    target_col = value_column or reference_period
    if target_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열({target_col})이 존재하지 않습니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()

    # 집계 행 제외
    agg_excluded = 0
    if exclude_aggregates:
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    # 숫자 변환 및 결측치 제외
    work_df["_numeric_val"] = pd.to_numeric(work_df[target_col], errors="coerce")
    clean_df = work_df.dropna(subset=["_numeric_val"]).copy()
    missing_excluded = len(work_df) - len(clean_df)
    total_excluded = original_rows - len(clean_df)

    if len(clean_df) == 0:
        raise ValueError(f"기준 시점({target_col})에 값이 있는 유효 데이터가 없습니다.")

    # 정렬
    clean_df = clean_df.sort_values(by="_numeric_val", ascending=False)

    if order == "top":
        selected_df = clean_df.head(n)
    elif order == "bottom":
        selected_df = clean_df.tail(n).sort_values(by="_numeric_val", ascending=True)
    else: # "both"
        top_half = clean_df.head(n)
        bottom_half = clean_df.tail(n)
        selected_df = pd.concat([top_half, bottom_half]).drop_duplicates()

    labels = [str(r[label_column]) for _, r in selected_df.iterrows()]
    values = [round(float(r["_numeric_val"]), 2) for _, r in selected_df.iterrows()]

    return {
        "tool": "top_bottom_n",
        "reference_period": str(reference_period),
        "rows_used": len(selected_df),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행({agg_excluded}건) 및 기준 시점 결측치({missing_excluded}건) 제외",
        "columns_used": [label_column, target_col],
        "unit": "수치 (기준 시점)",
        "caution": "동일 시점 데이터만을 기준으로 순위를 매겼습니다. (서로 다른 연도를 혼합하지 않음)",
        "chart_type": "bar",
        "chart_options": {"indexAxis": "y"}, # 수평 막대
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": f"{target_col}년 수치",
                "data": values,
                "backgroundColor": "#3b82f6"
            }]
        },
        "table": [
            {"rank": i + 1, "label": labels[i], "value": values[i]}
            for i in range(len(labels))
        ]
    }


# ==========================================
# 도구 8: group_summary (그룹별 평균·합계·개수 - 막대)
# ==========================================
def group_summary(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    reference_period: str,
    metric: str = "mean", # "mean", "sum", "count"
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 8: 기준 시점 필수]
    특정 기준 시점의 수치를 그룹 열(예: Region, IncomeGroup)별로 집계(평균, 합계, 개수)하여 막대 차트 데이터를 생성합니다.
    """
    if not reference_period:
        raise ValueError("[도구 8 오류] 기준 시점(reference_period)은 필수 입력 항목입니다.")

    target_col = value_column or reference_period
    if target_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열({target_col})이 존재하지 않습니다.")

    if group_column not in df.columns:
        raise ValueError(f"그룹 기준 열({group_column})을 찾을 수 없습니다.")

    original_rows = len(df)
    work_df = df.copy()

    # 집계 행 제외
    agg_excluded = 0
    if exclude_aggregates:
        # 라벨 열 후보 찾기
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        lbl_col = lbl_candidates[0] if lbl_candidates else df.columns[0]
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=lbl_col, exclude=True)

    work_df["_numeric_val"] = pd.to_numeric(work_df[target_col], errors="coerce")
    clean_df = work_df.dropna(subset=["_numeric_val", group_column]).copy()
    missing_excluded = len(work_df) - len(clean_df)
    total_excluded = original_rows - len(clean_df)

    if len(clean_df) == 0:
        raise ValueError(f"그룹 분석에 사용할 유효 데이터가 없습니다.")

    # 그룹 연산
    grouped = clean_df.groupby(group_column)["_numeric_val"]
    if metric == "mean":
        agg_res = grouped.mean().round(2)
        metric_name = "평균"
    elif metric == "sum":
        agg_res = grouped.sum().round(2)
        metric_name = "합계"
    else: # count
        agg_res = grouped.count()
        metric_name = "개수"

    agg_res = agg_res.sort_values(ascending=False)
    labels = [str(idx) for idx in agg_res.index]
    values = [safe_value(val) for val in agg_res.values]

    return {
        "tool": "group_summary",
        "reference_period": str(reference_period),
        "rows_used": len(clean_df),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행({agg_excluded}건) 및 그룹/수치 결측치({missing_excluded}건) 제외",
        "columns_used": [group_column, target_col],
        "unit": f"{metric_name} 수치",
        "caution": "그룹 내 표본 수가 적은 집단은 평균 왜곡이 발생할 수 있으므로 주의해야 합니다.",
        "chart_type": "bar",
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": f"{target_col}년 {metric_name}",
                "data": values,
                "backgroundColor": "#10b981"
            }]
        },
        "table": [
            {"group": labels[i], "value": values[i]}
            for i in range(len(labels))
        ]
    }

# ==========================================
# 도구 9: change_rate (두 시점 사이 변화량·변화율 - 막대)
# ==========================================
def change_rate(
    df: pd.DataFrame,
    start_period: str,
    end_period: str,
    label_column: Optional[str] = None,
    n: int = 10,
    order: str = "top", # "top", "bottom"
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 9: 기준 시점 필수]
    시작 연도(start_period)와 종료 연도(end_period) 사이의 절대 변화량 및 변화율(%)을 계산합니다.
    """
    if not start_period or not end_period:
        raise ValueError("[도구 9 오류] 시작 시점(start_period)과 종료 시점(end_period)은 필수 입력 항목입니다.")

    if start_period not in df.columns or end_period not in df.columns:
        raise ValueError(f"시점 열({start_period} 또는 {end_period})이 데이터에 존재하지 않습니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()

    agg_excluded = 0
    if exclude_aggregates:
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    work_df["_start_val"] = pd.to_numeric(work_df[start_period], errors="coerce")
    work_df["_end_val"] = pd.to_numeric(work_df[end_period], errors="coerce")

    # 두 시점 모두 유효한 데이터만 보존
    clean_df = work_df.dropna(subset=["_start_val", "_end_val"]).copy()
    missing_excluded = len(work_df) - len(clean_df)
    total_excluded = original_rows - len(clean_df)

    if len(clean_df) == 0:
        raise ValueError(f"선택한 두 시점({start_period}, {end_period}) 모두에 값이 존재하는 행이 없습니다.")

    clean_df["_diff"] = clean_df["_end_val"] - clean_df["_start_val"]
    # 0으로 나누기 방지
    clean_df["_rate_pct"] = np.where(
        clean_df["_start_val"] != 0,
        ((clean_df["_diff"] / clean_df["_start_val"]) * 100).round(2),
        np.nan
    )

    clean_df = clean_df.sort_values(by="_diff", ascending=(order != "top"))
    selected_df = clean_df.head(n)

    labels = [str(r[label_column]) for _, r in selected_df.iterrows()]
    diff_values = [round(float(r["_diff"]), 2) for _, r in selected_df.iterrows()]
    rate_values = [safe_value(r["_rate_pct"]) for _, r in selected_df.iterrows()]

    return {
        "tool": "change_rate",
        "reference_period": f"{start_period} → {end_period}",
        "rows_used": len(selected_df),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행({agg_excluded}건) 및 두 시점 중 결측치({missing_excluded}건) 제외",
        "columns_used": [label_column, start_period, end_period],
        "unit": "절대 변화량 (%p 또는 단위 차이)",
        "caution": "시작 시점 수치가 매우 작은 경우 변화율(%)이 비정상적으로 크게 나타날 수 있으므로 절대 변화량과 함께 비교해야 합니다.",
        "chart_type": "bar",
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": f"변화량 ({start_period} 대비 {end_period})",
                "data": diff_values,
                "backgroundColor": "#6366f1"
            }]
        },
        "table": [
            {
                "label": labels[i],
                "start_val": round(float(selected_df.iloc[i]["_start_val"]), 2),
                "end_val": round(float(selected_df.iloc[i]["_end_val"]), 2),
                "diff": diff_values[i],
                "rate_pct": rate_values[i]
            }
            for i in range(len(labels))
        ]
    }


# ==========================================
# 도구 10: distribution (구간별 분포 - 히스토그램)
# ==========================================
def distribution(
    df: pd.DataFrame,
    value_column: str,
    reference_period: str,
    label_column: Optional[str] = None,
    bins: int = 10,
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 10: 기준 시점 필수]
    특정 기준 시점의 데이터 구간별 빈도수(히스토그램)를 계산합니다.
    """
    if not reference_period:
        raise ValueError("[도구 10 오류] 기준 시점(reference_period)은 필수 입력 항목입니다.")

    target_col = value_column or reference_period
    if target_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열({target_col})이 존재하지 않습니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()

    agg_excluded = 0
    if exclude_aggregates:
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    numeric_vals = pd.to_numeric(work_df[target_col], errors="coerce").dropna()
    total_excluded = original_rows - len(numeric_vals)

    if len(numeric_vals) == 0:
        raise ValueError("분포를 계산할 유효 숫자 데이터가 없습니다.")

    # 히스토그램 구간 계산 (np.histogram)
    counts, bin_edges = np.histogram(numeric_vals, bins=bins)
    
    labels = []
    for i in range(len(counts)):
        b_start = round(float(bin_edges[i]), 1)
        b_end = round(float(bin_edges[i+1]), 1)
        labels.append(f"{b_start}~{b_end}")

    counts_list = [int(c) for c in counts]

    return {
        "tool": "distribution",
        "reference_period": str(reference_period),
        "rows_used": len(numeric_vals),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행 및 기준 시점 결측치({total_excluded}건) 제외",
        "columns_used": [label_column, target_col],
        "unit": "개국 / 항목 수",
        "caution": "특정 구간에 빈도가 과도하게 쏠린 경우 이상치(Outlier)나 측정 상한선(100% Capping)의 영향을 점검해야 합니다.",
        "chart_type": "bar",
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": f"{target_col}년 데이터 분포",
                "data": counts_list,
                "backgroundColor": "#8b5cf6"
            }]
        },
        "table": [
            {"range": labels[i], "count": counts_list[i]}
            for i in range(len(labels))
        ]
    }


# ==========================================
# 도구 11: correlation_scatter (두 숫자 열 상관계수 - 산점도)
# ==========================================
def correlation_scatter(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    reference_period: str,
    label_column: Optional[str] = None,
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 11: 기준 시점 필수]
    두 숫자 열 사이의 피어슨 상관계수를 계산하고 산점도(Scatter Plot) 데이터를 생성합니다.
    (주의사항에 '상관관계는 인과관계가 아니다'를 반드시 포함)
    """
    if not reference_period:
        raise ValueError("[도구 11 오류] 기준 시점(reference_period)은 필수 입력 항목입니다.")

    if x_column not in df.columns or y_column not in df.columns:
        raise ValueError(f"분석할 두 열({x_column}, {y_column})이 데이터에 존재하지 않습니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()

    agg_excluded = 0
    if exclude_aggregates:
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    work_df["_x"] = pd.to_numeric(work_df[x_column], errors="coerce")
    work_df["_y"] = pd.to_numeric(work_df[y_column], errors="coerce")

    clean_df = work_df.dropna(subset=["_x", "_y"]).copy()
    total_excluded = original_rows - len(clean_df)

    if len(clean_df) < 2:
        raise ValueError("상관관계를 계산하기 위한 유효 행이 2개 미만입니다.")

    corr_value = float(clean_df["_x"].corr(clean_df["_y"]))
    corr_rounded = round(corr_value, 4) if not math.isnan(corr_value) else 0.0

    # Chart.js 산점도 포인트 포맷: [{x, y, label}]
    points = []
    for _, r in clean_df.iterrows():
        points.append({
            "x": round(float(r["_x"]), 2),
            "y": round(float(r["_y"]), 2),
            "label": str(r[label_column])
        })

    return {
        "tool": "correlation_scatter",
        "reference_period": str(reference_period),
        "rows_used": len(clean_df),
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행 및 둘 중 결측치({total_excluded}건) 제외",
        "columns_used": [label_column, x_column, y_column],
        "unit": "피어슨 상관계수 (r)",
        "caution": "⚠️ [중요 원칙] 상관관계는 인과관계가 아닙니다. 두 지표의 상관계수가 높다고 해서 한쪽이 다른 쪽의 원인이 됨을 의미하지는 않습니다.",
        "correlation": corr_rounded,
        "chart_type": "scatter",
        "chart_data": {
            "datasets": [{
                "label": f"{x_column} vs {y_column} (r={corr_rounded})",
                "data": points,
                "backgroundColor": "#ec4899"
            }]
        }
    }


# ==========================================
# 도구 12: compare_one_vs_all (특정 항목 vs 전체 평균·중앙값 - 강조 막대)
# ==========================================
def compare_one_vs_all(
    df: pd.DataFrame,
    target_item: str,
    value_column: str,
    reference_period: str,
    label_column: Optional[str] = None,
    exclude_aggregates: bool = True
) -> Dict[str, Any]:
    """
    [도구 12: 기준 시점 필수]
    특정 1개 항목(예: 대한민국)의 수치와 전체 집단의 평균 및 중앙값을 대비하는 강조 막대 차트 데이터를 생성합니다.
    """
    if not reference_period:
        raise ValueError("[도구 12 오류] 기준 시점(reference_period)은 필수 입력 항목입니다.")

    target_col = value_column or reference_period
    if target_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열({target_col})이 존재하지 않습니다.")

    if not label_column:
        lbl_candidates = [c for c in df.columns if any(k in str(c).lower() for k in ["name", "country", "label"])]
        label_column = lbl_candidates[0] if lbl_candidates else df.columns[0]

    original_rows = len(df)
    work_df = df.copy()

    agg_excluded = 0
    if exclude_aggregates:
        work_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_column, exclude=True)

    work_df["_numeric_val"] = pd.to_numeric(work_df[target_col], errors="coerce")
    clean_df = work_df.dropna(subset=["_numeric_val"]).copy()
    total_excluded = original_rows - len(clean_df)

    if len(clean_df) == 0:
        raise ValueError(f"기준 시점({target_col})에 값이 있는 유효 데이터가 없습니다.")

    # 특정 항목 찾기
    matched = clean_df[clean_df[label_column].astype(str).str.strip().str.lower() == str(target_item).strip().lower()]
    if len(matched) == 0:
        # 부분 일치 시도 (예: "Korea" -> "Korea, Rep.")
        matched = clean_df[clean_df[label_column].astype(str).str.contains(str(target_item), case=False, na=False)]
        if len(matched) == 0:
            raise ValueError(f"선택한 항목('{target_item}')을 데이터셋에서 찾을 수 없습니다.")

    target_actual_name = str(matched.iloc[0][label_column])
    target_value = round(float(matched.iloc[0]["_numeric_val"]), 2)

    mean_value = round(float(clean_df["_numeric_val"].mean()), 2)
    median_value = round(float(clean_df["_numeric_val"].median()), 2)

    # 순위 계산 (1등부터)
    clean_df = clean_df.sort_values(by="_numeric_val", ascending=False).reset_index(drop=True)
    rank = int(clean_df[clean_df[label_column] == target_actual_name].index[0]) + 1
    total_evaluated = len(clean_df)

    labels = [target_actual_name, "전체 평균 (Mean)", "전체 중앙값 (Median)"]
    values = [target_value, mean_value, median_value]
    colors = ["#ef4444", "#94a3b8", "#64748b"]

    return {
        "tool": "compare_one_vs_all",
        "reference_period": str(reference_period),
        "rows_used": total_evaluated,
        "rows_excluded": total_excluded,
        "exclusion_reason": f"집계 행({agg_excluded}건) 및 기준 시점 결측치 제외 후 총 {total_evaluated}개 항목 비교",
        "columns_used": [label_column, target_col],
        "unit": "수치 단위 (예: %)",
        "caution": "대상 항목이 전체 표본에서 몇 위에 위치하는지 백분위와 함께 확인해야 합니다.",
        "target_item": target_actual_name,
        "rank": rank,
        "total_evaluated": total_evaluated,
        "percentile_top_pct": round((rank / total_evaluated * 100), 1),
        "chart_type": "bar",
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": f"{target_col}년 비교",
                "data": values,
                "backgroundColor": colors
            }]
        },
        "table": [
            {"item": labels[0], "value": values[0], "note": f"전체 {total_evaluated}개국 중 {rank}위"},
            {"item": labels[1], "value": values[1], "note": "산술 평균"},
            {"item": labels[2], "value": values[2], "note": "중앙값"}
        ]
    }


# ==========================================
# 도구 실행 디스패처 (tools.run_tool)
# ==========================================
TOOL_CATALOG = {
    "reshape_wide_to_long": reshape_wide_to_long,
    "quality_report": quality_report,
    "year_coverage": year_coverage,
    "detect_aggregates": detect_aggregates,
    "describe_numeric": describe_numeric,
    "trend_line": trend_line,
    "top_bottom_n": top_bottom_n,
    "group_summary": group_summary,
    "change_rate": change_rate,
    "distribution": distribution,
    "correlation_scatter": correlation_scatter,
    "compare_one_vs_all": compare_one_vs_all,
}

def run_tool(df: pd.DataFrame, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    도구 카탈로그에서 도구를 찾아 안전하게 실행합니다.
    """
    if tool_name not in TOOL_CATALOG:
        raise ValueError(f"도구 카탈로그에 존재하지 않는 도구입니다: '{tool_name}'.")

    func = TOOL_CATALOG[tool_name]
    logger.info(f"[TOOL] 도구명={tool_name} 파라미터={params}")
    return func(df, **params)
