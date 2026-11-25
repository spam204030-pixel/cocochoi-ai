"""블로그 주제 발굴 (네이버 검색광고 API만 사용)

사용법:
    python scripts/blog_topics_ad.py            # 일반 (쿠팡+블로그 균형)
    python scripts/blog_topics_ad.py --adpost   # 애드포스트용 (정보형 우선, 상위 30개)

하는 일:
  1. 4050 여성 겨울 패션 씨앗 키워드 30개 → 연관 키워드 전부 수집
  2. 월 검색량 500~50,000, 패션 관련만 남기고 남성·아동·학생·브랜드명 제외
  3. 모바일 비중, 월 평균 클릭수, 클릭률, 광고 깊이, 경쟁도 계산
  4. 정보형 / 구매형 분류
  5. 비슷한 키워드를 한 글 주제로 묶기 (메인 1 + 서브 3~5)
  6. 점수 매겨 상위 20개 주제 + 블로그 제목 예시
  7. reports/ 에 날짜별 저장, 지난 결과와 비교해 검색량 오른 키워드 표시

필요한 키 (.env): NAVER_AD_API_KEY, NAVER_AD_SECRET, NAVER_AD_CUSTOMER_ID
"""
import csv
import math
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from naver_keyword import API_KEY, BASE_URL, CUSTOMER_ID, SECRET, URI, headers, to_int  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
PREFIX = "blog_topics_ad_"

# ================================================================ 설정 (여기만 고치면 됨)
SEEDS = [
    "스웨이드자켓", "여성롱패딩", "여성하프코트", "캐시미어코트", "울코트", "니트원피스", "겨울하객룩",
    "기모슬랙스", "와이드팬츠", "터틀넥", "가디건", "무스탕", "퍼자켓", "롱스커트", "앵클부츠", "머플러",
    "여성숏패딩", "여성경량패딩", "핸드메이드코트", "트위드자켓", "캐시미어니트", "겨울원피스", "롱부츠",
    "여성패딩조끼", "기모바지", "니트가디건", "여성구스다운", "체크코트", "겨울니트", "숄",
]
MIN_VOL, MAX_VOL = 500, 50_000
TOP_N = 20

