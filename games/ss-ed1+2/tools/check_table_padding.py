#!/usr/bin/env python3
"""**다시 쓴 표가 원판의 빈 칸·패딩·종결을 지키나** — 원본과 최종 이미지를 바이트로 대조한다 (sfc-ed2 가 찾은 결함 부류, 2026-10-24).

    python3 tools/check_table_padding.py        # 실패면 종료코드 1

## 왜 있나
sfc-ed2 는 몬스터 이름 군을 다시 쓰면서 원판의 **길이 0 패딩**을 빠뜨렸고, 빈 슬롯이 **다음 군의 이름을 읽어** 이벤트 전투에서 파티 상태가 깨졌다.
이 게임에서 다시 쓰는 표는 둘이다 — ① 고정 폭 레코드 표(`patch_ui.rows`, 메뉴·HUD 라벨 …) ② 고유명사 표 다섯(`patch_ui.name_rows`, 아이템·주문·몬스터 —
**표 전체를 다시 깔고 포인터만 고친다**) + 몬스터 이름 칸(`patch_mon_names`, ED2MON01~10).

## 무엇을 본다
A. 고정 폭 레코드(`stride`): 원본이 비었거나(첫 바이트 0) 번역 대상이 아닌(KR 없음) 레코드는 **바이트까지 그대로**여야 한다. 번역한 레코드는
   `글 + NUL + 0 채움` 으로 끝나야 하고(NUL 뒤에 0 아닌 바이트가 남으면 안 된다), 원본의 꼬리 패턴(0 채움)을 따라야 한다.
B. **빈 칸을 가리키는 포인터**: 원본에서 포인터가 가리키는 자리가 NUL(길이 0 문자열·패딩)이고 그 자리가 다시 깐 구간 안이면, 최종 이미지의 같은 자리도
   **NUL 이어야 한다.** 다시 깔면서 한글 이름이 그 위에 얹히면 빈 칸이 그 이름을 읽는다(sfc-ed2 결함의 모양).
C. 고유명사 표의 칸 사이·표 끝 채움은 0 이어야 한다(옛 `\\t`(0x09)·찌꺼기 금지).
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "shared"))

import common
import dump_scn


def main():
    import patch_mon_names as MN
    import patch_ui as U

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    _fo, mo = common.open_image()
    _fb, mb = common.open_image(dst)
    cache = {}

    def get(path, built):
        k = (path, built)
        if k not in cache:
            cache[k] = bytes(common.extract(path, mb if built else mo))
        return cache[k]

    bad = []

    # ── A. 고정 폭 레코드 ───────────────────────────────────────────────────
    n_a = n_empty = n_untr = n_tr = 0
    for key, name, i, at, stride, _jp, kr in U.rows():
        path = U.dump_ui.FILES[key]
        o, b = get(path, False), get(path, True)
        orec, brec = o[at : at + stride], b[at : at + stride]
        n_a += 1
        if orec[0] == 0:
            n_empty += 1
            if brec != orec:
                bad.append(
                    f"A 빈 레코드가 바뀜 {path} {name}[{i}] {at:#x}: {orec.hex()} → {brec.hex()}"
                )
        elif kr is None:
            n_untr += 1
            if brec != orec:
                bad.append(f"A 번역 안 한 레코드가 바뀜 {path} {name}[{i}] {at:#x}")
        else:
            n_tr += 1
            z = brec.find(b"\x00")
            if z < 0:
                bad.append(f"A NUL 종결 없음 {path} {name}[{i}] {at:#x}: {brec.hex()}")
            elif any(brec[z:]):
                bad.append(f"A NUL 뒤에 0 아닌 바이트 {path} {name}[{i}] {at:#x}: {brec.hex()}")

    # ── B·C. 다시 깐 구간 안의 「빈 칸을 가리키는 포인터」 ───────────────────────
    regions = {}  # path → [(시작, 끝)]
    for t in U.name_rows(mo):
        regions.setdefault(t["path"], []).append((t["off"], t["off"] + t["room"]))
    mon = MN.table("monster", "eiyuu")
    for path in MN.FILES:
        sl = MN.slots(path, mon)
        if sl:
            d = get(path, False)
            end = max(t + len(d[t:].split(b"\x00", 1)[0]) for t, _jp, _kr in sl) + 1
            regions.setdefault(path, []).append((min(t for t, _jp, _kr in sl), end))
    n_ptr = n_blank = 0
    for path, regs in regions.items():
        o, b = get(path, False), get(path, True)
        base = dump_scn.base_for(os.path.basename(path)) or U.NAME_PTR_BASE
        for pos in range(0, len(o) - 3, 2):
            v = struct.unpack(">I", o[pos : pos + 4])[0]
            if not (base <= v < base + len(o)):
                continue
            t = v - base
            if not any(a <= t < e for a, e in regs):
                continue
            n_ptr += 1
            if o[t] != 0:
                continue  # 살아 있는 문자열을 가리킨다 — 그건 name_rows·check_name_tables 몫(포인터 갱신)
            n_blank += 1
            if b[t] != 0:
                bad.append(
                    f"B 빈 칸 포인터가 이름을 읽는다 {path} 포인터 {pos:#x} → {t:#x}: 원본 00, 빌드 {b[t : t + 8].hex()}"
                )
    # C. 고유명사 표 사이·끝 채움
    n_c = 0
    for t in U.name_rows(mo):
        b = get(t["path"], True)
        last = max(r[0] for r in t["recs"])
        j = last
        while j < len(b) and b[j] != 0:
            j += 1  # 마지막 이름 끝(빌드는 이름 길이가 다르니 빌드에서 다시 찾는다)
        o_t = get(t["path"], False)
        end = t["off"] + t["room"]
        for k in range(j, end):
            n_c += 1
            # 🔴 **표 꼬리는 시스템 메시지 풀이기도 하다**(`patch_ui.sys_pack` 의 `pool` — `room > used` 인 표의 남는 꼬리를 메시지가 쓴다, 11-14).
            #    그래서 「0 이 아님」만으로는 메시지를 찌꺼기로 오판한다(지문을 존대로 늘리자 메시지 하나가 ED.BIN 0x1c2ea 꼬리에 앉았다).
            #    찌꺼기의 정체는 **옛 표의 글자가 그대로 남은 것**(옛 `\t`(0x09) · 원본과 같은 바이트가 4개 이상 이어진 것)이다 — 그걸 센다.
            if b[k] == 0x09 or (b[k] != 0 and k + 4 <= end and b[k : k + 4] == o_t[k : k + 4]):
                bad.append(f"C 표 끝 채움에 옛 표 찌꺼기 {t['path']} {k:#x}: {b[k]:#04x}")
                break
    print(
        f"  표 패딩 [고정 폭 {n_a}: 빈 {n_empty} · 번역 안 함 {n_untr} · 번역 {n_tr}] · 다시 깐 구간 안 포인터 {n_ptr}(빈 칸 {n_blank}) · 표 끝 채움 {n_c}B — 어긋남 {len(bad)}"
    )
    for x in bad[:25]:
        print("     ❌", x)
    if n_a == 0 or n_ptr == 0:
        raise SystemExit("분모 0 — 표를 못 읽었다(통과가 아니다)")
    if bad:
        raise SystemExit(f"표 패딩 {len(bad)}건 — 위를 본다")
    print("  ✅ 표 패딩 — 원판의 빈 칸·패딩·종결을 그대로 지킨다")


if __name__ == "__main__":
    main()
