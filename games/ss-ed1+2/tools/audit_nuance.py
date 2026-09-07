"""**우리 문안이 원문의 뜻을 지켰나** — 일본어 원문을 축으로 의심 자리를 순위로 낸다.

    python3 tools/audit_nuance.py            # 화면 코퍼스 전량 → 검토표
    python3 tools/audit_nuance.py --top 40   # 상위만 화면에

## 왜

오역 중 제일 조용한 것이 **그럴듯한 딴소리**다. 빠뜨림은 숫자·고유명사로 잡히지만 뜻이
통째로 미끄러진 자리는 문장이 매끄러워서 아무 검사도 안 운다(`check_text` 도 못 본다).
12,000 블록을 사람이 다시 읽을 수는 없으니 **의심 자리만 추린다.**

## 축은 **일본어 원문**이다 — 정발이 아니다

「우리 ↔ 정발」만 재면 순환에 빠진다. 정발은 정답이 아니고, 이 게임의 새턴 문안은
**정발을 안 보고 쓴 것**이라(status 4절) 정발과 다른 게 오히려 정상이다.
⇒ LaBSE(번역쌍 찾기용 다국어 모델)로 **원문 ↔ 우리**를 잰다.

🔴 **점수는 절대값이 아니라 순위로 읽는다.** LaBSE 의 JP↔KR 판정은 약하다 — PS1 홀드아웃
   실측 정밀도 79%. 게다가 구조적 오탐이 둘이다:

1. **구어체·사투리** — 정식 번역쌍으로 배운 모델이라 `~구먼`·`옙`·`~올시다` 에 점수를 깎는다.
   **문체가 살아 있을수록 점수가 낮다** — 이 게임에선 그게 미덕이다.
2. **짧은 문장** — 표기 하나가 전부를 흔든다. 8자 미만은 따로 갈라 본다.

⚠ **게이트가 아니다.** 후보만 낸다 — 판정은 사람이 문맥으로 한다.
⚠ 비결정적(임베딩)이므로 **빌드 경로에 두지 않는다**(레포 제1원칙). 산출물은 `work/review/`
  (gitignore) — 원문을 담으므로 커밋 금지다.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import check_text
import common

MODEL_NAME = "sentence-transformers/LaBSE"
SHORT = 8  # 이보다 짧으면 점수를 못 믿는다(backtrans.SHORT 와 같은 기준)
MARK = re.compile(r"%[csd]")
WS = re.compile(r"\s+")
OUT = os.path.join(common.REVIEW_DIR, "nuance.md")


def flatten(s):
    """마크업만 지운 한 줄 — 모델에 넣을 꼴.

    🔴 **공백을 지우면 안 된다**(2026-08-27 실측). 다 붙여 넣었더니 한국어 토큰이 통째로
       깨져 **점수가 음수**로 나왔다 — `ギャノアが現れた。` ↔ `갸노아가나타났다.` 가 -0.303.
       뜻이 정확한 문장이 최하위로 올라오니 순위 자체가 무의미해진다.
    """
    return WS.sub(" ", MARK.sub("", s)).strip()


def load_model():
    """LaBSE 로더. ⚠ 캐시가 없으면 내려받는다 — 망이 없으면 여기서 죽는다."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, device="cpu")


def score(rows, model, batch=64):
    """`[(점수, 파일, 오프셋, 원문, 우리)]` — 낮은 것부터."""
    import numpy as np

    jp = [flatten(r[2]) for r in rows]
    kr = [flatten(r[3]) for r in rows]
    a = model.encode(jp, batch_size=batch, normalize_embeddings=True, show_progress_bar=True)
    b = model.encode(kr, batch_size=batch, normalize_embeddings=True, show_progress_bar=True)
    sim = np.sum(a * b, axis=1)
    out = [(float(s), *r) for s, r in zip(sim, rows, strict=True)]
    out.sort(key=lambda x: x[0])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    common.verify_source()
    rows = check_text.corpus()
    print(f"  화면 코퍼스 {len(rows):,}블록 — LaBSE 로 원문 ↔ 우리를 잰다")
    ranked = score(rows, load_model())

    long_, short_ = [], []
    for s, path, off, jp, kr in ranked:
        (short_ if min(len(flatten(jp)), len(flatten(kr))) < SHORT else long_).append(
            (s, path, off, jp, kr)
        )
    os.makedirs(common.REVIEW_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# 뜻이 미끄러진 자리 — 낮은 점수부터\n\n")
        f.write("⚠ 원문 포함 · 커밋 금지. 점수는 순위로만 읽는다(모듈 주석).\n\n")
        for title, group in (("## 본론 (8자 이상)", long_), ("## 짧아서 못 믿는 것", short_)):
            f.write(f"\n{title} — {len(group):,}\n\n")
            for s, path, off, jp, kr in group:
                f.write(f"- `{s:.3f}` {path} 0x{off:X}\n  - JP `{jp}`\n  - KR `{kr}`\n")
    print(f"  검토표 → {OUT}  (본론 {len(long_):,} · 짧은 것 {len(short_):,})")
    print(f"\n  ── 의심 상위 {a.top}")
    for s, path, off, jp, kr in long_[: a.top]:
        print(
            f"  {s:.3f}  {path} 0x{off:X}\n      JP {flatten(jp)[:56]}\n      KR {flatten(kr)[:56]}"
        )
    with open(os.path.join(common.REVIEW_DIR, "nuance.json"), "w", encoding="utf-8") as f:
        json.dump([{"s": s, "f": p, "o": o} for s, p, o, _j, _k in ranked], f)


if __name__ == "__main__":
    main()
