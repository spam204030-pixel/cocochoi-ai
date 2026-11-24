# 변경 기록

## 2026-11-24 — 작업 0-6 파일 업로드

- 제품 상세 화면에 사진·영상 업로드: 끌어다 놓기 또는 눌러서 고르기, 여러 개 동시, 진행률 표시 (자바스크립트가 꺼져 있어도 올리기 가능)
- 저장 규칙: `storage/assets/<번호>/original.<확장자>` + `thumb.jpg`(가로 320px). 원래 파일 이름(한글)은 DB에만 기록, 디스크에는 영문 이름 (윈도우 경로 문제 방지)
- 업로드할 때 FFmpeg로 종류·길이·가로세로·fps·소리 유무를 읽어 DB에 저장. 영상은 "영상 소재(샤오홍슈 등)" / "직접 촬영" 구분
- 같은 파일(내용 동일) 중복 업로드 차단, 형식 제한(사진 jpg·png·webp·heic, 영상 mp4·mov·m4v·webm), 파일당 최대 500MB(`.env`의 MAX_UPLOAD_MB로 변경 가능), 깨진 파일 거절. 여러 개 중 일부가 실패해도 나머지는 올라감. 실패한 파일은 디스크에 남지 않음
- 출처 URL·메모 입력(업로드 때 또는 파일별로 나중에), 파일 삭제(확인 창, 콘텐츠에 쓰인 파일은 삭제 불가)
- API: `/api/products/{id}/assets`(올리기·목록), `/api/assets/{id}`(출처 수정·삭제), 파일 보기 `/media/{id}/thumb`, `/media/{id}/file`
- 오류 코드 4개 추가: ASSET_DUPLICATE, ASSET_IN_USE, UNSUPPORTED_FILE, FILE_TOO_LARGE

## 2026-11-24 — 작업 0-5 제품 관리

- 제품 화면: 목록(최신순, 검색), 등록(필수는 제품명만), 상세, 수정, 삭제(확인 창). 입력 오류는 칸별 한국어 안내, 입력한 값 유지
- 제품 API: `/api/products` 등록·목록·조회·수정(보낸 칸만)·삭제
- 가격은 "19,800원"처럼 쉼표·원을 붙여도 숫자로 인식, 주요 특징은 한 줄에 하나씩 입력
- 콘텐츠(프로젝트)에 쓰인 제품은 삭제 불가 (오류 PRODUCT_IN_USE). 삭제해도 연결된 사진·영상 기록은 남음
- 공통 화면 틀(`base.html`, 상단 메뉴), 첫 화면에 "제품 관리" 링크
- 부품 추가: python-multipart (화면 입력값 읽기, 무료)

## 2026-11-24 — 작업 0-4 FFmpeg 연결 확인

- `app/media/probe.py`: FFmpeg·ffprobe 설치 확인(버전 표시), 영상·사진·음원 정보 읽기(종류, 길이, 가로·세로, fps, 소리 유무, 코덱, 파일 크기). 휴대폰 세로 영상의 회전 정보 반영
- FFmpeg가 없으면 첫 화면에 윈도우 설치 방법(winget) 안내, `/api/health`에 FFmpeg 상태 표시
- 오류 코드 2개 추가: FFMPEG_MISSING, MEDIA_UNREADABLE (한국어 안내)
- `.env`에 FFMPEG_PATH·FFPROBE_PATH 선택 설정 추가 (자동으로 못 찾을 때만 사용)
- 편집·렌더링 기능은 만들지 않음 (Phase 3)

## 2026-11-24 — 작업 0-3 DB 기반

