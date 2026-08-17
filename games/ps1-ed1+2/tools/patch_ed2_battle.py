#!/usr/bin/env python3
"""ED2 전투 문안(ED2.EXE) 한글화 — 제자리 치환 + **넘치면 재배치**.

**소재.** 전투 문자열은 코드가 `lui`+`addiu/ori` 로 주소를 만들어 참조한다. 그 쌍을 전수로
훑어 **코드가 실제로 부르는 문자열**을 모은다(`patch_items.corpus_strings` 와 같은 방법).
ED2 는 477건이 나온다.

**절반은 공짜다.** ED1 전투 정본(`textmap/battle.json`, 498건)의 JP 원문과 **글자까지 같은
것**이 78건 있다 — 두 편이 같은 엔진이라 전투 메시지를 공유한다. 그건 다시 번역하지 않고
그대로 쓴다(표기가 갈릴 여지도 없어진다). ED2 에만 있는 것은 `textmap/battle_ed2.json`.

**넘치면 재배치한다**(2026-08-16). 예전엔 건너뛰고 보고만 했는데, 그러면 그 자리에
**원문이 그대로 남아 화면에 깨진 글자가 나간다**(50건). 풀은 ① 옮기는 문자열이 비우는
옛 칸 ② 제자리 문안이 남기는 꼬리 — 둘을 합쳐야 예산이 선다(①만으론 184B 부족).
⚠ 참조를 하나라도 놓치면 엉뚱한 주소를 읽으므로 `lui` 까지 갱신하고, 그 `lui` 를 다른
주소와 나눠 쓰는지 전수로 확인한다(공유면 즉시 실패).

  python3 tools/patch_ed2_battle.py --plan   # 제자리 / 넘침(재배치 대상) / 미번역
  python3 tools/patch_ed2_battle.py          # 이미지에 적용
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from battle_text import B
from common import BUILD_DIR, extract, write_user_data
from derive_text import jp_map
from patch_items import MIPS_ADDIU, MIPS_ORI, iter_lui_pairs

ED2_LBA, ED2_SIZE = 756, 872448
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# 참조가 몰려 있는 구획 — 밖은 맵 데이터·코드다. `--plan` 으로 늘려가며 확인한다.
CORPUS = ((0x3000, 0xC000), (0xD4000, 0xD5000))
KANA = re.compile(r"[ぁ-んァ-ヴー]")

# ⚠ **메모리카드·세이브 문구는 여기서 손대지 않는다** — 같은 구획에 섞여 있지만
# ED1 에서도 `patch_sys_ui` 관할이고, 두 곳에서 쓰면 서로 덮는다.
SKIP = re.compile(r"メモリーカード|カードには|データが壊れ|フォーマット|セーブ|ロード")

# 휴리스틱(가나 또는 `%`)이 못 잡는 자리를 **오프셋으로 명시 편입**한다.
# 0xD4974 `ＥＰ ` — 전각 라틴뿐이라 가나도 `%` 도 없다. 전투 승리 줄의 앞머리인데, 안 잡히면
# **ED1 은 정본을 따르고 ED2 만 원본이 남아 두 편이 조용히 갈린다**(2026-08-17 실측).
# 지금 값은 정발과 같은 전각 `ＥＰ ` 라 쓰나 마나지만, 표기를 고칠 때 ED2 가 따라오려면
# 이 경로가 있어야 한다.
# ⚠ ED1 쪽 정본은 `items_battle.json` 인데 `battle_text.B` 는 `battle.json` 만 싣는다 —
# 그래서 공용표로도 안 흘러온다. 값이 같아도 `battle_ed2.json` 에 한 줄이 필요하다.
EXTRA_OFF = (0xD4974,)


def _enc(kr):
    """한글은 슬롯 SJIS, 나머지(숫자·영문·부호·개행)는 원래 SJIS."""
    out = bytearray()
    for ch in kr:
        if "가" <= ch <= "힣":
            out += H.encode_kr(ch)
        elif ch == "\n":
            out.append(0x0A)
        else:
            out += ch.encode("shift_jis")
    return bytes(out)


def strings(buf):
    """{파일오프셋: JP} — 코드가 부르는 전투 문자열."""
    out = {}
    for _imm, _lui, _op, addr in iter_lui_pairs(buf, {MIPS_ADDIU, MIPS_ORI}):
        fo = addr - 0x80010000 + 0x800
        if not any(lo <= fo < hi for lo, hi in CORPUS):
            continue
        j = buf.find(b"\x00", fo)
        if j < 0 or not (2 <= j - fo <= 200):
            continue
        try:
            s = buf[fo:j].decode("cp932")
        except Exception:  # noqa: BLE001 — 코드/데이터 구간
            continue
        # `\x80` 이 든 것은 문자열이 아니라 **포인터 배열이 앞에 붙은 자리**다.
        if ("\x80" in s) or not (KANA.search(s) or "%" in s):
            continue
        out[fo] = s
    for fo in EXTRA_OFF:
        j = buf.find(b"\x00", fo)
        out[fo] = buf[fo:j].decode("cp932")
    return out


def plan():
    """([(오프셋, JP, KR, 슬롯)], 넘치는 것, 번역 없는 것)."""
    buf = extract(ED2_LBA, ED2_SIZE)
    ed2 = jp_map("battle_ed2")
    # ⚠ **`battle_text.B` 는 `battle.json` 만 싣는다** — 「공용표」라고 다 공용이 아니다.
    # 아이템 획득·포기·소지품 초과 문구는 `items_battle.json` 에 있고 ED2 도 **같은 원문**을
    # 쓰는데, 여기서 안 보면 ED2 에만 일본어가 남는다(2026-08-17 실측 20건 — 그중 셋이
    # 실제 문장이고 나머지는 `%c%s%c` 같은 서식뿐이라 무해했다. 그래서 여태 안 보였다).
    items = jp_map("items_battle")
    fit, over, none = [], [], []
    for fo, jp in sorted(strings(buf).items()):
        if SKIP.search(jp):
            continue
        # ⚠ **ED2 정본이 먼저다**(2026-08-17). 두 편은 같은 원문을 쓰지만 **정발이 갈린다** —
        # `戦いに勝利しました。` 가 ED1 정발 「전투에서 승리했다.」· ED2 정발 「전투에서
        # 승리하였습니다」이고, 승리 로그 세 줄이 통째로 다르다. ED1 표를 앞에 두면 ED2 화면에
        # ED1 문안이 나가는데 **빌드는 통과한다**(둘 다 유효한 번역이라 게이트가 못 잡는다).
        # 공유는 「ED2 정본에 없을 때만」이다.
        kr = ed2.get(jp) or B.get(jp) or items.get(jp)
        if kr is None:
            none.append((fo, jp))
            continue
        end = buf.find(b"\x00", fo)
        nxt = end
        while nxt < len(buf) and buf[nxt] == 0:
            nxt += 1
        slot = nxt - fo
        (fit if len(_enc(kr)) + 1 <= slot else over).append((fo, jp, kr, slot))
    return fit, over, none


MIN_POOL = 8  # 이보다 짧은 꼬리는 조각이라 안 쓴다(파편만 는다)


def relocate(buf, fit, over):
    """제자리로 못 넣는 문안을 **풀에 옮기고 참조를 갱신**한다. 반환: 옮긴 수.

    ⚠ **조사 훅으로는 이 자리가 안 풀린다**(2026-08-16 실측). 훅은 표시할 때 병기를 고르는
    장치라 **저장된 문자열이 짧아지지 않는다** — 병기를 한 글자로 줄여도 29건이 여전히
    넘친다. 넘침은 병기가 아니라 **슬롯** 문제이고, 답은 ED1 이 이미 쓰는 재배치다
    (`patch_items.apply_battle`).

    **풀은 두 곳에서 나온다.** ① 옮기는 문자열이 비우는 옛 칸(993B) ② 제자리로 들어간
    문안이 남기는 **꼬리**(한국어가 원문보다 짧아서 생긴다). ①만으로는 184B 모자란다.

    ⚠ **`lui` 까지 갱신해야 한다.** 재배치는 구획 안 이동이 아니라 상위 16비트가 바뀌므로
    `addiu` lo 만 고치면 엉뚱한 주소를 읽는다. 그래서 **그 `lui` 를 다른 주소와 나눠 쓰는지
    전수로 확인**하고(공유면 오염되니 즉시 실패), 부호확장(`addiu`)도 보정한다.
    """
    from patch_items import ram_of

    targets = {ram_of(fo) for fo, _j, _k, _s in over}
    refs, lui_use = {}, {}
    for imm_off, lui_off, op, addr in iter_lui_pairs(bytes(buf), {MIPS_ADDIU, MIPS_ORI}):
        if addr in targets:
            refs.setdefault(addr, []).append((imm_off, lui_off, op))
        lui_use.setdefault(lui_off, set()).add(addr)

    # ⚠ **빈 문자열을 가리키는 참조가 꼬리 안에 숨어 있다**(2026-08-16 실측 4곳:
    # 0x0051F4·0xD4988·0xD49AC·0xD4A40). 코드가 「아무것도 안 나오는 자리」로 그 주소를
    # 쓰는데, 우리가 거기에 문안을 심으면 **없어야 할 글자가 화면에 뜬다.** 널이 하나
    # 남아 있기만 하면 되므로 그 **한 바이트를 경계로 풀을 가른다.**
    old_starts = {fo for fo, _j, _k, _s in over}
    reserved = sorted(
        (a - 0x80010000 + 0x800)
        for a in {addr for _i, _l, _o, addr in iter_lui_pairs(bytes(buf), {MIPS_ADDIU, MIPS_ORI})}
        if (a - 0x80010000 + 0x800) not in old_starts
    )

    def _add(pools, lo, hi):
        """[lo,hi) 에서 예약 바이트를 도려내고 쓸 만한 조각만 넣는다."""
        for r in reserved:
            if lo <= r < hi:
                _add(pools, lo, r)
                _add(pools, r + 1, hi)
                return
        if hi - lo >= MIN_POOL:
            pools.append([lo, hi])

    pools, moves = [], []
    for fo, _jp, kr, slot in fit:  # 제자리 + 남는 꼬리를 풀로
        kb = _enc(kr) + b"\x00"
        buf[fo : fo + slot] = kb.ljust(slot, b"\x00")
        _add(pools, fo + len(kb), fo + slot)
    for fo, jp, kr, slot in over:  # 옛 칸을 비우고 풀에 넣는다
        buf[fo : fo + slot] = b"\x00" * slot
        _add(pools, fo, fo + slot)
        moves.append((ram_of(fo), _enc(kr) + b"\x00", jp))

    pools.sort()
    merged = []
    for lo, hi in pools:  # 인접 조각은 붙인다 — 큰 문안이 들어갈 자리가 생긴다
        if merged and merged[-1][1] == lo:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    pools = merged

    for old, kb, jp in sorted(moves, key=lambda m: -len(m[1])):  # 큰 것부터 최적적합
        cand = [p for p in pools if p[1] - p[0] >= len(kb)]
        if not cand:
            raise SystemExit(f"풀 부족: {jp[:14]!r} ({len(kb)}B)")
        pool = min(cand, key=lambda p: p[1] - p[0])
        dst = pool[0]
        pool[0] += len(kb)
        buf[dst : dst + len(kb)] = kb
        new = ram_of(dst)
        hi_sx = (new >> 16) + (1 if new & 0x8000 else 0)  # addiu 부호확장 보정
        assert refs.get(old), f"참조 0건: {jp[:14]!r}"
        for imm_off, lui_off, op in refs[old]:
            others = lui_use[lui_off] - {old}
            assert not others, f"0x{imm_off:X}: lui 공유({[hex(a) for a in others]}) — 재배치 불가"
            hi_w, lo_w = (new >> 16, new & 0xFFFF) if op == MIPS_ORI else (hi_sx, new & 0xFFFF)
            w = struct.unpack_from("<I", buf, lui_off)[0]
            struct.pack_into("<I", buf, lui_off, (w & 0xFFFF0000) | hi_w)
            w = struct.unpack_from("<I", buf, imm_off)[0]
            struct.pack_into("<I", buf, imm_off, (w & 0xFFFF0000) | lo_w)
    left = sum(p[1] - p[0] for p in pools)
    print(
        f"  재배치 {len(moves)}건 · 참조 갱신 {sum(len(refs[o]) for o, _, _ in moves)}곳 (풀 잔여 {left}B)"
    )
    return len(moves)


def main():
    fit, over, none = plan()
    if "--plan" in sys.argv:
        for fo, _jp, kr, slot in fit:
            print(f"  {fo:#07x} [{slot:>3}B] → {kr!r}")
        for fo, _jp, kr, slot in over:
            print(f"  ⚠ 넘침 {fo:#07x} [{slot}B] → {kr!r} ({len(_enc(kr)) + 1}B)")
        print(f"\n제자리 {len(fit)} · 넘침 {len(over)} · 번역 없음 {len(none)}")
        return 0
    buf = bytearray(extract(ED2_LBA, ED2_SIZE, path=IMG))
    moved = relocate(buf, fit, over)
    with open(IMG, "r+b") as f:
        n = write_user_data(f, ED2_LBA, bytes(buf), label="ED2 전투 문안 (ED2.EXE)")
    print(
        f"ED2.EXE: 섹터 {n}개 수정 — 전투 문안 {len(fit)}건 제자리 + {moved}건 재배치"
        f" (미번역 {len(none)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
