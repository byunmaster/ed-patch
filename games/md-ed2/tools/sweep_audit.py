"""전 대사 조판 전수 자동 필터 — 촬영 PNG(잉크 bbox)와 정본 문안(script/·sysmsg·battle)에서 객관 결함 후보를 뽑는다(마스터 10-30).

    python3 tools/sweep_audit.py SWEEP_DIR            # SWEEP_DIR/scene/**.png 를 읽고 anomalies.tsv · SUMMARY.txt 를 쓴다

화면(PNG, 대사창 테두리 안 x 24~298 · y 146~208 의 흰·주황 잉크) — 하네스 실측(1500장): 글 시작 x=57 · 오른쪽 끝 ≤ 266 · 줄 간격 16(화자 줄 포함 4줄까지 정상).
 · 빈 쪽·다른 창 — 글 잉크 0(상자 없는 획득 문구 따위 — 눈으로 본다)     · 넘침(오른쪽) — 글 오른쪽 끝 > 272
문안(`ours`) — 일본어 가나·한자 잔재 · 일본식 부호(、。・，．) · 전각 느낌표·물음표·숫자 · 겹 공백 · 줄·쪽 머리 공백 · 쪽 끝 공백 · 빈 쪽.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")
HANJA = re.compile(r"[一-鿿]")
JPPUNCT = re.compile(r"[、。・，．]")
FULL = re.compile(r"[！？０-９]")
TAG = re.compile(r"<[0-9a-fA-F:]+>|<1e>|<04>")


def png_checks(root: Path, rows: list):
    n = 0
    for p in sorted(root.rglob("*.png")):
        n += 1
        a = np.asarray(Image.open(p).convert("RGB")).astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        ink = ((r > 215) & (g > 215) & (b > 215)) | ((r > 215) & (g > 140) & (g < 215) & (b < 120))
        reg = ink[146:208, 24:298]  # 창 테두리(x 16~18 · 302 · y 208) 안쪽
        tag = f"{p.parent.name}/{p.stem}"
        if int(reg.sum()) == 0:
            # 대사창 구역에 ▼(파랑 · 대기 커서)만 있고 글자색(흰·주황·초록)이 없으면 — 쪽 지움(\f)으로 시작하는 이음 조각의 첫 화면(앞 글 없이 띄운 하네스 꼴)
            sub = a[146:208, 24:298]
            green = int(((sub[..., 1] > 190) & (sub[..., 0] < 60) & (sub[..., 2] < 60)).sum())
            blue = int(((sub[..., 2] > 200) & (sub[..., 0] < 60) & (sub[..., 1] > 90)).sum())
            if green == 0 and blue > 0:
                rows.append((tag, "▼만 있는 빈 창(이음 조각 첫 쪽)", f"▼ {blue}px", str(p)))
            else:
                rows.append((tag, "빈 쪽·다른 창", "글 잉크 0 — 눈으로 본다", str(p)))
            continue
        xs = np.nonzero(reg)[1]
        x1 = int(xs.max()) + 24
        if x1 > 272:
            rows.append((tag, "넘침(오른쪽)", f"글 오른쪽 끝 x={x1}", str(p)))
    return n


def _streams():
    """→ [(자리, ours)] — 씬 대본(script/) · 시스템 문안(sysmsg) · 전투 문안(battle)."""
    for f in sorted((common.GAME_DIR / "script").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for off, st in d["streams"].items():
            yield f"{f.stem}:{off}", st.get("ours")
    for name in ("sysmsg", "battle"):
        d = json.loads((common.GAME_DIR / "textmap" / f"{name}.json").read_text(encoding="utf-8"))
        for off, st in d.items():
            yield f"{name}:{off}", st.get("ours")


def text_checks(rows: list):
    n = 0
    for tag, t in _streams():
        if not t or not re.search(r"[가-힣]", t):
            continue
        n += 1
        body = TAG.sub(
            "§", re.sub(r"\{[^}]*\}", "§", t)
        )  # {원문 이름|조사} 자리는 빌드가 정본 이름으로 바꾼다
        for rx, kind in (
            (KANA, "일본어 가나"),
            (HANJA, "한자"),
            (JPPUNCT, "일본식 부호"),
            (FULL, "전각 부호·숫자"),
        ):
            m = rx.search(body)
            if m:
                rows.append((tag, kind, body[max(0, m.start() - 6) : m.end() + 6], ""))
        pages = t.split("\x0c")
        for i, pg in enumerate(pages):
            plain = TAG.sub("§", pg.replace("<01>", "\n").replace("<05>", "\n"))
            if 0 < i and not plain.strip():  # 맨 앞 쪽 지움(\f 로 시작)은 정상
                rows.append((tag, "빈 쪽(문안)", f"{i + 1}쪽", ""))
            if "  " in plain:
                rows.append((tag, "겹 공백", plain.strip()[:24], ""))
            if re.search(r"\n[ ]|[ ]\n", plain):
                rows.append((tag, "줄 머리·끝 공백", plain.strip()[:24], ""))
    return n


def main():
    root = Path(sys.argv[1])
    rows: list = []
    npng = png_checks(root / "scene", rows) if (root / "scene").exists() else 0
    ntxt = text_checks(rows)
    kinds = Counter(r[1] for r in rows)
    with (root / "anomalies.tsv").open("w", encoding="utf-8") as fh:
        fh.write("자리\t부류\t내용\t캡처\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    print(
        f"PNG {npng}장 · 문안 스트림 {ntxt} · 후보 {len(rows)} — "
        + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
    )


if __name__ == "__main__":
    main()
