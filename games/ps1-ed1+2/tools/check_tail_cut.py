#!/usr/bin/env python3
"""**꼬리 잘림**을 센다 — 만들어는 냈는데 화면에 안 나오는 문안.

구조 계약의 반대쪽이다. 창 수가 **모자라면** 소프트락이라 게이트가 빌드에서 뺀다
(`window_deficit`). **넘치면** 엔진이 원본 `%c` 수만큼만 읽고 멈추므로 뒤가 조용히
사라진다 — 죽지 않으니 아무도 안 알려준다. 그래서 따로 센다.

두 갈래이고 원인이 다르다:

- **창 수 초과** — 정발 엔트리가 JP 보다 페이지가 많은데 슬라이스 없이 통째로 물었다.
  PS1 이 대사를 줄이면서 블록을 갈랐는데 정발은 한 엔트리에 다 갖고 있는 자리다.
- **창당 줄 수 초과** — 한 창이 하드 리밋(`LINES_PER_PAGE`, 이름창이 있으면 −1)을 넘었다.
  ⚠ 이 부류는 대개 **이웃 블록과 중복**이다 — 뒤 문장을 이웃이 이미 맡고 있는데 이쪽이
  엔트리 전문을 물어서 넘친다(jp716 실측 2026-08-11).

⚠ **`build_candidate` 를 직접 부른다** — 재배치·제외(`size`)를 거치기 전 값이다. 제외된
블록은 애초에 안 쓰이니 여기 뜨는 건 "쓰이는데 잘리는" 것뿐이다.

  python3 tools/check_tail_cut.py          # 요약
  python3 tools/check_tail_cut.py -v       # 잘리는 문안까지
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R  # noqa: E402
from common import OUT_DIR  # noqa: E402
from patch_sys_ui import _scn_layout  # noqa: E402


def visible(b, n):
    """엔진이 실제로 읽는 부분 — 원본 `%c` 개수까지."""
    out, cnt = bytearray(), 0
    for i in range(len(b)):
        out += b[i : i + 1]
        if b[i : i + 1] == R.MC:
            cnt += 1
            if cnt >= n:
                break
    return bytes(out)


def scan(verbose=False):
    tot = 0
    for name, _lba, _size in _scn_layout():
        doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
        raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
        tr, _, _ = R.load_translations(name.replace("SCN", "_SCN"), name)
        win, lines, spare = [], [], []
        for eid, t in sorted(tr.items()):
            if eid not in raw:
                continue
            try:
                cand, _why = R.build_candidate(raw[eid], t, eid)
            except Exception:  # noqa: BLE001 — 검사기는 빌드를 안 세운다
                continue
            if cand is None:
                continue
            n = raw[eid].count(R.MC)
            if cand.count(R.MC) > n:
                # ⚠ **잃는 문안이 있을 때만 꼬리 잘림이다.** 원본이 종단 없는 조각(`%c%s%c`
                # 아이템 감싸기 등)이면 우리가 종단을 하나 더 내도 잘리는 글자가 없다 —
                # 그건 흐름 표식 차이지 표시 손실이 아니다(jp786 실측 2026-08-11).
                cut = cand.rstrip(b"\x00")[len(visible(cand, n)) :].replace(R.MC, b"").strip()
                (win if cut else spare).append((eid, n, cand.count(R.MC), cand))
            body = cand.rstrip(b"\x00")
            for k, seg in enumerate(body.split(R.MC)[:n]):
                if seg and seg.count(b"\x0a") + 1 > R.LINES_PER_PAGE:
                    lines.append((eid, k, seg.count(b"\x0a") + 1))
        tot += len(win) + len(lines)
        mark = "✅" if not (win or lines) else "⚠"
        print(f"  {mark} {name}: 창 수 초과 {len(win)} · 줄 수 초과 {len(lines)}")
        for eid, a, b, cand in win:
            print(f"      jp{eid}  창 {a} → {b}")
            if verbose:
                cut = cand.rstrip(b"\x00")[len(visible(cand, a)) :]
                print(f"        잘림: {cut.decode('cp932', 'ignore')[:70]!r}")
        for eid, k, n in lines:
            print(f"      jp{eid}  창#{k} {n}줄 (리밋 {R.LINES_PER_PAGE})")
        for eid, a, b, _c in spare if verbose else ():
            print(f"      · jp{eid}  종단만 {a} → {b} (잃는 글자 없음)")
    print(f"\n{'✅ 꼬리 잘림 없음' if not tot else f'⚠ 꼬리 잘림 {tot}건'}")
    return tot


if __name__ == "__main__":
    sys.exit(1 if scan("-v" in sys.argv) else 0)
