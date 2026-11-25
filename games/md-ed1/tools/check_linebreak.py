"""줄·쪽 나눔 지표 래칫(규칙 2-16) — 대사 전량을 **조판 결과**로 세어 기준선보다 늘면 실패한다.

(a) 쪽 끝 한 어절 고아 · (b) 문장 중간에서 한 낱말 토막으로 끝나는 쪽 · (c) 문장 중간 손 개행 ·
(d) 절째 내리면 들어가는데 쪼갠 줄. 기준선: `linebreak_baseline.json`(`--freeze` 로 내린다).
`ED_LB=0` 이면 규칙을 끄고 잰다(「전」 값).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import linebreak
import textmap

BASE = Path(__file__).resolve().parent.parent / "linebreak_baseline.json"


def measure() -> dict:
    streams = []
    for blk, doc in sorted(textmap.load_all().items()):
        for k, ent in sorted(doc.get("streams", {}).items()):
            if ent.get("ours") and not ent.get("raw"):
                streams.append((f"{blk:03d}", k, ent["ours"]))

    def fn(body):
        lead = " " if body[:1] == " " else ""
        return build.typeset(body, lead)

    def off(body):
        lead = " " if body[:1] == " " else ""
        was, build.LB_RULES = build.LB_RULES, False
        try:
            return build.typeset(body, lead)
        finally:
            build.LB_RULES = was

    return linebreak.metrics(
        fn,
        streams,
        build.WIDTH,
        flattened=build.LB_RULES,
        before_fn=off if build.LB_RULES else None,
    )


def preserved() -> list[tuple[str, str]]:
    """글 보존 게이트 — 규칙 전·후 조판 결과를 공백·개행 없이 이어 붙여 같아야 한다. 다르면 글이 새거나 늘었다."""
    bad = []
    for blk, doc in sorted(textmap.load_all().items()):
        for k, ent in sorted(doc.get("streams", {}).items()):
            o = ent.get("ours")
            if not o or ent.get("raw"):
                continue
            pend: list[str] = []
            for kind, val in [*textmap.parse_ours(o), ("end", None)]:
                if kind == "text":
                    pend.append(val)
                    continue
                body = "".join(pend)
                pend.clear()
                if not body.strip():
                    continue
                was, build.LB_RULES = build.LB_RULES, False
                a = build.typeset(body)
                build.LB_RULES = True
                b = build.typeset(body)
                build.LB_RULES = was
                j = lambda P: "".join("".join(p) for p in P).replace(" ", "")
                if j(a) != j(b):
                    bad.append((f"{blk:03d}", k))
    return bad


def main() -> int:
    r = measure()
    lost = preserved()
    print(f"글 보존 — 전·후 글자 다른 덩이 {len(lost)}")
    if lost:
        print("❌ 글이 달라졌다:", lost[:5])
        return 1
    cnt = {k: len(v) for k, v in r.items()}
    print(
        "줄·쪽 나눔 지표 "
        + " ".join(f"{k}={v}" for k, v in cnt.items())
        + f" (규칙 {'ON' if build.LB_RULES else 'OFF'})"
    )
    if "--list" in sys.argv:
        for k, v in r.items():
            for blk, key, t in v:
                print(f"  {k} {blk}:{key} {t}")
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps(cnt, indent=1) + "\n")
        print("기준선 갱신")
        return 0
    if not build.LB_RULES:
        return 0
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    bad = [k for k, v in cnt.items() if v > base.get(k, 0)]
    if bad:
        print("❌ 기준선보다 늘었다:", {k: (base.get(k, 0), cnt[k]) for k in bad})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