# 패션 키워드로 인정할 단어 (하나라도 있어야 함)
FASHION_WORDS = [
    "패딩", "코트", "자켓", "재킷", "점퍼", "잠바", "파카", "블루종", "무스탕", "가디건", "니트", "원피스",
    "스커트", "치마", "슬랙스", "팬츠", "바지", "셋업", "정장", "블라우스", "셔츠", "티셔츠", "아우터",
    "아웃터", "외투", "조끼", "베스트", "후리스", "플리스", "하객룩", "코디", "패션", "스웨이드", "세무",
    "가죽", "레더", "트위드", "퀼팅", "누빔", "구스", "덕다운", "다운", "터틀넥", "폴라", "목폴라", "레깅스",
    "부츠", "머플러", "목도리", "스카프", "숄", "판초", "케이프", "퍼", "밍크", "캐시미어", "울", "모직",
    "핸드메이드", "기모", "룩", "옷", "카디건", "롱스커트", "앵클", "보풀",
]
# 남성·아동·학생 및 패션이 아닌 뜻(자동차 머플러 등)
EXCLUDE_WORDS = [
    "남자", "남성", "맨즈", "중딩", "고딩", "초딩", "아동", "키즈", "주니어", "초등", "중학생", "고등학생", "학생", "교복", "아기",
    "유아", "베이비", "남아", "여아", "신생아", "군대", "깔깔이", "커플", "강아지", "애견", "반려",
    "자동차", "차량", "오토바이", "배기", "소음기", "튜닝", "울산", "울릉", "울진", "숄더", "퍼프", "퍼스트", "퍼즐",
    "벽지", "카페트", "카펫", "커튼", "소파", "쇼파", "운동화", "신발", "이불", "베개", "침구", "토퍼", "담요", "도매", "만들기", "뜨기", "도안", "뜨개", "털실", "원단", "수선",
]
# 브랜드명 (목록에 있는 것만 걸러짐 — 모르는 브랜드는 남을 수 있음)
BRANDS = [
    "노스페이스", "디스커버리", "네파", "코오롱", "블랙야크", "아이더", "K2", "케이투", "밀레", "몽클레어",
    "몽클레르", "캐나다구스", "탑텐", "유니클로", "스파오", "자라", "지오다노", "무신사", "로엠", "미쏘",
    "에잇세컨즈", "나이키", "아디다스", "뉴발란스", "휠라", "데상트", "컬럼비아", "내셔널지오그래픽", "버버리",
    "막스마라", "구찌", "프라다", "샤넬", "에르메스", "루이비통", "아크테릭스", "파타고니아", "시스템",
    "타임", "마인", "쥬시꾸뛰르", "닥스", "빈폴", "헤지스", "라코스테", "폴로", "랄프로렌", "톰보이",
    "지컷", "듀엘", "앤드지", "크로커다일", "올리비아로렌", "베네통", "게스", "리바이스", "캘빈클라인",
    "타미", "망고", "코스", "아르켓", "르메르", "이자벨마랑", "써스데이아일랜드", "닥터마틴", "반스",
    "컨버스", "크록스", "어그오스트레일리아", "에뛰드", "모조에스핀", "잇미샤", "온앤온", "보브", "플라스틱아일랜드",
    "베스띠벨리", "씨", "지고트", "미샤", "구호", "띠어리", "산드로", "마쥬", "토리버치", "마이클코어스",
    "코치", "MLB", "엠엘비", "질스튜어트", "커버낫", "마르디", "디스이즈네버댓", "로라로라", "아떼",
    "브랜디", "지그재그", "에이블리", "쿠팡", "이마트", "홈쇼핑", "아울렛", "SUADE", "톰하디", "크롬하츠",
    "다이소", "암웨이", "다우니", "글리너", "아이프리", "시슬리", "에고이스트", "케네스레이디", "리스트", "쉬즈미스", "JJ지고트", "BCBG", "모그", "르샵", "티엔지티",
    "올젠", "인디안", "세정", "까스텔바작", "파리게이츠", "와이드앵글", "르까프", "엘레강스", "몬테밀라노",
]
# 정보형 신호 단어
INFO_WORDS = ["코디", "관리", "세탁", "보풀", "제거", "차이", "고르는", "추천", "방법", "보관", "뜻", "입는", "매는", "스타일링",
              "룩", "브랜드순위", "가격", "후기", "비교"]
