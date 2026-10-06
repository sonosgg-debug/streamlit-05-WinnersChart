
import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
import datetime
import plotly.graph_objects as go
import os
import requests
import xml.etree.ElementTree as ET

STANDARD_CHART_THEME = {
    'paper_bgcolor': '#1E293B',    # Tailwind Slate-800 (외곽 카드 배경)
    'plot_bgcolor': '#0F172A',     # Tailwind Slate-900 (내부 딥 블랙 플롯)
    'text_main': '#F8FAFC',        # 타이틀/헤더 텍스트 (순백색)
    'text_body': '#E2E8F0',        # 본문 및 축 라벨 (부드러운 화이트)
    'text_muted': '#CBD5E1',       # 축 눈금 수치 텍스트 (Slate-300)
    'grid_color': '#334155',       # 그리드 격자선 (Slate-700)
    'border_color': '#475569',     # 축 기준선 (Slate-600)
    'legend_bg': 'rgba(30, 41, 59, 0.85)',
    'legend_border': '#334155',
    'hover_bg': 'rgba(15, 23, 42, 0.9)',
    'hover_border': '#334155'
}

# 한국거래소(KRX) 정규 휴장일 및 법정 공휴일 (2024~2027)
KRX_HOLIDAYS = {
    # 2024
    '20240101', '20240209', '20240212', '20240301', '20240410', '20240501', '20240506',
    '20240515', '20240606', '20240815', '20240916', '20240917', '20240918', '20241001',
    '20241003', '20241009', '20241225', '20241231',
    # 2025
    '20250101', '20250128', '20250129', '20250130', '20250303', '20250501', '20250505',
    '20250506', '20250606', '20250815', '20251003', '20251006', '20251007', '20251008',
    '20251009', '20251225', '20251231',
    # 2026
    '20260101', '20260216', '20260217', '20260218', '20260302', '20260501', '20260505',
    '20260525', '20260603', '20260606', '20260817', '20260924', '20260925', '20261005',
    '20261009', '20261225', '20261231',
    # 2027
    '20270101', '20270208', '20270209', '20270210', '20270301', '20270503', '20270505',
    '20270513', '20270607', '20270816', '20270914', '20270915', '20270916', '20271004',
    '20271011', '20271225', '20271231'
}

# 미국 증시(NYSE/NASDAQ) 정규 휴장일 (2024~2027)
US_HOLIDAYS = {
    # 2024
    '20240101', '20240115', '20240219', '20240329', '20240527', '20240619', '20240704', '20240902', '20241128', '20241225',
    # 2025
    '20250101', '20250120', '20250217', '20250418', '20250526', '20250619', '20250704', '20250901', '20251127', '20251225',
    # 2026
    '20260101', '20260119', '20260216', '20260403', '20260525', '20260619', '20260703', '20260907', '20261126', '20261225',
    # 2027
    '20270101', '20270118', '20270215', '20270326', '20270531', '20270618', '20270705', '20270906', '20271125', '20271224'
}

def is_krx_trading_day(date_val) -> bool:
    """주어진 날짜가 한국거래소(KRX) 정규 거래일인지 판별합니다."""
    clean_date = str(date_val).replace('-', '').strip()
    try:
        dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
        return (dt.weekday() < 5) and (clean_date not in KRX_HOLIDAYS)
    except Exception:
        return False

def is_us_trading_day(date_val) -> bool:
    """주어진 날짜가 미국 증시(NYSE/NASDAQ) 정규 거래일인지 판별합니다."""
    clean_date = str(date_val).replace('-', '').strip()
    try:
        dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
        return (dt.weekday() < 5) and (clean_date not in US_HOLIDAYS)
    except Exception:
        return False

def is_any_market_trading_day(date_val) -> bool:
    """한국거래소 또는 미국 증시 중 최소 한 곳이라도 정규 개장한 날인지 판별합니다."""
    return is_krx_trading_day(date_val) or is_us_trading_day(date_val)

