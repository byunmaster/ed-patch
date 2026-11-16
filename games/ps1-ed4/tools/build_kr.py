"""번역 빌드 — **정본에 든 번역만** 얹은 한글 이미지를 굽는다(마스터에게 보이는 진짜 빌드. 가짜 한글 시험은 `probe.py`).

    python3 tools/build_kr.py            # → work/build/<꼬리표>/  (꼬리표 = 브랜치)

얹는 것: ① 실행파일 UI 문안(`ui_ed4.json`) ② (대본 번역 — 정본이 서면 여기) ③ 쓰인 글자의 글리프(`hangul_map.json` 자리).
끝에서 **구운 이미지를 다시 읽어** 정본 문안이 그 자리에 코드로 앉았는지 검산하고, 아직 안 옮긴 수를 센다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import common
import halfwidth
import hangul
import josa_build
import narration
import script_kr
import title_img
import uitext


def exe_edit(exe):
    table = hangul.load()
    uitext.apply(exe, table)
    hangul.bake(exe, table, uitext.used_chars() + script_kr.used_chars())
    # 시스템 하위 메뉴 창(필드 메뉴 → 시스템)의 열 수 7 → 6 (`0x80029098 addiu a2,zero,7` — 이 창을 만드는 유일한 호출). 글자는 「메시지 속도」 5.5칸이 최대(마스터 10-25 「6칸으로 줄이자」)
    # 전리품(「n 피스카를 얻었다.」) 창 둘 — 열 수 9 → 14·x 0x5e → 0x40(가운데 유지). 원문 길이(「ピスカを得た」)에 맞춘 상수라 번역이 길면 「다.」가 잘린다(마스터 10-25)
    for a, want, new_w in (
        (0x8003AA48, 0x2404005E, 0x24040040),
        (0x8003AA50, 0x24060009, 0x2406000E),
        (0x80041E1C, 0x2404005E, 0x24040040),
        (0x80041E24, 0x24060009, 0x2406000E),
    ):
        o2 = halfwidth._off(a)
        if int.from_bytes(exe[o2 : o2 + 4], "little") != want:
            raise SystemExit(f"🔴 전리품 창 자리 {a:#x} 가 원판이 아니다")
        exe[o2 : o2 + 4] = new_w.to_bytes(4, "little")
    # 세이브/로드 창 슬롯 정보 창(열 11, 왼쪽 지명 칸 = 열 − 시간 4 = 7칸)을 14열로 — 「전망 좋은 오두막」(9코드)이 7칸에서 잘렸다(마스터 10-25). 오른쪽 가장자리 x=0x82+14×12+16=314
    for a in (0x8001F7A8, 0x8001FE14):
        o3 = halfwidth._off(a)
        if int.from_bytes(exe[o3 : o3 + 4], "little") != 0x2406000B:
            raise SystemExit(f"🔴 세이브/로드 창 열 수 자리 {a:#x} 가 원판이 아니다")
        exe[o3 : o3 + 4] = (0x2406000E).to_bytes(4, "little")
    o = halfwidth._off(0x80029098)
    if int.from_bytes(exe[o : o + 4], "little") != 0x24060007:
        raise SystemExit("🔴 시스템 창 열 수 자리가 원판이 아니다")
    exe[o : o + 4] = (0x24060006).to_bytes(4, "little")
    if os.environ.get("ED_HOOK_TRAP2") == "1":  # 시험 — 둘째 동굴 첫머리에 「ra 를 0x801F7F10 에 적고 돌아가는」 덫(커서 줄 훅 자리가 정말 죽은 함수인지 실게임으로 본다)
        import struct

        off = halfwidth._off(halfwidth.CAVE2)
        for k, w in enumerate((0x3C08801F, 0xAD1F7F10, 0x03E00008, 0)):
            exe[off + 4 * k : off + 4 * k + 4] = struct.pack("<I", w)
    if os.environ.get("ED_HOOK_TRAP") == "1":  # 시험 — 동굴 첫머리에 「ra 를 0x801F7F00 에 적고 돌아가는」 덫을 둔다(누가 이 자리를 실행하나)
        import struct

        off = halfwidth._off(halfwidth.CAVE)
        for k, w in enumerate((0x3C08801F, 0xAD1F7F00, 0x03E00008, 0)):
            exe[off + 4 * k : off + 4 * k + 4] = struct.pack("<I", w)
    elif os.environ.get("ED_NO_HOOK") != "1":  # 반각 합성 + 조사 훅(동굴 — 실행 BP 확인 자리, docs/status.md)
        josa = {
            "markers": josa_build.markers(table),
            "bt": josa_build.batchim_bits(table, 8 * halfwidth.BT_BYTES),
        }
        halfwidth.patch_exe(
            exe, hangul.half_codes(), josa=None if os.environ.get("ED_NO_JOSA") == "1" else josa, item_blob=bytes(uitext.ITEM_BLOB)
        )


def main():
    members = build.identity_gate({})
    per, notes = script_kr.edits(members, table=hangul.load())
    out, rep = build.build(
        {"script": per, "exe": exe_edit, "members": {**narration.member_edits(), **title_img.member_edits()}}, kind="kr"
    )
    # 🔴 되읽기 — 구운 이미지에서 실행파일을 다시 꺼내 정본 문안이 코드로 앉았나
    lba, size = common.iso_files(out)[common.EXE_PATH]
    with common.open_disc(out) as d:
        exe = d.read_extent(lba, size)
    orig = bytes(common.read_file(common.EXE_PATH))
    bad_rb = uitext.readback(orig, exe)
    if bad_rb:
        raise SystemExit("🔴 되읽기:\n  " + "\n  ".join(bad_rb[:8]))
    nseg = sum(len(v) for v in per.values())
    n, total, bad = uitext.check()
    for note in notes[:10]:
        print("  ⚠", note)
    print(
        f"번역 빌드: 대본 조각 {nseg}(멤버 {len(per)}) · UI 문안 {n}/{total} · 쪽 넘침 {len(notes)} · 쓴 섹터 {rep['written_sectors']} · 바뀐 섹터 {rep['changed_sectors']} · 되읽기 ✅\n"
        f"  sha1 {common.sha1_of(out)}\n→ {out}"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