# 이 단어가 있으면 광고 신호와 상관없이 정보형 (방법을 찾는 검색이 분명함. 광고는 세탁소·제품이 붙는 것)
STRONG_INFO_WORDS = ["세탁", "관리", "보관", "매는법", "보풀제거", "손질", "얼룩", "줄었", "늘어난"]
# 단, 이런 말로 끝나면 '제품'을 찾는 검색 → 구매형 (보풀제거기, 얼룩제거제, 세탁세제)
PRODUCT_WORDS = ["제거기", "제거제", "세제", "크리너", "클리너", "스프레이"]
# 애드포스트 모드: 관리 키워드는 '소재 묶음 + 관리 방법'으로 묶음
CARE_FAMILIES = [
    ("패딩", ["패딩", "구스", "오리털", "덕다운", "다운", "점퍼", "파카"]),
    ("스웨이드·가죽·무스탕", ["스웨이드", "세무", "가죽", "레더", "무스탕", "양털", "어그"]),
    ("니트·캐시미어·울코트", ["니트", "캐시미어", "울", "코트", "가디건", "스웨터", "목도리", "머플러"]),
]
CARE_ONE_TOPIC = {"보풀": "니트·코트", "얼룩": "옷"}
CARE_ACTIONS = [("보풀", ["보풀"]), ("얼룩", ["얼룩"]), ("보관", ["보관"]), ("세탁·관리", ["세탁", "관리", "손질"])]
# 정보형/구매형 판단 기준값 (실행 결과의 분포를 보고 정함)
CTR_LOW = 1.0      # 클릭률(%)이 이보다 낮으면 '광고를 덜 누르는 검색' = 정보 찾는 사람
DEPTH_LOW = 10     # 광고 깊이(검색 결과에 붙는 광고 개수)가 이보다 낮으면 광고주 관심이 적음
# 주제 묶을 때 떼어낼 꾸밈말 (떼고 남은 말이 같으면 같은 주제)
MODIFIERS = [
    "40대", "50대", "4050", "중년", "여성", "여자", "엄마", "미시", "초겨울", "늦가을", "겨울", "가을", "간절기", "데일리",
    "블랙", "브라운", "베이지", "그레이", "회색", "네이비", "아이보리", "카키", "화이트", "흰색", "검정",
    "검은색", "차콜", "와인", "카멜", "크림", "추천", "코디", "인기", "예쁜", "고급", "명품", "저렴한", "세일",
    "할인", "빅사이즈", "오버핏", "루즈핏", "브랜드", "순위", "가격", "후기", "스타일", "룩",
    "하는방법", "하는법", "방법", "집에서",
]
# 같은 물건의 다른 이름 (주제 묶을 때만 사용)
SYNONYMS = {"앵글": "앵클", "골덴": "코듀로이", "바지": "팬츠", "재킷": "자켓", "카디건": "가디건", "세무": "스웨이드", "후리스": "플리스"}
SECOND_ROUND = 30  # 2차 확장: 1차 상위 주제 몇 개의 메인 키워드로 연관 키워드를 한 번 더 모을지
COMP_SCORE = {"낮음": 1.0, "중간": 0.6, "높음": 0.2}

# ---------------- 애드포스트 모드 (--adpost) 설정
ADPOST = "--adpost" in sys.argv
ADPOST_SEEDS = [
    "패딩세탁", "롱패딩세탁", "니트보풀제거", "니트세탁", "캐시미어세탁", "코트보관", "울코트세탁",
    "스웨이드관리", "무스탕세탁", "목도리매는법", "스카프매는법", "하객룩", "겨울코디", "레이어드코디",
]
ADPOST_TOP_N = 30
MAIN_BEST = (1_000, 20_000)   # 메인 키워드 검색량이 이 범위면 만점 (너무 크면 대형 블로그와 경쟁)
BRAND_CMP_WORDS = ["브랜드", "명품", "순위", "vs", "VS", "비교"]  # 브랜드 비교 키워드 → 감점
# ================================================================


def fetch_related(seeds):
    rows = {}
    for i in range(0, len(seeds), 5):
        chunk = seeds[i:i + 5]
        for attempt in range(3):
            r = requests.get(BASE_URL + URI, params={"hintKeywords": ",".join(chunk), "showDetail": "1"},
                             headers=headers("GET", URI), timeout=20)
            if r.status_code == 429:
                time.sleep(2 + attempt)
                continue
            break
        if r.status_code != 200:
            sys.exit(f"[오류] {r.status_code} {r.text[:300]}")
        for it in r.json().get("keywordList", []):
            rows[it["relKeyword"]] = it
        print(f"  씨앗 {i + len(chunk)}/{len(seeds)} → 누적 {len(rows):,}개")
        time.sleep(0.6)
    return rows


