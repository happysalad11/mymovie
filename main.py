import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

# -------------------------------------------------
# 기본 설정
# -------------------------------------------------
st.set_page_config(
    page_title="박스오피스 대시보드",
    page_icon="🎬",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 1250px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        .main-title {
            font-size: 2.3rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }

        .sub-title {
            color: #666666;
            margin-bottom: 1.5rem;
        }

        div[data-testid="stMetric"] {
            background-color: #f7f7f9;
            border: 1px solid #e5e5e5;
            border-radius: 14px;
            padding: 16px;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid #e5e5e5;
            border-radius: 12px;
            overflow: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">🎬 박스오피스 대시보드</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">영화진흥위원회 일별 박스오피스 자료를 한눈에 확인해 보세요.</div>',
    unsafe_allow_html=True,
)


# -------------------------------------------------
# 인증키 확인
# -------------------------------------------------
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except KeyError:
    st.error("인증키가 설정되지 않았습니다.")
    st.info(
        """
        스트림릿 클라우드의 Secrets에 다음과 같이 입력해 주세요.

        KOBIS_KEY = "발급받은 인증키"
        """
    )
    st.stop()


# -------------------------------------------------
# 날짜 설정
# -------------------------------------------------
korea_today = datetime.now(ZoneInfo("Asia/Seoul")).date()
default_date = korea_today - timedelta(days=1)

with st.sidebar:
    st.header("🔎 조회 설정")

    selected_date = st.date_input(
        "박스오피스 날짜",
        value=default_date,
        max_value=default_date,
        help="당일 자료는 아직 집계되지 않을 수 있어 어제까지만 선택할 수 있습니다.",
    )

    chart_count = st.slider(
        "차트에 표시할 영화 수",
        min_value=3,
        max_value=10,
        value=5,
    )

    search_word = st.text_input(
        "영화명 검색",
        placeholder="영화 제목을 입력하세요",
    )

    st.divider()
    st.caption("자료 출처: 영화진흥위원회 영화관입장권통합전산망")


# -------------------------------------------------
# API 요청 함수
# -------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_boxoffice(target_date: date) -> pd.DataFrame:
    target_dt = target_date.strftime("%Y%m%d")

    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    try:
        response = requests.get(
            url,
            params={
                "key": KOBIS_KEY,
                "targetDt": target_dt,
            },
            timeout=15,
        )

        response.raise_for_status()

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "서버 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "인터넷 연결을 확인해 주세요."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"자료 요청 중 오류가 발생했습니다: {exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "서버에서 올바르지 않은 형식의 응답을 받았습니다."
        ) from exc

    if "faultInfo" in data:
        error_message = data["faultInfo"].get(
            "message",
            "인증키 또는 요청 정보를 확인해 주세요.",
        )
        raise RuntimeError(f"영화진흥위원회 API 오류: {error_message}")

    box_list = (
        data.get("boxOfficeResult", {})
        .get("dailyBoxOfficeList", [])
    )

    if not box_list:
        return pd.DataFrame()

    df = pd.DataFrame(box_list)

    numeric_columns = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiInten",
        "audiAcc",
        "salesAmt",
        "salesAcc",
        "salesShare",
        "scrnCnt",
        "showCnt",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            ).fillna(0)

    return df


# -------------------------------------------------
# 순위 변동 표시 함수
# -------------------------------------------------
def make_rank_change(row) -> str:
    rank_change = int(row.get("rankInten", 0))
    old_and_new = row.get("rankOldAndNew", "OLD")

    if old_and_new == "NEW":
        return "🆕 신규"

    if rank_change > 0:
        return f"🔺 {rank_change}"

    if rank_change < 0:
        return f"🔻 {abs(rank_change)}"

    return "➖ 유지"


# -------------------------------------------------
# 자료 불러오기
# -------------------------------------------------
with st.spinner("박스오피스 자료를 불러오는 중입니다."):
    try:
        df = get_boxoffice(selected_date)
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

if df.empty:
    st.warning("선택한 날짜의 박스오피스 자료가 없습니다.")
    st.info("하루 전 날짜를 선택하여 다시 확인해 주세요.")
    st.stop()


# -------------------------------------------------
# 자료 정리
# -------------------------------------------------
df = df.sort_values("rank").reset_index(drop=True)
df["순위 변동"] = df.apply(make_rank_change, axis=1)

table_columns = {
    "rank": "순위",
    "movieNm": "영화명",
    "openDt": "개봉일",
    "audiCnt": "일일 관객수",
    "audiAcc": "누적 관객수",
    "salesShare": "매출 점유율",
    "scrnCnt": "스크린 수",
    "showCnt": "상영 횟수",
}

available_columns = [
    column for column in table_columns
    if column in df.columns
]

table = df[available_columns].copy()
table = table.rename(columns=table_columns)
table.insert(1, "순위 변동", df["순위 변동"])

table["순위"] = table["순위"].astype(int)
table["일일 관객수"] = table["일일 관객수"].astype(int)
table["누적 관객수"] = table["누적 관객수"].astype(int)
table["스크린 수"] = table["스크린 수"].astype(int)
table["상영 횟수"] = table["상영 횟수"].astype(int)
table["매출 점유율"] = table["매출 점유율"].round(1)