def get_latest_expected_trading_day(target_date: str = None) -> str:
    """
    서버 OS 타임존과 무관하게 한국 표준시(KST, UTC+9)를 기준으로
    한국 또는 미국 증시 중 최소 한 곳이라도 공식 마감 종가가 확정된 최신 영업일 YYYY-MM-DD 반환.
    - target_date 지정 시: 해당 날짜 이하에서 양국 중 최소 한 곳 개장한 최신 거래일로 자동 보정
    - target_date 미지정 시:
        1) 오늘이 한국 거래일이고 15:45 이후이면 오늘 종가 채택
        2) 그 외에는 어제(또는 그 이전) 중 한국 또는 미국 시장이 마감 완료된 최신 거래일 반환
           (미국 거래일 공식 마감은 KST 익일 06:00 이후 확정)
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_kst = now_utc + datetime.timedelta(hours=9)
    today = now_kst.date()

    if target_date:
        if isinstance(target_date, str):
            clean_date = target_date.replace('-', '').strip()
            dt = datetime.datetime.strptime(clean_date, "%Y%m%d").date()
        elif isinstance(target_date, datetime.date):
            dt = target_date
        else:
            dt = today
        for _ in range(60):
            if is_any_market_trading_day(dt):
                return dt.strftime("%Y-%m-%d")
            dt -= datetime.timedelta(days=1)
        return today.strftime("%Y-%m-%d")

    # 1. 오늘이 한국 정규 거래일이고 15:45 이후(장 마감)인 경우 오늘 반환
    if (now_kst.hour > 15 or (now_kst.hour == 15 and now_kst.minute >= 45)) and is_krx_trading_day(today):
        return today.strftime("%Y-%m-%d")

    # 2. 어제 또는 그 이전 날짜 중 최신 마감 영업일 탐색
    d = today - datetime.timedelta(days=1)
    for _ in range(60):
        # d가 미국 거래일인 경우: KST 익일 06:00 이후 공식 마감
        if is_us_trading_day(d):
            if d == (today - datetime.timedelta(days=1)) and now_kst.hour < 6:
                if is_krx_trading_day(d):
                    return d.strftime("%Y-%m-%d")
            else:
                return d.strftime("%Y-%m-%d")
        elif is_krx_trading_day(d):
            return d.strftime("%Y-%m-%d")
        d -= datetime.timedelta(days=1)

    return (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

# 페이지 설정
st.set_page_config(
    page_title="주식 & 지수 수익률 비교",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 사이드바 접기/펼치기 버튼 상시 표시 및 모바일 대비 강화 CSS
st.markdown("""
<style>
    /* Streamlit 고정 상단 헤더 배경 투명화 */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* 메인 콘텐츠 상단 여백 규격화 */
    .main .block-container,
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 2.0rem !important;
    }

    /* Headers & Main Title (00 Bookmarks 테마 일치) */
    h1, .main h1, [data-testid="stHeadingWithActionElements"] h1, .main-title {
        color: #8AB4F8 !important;
        -webkit-text-fill-color: #8AB4F8 !important;
        font-size: 2.0rem !important;
        font-weight: 800 !important;
        text-align: center !important;
    }

    /* Button Styling (39 DividendStock 표준 스타일 일치) */
    .stButton button[kind="primary"],
    .stButton > button[kind="primary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.2s ease !important;
    }
    .stButton button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover,
    section[data-testid="stSidebar"] button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.4) !important;
    }

    /* 다운로드 버튼 공통 통일 스타일 */
    div[data-testid="stDownloadButton"] > button,
    .stDownloadButton > button {
        background-color: #334155 !important;
        color: #f8fafc !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        line-height: 36px !important;
        padding: 0 16px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        transition: all 0.2s ease-in-out !important;
        box-sizing: border-box !important;
    }
    div[data-testid="stDownloadButton"] > button:hover,
    .stDownloadButton > button:hover {
        background-color: #475569 !important;
        border-color: #38bdf8 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.25) !important;
    }
    div[data-testid="stDownloadButton"] > button:active,
    .stDownloadButton > button:active {
        background-color: #1e293b !important;
        border-color: #0284c7 !important;
    }
    div[data-testid="stDownloadButton"] > button p,
    div[data-testid="stDownloadButton"] > button span,
    .stDownloadButton > button p,
    .stDownloadButton > button span {
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: inherit !important;
        line-height: inherit !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"], [data-testid="stSidebar"] {
        background-color: #1e293b !important;
        border-right: 1px solid #334155 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #f8fafc !important;
        -webkit-text-fill-color: #f8fafc !important;
    }

    /* Sidebar button horizontal layout styling (빠른 선택 버튼 등) */
    section[data-testid="stSidebar"] div.stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        padding-left: 2px !important;
        padding-right: 2px !important;
        padding-top: 4px !important;
        padding-bottom: 4px !important;
        min-height: 34px !important;
        height: 34px !important;
        white-space: nowrap !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    /* =========================================================
       사이드바 접기(<<) 및 펼치기(>>) 버튼 항상 표시 및 시인성/대비 강화
       ========================================================= */
    /* 1. 사이드바가 열려 있을 때 접기 버튼 (<<) 상시 표시 */
    [data-testid="stSidebarCollapseButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        display: inline-flex !important;
    }
    
    [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
        background-color: #1e293b !important;       /* 진한 네이비 배경 */
        border: 1.5px solid #38bdf8 !important;     /* 선명한 스카이블루 테두리로 상자 명확화 */
        border-radius: 8px !important;
        width: 38px !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
        transition: all 0.2s ease !important;
    }
    
    /* 상자 내부의 << 아이콘(Material Icon span/svg/문자)을 순백색으로 강제하여 상자와 극명한 대비 구현 */
    [data-testid="stSidebarCollapseButton"] button *,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapseButton"] svg {
        color: #ffffff !important;
        fill: #ffffff !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }
    
    /* 호버(PC) 및 터치 시 반전 효과 */
    [data-testid="stSidebarCollapseButton"] button:hover {
        background-color: #38bdf8 !important;
        border-color: #38bdf8 !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover * {
        color: #0f172a !important;
        fill: #0f172a !important;
    }

    /* 2. 사이드바 헤더 영역 패딩 및 정렬 보정 */
    [data-testid="stSidebarHeader"] {
        padding-top: 0.5rem !important;
        padding-bottom: 0.5rem !important;
    }

    /* 3. 사이드바가 닫혔을 때 다시 여는 버튼 (>>) 시인성 강화 */
    [data-testid="stSidebarCollapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button {
        background-color: #1e293b !important;
        border: 1.5px solid #38bdf8 !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
    }
    
    [data-testid="stSidebarCollapsedControl"] button *,
    [data-testid="stSidebarCollapsedControl"] span,
    [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarCollapsedControl"] svg {
        color: #38bdf8 !important;
        fill: #38bdf8 !important;
        opacity: 1 !important;
        visibility: visible !important;
        font-size: 1.35rem !important;
    }

