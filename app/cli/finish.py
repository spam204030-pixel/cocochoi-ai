"""/기획 마지막 단계: Claude 가 쓴 분석.json·대본.json 을 검사하고 읽기 쉬운 결과 파일을 만든다.

사용: uv run python -m app.cli.finish outputs/<날짜>_<상품폴더>
만드는 파일: 분석.md, 기획.md, 대본.md, 자막.srt, 편집지시표.csv  (시간은 코드가 글자 수로 계산한 예상값)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from app.prompts.schemas import AnalysisResult, ScriptResult

CHARS_PER_SEC = 6.5  # 한국어 나레이션 읽기 속도 (추정, 캡컷에서 실제 녹음에 맞춰 조정)
MIN_SEC = 1.2
BANNED = ("노출 보장", "상위 노출", "무조건 뜨", "10년 차", "10년차")
COUPANG_NOTICE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로"
SRC = {"user_input": "입력", "visible": "화면", "inferred": "추정"}


def seconds(text: str) -> float:
    return max(len(re.sub(r"\s", "", text)) / CHARS_PER_SEC, MIN_SEC)


def ts(sec: float) -> str:
    ms = round(sec * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def scene_label(scenes: dict, sid: int) -> str:
    v, s = scenes[sid]
    return f"[{sid}] 영상{v['번호']}({Path(v['파일']).name}) {s['시작']:.1f}-{s['끝']:.1f}초"


def load(out: Path, name: str, model, scene_ids):
    path = out / name
    if not path.exists():
        raise SystemExit(f"{name} 이 없습니다")
    try:
        return model.model_validate(
            json.loads(path.read_text("utf-8-sig")), context={"segment_ids": scene_ids}
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SystemExit(f"{name} 형식 오류 — 고친 뒤 다시 실행하세요:\n{exc}") from None


def finish(out: Path) -> list[str]:
    """검사 통과 시 만든 파일 목록. 실패하면 SystemExit(이유)."""
    scenes_data = json.loads((out / "장면.json").read_text("utf-8"))
    scenes = {s["id"]: (v, s) for v in scenes_data["영상"] for s in v["장면"]}
    ids = list(scenes)
    analysis = load(out, "분석.json", AnalysisResult, ids)
    script = load(out, "대본.json", ScriptResult, ids)
    if not 1 <= script.selected <= len(script.plans):
        raise SystemExit("대본.json 형식 오류: selected 가 기획안 번호 범위를 벗어남")

    a = analysis
    md = [f"# 상품·소비자 분석\n\n**{a.identity}**\n", "## 구매 포인트"]
    md += [
        f"- {p.point} `{SRC[p.source]}` — {p.situation}"
        + (f" (장면 {p.segment_ids})" if p.segment_ids else "")
        for p in a.purchase_points
    ]
    md += ["\n## 구매 이유", *[f"- {r}" for r in a.buy_reasons], "\n## 구매 고민 → 답"]
    md += [f"- {w.worry} → {w.answer} `{SRC[w.source]}`" for w in a.worries]
    md += [
        "\n## 타깃",
        *[f"- {t.situation} ({t.persona}, 가능성 {t.likelihood}) — {t.reason}" for t in a.targets],
    ]
    md += ["\n## 특징", *[f"- {f.text} `{SRC[f.source]}` ({f.evidence})" for f in a.features]]
    if a.differentiators:
        md += ["\n## 차별점", *[f"- {f.text} `{SRC[f.source]}`" for f in a.differentiators]]
    md += ["\n## 대표님 확인 필요", *[f"- {q}" for q in a.needs_confirmation]]
    md += ["\n## 쓰면 안 되는 표현", *[f"- {b}" for b in a.banned_claims], "\n## 장면별 분석"]
    for sc in a.scenes:
        v, s = scenes[sc.segment_id]
        md.append(
            f"- **[{sc.segment_id}] 영상{v['번호']} {s['시작']:.1f}–{s['끝']:.1f}초** {sc.content}"
            f"{'' if sc.usable else ' ⚠사용 비추천'}\n  - 보이는 것: {', '.join(sc.visible_facts)}"
            + (f"\n  - 추정: {', '.join(sc.inferred)}" if sc.inferred else "")
        )
    (out / "분석.md").write_text("\n".join(md) + "\n", "utf-8")

    sel = script.plans[script.selected - 1]
    plan = ["# 후킹 5개", *[f"{i}. {h}" for i, h in enumerate(script.hooks, 1)], "\n# 기획안"]
    for i, p in enumerate(script.plans, 1):
        mark = " ✅ 선정" if i == script.selected else ""
        plan.append(
            f"\n## {i}. {p.title} — {p.score}점{mark}\n- 후킹: {p.hook}"
            f"\n- 스토리: {p.story}\n- 평가: {p.reason}"
        )
    plan.append(f"\n**선정 이유:** {script.selected_reason}")
    (out / "기획.md").write_text("\n".join(plan) + "\n", "utf-8")

    t, rows, srt, body = (
        0.0,
        [],
        [],
        [f"# 나레이션 대본 — {sel.title}\n", "(예상 길이는 글자 수로 계산한 추정값)\n"],
    )
    for ln in script.lines:
        d = seconds(ln.narration)
        srt.append(f"{ln.no}\n{ts(t)} --> {ts(t + d)}\n{ln.subtitle}\n")
        src = "; ".join(scene_label(scenes, i) for i in ln.scene_ids)
        rows.append(
            [ln.no, f"{t:.1f}", f"{t + d:.1f}", src, ln.narration, ln.subtitle, ln.proof, ln.edit_note]
        )
        body.append(
            f"{ln.no}. [{ln.role}] {ln.narration}\n   - 자막: {ln.subtitle}"
            f"\n   - 장면 {ln.scene_ids}: {ln.proof} (약 {d:.1f}초)"
        )
        t += d
    body.append(f"\n총 약 {t:.0f}초")
    (out / "대본.md").write_text("\n".join(body) + "\n", "utf-8")
    (out / "자막.srt").write_text("\n".join(srt), "utf-8")
    with (out / "편집지시표.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "순서",
                "시작(초, 예상)",
                "끝(초, 예상)",
                "사용할 장면",
                "나레이션",
                "자막",
                "근거(화면)",
                "편집 메모",
            ]
        )
        w.writerows(rows)

    warnings = []
    cap = out / "캡션.md"
    if cap.exists():
        text = cap.read_text("utf-8")
        warnings += [f"캡션.md 금지 표현: {b}" for b in BANNED if b in text]
        if "coupang" in scenes_data["상품정보"].lower() and COUPANG_NOTICE not in text:
            warnings.append("캡션.md: 쿠팡 대가성 문구 없음")
    else:
        warnings.append("캡션.md 가 아직 없습니다")
    return warnings


def main() -> None:
    ap = argparse.ArgumentParser(description="/기획 결과 검사·파일 생성")
    ap.add_argument("folder", type=Path)
    out = ap.parse_args().folder
    warnings = finish(out)
    print("완료: 분석.md 기획.md 대본.md 자막.srt 편집지시표.csv")
    for w in warnings:
        print("⚠", w)
    sys.exit(1 if warnings else 0)


if __name__ == "__main__":
    main()
