"""재삽입 시험 빌드 — **가짜 한글 몇 줄**을 프롤로그(첫 대사창)에 넣어 굽는다. 번역문이 아니다(글리프 자리 정본의 글자로 지은 무의미한 열).

    ED_BUILD_TAG=test-probe python3 tools/probe.py [--mode same|resize]

🔴 시험 빌드는 꼬리표가 `test-` 로 시작해야 한다(마스터 10-15 — 마스터 목록에 안 나오게). 아니면 거부한다.
대상: `/O/SC400.DAT!..\\BIN\\OP00000.BIN` 조각 4·5(프롤로그 첫 대사 둘).
- `same`   — 같은 크기로 넣는다(멤버 크기 불변).
- `resize` — 길이를 바꿔 넣는다(멤버가 커지고 아카이브가 재배치된다 — 디렉터리 크기 갱신까지).
끝에서 **구운 이미지를 다시 읽어** 넣은 문안이 그대로 되읽히는지, 글리프가 구워졌는지, 안 건드린 조각이 그대로인지 검산한다.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common
import font
import hangul
import reinsert
import textenc

from shared.ps1 import gmf_arc

KEY = ("/O/SC400.DAT", "..\\BIN\\OP00000.BIN")
TEXTS = {
    "same": {4: "아니 어서 입도 시스템", 5: "보레 시스 방금"},
    "resize": {4: "아니 어서", 5: "입도 시스템 보레 시스 방금 정시 데터 공격 레벨 아니 어서"},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("same", "resize"), default="same")
    a = ap.parse_args()
    if not common.BUILD_TAG.startswith("test-"):
        raise SystemExit(
            "🔴 시험 빌드는 `ED_BUILD_TAG=test-<무엇>` 로 굽는다(꼬리표가 test- 로 시작해야 마스터 목록에 안 나온다)"
        )
    table = hangul.load()
    texts = TEXTS[a.mode]
    members = build.identity_gate({})
    per = reinsert.edits_for(members, KEY, texts, same_size=(a.mode == "same"), table=table)
    used = "".join(texts.values())

    def exe_edit(exe):
        hangul.bake(exe, table, used)

    out, rep = build.build(
        {"script": per, "exe": exe_edit}, kind=f"probe-{a.mode}", suffix=" (TEST)"
    )

    # 🔴 되읽기 — 구운 이미지에서 멤버를 다시 꺼내 넣은 문안·안 건드린 조각·글리프를 본다
    with common.open_disc(out) as d:
        lba, size = common.iso_files(out)[KEY[0]]
        data = d.read_extent(lba, size)
        exe_lba, exe_size = common.iso_files(out)[common.EXE_PATH]
        exe = bytearray(d.read_extent(exe_lba, exe_size))
    mem = {n: (o, s) for n, o, s in gmf_arc.arc_parse(data)[1]}[KEY[1]]
    new = reinsert.member_segments(data[mem[0] : mem[0] + mem[1]])
    old = reinsert.member_segments(members[KEY])
    inv = textenc.charmap()
    for i in texts:
        got = [c for c in new[i]]
        want = per[KEY][i]
        if got != want:
            raise SystemExit(f"🔴 조각 {i} 되읽기가 넣은 것과 다르다")
        back = "".join(next((k for k, v in table.items() if v == c), inv.get(c, "?")) for c in got)
        print(f"  조각 {i}: {len(old[i])}→{len(got)} 코드 · 되읽음 「{back.rstrip()}」")
    others = [i for i in range(len(old)) if i not in texts]
    if [new[i] for i in others] != [old[i] for i in others]:
        raise SystemExit("🔴 안 건드린 조각이 바뀌었다")
    for ch in set(used) - {" "}:
        want = font.hangul_glyph(ch)
        got = font.read_glyph(exe, table[ch])[:, : want.shape[1]]
        if (got != want[: got.shape[0]]).any() or font.read_glyph(exe, table[ch])[
            :, want.shape[1] :
        ].any():
            raise SystemExit(f"🔴 글리프 「{ch}」(코드 {table[ch]}) 가 구워지지 않았다")
    print(
        f"probe-{a.mode}: 멤버 {len(members[KEY])}→{mem[1]}B · 쓴 섹터 {rep['written_sectors']} · 바뀐 섹터 {rep['changed_sectors']} · "
        f"디렉터리 크기 갱신 {rep['resized']} · 되읽기 ✅ · 안 건드린 조각 {len(others)} 동일 ✅\n→ {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