def keep(kw, vol):
    if not (MIN_VOL <= vol <= MAX_VOL):
        return False
    up = kw.upper()
    if not any(w in kw for w in FASHION_WORDS):
        return False
    if any(w in kw for w in EXCLUDE_WORDS):
        return False
    if any(b.upper() in up for b in BRANDS if len(b) >= 2):
        return False
    return True


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_row(it):
    pc, mo = to_int(it["monthlyPcQcCnt"]), to_int(it["monthlyMobileQcCnt"])
    vol = pc + mo
    clk = to_float(it.get("monthlyAvePcClkCnt")) + to_float(it.get("monthlyAveMobileClkCnt"))
    kw = it["relKeyword"]
    ctr = clk / vol * 100 if vol else 0
    depth = to_float(it.get("plAvgDepth"))
    has_word = any(w in kw.replace("얼룩", "") for w in INFO_WORDS)   # '얼룩' 안의 '룩'은 코디 뜻이 아님
    low_ad = (ctr < CTR_LOW) + (depth < DEPTH_LOW)
    # 정보 단어(코디·관리·차이 등)가 있고, 클릭률·광고 깊이 중 하나 이상이 낮으면 정보형. 나머지는 구매형
    strong = any(w in kw for w in STRONG_INFO_WORDS) and not any(w in kw for w in PRODUCT_WORDS)
    product = any(w in kw for w in PRODUCT_WORDS)   # 제거기·세제 등 제품 검색은 무조건 구매형
    kind = "정보형" if not product and (strong or (has_word and low_ad >= 1)) else "구매형"
    return {
        "키워드": kw, "월검색량": vol, "PC": pc, "모바일": mo,
        "모바일비중": round(mo / vol * 100, 1) if vol else 0,
        "월평균클릭수": round(clk, 1), "클릭률": round(ctr, 2),
        "광고깊이": depth, "경쟁도": it.get("compIdx", ""), "유형": kind,
    }


def care_key(kw):
    """애드포스트 모드에서 관리 키워드면 '#소재#방법' 키를, 아니면 None."""
    if any(w in kw for w in PRODUCT_WORDS):
        return None
    action = next((a for a, ws in CARE_ACTIONS if any(w in kw.replace("캐주얼룩", "") for w in ws)), None)
    if not action:
        return None
    if action in CARE_ONE_TOPIC:   # 보풀·얼룩은 소재 상관없이 한 주제
        return f"#{CARE_ONE_TOPIC[action]}#{action}"
    fam = next((f for f, ws in CARE_FAMILIES if any(w in kw for w in ws)), "옷")
    return f"#{fam}#{action}"


def core(kw):
    if ADPOST and (ck := care_key(kw)):
        return ck
    s = kw
    for a, b in SYNONYMS.items():
        s = s.replace(a, b)
    for m in sorted(MODIFIERS, key=len, reverse=True):
        s = s.replace(m, "")
    if not s and "코디" in kw:   # '겨울코디', '여자겨울코디' 처럼 꾸밈말만 남으면 → '코디' 한 주제
        return "코디"
    return s or kw


def group(rows):
    g = defaultdict(list)
    for r in rows:
        g[core(r["키워드"])].append(r)
    # 작은 묶음(2개 이하)은 그 이름을 포함하는 더 큰 묶음에 합치기 (예: 스웨이드블루종 X / 롱패딩 ← 구스다운롱패딩)
    keys = sorted(g, key=lambda k: -len(g[k]))
    for k in sorted(g, key=len, reverse=True):
        if k not in g or len(g[k]) > 2 or k.startswith("#"):
            continue
        # 애드포스트 모드는 관리 주제가 작게 흩어져 있어 작은 묶음끼리도 합침
        need = 1 if ADPOST else 3
        target = next((t for t in keys if t != k and t in g and len(t) >= 3 and t in k and len(g[t]) >= need), None)
        if target:
            g[target].extend(g.pop(k))
    topics = []
    for key, members in g.items():
        members.sort(key=lambda r: -r["월검색량"])
        main, subs = members[0], members[1:6]
        used = [main] + subs
        total = sum(r["월검색량"] for r in used)
        info_vol = sum(r["월검색량"] for r in used if r["유형"] == "정보형")
        kinds = {r["유형"] for r in used}
        if kinds == {"정보형"}:
            kind = "정보형"
        elif kinds == {"구매형"}:
            kind = "구매형"
        else:
            kind = "정보형(+구매)" if info_vol >= total / 2 else "구매형(+정보)"
        topics.append({
            "key": key, "main": main, "subs": subs, "total": total, "kind": kind,
            "info_share": info_vol / total,
            "mobile": sum(r["모바일"] for r in used) / total * 100,
            "comp": sum(COMP_SCORE.get(r["경쟁도"], 0.6) * r["월검색량"] for r in used) / total,
            "depth": sum(r["광고깊이"] * r["월검색량"] for r in used) / total,
            "ctr": sum(r["클릭률"] * r["월검색량"] for r in used) / total,
        })
    return topics