</style>
""", unsafe_allow_html=True)

# 제목 및 소개
st.markdown("<h1 class='main-title' style='text-align: center; font-size: 2.0rem !important; font-weight: 800 !important; color: #8AB4F8 !important; -webkit-text-fill-color: #8AB4F8 !important; margin-bottom: 10px;'><span style='color: #8AB4F8 !important; -webkit-text-fill-color: #8AB4F8 !important;'>국내외 주식 & 지수 수익률 비교</span></h1>", unsafe_allow_html=True)
st.markdown("""
<div style="text-align: center; color: #BDC1C6; font-size: 0.9rem; margin-bottom: 20px; line-height: 1.6;">
한국 및 미국 주식과 주요 지수의 누적 수익률을 비교할 수 있는 대시보드입니다.<br/>
시작일의 자산 가격을 <b>100%</b> 기준으로 설정하여 종료일까지의 상대적인 변동 추이를 백분율(%)로 보여줍니다.
</div>
""", unsafe_allow_html=True)
st.markdown("<hr style='border: 0; height: 1px; background-color: #334155; margin-bottom: 22px;'>", unsafe_allow_html=True)

# --- 데이터 캐싱 및 매핑 로직 ---

@st.cache_data(ttl=86400)  # 24시간 동안 캐시 유지
def load_krx_data():
    """KRX 종목 목록을 가져와서 코드가 포함된 데이터프레임을 반환합니다."""
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "krx_cache.csv")
    try:
        # 실시간 데이터 로드 시도
        df = fdr.StockListing('KRX')
        df_cleaned = df[['Code', 'Name', 'Market']].copy()
        # 로컬 백업 파일 저장
        df_cleaned.to_csv(cache_file, index=False, encoding='utf-8-sig')
        return df_cleaned
    except Exception as e:
        # 실시간 로드 실패 시 로컬 캐시 시도
        if os.path.exists(cache_file):
            try:
                return pd.read_csv(cache_file, dtype={'Code': str})
            except Exception:
                pass
        
        # 캐시 파일도 없는 경우, 주요 대형주 폴백 데이터 반환
        fallback_data = [
            {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI"},
            {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI"},
            {"Code": "005935", "Name": "삼성전자우", "Market": "KOSPI"},
            {"Code": "035720", "Name": "카카오", "Market": "KOSPI"},
            {"Code": "035420", "Name": "NAVER", "Market": "KOSPI"},
            {"Code": "005380", "Name": "현대차", "Market": "KOSPI"},
            {"Code": "000270", "Name": "기아", "Market": "KOSPI"},
            {"Code": "207940", "Name": "삼성바이오로직스", "Market": "KOSPI"},
            {"Code": "068270", "Name": "셀트리온", "Market": "KOSPI"},
            {"Code": "051910", "Name": "LG화학", "Market": "KOSPI"},
            {"Code": "373220", "Name": "LG에너지솔루션", "Market": "KOSPI"},
            {"Code": "006400", "Name": "삼성SDI", "Market": "KOSPI"},
            {"Code": "247540", "Name": "에코프로비엠", "Market": "KOSDAQ"},
            {"Code": "086520", "Name": "에코프로", "Market": "KOSDAQ"},
        ]
        return pd.DataFrame(fallback_data)

@st.cache_data(ttl=86400)
def get_us_stock_name(symbol):
    """yfinance를 이용해 미국 주식의 기업명을 가져옵니다."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        name = info.get('shortName') or info.get('longName') or symbol
        # 특수문자나 너무 긴 이름 축소
        if name and len(name) > 25:
            name = name[:22] + "..."
        return name
    except Exception:
        return symbol

def resolve_ticker(input_str, krx_df):
    """
    사용자가 입력한 종목명이나 코드를 검출하여 yfinance 티커와 한글/영문 표시 이름으로 변환합니다.
    Returns: (resolved_ticker, display_name)
    """
    input_clean = input_str.strip()
    if not input_clean:
        return None, None

    # 1. 한국 주식 한글명으로 검색
    name_match = krx_df[krx_df['Name'].str.lower() == input_clean.lower()]
    if not name_match.empty:
        code = name_match.iloc[0]['Code']
        market = name_match.iloc[0]['Market']
        name = name_match.iloc[0]['Name']
        suffix = '.KS' if market == 'KOSPI' else '.KQ'
        return f"{code}{suffix}", name

    # 2. 한국 주식 코드로 검색 (소수점 접미사 제거 후 비교)
    code_clean = input_clean
    if code_clean.endswith('.KS') or code_clean.endswith('.KQ'):
        code_clean = code_clean[:-3]

    if code_clean.isdigit() and len(code_clean) == 6:
        code_match = krx_df[krx_df['Code'] == code_clean]
        if not code_match.empty:
            market = code_match.iloc[0]['Market']
            name = code_match.iloc[0]['Name']
            suffix = '.KS' if market == 'KOSPI' else '.KQ'
            return f"{code_clean}{suffix}", name
        else:
            # KRX 목록에 없지만 한국 코드 형식인 경우 디폴트로 .KS 설정
            return f"{code_clean}.KS", f"한국주식({code_clean})"

    # 3. 미국 주식 또는 기타 해외 티커로 인식
    symbol = input_clean.upper()
    
    # 지수 예외 처리 (수동 입력 시 대응)
    index_map = {
        '^KS11': 'KOSPI',
        '^KQ11': 'KOSDAQ',
        '^GSPC': 'S&P 500',
        '^IXIC': 'Nasdaq'
    }
    if symbol in index_map:
        return symbol, index_map[symbol]
        
    display_name = get_us_stock_name(symbol)
    return symbol, display_name

