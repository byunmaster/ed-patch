"""줄·쪽 나눔 지표 검사(규칙 2-16) — 구운 빌드가 남긴 `layout_metrics.json`(대사 전량의 **조판 결과**)을 읽어 a/b/c/d 를 기준선과 맞댄다.

    python3 tools/check_layout.py [빌드칸]           # 기준선보다 늘면 실패
    python3 tools/check_layout.py [빌드칸] --freeze   # 줄었을 때 기준선을 내린다(래칫)

a 쪽 끝 한 어절 고아 쪽 · b 문장 중간 한 낱말로 끝나는 쪽 · c 문장 중간 손 개행(원고) · d 절째 내리면 들어가는데 쪼갠 줄 · e 줄 끝·첫머리로 갈린 굳은 [명사+명사] 구 · h 창이 둘 이상인 단위의 마지막 창이 한 어절 · h2 창 줄 수 차가 2 이상인 단위 · f 규칙이 만든 퇴행(새 보조용언·의존명사 끊김, 한 줄이던 문장의 갈림 — 기준선 0). 정의는 layout.py.
기준선 파일 `layout_baseline.json` 의 `before` 는 공용 krwrap 그대로(`ED_LAYOUT=0`) 잰 값 — 기록용이다.
"""

import json
import sys
from pathlib import Path

import common

BASE = Path(__file__).resolve().parents[1] / "layout_baseline.json"
KEYS = ("a", "b", "c", "d", "e", "f", "h", "h2")


def main() -> int:
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    d = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG.replace("/", "_")
    p = d / "layout_metrics.json" if d.is_dir() else d
    if not p.exists():
        print(f"❌ 지표 파일이 없다: {p} (빌드가 남긴다)")
        return 1
    got = json.loads(p.read_text(encoding="utf-8"))
    m = got["metrics"]
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.exists() else None
    print(
        f"  줄·쪽 나눔 지표 — 조판 덩이 {got['calls']:,} · a {m['a']} · b {m['b']} · c {m['c']} · d {m['d']} · e {m['e']} · f {m['f']} · h {m['h']} · h2 {m['h2']} · 글 보존 {got.get('preserved', 0)} (되돌린 덩이 {got.get('f_revert', 0)})"
        + ("" if got["enabled"] else "  (규칙 끔)")
    )
    if "--freeze" in sys.argv:
        before = (base or {}).get("before", {})
        notes = (base or {}).get("d_notes", {})  # 기준선이 오른 사유 — freeze 가 지우지 않는다
        BASE.write_text(
            json.dumps(
                {"before": before, "now": m, **({"d_notes": notes} if notes else {})},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  기준선을 {m} 로 썼다")
        return 0
    if base is None:
        print("❌ 기준선(layout_baseline.json)이 없다 — --freeze")
        return 1
    if not got["enabled"]:
        print("❌ ED_LAYOUT=0 으로 구운 빌드다 — 제품 빌드가 아니다")
        return 1
    now = base["now"]
    bad = [k for k in KEYS if m[k] > now[k]]
    if bad:
        print("❌ 기준선보다 늘었다: " + ", ".join(f"{k} {now[k]}→{m[k]}" for k in bad))
        return 1
    low = [k for k in KEYS if m[k] < now[k]]
    if low:
        print(
            "  ℹ 줄었다 — `check_layout.py --freeze` 로 기준선을 내린다: "
            + ", ".join(f"{k} {now[k]}→{m[k]}" for k in low)
        )
    print(f"  ✅ 기준선 이하 (전 {base.get('before')} → 기준 {now})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