def score_adpost(t):
    # 정보형 40 = 주제 안 정보형 검색량 비율 25 + 메인 키워드가 정보형이면 15
    s_kind = 25 * t["info_share"] + (15 if t["main"]["유형"] == "정보형" else 0)
    # 메인 검색량 25: 1,000~20,000 만점. 그보다 적으면 300까지 줄어들고, 많으면 50,000에서 12점
    v = t["main"]["월검색량"]
    lo, hi = MAIN_BEST
    if v < lo:
        s_main = 25 * max(math.log(v / 300), 0) / math.log(lo / 300)
    elif v > hi:
        s_main = 25 - 13 * min(math.log(v / hi) / math.log(50_000 / hi), 1)
    else:
        s_main = 25
    # 낮은 경쟁도 20 = 광고 경쟁도 12 + 광고 깊이 8
    s_comp = 12 * t["comp"] + 8 * min(max((15 - t["depth"]) / 10, 0), 1)
    # 모바일 10
    s_mob = 10 * min(max((t["mobile"] - 70) / 25, 0), 1)
    # 주제 전체 검색량 5 (서브까지 합친 유입 크기)
    tv = min(max(t["total"], 1_000), 100_000)
    s_tot = 5 * math.log(tv / 1_000) / math.log(100)
    # 브랜드 비교 감점: 브랜드·명품·순위·비교 키워드의 검색량 비율 × 최대 -20
    used = [t["main"]] + t["subs"]
    bvol = sum(r["월검색량"] for r in used if any(w in r["키워드"] for w in BRAND_CMP_WORDS))
    s_brand = -20 * bvol / t["total"]
    return round(s_kind), round(s_main), round(s_comp), round(s_mob), round(s_tot), round(s_brand)


def score(t):
    if ADPOST:
        return score_adpost(t)
    # 검색량 35: 주제 전체 검색량 500 → 0점, 100,000 → 35점 (로그 비례)
    v = min(max(t["total"], 500), 100_000)
    s_vol = 35 * (math.log(v) - math.log(500)) / (math.log(100_000) - math.log(500))
    # 낮은 경쟁도 25 = 광고 경쟁도 15 (낮음1/중간0.6/높음0.2, 검색량 비중 평균) + 광고 깊이 10 (5 이하 만점, 15 이상 0점)
    s_comp = 15 * t["comp"] + 10 * min(max((15 - t["depth"]) / 10, 0), 1)
    # 모바일 비중 15: 70% 이하 0점 → 95% 이상 15점 (블로그는 모바일 검색에서 더 잘 보임)
    s_mob = 15 * min(max((t["mobile"] - 70) / 25, 0), 1)
    # 유형 25: 주제 안 정보형 키워드의 검색량 비율. 전부 구매형 10점 → 전부 정보형 25점
    #   (블로그는 정보 검색에서 상위 노출·애드포스트가 유리하고, 구매 키워드는 쇼핑 탭과 경쟁)
    s_kind = 10 + 15 * t["info_share"]
    return round(s_vol), round(s_comp), round(s_mob), round(s_kind)