- SQLite DB `storage/cocochoi.db` + SQLAlchemy + Alembic. 프로그램을 켜면 DB를 만들고 최신 구조로 맞춤 (기존 데이터 유지)
- 표 6개: products, assets, projects, project_assets, jobs, role_runs (`app/core/models.py`, 변경 기록 `migrations/versions/0001_phase0_tables.py`)
- 영상·사진은 DB에 넣지 않고 경로만 저장. 같은 파일 중복 등록 방지(file_hash)
- 기본 표를 지우는 되돌리기(downgrade)는 막아 둠
- 설계서와 다른 점: `assets`에 original_name·file_size, `products`·`projects`에 updated_at, `jobs`에 finished_at 추가 (업로드·작업 관리에 필요). `projects.brand_profile_id`는 brand_profiles 표가 생길 때까지 연결 없이 숫자만 저장
- `/api/health`에 DB 상태 추가

## 2026-11-24 — 작업 0-2 설정·오류·로그

**만든 것**
- `app/core/settings.py`: `.env` 읽기(API 키, 데이터 폴더, 서버 주소·포트, 로그 수준), 빈 값은 기본값 사용, `storage/`·`storage/logs/` 자동 생성, 쓰기 가능 여부 검사. API 키는 화면·로그에 "설정됨 / 없음"만 표시
- `app/core/errors.py`: 오류 코드 12종과 한국어 안내 문구·해결 방법을 한 곳에 모음. 모든 오류 응답 형식 통일 (`code`, `message`, `action`, `detail`, `error_id`)
- `app/core/logging.py`: `storage/logs/factory.log`에 기록 (UTF-8, 5MB마다 새 파일, 최근 5개 보관), API 키처럼 보이는 문자열은 자동으로 가림
- 오류 화면 `error.html`: 화면 주소는 한국어 안내 화면, `/api/` 주소는 JSON. 예상하지 못한 오류는 원인을 화면에 보이지 않고 오류 번호만 보여주며, 원인은 로그에 남김
- `/api/health`에 데이터 폴더 상태와 AI 키 설정 여부 추가

**0-1 파일 수정**
- `app/main.py`: 오류 처리·로그를 연결하기 위해 `create_app()` 구조로 변경. 상태 확인과 첫 화면 동작은 그대로
- `tests/test_health.py`: 실제 `storage/`를 건드리지 않도록 임시 폴더를 쓰는 테스트 방식으로 변경

**선택 설정 (`.env`에 넣을 수 있는 값, 넣지 않으면 기본값)**
- `HOST` (기본 127.0.0.1), `PORT` (기본 8000), `LOG_LEVEL` (기본 INFO), `STORAGE_DIR` (기본 storage/)

## 2026-11-24 — 작업 0-1 프로젝트 뼈대 + 테스트 환경

**만든 것**
- 프로그램 시작점(`app/main.py`), 상태 확인 주소 `/api/health`, "정상" 표시 첫 화면
- 패키지 설정(`pyproject.toml`, uv), 테스트(pytest), 코드 검사(ruff)
- 테스트: 상태 확인, 첫 화면, API 키가 저장소에 없는지, `.env`가 Git에서 제외되는지
- `.env.example`, `.gitignore`에 프로그램 데이터·영상 파일 제외 추가
- 확정 설계서 `docs/DESIGN.md`(v3.3), `docs/PROMPTS.md`(v3.3)

**설계서와 다르게 정한 것**
- 프로그램 데이터 폴더를 `data/` 대신 **`storage/`**로 변경. 이유: 기존 `data/`에는 `/트렌드` 명령이 쓰는 CSV·메모가 있어 섞이지 않게 분리. 설계서 경로도 함께 수정함

**대표 결정 사항 반영 (`CLAUDE.md`)**
- 규칙 4: 대표가 업로드한 영상·사진 소재를 편집 소재로 사용 허용. 출처 기록과 사용 판단은 대표가 함
- "10년 차 MD가 직접 골라주는 상품" 차별점 문구 삭제, 경력 내세우기 앵글 금지 추가
- 기존 `/트렌드`, `/만들기` 명령은 그대로 유지
- 콘텐츠 공장 개발 규칙 12개 추가, 실행 PC는 윈도우 기준
