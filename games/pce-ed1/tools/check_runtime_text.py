#!/usr/bin/env python3
"""런타임 조립 글 게이트(11-18) — 구운 롬의 씬 블록을 스크립트 VM 으로 따라가 뽑은 **창 단위 글**(`runtime_text.py`)의 결함이 기준선보다 늘면 실패.

잡는 것: 붙음(조각 경계에서 문장 끝 부호+한글이 공백 없이 붙음 — 「으음.이건」·「어!?이」) · 창/쪽 첫 칸 공백(「 석비에는」) · 이름반복.
(글자반복·모르는코드는 의성어·피연산자 오탐이 섞여 게이트 밖 — `runtime_text.py` 로 사람이 본다.)
양성 대조가 먼저 돈다 — VM(호출표 `16` + 복귀 `06` · 경계)과 검사 함수가 진짜 걸리는지. 기준선 `script/runtime_text_baseline.json` = **고칠 대상 목록**
(새 결함이 생기면 실패 · 고치면 `--freeze` 로 내린다).

    python3 games/pce-ed1/tools/check_runtime_text.py [--freeze] [--iso <ed1.iso>]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import runtime_text as R

BASE_FILE = Path(__file__).resolve().parent.parent / "script" / "runtime_text_baseline.json"
GATED = ("붙음", "첫칸공백", "쪽첫공백", "이름반복")


def selftest() -> list[str]:
    bad: list[str] = []
    inv = {bytes([0xF0, 1]): "으", bytes([0xF0, 2]): "음", bytes([0xF0, 3]): ".", bytes([0xF0, 4]): "이", bytes([0xF0, 5]): "건"}
    # 호출표 `16` 다섯 포인터 → 조각 「으음.」 `06`(복귀) → 표 뒤 꼬리 「이건」 `00`
    base = 0xA000
    callee = bytes([0xF0, 1, 0xF0, 2, 0xF0, 3, 0x06])
    tail = bytes([0xF0, 4, 0xF0, 5, 0x00])
    head_len = 1 + 10
    callee_at = head_len + len(tail)
    buf = bytearray([0x16])
    for _ in range(5):
        buf += (base + callee_at).to_bytes(2, "little")
    buf += tail + callee
    ws = [w for p in R.walk(bytes(buf), 0, inv) for w in R.windows(p)]
    if not any("으음.∥이건" in w for w in ws):
        bad.append(f"VM: 호출표→복귀→꼬리 이음이 안 읽힌다 {ws}")
    if not any(c == "붙음" for w in ws for c, _ in R.checks(w)):
        bad.append("검사: 「으음.∥이건」이 붙음으로 안 걸린다")
    if any(c == "붙음" for c, _ in R.checks("으음. ∥이건")):
        bad.append("검사: 공백이 있는 경계를 붙음으로 센다(거짓 양성)")
    if not any(c == "쪽첫공백" for c, _ in R.checks("완성되었습니다.⏸ 석비에는")):
        bad.append("검사: 쪽 첫 칸 공백이 안 걸린다")
    if not any(c == "첫칸공백" for c, _ in R.checks("〔게일〕\n 다시 잘")):
        bad.append("검사: 창 첫 칸 공백이 안 걸린다")
    return bad


def keys(rows) -> list[str]:
    return sorted({f"{r['sid']}:{r['cls']}:{r['why']}" for r in rows if r["cls"] in GATED})


def main() -> int:
    argv = sys.argv[1:]
    bad = selftest()
    if bad:
        for b in bad:
            print("  ❌ 양성 대조", b)
        return 1
    iso = Path(argv[argv.index("--iso") + 1]) if "--iso" in argv else common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print("구운 이미지가 없다 —", iso)
        return 1
    rows, n = R.scan(iso)
    now = keys(rows)
    if "--freeze" in argv:
        BASE_FILE.write_text(json.dumps({"_doc": "런타임 조립 글 결함 기준선 — 고칠 대상 목록(check_runtime_text.py --freeze)", "keys": now}, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"기준선 {len(now)}건 기록")
        return 0
    base = set(json.loads(BASE_FILE.read_text("utf-8"))["keys"]) if BASE_FILE.exists() else set()
    new = [k for k in now if k not in base]
    gone = [k for k in base if k not in set(now)]
    print(f"런타임 조립 글 — 창 {n}개 · 결함 {len(now)}건(기준선 {len(base)}) · 새 {len(new)} · 고쳐진 {len(gone)}")
    for k in new:
        print("  ❌ 새 결함", k)
    if gone:
        print(f"  ℹ 기준선에서 빠질 수 있다 {len(gone)}건 — `--freeze` 로 내린다")
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