def title(t):
    m = t["main"]["키워드"]
    if t["key"].startswith("#"):
        fam, action = t["key"][1:].split("#")
        if action == "보풀":
            return "니트·코트 보풀 제거, 옷 상하지 않게 없애는 법 + 보풀 덜 나는 니트 고르는 기준"
        return {
            "보풀": f"{fam} 보풀 제거, 옷 상하지 않게 없애는 법 + 보풀 덜 나는 옷 고르는 기준",
            "얼룩": f"{fam} 얼룩 제거, 세탁소 가기 전 집에서 먼저 해볼 것 3가지",
            "보관": f"{fam} 보관법, 내년에도 새것처럼 입는 옷장 정리 방법",
            "세탁·관리": f"{fam} 세탁·관리법, 집에서 해도 망치지 않는 순서 — 10년 차 MD가 알려드려요",
        }[action]
    item = t["key"] if len(t["key"]) >= 2 else core(m)
    for w in ["세탁법", "세탁", "보관법", "보관", "관리법", "관리", "보풀제거", "매는법"]:
        item = item.replace(w, "")
    item = item or m
    sub = next((s["키워드"] for s in t["subs"] if core(s["키워드"]) == item and s["키워드"] != m), None)
    words = " ".join(r["키워드"] for r in [t["main"]] + t["subs"])
    if t["key"] == "코디":
        return f"{m}, 40·50대가 가진 옷으로 세련돼 보이는 겨울 코디 공식 5가지"
    if "보풀" in words:
        return f"{item} 보풀 제거, 옷 상하지 않게 없애는 법 + 보풀 덜 나는 옷 고르는 기준"
    if "세탁" in words:
        return f"{item} 세탁, 집에서 해도 망치지 않는 순서 — 10년 차 MD가 알려드려요"
    if "보관" in words:
        return f"{item} 보관법, 내년에도 새것처럼 입는 정리 방법"
    if "매는법" in words:
        return f"{item} 매는 법, 40·50대 얼굴이 환해 보이는 3가지 ({m} 고르는 기준까지)"
    if "관리" in words or "세탁" in words:
        return f"{item} 관리법, 10년 차 MD가 알려주는 오래 입는 방법 ({m})"
    if "차이" in words:
        return f"{m} 차이, 헷갈리면 이것만 보세요 — 10년 차 MD 정리"
    if "코디" in words or "룩" in words:
        return f"{m} 40·50대 코디, 어색하지 않게 입는 3가지 기준"
    if "추천" in words:
        return f"{m} 추천, 동대문 10년 차 MD가 고르는 기준 5가지"
    if t["kind"].startswith("구매형"):
        extra = f" ({sub})" if sub else ""
        return f"{m} 고르는 법, 40·50대가 사기 전에 꼭 볼 소재·디자인 체크리스트{extra}"
    return f"{m} 완벽 정리, 40·50대에게 맞는 선택 기준"


def previous_volumes():
    today = date.today().isoformat()
    files = sorted(p for p in REPORTS.glob(f"{PREFIX}*_keywords.csv")
                   if p.name[len(PREFIX):len(PREFIX) + 10] < today)
    if not files:
        return None, {}
    prev = files[-1]
    vols = {r["키워드"]: int(r["월검색량"]) for r in csv.DictReader(open(prev, encoding="utf-8-sig"))}
    return prev.name[len(PREFIX):len(PREFIX) + 10], vols


def change(kw, vol, prev):
    if not prev:
        return ""
    if kw not in prev:
        return "NEW"
    old = prev[kw]
    pct = (vol - old) / old * 100 if old else 0
    if pct >= 10:
        return f"▲{pct:.0f}%"
    if pct <= -10:
        return f"▼{-pct:.0f}%"
    return ""