def resolve_stock_selection(selected_display, krx_df):
    """
    선택된 '종목명 (코드/티커)' 문자열을 파싱하여 yfinance 티커와 표시 이름으로 변환합니다. (32 FinancialChart 방식)
    """
    if not selected_display or selected_display == "선택 안 함":
        return None, None

    if "(" in selected_display and selected_display.endswith(")"):
        code_part = selected_display.split("(")[-1].replace(")", "").strip()
        name_part = selected_display.split("(")[0].strip()

        # 한국 6자리 종목 코드인 경우
        if code_part.isdigit() and len(code_part) == 6:
            code_match = krx_df[krx_df['Code'] == code_part]
            if not code_match.empty:
                market = code_match.iloc[0]['Market']
                name = code_match.iloc[0]['Name']
                suffix = '.KS' if market == 'KOSPI' else '.KQ'
                return f"{code_part}{suffix}", name
            return f"{code_part}.KS", name_part
        else:
            # 미국 주식 티커
            symbol = code_part.upper()
            return symbol, name_part

    # 그 외 직접 입력된 텍스트 처리
    return resolve_ticker(selected_display, krx_df)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_kr_index_data(ticker: str, start_date, end_date) -> pd.DataFrame:
    """
    KOSPI(^KS11) 및 KOSDAQ(^KQ11) 지수 데이터를 실시간 수집합니다.
    FinanceDataReader의 'KS11'/'KQ11' 정적 캐시가 과거 특정 일자 이후 중단되는 결함을 방어하기 위해
    1순위: 네이버 금융 fchart API (실시간 최신 공식 확정 종가)
    2순위: yfinance history (^KS11, ^KQ11)
    3순위: FinanceDataReader
    순으로 다중 계층 안전 폴백을 적용합니다.
    """
    symbol = 'KOSPI' if ticker in ['^KS11', 'KS11', 'KOSPI'] else ('KOSDAQ' if ticker in ['^KQ11', 'KQ11', 'KOSDAQ'] else ticker)
    
    # 1순위: 네이버 금융 공식 차트 API (실시간 일별 시세)
    try:
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=6000&requestType=0"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200 and r.text:
            root = ET.fromstring(r.text)
            rows = []
            for item in root.findall('.//item'):
                data_attr = item.get('data', '')
                parts = data_attr.split('|')
                if len(parts) >= 5:
                    rows.append({
                        'Date': datetime.datetime.strptime(parts[0], '%Y%m%d'),
                        'Open': float(parts[1]),
                        'High': float(parts[2]),
                        'Low': float(parts[3]),
                        'Close': float(parts[4]),
                        'Volume': float(parts[5]) if len(parts) > 5 else 0.0
                    })
            if rows:
                df = pd.DataFrame(rows).set_index('Date').sort_index()
                s_dt = pd.to_datetime(start_date)
                e_dt = pd.to_datetime(end_date)
                df_filtered = df.loc[(df.index >= s_dt) & (df.index <= e_dt)]
                if not df_filtered.empty:
                    return df_filtered
    except Exception as e_naver:
        print(f"[fetch_kr_index_data] 네이버 지수 API 조회 실패: {e_naver}")

    # 2순위: yfinance history 폴백
    try:
        yf_sym = '^KS11' if symbol == 'KOSPI' else '^KQ11'
        yf_end = (pd.to_datetime(end_date) + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        df_yf = yf.Ticker(yf_sym).history(start=str(start_date)[:10], end=yf_end)
        if df_yf is not None and not df_yf.empty and 'Close' in df_yf.columns:
            return df_yf
    except Exception as e_yf:
        print(f"[fetch_kr_index_data] yfinance 지수 조회 실패: {e_yf}")

    # 3순위: FinanceDataReader 폴백
    try:
        fdr_code = 'KS11' if symbol == 'KOSPI' else 'KQ11'
        df_fdr = fdr.DataReader(fdr_code, start_date, end_date)
        if df_fdr is not None and not df_fdr.empty:
            return df_fdr
    except Exception as e_fdr:
        print(f"[fetch_kr_index_data] FinanceDataReader 지수 조회 실패: {e_fdr}")

    return pd.DataFrame()

def format_price(value, ticker):
    """자산 종류에 맞게 화폐 단위 및 가격을 포맷팅합니다."""
    if ticker.startswith('^'):
        return f"{value:,.2f} pt"
    elif ticker.endswith('.KS') or ticker.endswith('.KQ'):
        return f"{int(round(value)):,} 원"
    else:
        return f"${value:,.2f}"

def format_return(value):
    """수익률 변동폭에 맞게 기호 및 색상을 적용한 텍스트를 반환합니다."""
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.2f}%"