if search_word.strip():
    filtered_table = table[
        table["영화명"].str.contains(
            search_word.strip(),
            case=False,
            na=False,
        )
    ].copy()
else:
    filtered_table = table.copy()


# -------------------------------------------------
# 조회일 표시
# -------------------------------------------------
st.caption(
    f"📅 조회 기준일: {selected_date.strftime('%Y년 %m월 %d일')}"
)


# -------------------------------------------------
# 핵심 지표
# -------------------------------------------------
top_movie = df.iloc[0]

total_audience = int(df["audiCnt"].sum())
total_screens = int(df["scrnCnt"].sum())
total_shows = int(df["showCnt"].sum())

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric(
    "🏆 박스오피스 1위",
    top_movie["movieNm"],
)

metric2.metric(
    "👥 1위 일일 관객수",
    f"{int(top_movie['audiCnt']):,}명",
)

metric3.metric(
    "🎟️ 상위 10편 총관객수",
    f"{total_audience:,}명",
)

metric4.metric(
    "🎞️ 전체 상영 횟수",
    f"{total_shows:,}회",
)


# -------------------------------------------------
# 탭 구성
# -------------------------------------------------
tab1, tab2, tab3 = st.tabs(
    [
        "📋 순위표",
        "📊 관객수 분석",
        "🎥 상영 현황",
    ]
)


# -------------------------------------------------
# 탭 1: 순위표
# -------------------------------------------------
with tab1:
    st.subheader("박스오피스 TOP 10")

    if filtered_table.empty:
        st.warning("검색어와 일치하는 영화가 없습니다.")
    else:
        display_table = filtered_table.copy()

        st.dataframe(
            display_table,
            width="stretch",
            hide_index=True,
            column_config={
                "순위": st.column_config.NumberColumn(
                    "순위",
                    format="%d위",
                ),
                "영화명": st.column_config.TextColumn(
                    "영화명",
                    width="large",
                ),
                "일일 관객수": st.column_config.NumberColumn(
                    "일일 관객수",
                    format="%d명",
                ),
                "누적 관객수": st.column_config.NumberColumn(
                    "누적 관객수",
                    format="%d명",
                ),
                "매출 점유율": st.column_config.NumberColumn(
                    "매출 점유율",
                    format="%.1f%%",
                ),
                "스크린 수": st.column_config.NumberColumn(
                    "스크린 수",
                    format="%d개",
                ),
                "상영 횟수": st.column_config.NumberColumn(
                    "상영 횟수",
                    format="%d회",
                ),
            },
        )

        csv_data = display_table.to_csv(
            index=False,
            encoding="utf-8-sig",
        )

        st.download_button(
            label="📥 순위표 CSV 내려받기",
            data=csv_data,
            file_name=(
                f"박스오피스_{selected_date.strftime('%Y%m%d')}.csv"
            ),
            mime="text/csv",
        )


# -------------------------------------------------
# 탭 2: 관객수 분석
# -------------------------------------------------
with tab2:
    st.subheader(f"일일 관객수 상위 {chart_count}편")

    audience_chart = (
        table.sort_values(
            "일일 관객수",
            ascending=False,
        )
        .head(chart_count)
        .set_index("영화명")[["일일 관객수"]]
    )

    st.bar_chart(
        audience_chart,
        horizontal=True,
        height=420,
    )

    st.subheader(f"누적 관객수 상위 {chart_count}편")

    accumulated_chart = (
        table.sort_values(
            "누적 관객수",
            ascending=False,
        )
        .head(chart_count)
        .set_index("영화명")[["누적 관객수"]]
    )

    st.bar_chart(
        accumulated_chart,
        horizontal=True,
        height=420,
    )


# -------------------------------------------------
# 탭 3: 상영 현황
# -------------------------------------------------
with tab3:
    left, right = st.columns(2)

    with left:
        st.subheader("영화별 스크린 수")

        screen_chart = (
            table.head(chart_count)
            .set_index("영화명")[["스크린 수"]]
        )

        st.bar_chart(
            screen_chart,
            height=400,
        )

    with right:
        st.subheader("영화별 상영 횟수")

        show_chart = (
            table.head(chart_count)
            .set_index("영화명")[["상영 횟수"]]
        )

        st.bar_chart(
            show_chart,
            height=400,
        )

    st.divider()

    screen1, screen2, screen3 = st.columns(3)

    screen1.metric(
        "상위 10편 전체 스크린",
        f"{total_screens:,}개",
    )

    screen2.metric(
        "영화 한 편당 평균 스크린",
        f"{total_screens / len(df):,.1f}개",
    )

    screen3.metric(
        "영화 한 편당 평균 상영",
        f"{total_shows / len(df):,.1f}회",
    )


# -------------------------------------------------
# 아래쪽 안내
# -------------------------------------------------
st.divider()
st.caption(
    "※ 박스오피스 자료는 영화진흥위원회 집계 상황에 따라 추후 수정될 수 있습니다."
)
