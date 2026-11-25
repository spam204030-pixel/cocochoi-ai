"""블로그 주제 발굴: 키워드 검색량 결과에 블로그 포화도·시기·4050 여성 비중을 붙여 점수를 매긴다.

사용법:
    python scripts/blog_topics.py                       # reports/ 안의 가장 최근 keywords_*.csv 사용
    python scripts/blog_topics.py reports/keywords_2026-11-24.csv

필요한 키 (.env, Git에 올리지 않음): NAVER_CLIENT_ID, NAVER_CLIENT_SECRET  (developers.naver.com)
사용하는 API (모두 네이버 공식, 무료):
    - 검색 > 블로그        : 블로그 문서 수        (하루 25,000회)
    - 데이터랩 검색어트렌드 : 최근 12개월 월별 추이  (하루 1,000회)
    - 데이터랩 쇼핑인사이트 : 성별·연령 클릭 비중    (하루 1,000회)

결과: reports/blog_topics_날짜.md (상위 20개 표) / reports/blog_topics_날짜.csv (전체)
"""
import csv
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
API = "https://openapi.naver.com/v1"

# ---------------------------------------------------------------- 설정 (필요하면 여기만 고치면 됨)
MIN_VOL, MAX_VOL = 1_000, 30_000
TOP_N = 20

# 패션 키워드로 인정할 단어 (하나라도 들어 있어야 함)
FASHION_WORDS = [
    "패딩", "코트", "자켓", "재킷", "점퍼", "잠바", "파카", "블루종", "무스탕", "가디건", "니트", "원피스",
    "스커트", "치마", "슬랙스", "팬츠", "바지", "셋업", "정장", "블라우스", "셔츠", "티셔츠", "아우터",
    "아웃터", "외투", "조끼", "후리스", "플리스", "하객룩", "코디", "패션", "옷", "가방", "스웨이드",
    "세무", "가죽", "레더", "트위드", "퀼팅", "퀄팅", "누빔", "구스다운", "다운", "충전재", "집업", "트렌치",
]
# 타깃(40~50대 여성)과 맞지 않거나 특정 브랜드 이름이라 블로그 주제로 쓰기 어려운 단어
EXCLUDE_WORDS = [
    "남자", "남성", "중학생", "고등학생", "군대", "깔깔이", "커플", "키즈", "아동",
    "크롬하츠", "톰하디", "로엠", "시리즈", "SUADE",
]
# 이런 단어가 있으면 '정보형'(애드포스트용 정보 글), 없으면 '구매형'(쿠팡 링크 글)
INFO_WORDS = ["코디", "관리", "세탁", "충전재", "차이", "방법", "고르는", "보관", "뜻", "룩", "패션"]
# 쇼핑인사이트 분야: 패션잡화(가방 등)와 패션의류
CAT_ACC, CAT_CLOTHES = "50000001", "50000000"
ACC_WORDS = ["가방", "신발", "부츠", "모자", "머플러", "목도리", "장갑"]
# ----------------------------------------------------------------


def headers():
    return {"X-Naver-Client-Id": CLIENT_ID, "X-Naver-Client-Secret": CLIENT_SECRET,
            "Content-Type": "application/json"}


def call(method, path, **kw):
    for attempt in range(3):
        r = requests.request(method, API + path, headers=headers(), timeout=20, **kw)
        if r.status_code == 429:  # 너무 빨리 요청함 → 잠시 쉬고 다시
            time.sleep(1 + attempt)
            continue
        if r.status_code != 200:
            sys.exit(f"[오류] {path} {r.status_code} {r.text[:300]}")
        time.sleep(0.12)
        return r.json()
    sys.exit(f"[오류] {path} 요청 한도 초과 (잠시 후 다시 실행해 주세요)")


def month_range():
    """오늘 기준 지난 12개 '완성된' 달 (예: 11/25 실행 → 작년 11월 ~ 올해 10월)."""
    t = date.today()
    end_y, end_m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    start_y, start_m = (end_y - 1, end_m + 1) if end_m < 12 else (end_y, 1)
    end_day = (date(end_y + (end_m == 12), end_m % 12 + 1, 1) - date.resolution).day
    return f"{start_y}-{start_m:02d}-01", f"{end_y}-{end_m:02d}-{end_day:02d}"


