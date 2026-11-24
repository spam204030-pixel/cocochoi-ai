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

## 설치와 실행 (윈도우)
자세한 순서와 확인 체크리스트: **`docs/WINDOWS_CHECK.md`**

요약
1. uv 설치(처음 한 번): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. FFmpeg 설치(처음 한 번): `winget install Gyan.FFmpeg`
3. PowerShell을 다시 열고 프로그램 폴더에서 `uv run factory` → 브라우저에서 http://localhost:8000
4. 끄기: `Ctrl + C` / 테스트: `uv run pytest`

## 지금 되는 것 (Phase 0, 버전 0.0)
- 현황판(신규·제작 중·검수 대기·완료), 제품 등록·수정, 사진·영상 업로드(썸네일·길이·해상도 자동 기록, 출처 메모)
- 콘텐츠 만들기(소재 선택, 길이·스타일·나레이션·플랫폼·광고 표기 설정)
- 시험 실행: 8단계 진행·일시정지·재개·취소·다시 실행, 껐다 켜도 이어서 진행 (가짜 작업, AI 비용 0원)
- 실제 AI 분석·영상 제작은 Phase 1부터 단계별로 연결