def main():
    if not (API_KEY and SECRET and CUSTOMER_ID):
        sys.exit("[오류] .env 에 NAVER_AD_API_KEY / NAVER_AD_SECRET / NAVER_AD_CUSTOMER_ID 가 필요합니다.")
    global PREFIX, TOP_N
    seeds = SEEDS + ADPOST_SEEDS if ADPOST else SEEDS
    if ADPOST:
        PREFIX, TOP_N = "blog_topics_adpost_", ADPOST_TOP_N
    today = date.today().isoformat()
    REPORTS.mkdir(exist_ok=True)

    print(f"1) 씨앗 {len(seeds)}개로 연관 키워드 모으는 중...")
    raw = fetch_related(seeds)
    rows = [r for r in map(build_row, raw.values()) if keep(r["키워드"], r["월검색량"])]
    # 2차 확장: 1차 상위 주제의 메인 키워드로 한 번 더 모아 서브 키워드를 채움
    first = group(rows)
    for t in first:
        t["score"] = sum(score(t))
    hints = [t["main"]["키워드"] for t in sorted(first, key=lambda t: -t["score"])[:SECOND_ROUND]]
    hints = [h for h in hints if h not in seeds]
    print(f"   2차 확장: 상위 주제 메인 키워드 {len(hints)}개로 한 번 더 수집...")
    raw.update(fetch_related(hints))
    rows = [r for r in map(build_row, raw.values()) if keep(r["키워드"], r["월검색량"])]
    print(f"2) 필터 후 {len(rows)}개 (전체 수집 {len(raw):,}개)")

    prev_date, prev = previous_volumes()
    for r in rows:
        r["변화"] = change(r["키워드"], r["월검색량"], prev)

    topics = group(rows)
    for t in topics:
        parts = score(t)
        t.update(parts=parts, score=sum(parts), title=title(t))
    topics.sort(key=lambda t: -t["score"])
    print(f"3) 주제 {len(topics)}개로 묶음")

    # --- 키워드 전체 CSV (다음 실행 때 비교 기준)
    kw_csv = REPORTS / f"{PREFIX}{today}_keywords.csv"
    cols = ["키워드", "유형", "월검색량", "PC", "모바일", "모바일비중", "월평균클릭수", "클릭률", "광고깊이", "경쟁도", "변화", "주제"]
    topic_of = {r["키워드"]: t["main"]["키워드"] for t in topics for r in [t["main"]] + t["subs"]}
    with open(kw_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: -r["월검색량"]):
            w.writerow({**r, "주제": topic_of.get(r["키워드"], "")})

    # --- 주제 전체 CSV
    tp_csv = REPORTS / f"{PREFIX}{today}_topics.csv"
    with open(tp_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["순위", "점수", "메인키워드", "서브키워드", "유형", "주제검색량", "모바일비중", "평균클릭률",
                    "평균광고깊이", "경쟁도점수", "제목예시"])
        for i, t in enumerate(topics, 1):
            w.writerow([i, t["score"], t["main"]["키워드"], " / ".join(s["키워드"] for s in t["subs"]), t["kind"],
                        t["total"], f"{t['mobile']:.0f}%", f"{t['ctr']:.2f}%", f"{t['depth']:.1f}",
                        f"{t['comp']:.2f}", t["title"]])

    # --- 상위 20 마크다운
    def kw_txt(r):
        c = f" {r['변화']}" if r["변화"] else ""
        return f"{r['키워드']}({r['월검색량']:,}{c})"

    rising = sorted((r for r in rows if r["변화"].startswith("▲")),
                    key=lambda r: -int(r["변화"][1:-1]))
    if ADPOST:
        head = f"# 애드포스트 우선순위 TOP {TOP_N} ({today})"
        score_desc = ("- 점수(100) = 정보형 40(정보형 검색량 비율 25 + 메인이 정보형 15) + 메인 검색량 25"
                      f"({MAIN_BEST[0]:,}~{MAIN_BEST[1]:,} 만점) + 낮은 경쟁도 20 + 모바일 10 + 주제 전체 검색량 5"
                      " − 브랜드 비교 감점(브랜드·명품·순위·비교 키워드 비율 × 최대 20)")
        score_note = "점수 괄호: 정보형/메인검색량/경쟁도/모바일/주제검색량/브랜드감점"
    else:
        head = f"# 블로그 주제 TOP {TOP_N} — 검색광고 API ({today})"
        score_desc = "- 점수(100) = 검색량 35 + 낮은 경쟁도 25(광고 경쟁도 15 + 광고 깊이 10) + 모바일 비중 15 + 유형 25(정보형 검색량 비율: 전부 구매형 10 → 전부 정보형 25)"
        score_note = "점수 괄호: 검색량/경쟁도/모바일/유형"
    lines = [
        head, "",
        f"- 출처: 네이버 검색광고 키워드도구 API (최근 30일 기준 월 검색량), 조회일 {today}",
        f"- 씨앗 {len(seeds)}개 (+ 2차 확장 {len(hints)}개) → 연관 키워드 {len(raw):,}개 수집 → 필터 후 {len(rows)}개 → 주제 {len(topics)}개",
        f"- 필터: 월 검색량 {MIN_VOL:,}~{MAX_VOL:,}, 패션 관련, 남성·아동·학생·브랜드명 제외 (브랜드는 목록 기준이라 일부 남을 수 있음)",
        f"- 유형: 클릭률 {CTR_LOW}% 미만·광고 깊이 {DEPTH_LOW} 미만이면 광고 신호 낮음. 정보 단어(코디·관리·차이·추천 등)+광고 신호 낮음 → 정보형",
        score_desc,
        "- 유형 칸: 정보형(+구매) = 정보형이 절반 이상이고 구매 키워드도 섞인 주제 → 정보 글에 쿠팡 링크를 곁들이기 좋음",
        f"- 지난 결과 비교: {prev_date + ' 대비 (▲ 10% 이상 상승, NEW 새로 등장)' if prev_date else '첫 실행이라 비교 없음 — 다음 실행부터 표시'}",
        "",
        "| 순위 | 메인 키워드 | 서브 키워드 | 유형 | 주제 검색량 | 모바일 | 클릭률 | 광고깊이 | 점수 | 제목 예시 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    full = [t for t in topics if len(t["subs"]) >= 3]   # 메인 1 + 서브 3~5 를 갖춘 주제만 순위에
    for i, t in enumerate(full[:TOP_N], 1):
        subs = ", ".join(kw_txt(s) for s in t["subs"]) or "-"
        lines.append(
            f"| {i} | **{kw_txt(t['main'])}** | {subs} | {t['kind']} | {t['total']:,} | {t['mobile']:.0f}% | "
            f"{t['ctr']:.2f}% | {t['depth']:.1f} | **{t['score']}** ({'/'.join(map(str, t['parts']))}) | {t['title']} |")
    lines += ["", score_note, "",
              "## 참고: 서브 키워드가 3개 미만이라 순위에서 뺀 큰 키워드 (검색량 순)", ""]
    solo = sorted((t for t in topics if len(t["subs"]) < 3), key=lambda t: -t["total"])[:10]
    lines += [f"- {kw_txt(t['main'])} {', '.join(kw_txt(x) for x in t['subs'])} — {t['kind']}, 점수 {t['score']}" for t in solo]
    lines += [""]
    if prev_date:
        lines += [f"## 검색량이 오른 키워드 ({prev_date} 대비)", ""]
        lines += [f"- {r['키워드']}: {prev[r['키워드']]:,} → {r['월검색량']:,} ({r['변화']})" for r in rising[:30]] or ["- 없음"]
    md = REPORTS / f"{PREFIX}{today}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "\n".join(lines[10:10 + TOP_N + 2]))
    print(f"\n저장: {md.relative_to(ROOT)}\n      {tp_csv.relative_to(ROOT)}\n      {kw_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