# --- UI 레이아웃 구성 ---

# KRX 데이터 로드
krx_df = load_krx_data()

# 종목 리스트 포맷팅 (32 FinancialChart 방식: 종목명 (코드))
if not krx_df.empty:
    krx_display_names = (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
else:
    krx_display_names = []

# 주요 미국 주식 목록 (한국어 종목명 + 티커)
us_stocks = [
    "애플 (AAPL)",
    "마이크로소프트 (MSFT)",
    "엔비디아 (NVDA)",
    "테슬라 (TSLA)",
    "아마존 (AMZN)",
    "알파벳A (GOOGL)",
    "메타 (META)",
    "버크셔해서웨이 (BRK-B)",
    "브로드컴 (AVGO)",
    "TSMC (TSM)",
    "일라이릴리 (LLY)",
    "JP모건 (JPM)",
    "월마트 (WMT)",
    "비자 (V)",
    "엑슨모빌 (XOM)",
    "넷플릭스 (NFLX)",
    "코스트코 (COST)",
    "ASML (ASML)",
    "AMD (AMD)",
    "퀄컴 (QCOM)",
    "팔란티어 (PLTR)",
    "아이온큐 (IONQ)",
    "인텔 (INTC)"
]

stock_select_options = ["선택 안 함"] + krx_display_names + us_stocks + ["[직접 입력]"]

# 종목 1 디폴트 인덱스 (삼성전자)
default_idx1 = 0
for idx, opt in enumerate(stock_select_options):
    if "삼성전자 (005930)" in opt:
        default_idx1 = idx
        break

# 종목 2 디폴트 인덱스 (엔비디아)
default_idx2 = 0
for idx, opt in enumerate(stock_select_options):
    if "엔비디아 (NVDA)" in opt:
        default_idx2 = idx
        break

# 사이드바 설정
with st.sidebar:
    st.markdown(
        """
        <div style='padding: 2px 0 12px 0;'>
            <div style='font-size: 1.25rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em; display: flex; align-items: center; gap: 8px;'>
                <span>⚙️</span> 조회/분석 설정
            </div>
            <div style='font-size: 0.82rem; color: #94a3b8; margin-top: 4px; line-height: 1.4;'>
                수익률을 비교 분석할 종목, 지수 및 기간을 설정합니다.
            </div>
        </div>
        <hr style='border: 0; height: 1px; background-color: #334155; margin: 10px 0 16px 0;'>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #e2e8f0; margin-bottom: 6px;'>🔍 종목 선택 (최대 3개)</div>", unsafe_allow_html=True)
    stock_select1 = st.selectbox(
        "종목 1",
        options=stock_select_options,
        index=default_idx1,
        help="키보드로 종목명(예: 삼성전자) 또는 종목코드(예: 005930)를 입력하여 검색할 수 있습니다."
    )
    custom_stock1 = None
    if stock_select1 == "[직접 입력]":
        custom_stock1 = st.text_input("종목 1 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

    stock_select2 = st.selectbox(
        "종목 2 (선택)",
        options=stock_select_options,
        index=default_idx2,
        help="키보드로 종목명 또는 종목코드를 입력하여 검색할 수 있습니다."
    )
    custom_stock2 = None
    if stock_select2 == "[직접 입력]":
        custom_stock2 = st.text_input("종목 2 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

    stock_select3 = st.selectbox(
        "종목 3 (선택)",
        options=stock_select_options,
        index=0,
        help="키보드로 종목명 또는 종목코드를 입력하여 검색할 수 있습니다."
    )
    custom_stock3 = None
    if stock_select3 == "[직접 입력]":
        custom_stock3 = st.text_input("종목 3 직접 입력 (코드/티커)", placeholder="예: AAPL, TSLA, 005930")

    st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #e2e8f0; margin-bottom: 6px;'>📊 지수 선택 (최대 2개)</div>", unsafe_allow_html=True)
    indices_options = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "선택 안 함": None
    }

    index_select1 = st.selectbox(
        "지수 선택 1",
        options=list(indices_options.keys()),
        index=0  # KOSPI 디폴트
    )

    index_select2 = st.selectbox(
        "지수 선택 2",
        options=list(indices_options.keys()),
        index=2  # S&P 500 디폴트
    )

    today = datetime.datetime.strptime(get_latest_expected_trading_day(), "%Y-%m-%d").date()
    if 'perf_start_date' not in st.session_state:
        st.session_state.perf_start_date = datetime.date(today.year, 1, 1)
    if 'perf_end_date' not in st.session_state:
        st.session_state.perf_end_date = today
    if 'selected_preset' not in st.session_state:
        st.session_state.selected_preset = "YTD"

    st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #e2e8f0; margin-bottom: 6px;'>📅 조회 기간</div>", unsafe_allow_html=True)

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input(
            "시작일",
            value=st.session_state.perf_start_date,
            label_visibility="collapsed",
            help="조회 시작일"
        )
    with col_end:
        end_date = st.date_input(
            "종료일",
            value=st.session_state.perf_end_date,
            label_visibility="collapsed",
            help="조회 종료일"
        )

    # 캘린더에서 사용자가 직접 날짜를 바꾼 경우 세션 상태 갱신
    if start_date != st.session_state.perf_start_date or end_date != st.session_state.perf_end_date:
        st.session_state.perf_start_date = start_date
        st.session_state.perf_end_date = end_date
        st.session_state.selected_preset = None

    # 빠른 날짜 선택 프리셋 버튼 (3M, 6M, 1Y, YTD, MAX)
    st.markdown("<div style='font-size: 0.82rem; color: #94a3b8; margin: 10px 0 6px 0; font-weight: 600;'>⚡ 빠른 선택</div>", unsafe_allow_html=True)
    preset_cols = st.columns(5)
    presets = [
        ("3M", today - datetime.timedelta(days=90), "최근 3개월 (90일)"),
        ("6M", today - datetime.timedelta(days=180), "최근 6개월 (180일)"),
        ("1Y", today - datetime.timedelta(days=365), "최근 1년 (365일)"),
        ("YTD", datetime.date(today.year, 1, 1), f"{today.year}년 연초 이후 (YTD)"),
        ("MAX", today - datetime.timedelta(days=365*5), "최근 5년 (전체)")
    ]

    for idx, (p_name, p_start, p_help) in enumerate(presets):
        with preset_cols[idx]:
            is_active = (st.session_state.get('selected_preset') == p_name)
            if st.button(p_name, key=f"btn_preset_{p_name}", type="primary" if is_active else "secondary", use_container_width=True, help=p_help):
                st.session_state.selected_preset = p_name
                st.session_state.perf_start_date = p_start
                st.session_state.perf_end_date = today
                st.session_state['need_run'] = True
                st.rerun()

    if start_date > end_date:
        st.error("시작일은 종료일보다 이전 날짜여야 합니다.")

    # 액션 버튼 (Update & 조회)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_update = st.button("🔄 Update", use_container_width=True, help="캐시를 초기화하고 최신 주가 및 지수 데이터를 다시 수집합니다.")
    with col_btn2:
        run_button = st.button("🔍 조회", type="primary", use_container_width=True, help="선택한 조건으로 대시보드를 새로고침합니다.")

    if btn_update:
        st.cache_data.clear()
        st.session_state['need_run'] = True
        st.rerun()

# 메인 콘텐츠 실행 로직
# 첫 실행이거나 조회 버튼 또는 프리셋 변경 시 실행
if run_button or st.session_state.get('need_run', False) or 'data_loaded' not in st.session_state:
    st.session_state['need_run'] = False
    st.session_state['data_loaded'] = True
    
    # 1. 입력 종목 및 지수 리스트 정리
    targets = []
    
    # 종목 분석 (32 FinancialChart 선택 방식 처리)
    selected_items = [
        (stock_select1, custom_stock1),
        (stock_select2, custom_stock2),
        (stock_select3, custom_stock3)
    ]
    for i, (select_val, custom_val) in enumerate(selected_items):
        target_str = ""
        if select_val == "[직접 입력]":
            if custom_val and custom_val.strip():
                target_str = custom_val.strip()
        elif select_val and select_val != "선택 안 함":
            target_str = select_val

        if target_str:
            ticker, name = resolve_stock_selection(target_str, krx_df)
            if ticker:
                if not any(t[0] == ticker for t in targets):
                    targets.append((ticker, name, f"종목 {i+1}"))
            else:
                st.warning(f"종목 '{target_str}'을(를) 해석할 수 없어 제외했습니다.")

    # 지수 분석
    for i, index_select in enumerate([index_select1, index_select2]):
        ticker = indices_options.get(index_select)
        if ticker:
            # 중복 방지
            if not any(t[0] == ticker for t in targets):
                targets.append((ticker, index_select, f"지수 {i+1}"))

    # 비교 대상이 없는 경우 예외 처리
    if not targets:
        st.info("비교할 종목 또는 지수를 왼쪽 사이드바에서 선택하거나 입력한 뒤 [조회하기] 버튼을 눌러주세요.")
    else:
        # 데이터 수집
        raw_data_dict = {}
        meta_dict = {}
        
        with st.spinner("금융 데이터를 가져오는 중입니다..."):
            # yfinance는 end가 exclusive이므로 1일을 더해줍니다.
            yf_end_date = end_date + datetime.timedelta(days=1)
            
            for ticker, display_name, category in targets:
                try:
                    is_kr_stock = ticker.endswith('.KS') or ticker.endswith('.KQ')
                    is_kr_index = ticker in ['^KS11', '^KQ11']
                    is_kr = is_kr_stock or is_kr_index
                    
                    if is_kr_stock:
                        code = ticker.replace('.KS', '').replace('.KQ', '')
                        df = fdr.DataReader(code, start_date, yf_end_date)
                        if df is None or df.empty:
                            t_obj = yf.Ticker(ticker)
                            df = t_obj.history(start=start_date, end=yf_end_date)
                    elif is_kr_index:
                        df = fetch_kr_index_data(ticker, start_date, yf_end_date)
                    else:
                        t_obj = yf.Ticker(ticker)
                        df = t_obj.history(start=start_date, end=yf_end_date)
                    
                    if df is None or df.empty:
                        st.warning(f"⚠️ '{display_name}' ({ticker})의 가격 데이터가 선택한 기간에 존재하지 않습니다.")
                        continue
                    
                    # 시간대 정보 제거 및 일자 단위 정규화
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    df.index = df.index.normalize()
                    
                    # Close 값 사용
                    series = df['Close'].dropna()
                    
                    if series.empty:
                        st.warning(f"⚠️ '{display_name}' ({ticker})의 유효한 종가 데이터가 없습니다.")
                        continue
                        
                    raw_data_dict[display_name] = series
                    meta_dict[display_name] = {'ticker': ticker, 'is_kr': is_kr, 'category': category}
                    
                except Exception as e:
                    st.error(f"❌ '{display_name}' ({ticker}) 데이터를 가져오는 도중 에러 발생: {e}")

        # 로드된 데이터가 하나라도 있는 경우 화면 표시
        if raw_data_dict:
            # [교차 시장 시계열 병합 및 결측 보정]
            # 1. 공통 캘린더 생성 (양국 중 최소 한 곳이라도 거래된 날 보존)
            combined_df = pd.DataFrame(raw_data_dict)
            combined_df = combined_df.dropna(how='all')
            combined_df.sort_index(inplace=True)
            
            # 2. ffill 적용 전 결측(휴장) 여부 플래깅
            holiday_flags = {}
            for col in combined_df.columns:
                holiday_flags[col] = combined_df[col].isna()
                
            # 3. 휴장일 직전 종가 순방향 유지 (Forward Fill)
            combined_df_filled = combined_df.ffill()
            
            # 각 자산별 정규화(시작가=100%) 데이터 및 플롯 트레이스 생성
            data_dict = {}
            hover_dict = {}
            for display_name in combined_df.columns:
                m_info = meta_dict[display_name]
                tk = m_info['ticker']
                is_kr = m_info['is_kr']
                
                valid_first_idx = combined_df[display_name].first_valid_index()
                if valid_first_idx is None:
                    continue
                start_price = combined_df.loc[valid_first_idx, display_name]
                if start_price <= 0:
                    continue
                
                s_filled = combined_df_filled.loc[valid_first_idx:, display_name]
                norm_series = (s_filled / start_price) * 100.0
                data_dict[display_name] = norm_series
                
                # 맞춤형 호버 텍스트 생성
                hover_texts = []
                for dt_idx, val in norm_series.items():
                    raw_price = s_filled.loc[dt_idx]
                    price_str = format_price(raw_price, tk)
                    is_h = bool(holiday_flags[display_name].get(dt_idx, False))
                    h_tag = " [국내 휴장, 직전 종가]" if (is_h and is_kr) else (" [미국 휴장, 직전 종가]" if (is_h and not is_kr) else "")
                    hover_texts.append(f"{dt_idx.strftime('%Y-%m-%d')}<br><b>{display_name}</b>: {val:.2f}% ({price_str}){h_tag}")
                hover_dict[display_name] = hover_texts
            
            col1, col2 = st.columns([3, 1])
            
            # --- 차트 그리기 (Plotly) ---
            fig = go.Figure()
            
            chart_colors = ['#38BDF8', '#F43F5E', '#10B981', '#FBBF24', '#A855F7', '#EC4899', '#6366F1']
            for i, (display_name, series_normalized) in enumerate(data_dict.items()):
                c = chart_colors[i % len(chart_colors)]
                h_texts = hover_dict.get(display_name, [])
                fig.add_trace(go.Scatter(
                    x=series_normalized.index,
                    y=series_normalized.values,
                    mode='lines',
                    name=display_name,
                    line=dict(width=2.5, color=c),
                    hovertext=h_texts,
                    hoverinfo='text'
                ))
            
            # 우측 Y축(yaxis2) 활성화를 위한 투명 더미 트레이스 추가
            fig.add_trace(go.Scatter(
                x=[None],
                y=[None],
                mode='markers',
                yaxis='y2',
                showlegend=False,
                hoverinfo='skip'
            ))
            
            # 32 FinancialChart 테마 적용 (슬레이트 다크 그레이 & 고대비 텍스트)
            fig.update_layout(
                xaxis=dict(
                    title=dict(text="날짜", font=dict(color="#E2E8F0")),
                    tickformat="%Y-%m-%d",
                    hoverformat="%Y-%m-%d",
                    gridcolor="#2A3342",
                    showline=True,
                    linewidth=1,
                    linecolor="#475569",
                    tickfont=dict(color="#E2E8F0")
                ),
                yaxis=dict(
                    title=dict(text="수익률 지수 (%)", font=dict(color="#E2E8F0")),
                    gridcolor="#334155",
                    showline=True,
                    linewidth=1,
                    linecolor="#475569",
                    ticksuffix="%",
                    tickfont=dict(color="#E2E8F0")
                ),
                yaxis2=dict(
                    overlaying="y",
                    side="right",
                    matches="y",
                    showgrid=False,
                    showline=True,
                    linewidth=1,
                    linecolor="#475569",
                    ticksuffix="%",
                    tickfont=dict(color="#E2E8F0")
                ),
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    font=dict(size=12, color="#E2E8F0"),
                    bgcolor="rgba(30, 41, 59, 0.85)",
                    bordercolor="#334155",
                    borderwidth=1
                ),
                hoverlabel=dict(
                    bgcolor="#0F172A",
                    font_color="#FFFFFF",
                    font_size=12,
                    bordercolor="#334155"
                ),
                font=dict(
                    family="Pretendard, Malgun Gothic, -apple-system, sans-serif",
                    color="#E2E8F0"
                ),
                plot_bgcolor=STANDARD_CHART_THEME['plot_bgcolor'],
                paper_bgcolor=STANDARD_CHART_THEME['paper_bgcolor'],
                margin=dict(l=50, r=50, t=40, b=40),
                height=550
            )
            
            # 메인 화면 차트 출력 (Level 2 표준 섹터 제목)
            st.markdown(
                f"<div style='font-size: 1.20rem; font-weight: 700; color: #8AB4F8; margin: 20px 0 10px 0; display: flex; align-items: center; gap: 8px;'>"
                f"<span>📈</span> 수익률 비교 차트 ({start_date} ~ {end_date}, 시작가 = 100%)"
                f"</div>",
                unsafe_allow_html=True
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
            st.caption("💡 **공휴일 데이터 처리 안내**: 한국 또는 미국 한쪽 시장만 휴장인 경우(예: 추석 연휴 등), 휴장 시장은 직전 거래일 종가가 유지(Forward Fill)되어 양국 자산의 시계열 및 수익률이 공정하고 연속적으로 비교됩니다.")
            
            # --- 요약 분석 표 생성 ---
            st.markdown(
                "<div style='font-size: 1.20rem; font-weight: 700; color: #8AB4F8; margin: 20px 0 10px 0; display: flex; align-items: center; gap: 8px;'>"
                "<span>📊</span> 비교 분석 요약 테이블"
                "</div>",
                unsafe_allow_html=True
            )
            
            summary_rows = []
            for display_name in combined_df.columns:
                m_info = meta_dict.get(display_name, {})
                ticker = m_info.get('ticker', '')
                is_kr = m_info.get('is_kr', False)
                
                raw_s = combined_df[display_name].dropna()
                if raw_s.empty:
                    continue
                start_val = raw_s.iloc[0]
                actual_latest_date = raw_s.index[-1]
                
                # ffill된 최종값 (공통 최종 기준일 시점의 유효가)
                end_val = combined_df_filled[display_name].iloc[-1]
                total_return = ((end_val - start_val) / start_val) * 100
                
                max_val = raw_s.max()
                min_val = raw_s.min()
                max_return = ((max_val - start_val) / start_val) * 100
                min_return = ((min_val - start_val) / start_val) * 100
                
                is_latest_holiday = bool(holiday_flags[display_name].iloc[-1])
                h_suffix = " (국내 휴장)" if (is_latest_holiday and is_kr) else (" (미국 휴장)" if (is_latest_holiday and not is_kr) else "")
                date_display = f"{actual_latest_date.strftime('%Y-%m-%d')}{h_suffix}"
                
                summary_rows.append({
                    "종목/지수명": display_name,
                    "티커": ticker,
                    "시작 가격": format_price(start_val, ticker),
                    "최종 가격": format_price(end_val, ticker),
                    "최종 기준일": date_display,
                    "최종 수익률": total_return,
                    "기간 최고 수익률": max_return,
                    "기간 최저 수익률": min_return
                })
            
            summary_df = pd.DataFrame(summary_rows)
            
            styled_df = summary_df.copy()
            styled_df["최종 수익률"] = styled_df["최종 수익률"].apply(format_return)
            styled_df["기간 최고 수익률"] = styled_df["기간 최고 수익률"].apply(format_return)
            styled_df["기간 최저 수익률"] = styled_df["기간 최저 수익률"].apply(format_return)
            
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True
            )
            
            # 간단한 성과 비교 인사이트 제공
            st.markdown(
                "<div style='font-size: 1.20rem; font-weight: 700; color: #8AB4F8; margin: 20px 0 10px 0; display: flex; align-items: center; gap: 8px;'>"
                "<span>💡</span> 주요 성과 인사이트"
                "</div>",
                unsafe_allow_html=True
            )
            
            # 최고 수익률 자산 찾기
            best_asset = max(summary_rows, key=lambda x: x["최종 수익률"])
            worst_asset = min(summary_rows, key=lambda x: x["최종 수익률"])
            
            st.markdown(f"""
            <div style="font-size: 0.88rem; color: #E2E8F0; line-height: 1.7;">
            • 선택한 기간 동안 가장 높은 성과를 낸 자산은 <b>{best_asset['종목/지수명']}</b>이며, 최종 수익률은 <b>{format_return(best_asset['최종 수익률'])}</b>을 기록했습니다.<br/>
            • 반면 가장 저조한 성과를 낸 자산은 <b>{worst_asset['종목/지수명']}</b>이며, 최종 수익률은 <b>{format_return(worst_asset['최종 수익률'])}</b>을 기록했습니다.
            </div>
            """, unsafe_allow_html=True)
            
        else:
            st.error("가져온 가격 데이터가 모두 비어 있어 차트를 생성하지 못했습니다. 입력 값 및 날짜 범위를 다시 확인해 주세요.")

st.markdown("---")
st.markdown("<div style='text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 8px; margin-bottom: 24px; line-height: 1.6;'>⚠️ 본 서비스에서 제공하는 모든 정보는 투자 참고용이며, 투자의 최종 결정과 책임은 투자자 본인에게 있습니다.</div>", unsafe_allow_html=True)
