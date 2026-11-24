"""/기획 1단계: 입력 폴더의 영상을 장면으로 나누고 장면 사진·격자를 만든다 (웹 프로그램·DB 불필요).

사용: uv run python -m app.cli.prepare inputs/상품폴더 [--받아쓰기]
결과: outputs/<날짜>_<상품폴더>/장면.json + _자료/ (장면 사진, 격자)
"""

import argparse
import json
from datetime import date
from pathlib import Path

from app.assets.service import PHOTO_EXTS, VIDEO_EXTS
from app.core.models import FootageSegment
from app.media.frames import labels, make_grids, measure_list
from app.media.scenes import detect_scenes

ROOT = Path(__file__).resolve().parents[2]
INFO_NAMES = ("상품정보.txt", "상품정보.md", "info.txt")


def prepare(src: Path, out: Path | None = None, transcribe: bool = False) -> Path:
    src = src.resolve()
    if not src.is_dir():
        raise SystemExit(f"폴더가 없습니다: {src}")
    out = out or ROOT / "outputs" / f"{date.today().isoformat()}_{src.name}"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src.iterdir() if p.is_file())
    info = next((p for p in files if p.name in INFO_NAMES), None)
    photos = [p for p in files if p.suffix.lower() in PHOTO_EXTS]
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXTS]
    data = {
        "상품정보": info.read_text("utf-8-sig") if info else "",
        "상품사진": [str(p) for p in photos],
        "영상": [],
    }
    next_id = 1
    for v, video in enumerate(videos, 1):
        spans = detect_scenes(video)
        segs = []
        for i, (start, end) in enumerate(spans, 1):
            segs.append(
                FootageSegment(id=next_id, idx=i, start=start, end=end, duration=round(end - start, 3))
            )
            next_id += 1
        folder = Path("_자료") / f"영상{v}"
        measure_list(segs, video, out, folder)
        grids = make_grids(segs, out / folder, out)
        if transcribe:
            from app.media.transcribe import assign, choose_model, whisper_transcribe

            assign(whisper_transcribe(video, choose_model("auto")), segs)
        data["영상"].append(
            {
                "번호": v,
                "파일": str(video),
                "길이": spans[-1][1] if spans else 0,
                "격자": [str(g) for g in grids],
                "장면": [
                    {
                        "id": s.id,
                        "장면": s.idx,
                        "시작": s.start,
                        "끝": s.end,
                        "사진": str(out / s.thumb_path) if s.thumb_path else None,
                        "경고": labels(s),
                        "원본음성": getattr(s, "transcript_zh", None),
                    }
                    for s in segs
                ],
            }
        )
    (out / "장면.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="/기획 장면 준비")
    ap.add_argument("folder", type=Path)
    ap.add_argument(
        "--받아쓰기", dest="transcribe", action="store_true", help="중국어 받아쓰기 (선택 설치 필요)"
    )
    args = ap.parse_args()
    out = prepare(args.folder, transcribe=args.transcribe)
    data = json.loads((out / "장면.json").read_text("utf-8"))
    scenes = sum(len(v["장면"]) for v in data["영상"])
    print(f"완료: {out}")
    print(
        f"상품정보 {'있음' if data['상품정보'] else '없음'} · 사진 {len(data['상품사진'])}장 · "
        f"영상 {len(data['영상'])}개 · 장면 {scenes}개"
    )


if __name__ == "__main__":
    main()