# 1) 후보 추리기 ---------------------------------------------------
def load_candidates(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    out = []
    for r in rows:
        kw, vol = r["키워드"], int(r["총검색량"])
        if not (MIN_VOL <= vol <= MAX_VOL):
            continue
        if not any(w in kw for w in FASHION_WORDS) or any(w in kw for w in EXCLUDE_WORDS):
            continue
        out.append({"키워드": kw, "월검색량": vol, "경쟁도(광고)": r.get("경쟁도", "")})
    return out


# 2) 블로그 문서 수 ------------------------------------------------
def blog_total(kw):
    return call("GET", "/search/blog.json", params={"query": kw, "display": 1})["total"]


# 3) 검색어트렌드 (5개씩) -----------------------------------------
def trends(keywords, start, end):
    result = {}
    for i in range(0, len(keywords), 5):
        chunk = keywords[i:i + 5]
        body = {"startDate": start, "endDate": end, "timeUnit": "month",
                "keywordGroups": [{"groupName": k, "keywords": [k]} for k in chunk]}
        for g in call("POST", "/datalab/search", json=body)["results"]:
            result[g["title"]] = {d["period"][:7]: d["ratio"] for d in g["data"]}
    return result


# 4) 쇼핑인사이트: 여성 비중 × 여성 중 40·50대 비중 ----------------
def shopping_share(kw, start, end):
    cats = [CAT_ACC, CAT_CLOTHES] if any(w in kw for w in ACC_WORDS) else [CAT_CLOTHES, CAT_ACC]
    for cat in cats:
        base = {"startDate": start, "endDate": end, "timeUnit": "month", "category": cat, "keyword": kw}
        g = call("POST", "/datalab/shopping/category/keyword/gender", json=base)["results"][0]["data"]
        if not g:
            continue  # 이 분야엔 데이터 없음 → 다른 분야로
        f = sum(d["ratio"] for d in g if d["group"] == "f")
        m = sum(d["ratio"] for d in g if d["group"] == "m")
        a = call("POST", "/datalab/shopping/category/keyword/age",
                 json={**base, "gender": "f"})["results"][0]["data"]
        tot = sum(d["ratio"] for d in a)
        a4050 = sum(d["ratio"] for d in a if d["group"] in ("40", "50"))
        female = f / (f + m) if f + m else 0
        in_female = a4050 / tot if tot else 0
        return female, in_female, female * in_female
    return None, None, None


# 5) 점수 (각 25점, 합계 100점) ------------------------------------
def log_scale(x, lo, hi):
    x = min(max(x, lo), hi)
    return (math.log(x) - math.log(lo)) / (math.log(hi) - math.log(lo))


def score(row, trend):
    # 검색량: 1,000 → 0점, 30,000 → 25점 (로그 비례)
    s_vol = 25 * log_scale(row["월검색량"], MIN_VOL, MAX_VOL)
    # 포화도: 검색량 1건당 블로그 글 수. 1개 이하 → 25점, 100개 이상 → 0점
    s_sat = 25 * (1 - log_scale(max(row["포화도"], 1), 1, 100))
    # 시기: 앞으로 1~2달(오늘 달·다음 달·다다음 달)의 작년 관심도가 피크 대비 얼마인지
    s_time = 0
    if trend:
        peak = max(trend.values()) or 1
        m = date.today().month
        months = [(m + k - 1) % 12 + 1 for k in range(3)]
        window = [v for p, v in trend.items() if int(p[5:7]) in months]
        s_time = 25 * (sum(window) / len(window) / peak) if window else 0
    # 4050 여성: 쇼핑 클릭 중 40·50대 여성 추정 비중. 50% 이상이면 만점
    s_4050 = 25 * min((row["4050여성비중"] or 0) / 0.5, 1)
    return round(s_vol), round(s_sat), round(s_time), round(s_4050)


def main():
    if not (CLIENT_ID and CLIENT_SECRET):
        sys.exit("[오류] .env 파일에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 필요합니다 (developers.naver.com).")
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    else:
        files = sorted((ROOT / "reports").glob("keywords_*.csv"))
        if not files:
            sys.exit("[오류] reports/keywords_*.csv 가 없습니다. 먼저 naver_keyword.py 를 실행해 주세요.")
        src = files[-1]

    rows = load_candidates(src)
    print(f"후보 {len(rows)}개 (검색량 {MIN_VOL:,}~{MAX_VOL:,}, 패션 관련) ← {src.name}")
    start, end = month_range()

    print("블로그 문서 수 조회 중...")
    for r in rows:
        r["블로그문서수"] = blog_total(r["키워드"])
        r["포화도"] = round(r["블로그문서수"] / r["월검색량"], 1)

    print("검색어트렌드 조회 중...")
    tr = trends([r["키워드"] for r in rows], start, end)

    print("쇼핑인사이트 조회 중...")
    for r in rows:
        female, in_female, share = shopping_share(r["키워드"], start, end)
        r["여성비중"], r["여성중4050"], r["4050여성비중"] = female, in_female, share

    for r in rows:
        t = tr.get(r["키워드"], {})
        if t and max(t.values()) > 0:
            peak = max(t, key=t.get)
            r["피크달"] = f"{int(peak[5:7])}월"
            r["월별추이"] = " ".join(f"{int(p[5:7])}월:{round(v)}" for p, v in sorted(t.items()))
        else:
            r["피크달"], r["월별추이"] = "-", ""
        r["유형"] = "정보형" if any(w in r["키워드"] for w in INFO_WORDS) else "구매형"
        sv, ss, st, s4 = score(r, t)
        r.update({"점수_검색량": sv, "점수_포화도": ss, "점수_시기": st, "점수_4050": s4,
                  "총점": sv + ss + st + s4})

    rows.sort(key=lambda r: -r["총점"])
    today = date.today().isoformat()
    pct = lambda v: "-" if v is None else f"{v*100:.0f}%"

    # 전체 CSV
    out_csv = ROOT / "reports" / f"blog_topics_{today}.csv"
    cols = ["총점", "키워드", "유형", "월검색량", "블로그문서수", "포화도", "피크달", "여성비중", "여성중4050",
            "4050여성비중", "점수_검색량", "점수_포화도", "점수_시기", "점수_4050", "경쟁도(광고)", "월별추이"]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, **{k: pct(r[k]) for k in ("여성비중", "여성중4050", "4050여성비중")}})

    # 상위 20 표 (마크다운)
    lines = [
        f"# 블로그 주제 TOP {TOP_N} ({today})", "",
        f"- 출처: 검색량 = 네이버 검색광고 키워드도구({src.name}) / 블로그 문서 수 = 네이버 검색 API / "
        f"월별 추이 = 네이버 데이터랩 검색어트렌드({start}~{end}) / 4050 비중 = 네이버 데이터랩 쇼핑인사이트(같은 기간), 조회일 {today}",
        "- 포화도 = 블로그 문서 수 ÷ 월 검색량 (낮을수록 경쟁이 덜함)",
        "- 4050 여성 비중 = 쇼핑 클릭 중 여성 비중 × 여성 클릭 중 40·50대 비중 (두 값을 곱한 **추정치**)",
        "- 점수(100) = 검색량 25 + 포화도 25 + 시기 25(앞으로 3달이 작년 피크에 얼마나 가까운지) + 4050 여성 25",
        "",
        "| 순위 | 키워드 | 유형 | 월검색량 | 블로그 문서 수 | 포화도 | 피크 달 | 4050 여성(추정) | 점수 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows[:TOP_N], 1):
        lines.append(f"| {i} | {r['키워드']} | {r['유형']} | {r['월검색량']:,} | {r['블로그문서수']:,} | "
                     f"{r['포화도']} | {r['피크달']} | {pct(r['4050여성비중'])} | **{r['총점']}** "
                     f"({r['점수_검색량']}/{r['점수_포화도']}/{r['점수_시기']}/{r['점수_4050']}) |")
    lines += ["", "점수 괄호 안: 검색량/포화도/시기/4050", "", "## 월별 추이 (상위 20, 각 키워드 최고 달 = 100 기준 아님, 같은 조회 묶음 안의 상대값)", ""]
    lines += [f"- **{r['키워드']}** (피크 {r['피크달']}): {r['월별추이']}" for r in rows[:TOP_N]]
    out_md = ROOT / "reports" / f"blog_topics_{today}.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(lines[7:7 + TOP_N + 2]))
    print(f"\n저장: {out_md.relative_to(ROOT)} / {out_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
