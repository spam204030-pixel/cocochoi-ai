# 윈도우 PC 확인 방법 (Phase 0 완료 확인)

처음 한 번은 20~30분 정도 걸립니다. 이후에는 4번(켜기)만 하면 됩니다.

## 1. 프로그램 받기

1. GitHub `spam204030-pixel/cocochoi-ai` 저장소에 들어갑니다.
2. 왼쪽 위 브랜치 선택에서 **`factory`** 를 고릅니다. (`v0.0` 태그를 골라도 같습니다)
3. 초록색 **Code → Download ZIP** 을 누릅니다.
4. 압축을 **`C:\cocochoi-ai`** 에 풉니다.
   - 바탕화면·문서 폴더는 피해 주세요. OneDrive가 동기화하면서 데이터 파일을 잠가 오류가 날 수 있습니다.
   - 압축을 풀면 `C:\cocochoi-ai\cocochoi-ai-factory\` 처럼 폴더가 한 겹 더 생길 수 있습니다. 그 안에 `pyproject.toml` 파일이 있는 폴더가 프로그램 폴더입니다.

## 2. uv 설치 (처음 한 번)

1. 시작 메뉴에서 **PowerShell** 을 엽니다.
2. 아래 한 줄을 붙여넣고 Enter:
   ```
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. PowerShell 을 **닫았다가 다시 엽니다.**
4. `uv --version` 을 입력해 버전이 나오면 완료입니다.

파이썬은 따로 설치하지 않아도 됩니다. 처음 실행할 때 uv가 필요한 버전(3.13)을 자동으로 받습니다.

## 3. FFmpeg 설치 (처음 한 번)

1. PowerShell 에서:
   ```
   winget install Gyan.FFmpeg
   ```
2. PowerShell 을 **닫았다가 다시 엽니다.**
3. `ffmpeg -version` 을 입력해 버전이 나오면 완료입니다.

`winget` 이 없다고 나오면 Microsoft Store 에서 "앱 설치 관리자(App Installer)"를 업데이트한 뒤 다시 해 주세요.

## 4. 프로그램 켜기

```
cd C:\cocochoi-ai\프로그램-폴더
uv run factory
```

- 처음에는 부품을 내려받느라 1~3분 걸립니다.
- "실행 중 → 브라우저에서 http://localhost:8000 을 여세요"가 보이면 브라우저(크롬·엣지)로 http://localhost:8000 을 엽니다.
- 끌 때: PowerShell 에서 `Ctrl + C`

## 5. 확인할 것 (체크리스트)

- [ ] 현황판이 열리고, 아래 줄에 "✅ 정상 · 버전 0.0 · FFmpeg: 정상"이 보인다
- [ ] 제품 → **+ 새 제품 등록** → 이름만 넣고 등록된다
- [ ] 제품 화면에서 휴대폰으로 찍은 사진 3장, 영상 2개를 끌어다 놓으면 썸네일·길이·해상도가 보인다
- [ ] **이 제품으로 콘텐츠 만들기** → 그대로 **콘텐츠 만들기**
- [ ] **▶ 시험 실행 시작** → 8단계가 차례로 ✅ 로 바뀐다 (약 15초)
- [ ] 진행 중 **일시정지** → **재개** 가 된다
- [ ] 다 끝나면 현황판 **검수 대기** 칸에 ⚠ 카드로 보인다
- [ ] 진행 중에 PowerShell 창을 닫았다가 다시 켜면(4번) 이어서 끝까지 진행된다
- [ ] (선택) 휴대폰을 같은 와이파이에 연결해 접속하는 것은 Phase 0 범위가 아닙니다

## 6. 테스트 (선택)

```
uv run pytest
```
모두 passed 로 끝나면 정상입니다. FFmpeg 가 없으면 영상 관련 테스트는 skipped 로 건너뜁니다.

## 문제가 생기면

- 화면에 오류 번호가 보이면 그 번호와 `storage\logs\factory.log` 파일을 알려주세요.
- `uv` 나 `ffmpeg` 를 찾을 수 없다고 나오면 PowerShell 을 닫았다가 다시 열어 보세요.
- "포트가 사용 중"이라고 나오면 이미 켜져 있는 PowerShell 창이 있는지 확인하세요.
