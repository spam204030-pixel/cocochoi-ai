# COCOCHOI AI 콘텐츠 엔진

## 사용법 (Claude Code에서)
1. `/트렌드` — 오늘 만들 콘텐츠 주제 TOP 5 추천 → `reports/`에 저장
2. `/만들기 1 https://link.coupang.com/...` — 1번 주제로 블로그·쇼츠·캡션 생성 → `outputs/`에 저장
3. 본 키워드나 아이디어는 `data/memo.md`에 적어두기
4. 발행한 콘텐츠 숫자는 `data/performance.csv`에 기록

규칙은 `CLAUDE.md`, 사업 방향은 `docs/BUSINESS.md`

---

# COCOCHOI AI CONTENT FACTORY (개발 중)

제품과 영상·사진 소재를 넣으면 판매 숏폼 영상과 플랫폼 게시물을 만드는 프로그램입니다.
설계서: `docs/DESIGN.md` · 변경 기록: `docs/CHANGELOG.md`

## 처음 한 번만 (윈도우)
1. PowerShell을 열고 uv 설치:
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. PowerShell을 닫았다가 다시 열기
3. 이 폴더로 이동: `cd 내려받은-폴더-경로\cocochoi-ai`

## 실행
- 프로그램 켜기: `uv run factory` → 브라우저에서 http://localhost:8000
- 끄기: PowerShell에서 `Ctrl + C`
- 테스트: `uv run pytest`
