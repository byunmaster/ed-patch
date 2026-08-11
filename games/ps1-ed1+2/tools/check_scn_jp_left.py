#!/usr/bin/env python3
"""**씬 대사**에 일본어가 남았는지 센다 — 그리고 왜 남았는지까지 짚는다.

⚠ 전투 코퍼스·이름 테이블·UI 는 `check_jp_left.py` 가 본다. 여기는 **SCN 오버레이 대사**만 —
층이 달라 판정 방식도 다르다(저쪽은 코드 참조로 문자열을 모으고, 여기는 블록 포인터를 본다).

⚠ 이건 `todo_untranslated`(손이 필요한 블록)와 **다른 층**이다. 배정이 붙어도 게이트에서
빠지거나 정형 빌더가 그 꼴을 못 알아보면 JP 가 그대로 나간다. 실제로 「파생값이 전부
한국어인 걸 확인했다」고 적어 둔 자리 여럿이 이미지에선 일본어였다(2026-08-10).
**파생값을 본 것과 이미지에 들어간 것을 본 것은 다르다.**

⚠ 재배치 뒤 자유 구간에는 **원본 꼬리가 그대로 남는다** — 포인터가 안 가리키면 화면에
안 나오는 죽은 바이트다. 그래서 **참조되는 블록만** 본다. 가나만 보고 한자는 넘긴다
(지명·이름 슬롯에 정상으로 남는 한자가 있다).

  python3 tools/check_scn_jp_left.py            # 전 씬
  python3 tools/check_scn_jp_left.py ED1SCN3    # 한 씬(사유까지)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import BUILD_DIR, OUT_DIR, extract
from lock_lines import SETTLED, load_lock
from patch_sys_ui import _scn_layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
KANA = re.compile(r"[ぁ-ゟァ-ヺ]")


def why_left(scene, eid, raw, tr, ov, am, settled):
    """이 블록이 왜 일본어로 남았나 — 층을 갈라 이름 붙인다."""
    if eid is None:
        return "원문 대조 실패(블록 경계 밖일 수 있다)"
    why = []
    if str(eid) in settled:
        why.append("판정완료")
    if str(eid) in ov:
        why.append("오버라이드")
    if str(eid) in am:
        why.append("배정 정본")
    if eid in tr:
        try:
            _, w = R.build_candidate(raw[eid], tr[eid], eid)
            why.append(f"게이트 제외:{w}" if w else "⚠ 번역이 있는데 JP — 배치 단계 제외 의심")
        except Exception as e:  # noqa: BLE001
            why.append(f"빌드 예외 {type(e).__name__}")
    else:
        why.append("번역 없음")
    return " · ".join(why)


def scan(scene, verbose):
    lba, size = next((a, b) for n, a, b in _scn_layout() if n == scene)
    data = bytes(extract(lba, size, path=IMG))
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scene}.json"), encoding="utf-8"))
    te = int(doc["source"]["text_end"], 16)
    refs = sorted({a - R.OVERLAY_RAM_BASE for _, _, _, a in R.find_refs(data, te)})
    raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
    tr = ov = am = settled = None
    hits = []
    for off in refs:
        end = data.find(b"\x00", off)
        if end < 0 or end - off > 400:
            end = off + 400
        body = data[off:end]
        if not KANA.search(body.decode("cp932", "ignore")):
            continue
        if tr is None:  # 필요할 때만 무겁게 연다
            tr, _, _ = R.load_translations(scene.replace("SCN", "_SCN"), scene)
            ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
                scene, {}
            )
            am = json.load(open(os.path.join(ROOT, "align_map.json"), encoding="utf-8")).get(
                scene, {}
            )
            settled = set(load_lock().get(SETTLED, {}).get(scene, {}))
        eid = next((i for i, r in raw.items() if r.rstrip(b"\x00") == body), None)
        hits.append((off, eid, body.decode("cp932", "ignore")))
        if verbose:
            tag = f"jp{eid}" if eid is not None else "?"
            print(f"  🔴 0x{off:X}  {tag:<8} {why_left(scene, eid, raw, tr, ov, am, settled)}")
            print(f"        {hits[-1][2][:64]!r}")
    return len(refs), hits


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    total = 0
    for name, _, _ in _scn_layout():
        if want and name not in want:
            continue
        n_ref, hits = scan(name, verbose=bool(want))
        total += len(hits)
        print(f"  {name}: 참조 블록 {n_ref} · 살아있는 가나 {len(hits)}곳")
    print(f"\n화면에 나오는 일본어 {total}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
