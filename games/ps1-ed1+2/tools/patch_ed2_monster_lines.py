#!/usr/bin/env python3
"""ED2 몬스터 전투 대사(`ED2MON0~5.BIN`) 한글화 — **제자리 치환만** 한다.

이름은 `patch_ed2_monsters.py` 가 맡고 여기는 **대사**다. 파일 안의 일본어 문자열 1,557개
가운데 진짜 대사는 **123개뿐**이다 — 나머지는 이름이거나, 2바이트 값이 SJIS 한자로 읽힌
이진 자료다(`曚B席` 류). 그래서 걸러내는 규칙이 이 도구의 반이다.

**79개는 자동 생성한다.** `Xが現れた。`·`XとYが現れた。`·`Xとの戦闘だ。` 는 이름이 문자열에
**박혀 있어서**(런타임 인자가 아니다) 이름 정본만 있으면 조사까지 정적으로 정해진다 —
`슬라임` 은 받침이 있으니 `이`, `부두` 는 `가`. 병기(`이(가)`)를 쓸 이유가 없다.

나머지 28개는 손으로 옮겨 `textmap/monster_lines_ed2.json` 에 둔다.

⚠ **조각으로 갈려 있다.** 한 문장이 `%c%s%cは` + `%c%s%cを冷たい` + `視線で見つめた。` 로
나뉘어 저장되고 엔진이 이어 붙인다. 한국어도 일본어와 어순이 같아서 **조각째 옮겨도 이어
붙는다** — 조각을 합치려 들면 슬롯 구조를 깨뜨린다.

⚠ **넘치면 건너뛴다**(`patch_ed2_battle.py` 와 같은 방침). 뒤가 곧 다음 문자열이다.

🔴 **밀어내기 재packing 은 하지 말 것 — 두 번 시험하고 접었다**(2026-08-17 실측). 이 파일은
데이터가 아니라 **오버레이(코드+데이터)** 다: `ED2.EXE` 디스패처(`0x8006D3D0`)가
`jal 0x8014A2DC` 처럼 **파일 안의 주소를 직접 부른다**(적재 = 로더 `0x800959F4` 가
파일표 13+g 번째를 `0x8014A000` 에 통짜로). 문자열을 밀면 뒤의 **코드가 밀려** 그 jal 들이
어긋나 전투 진입에서 프리징한다.

**대신 꼬리 재배치는 안전하다**(같은 날 인게임 증명 — devlog). 문자열 참조는 전부
**오버레이 안의 `lui`+`addiu` 쌍**이므로(파일당 수십 건), 슬롯을 넘는 문안은
① 파일 꼬리(마지막 섹터 여유)에 새로 쓰고 ② 그 쌍만 갱신한다. 코드는 한 바이트도 안
움직인다. write_memory 로 재현해 재조우 → 참조 지점 exec BP 에서 `a1 = 새 주소` 를 실측했다.
⚠ 부호확장: `lo ≥ 0x8000` 이면 `lui` 가 +1 로 박혀 있다(`0x8014A018` 이
`lui 0x8015; addiu -0x5FE8`). 갱신도 같은 규칙을 따라야 한다.

  python3 tools/patch_ed2_monster_lines.py --plan   # 무엇이 들어가고 무엇이 남는지
  python3 tools/patch_ed2_monster_lines.py          # 이미지에 적용
"""

import hashlib
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, ROOT, extract, write_user_data
from ed2_monster_review import MON, decode_sjis, resolve_name

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
NAMES = os.path.join(ROOT, "textmap", "monsters_ed2.json")
LINES = os.path.join(ROOT, "textmap", "monster_lines_ed2.json")

JP = re.compile(r"[ぁ-んァ-ヴー一-鿿]")
KANA = re.compile(r"[ぁ-んァ-ヴ]")
CTL = re.compile(r"[\x00-\x1f]")
# ⚠ cp932 는 미정의 바이트를 **사용자 영역**으로 넘긴다 — 이진 자료가 여기로 샌다.
PUA = re.compile(r"[-]")

APPEAR = re.compile(r"^(.+?)(?:と(.+?))?が現れた。$")
BATTLE = re.compile(r"^(.+?)との戦闘だ。$")


def is_dialog(s):
    """대사인가 — 이진 자료를 걸러낸다.

    ⚠ 규칙 셋이 다 필요하다. ①**세 글자 미만은 자료다**(2바이트 값 하나가 한자로 읽힌다 —
    `筧` 이 269번 나온다). ②**가나가 없으면 자료다**(대사엔 조사가 반드시 낀다). ③사용자
    영역 글자가 있으면 자료다. 하나라도 빼면 수백 개가 샌다.
    """
    if len(s) < 3 or PUA.search(s) or CTL.search(s) or not KANA.search(s):
        return False
    core = re.sub(r"%[csd]|[!?！？。、…・\s]", "", s)
    return bool(core) and len(JP.findall(core)) / len(core) >= 0.8


def josa(word, pair):
    """받침에 따라 조사를 고른다 — 이름이 문자열에 박혀 있으니 정적으로 정해진다.

    pair 는 (받침 있을 때, 없을 때). 한글이 아닌 꼬리(영문 접미 `A`)는 무받침으로 본다.
    """
    tail = word.strip()[-1:] if word.strip() else ""
    has = "가" <= tail <= "힣" and (ord(tail) - 0xAC00) % 28
    return pair[0] if has else pair[1]


def auto_lines(names):
    """`Xが現れた。` 류를 이름 정본에서 만든다 — {JP: KR}."""
    out = {}
    for jp, kr in names.items():
        # ⚠ **마침표를 붙인다.** ED2 정발은 안 붙이지만(`슬라임이 나타났다`) 원문에는 `。`
        # 가 있고 ED1 정발도 붙이며, 우리 표기 방침이 「문장 끝 마침표 일관 추가」다
        # (유저 재확인 2026-08-17). 1바이트가 늘어 슬롯 넘침이 다시 생기면 그건
        # **보고하고 건너뛰는 게 아니라 줄여서라도 넣어야 하는 자리**다 — 넘치면 원문이
        # 그대로 남아 화면에 일본어가 나간다.
        out[f"{jp}が現れた。"] = f"{kr}{josa(kr, ('이', '가'))} 나타났다."
        out[f"{jp}との戦闘だ。"] = f"{kr}{josa(kr, ('과', '와'))}의 전투다."
        for jp2, kr2 in names.items():
            if jp2 != jp:
                out[f"{jp}と{jp2}が現れた。"] = (
                    f"{kr}{josa(kr, ('과', '와'))} {kr2}{josa(kr2, ('이', '가'))} 나타났다."
                )
    return out


def _enc(kr):
    out = bytearray()
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return bytes(out)


BASE = 0x8014A000  # 오버레이 적재 주소 — 로더 0x800959F4 의 상수(EXE 에 이 한 곳)
BIN_DIR_LBA = 1182  # \BIN 디렉토리 레코드 섹터 (reinsert_kr_pilot 과 같은 값)
MIPS_LUI, MIPS_ADDIU, MIPS_ORI = 0x0F, 0x09, 0x0D


def overlay_refs(orig):
    """오버레이 안에서 자기 자신(BASE+)을 가리키는 `lui`+`addiu/ori` 쌍.

    반환: ({대상 파일오프셋: [(imm_off, lui_off, op)]}, {lui_off: {대상들}}).
    ⚠ **원본에서 스캔한다** — 우리 빌드는 문자열 슬롯만 바꾸고 코드는 안 건드리므로
    코드 오프셋은 같지만, 스캔 자체가 한글 바이트를 명령으로 오독하면 안 된다.
    """
    refs, lui_use = {}, {}
    lui_reg = {}  # 레지스터 → (상위16, lui_off)
    for p in range(0, len(orig) - 4, 4):
        w = struct.unpack_from("<I", orig, p)[0]
        op = w >> 26
        if op == MIPS_LUI:
            lui_reg[(w >> 16) & 0x1F] = ((w & 0xFFFF) << 16, p)
        elif op in (MIPS_ADDIU, MIPS_ORI):
            rs = (w >> 21) & 0x1F
            if rs in lui_reg:
                hi, lui_off = lui_reg[rs]
                imm = w & 0xFFFF
                if op == MIPS_ADDIU and imm & 0x8000:
                    imm -= 0x10000
                addr = hi + imm
                if BASE <= addr < BASE + len(orig):
                    refs.setdefault(addr - BASE, []).append((p, lui_off, op))
                    lui_use.setdefault(lui_off, set()).add(addr - BASE)
    return refs, lui_use


def plan():
    """([(lba, 오프셋, JP, KR, 슬롯)], 넘치는 것, 문안 없는 것)."""
    with open(NAMES, encoding="utf-8") as f:
        names = json.load(f)
    with open(LINES, encoding="utf-8") as f:
        hand = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    table = auto_lines(names)
    table.update(hand)  # 손으로 정한 것이 이긴다

    fit, move, over, none = [], [], [], []
    for group, (lba, size) in sorted(MON.items()):
        buf = bytes(extract(lba, size))
        refs, _lui_use = overlay_refs(buf)
        i = 0
        while i < len(buf) - 1:
            if buf[i] == 0:
                i += 1
                continue
            j = buf.find(b"\x00", i)
            if j < 0:
                break
            s = decode_sjis(buf[i:j]) if 2 <= j - i <= 200 else None
            # 이름 판정은 **정렬 후보 전부**를 정본에 걸어 본다 — 한 후보만 보면 유령 접두가
            # 붙은 자리가 대사로 새어 「문안 없음」이 된다(`resolve_name` 참조).
            if s and is_dialog(s) and resolve_name(buf[i:j], names) is None:
                nxt = j
                while nxt < len(buf) and buf[nxt] == 0:
                    nxt += 1
                head = j - len(s.encode("cp932", "replace"))
                slot = nxt - head
                kr = table.get(s)
                if kr is None:
                    none.append((group, head, s))
                elif len(_enc(kr)) + 1 <= slot:
                    fit.append((lba, head, s, kr, slot))
                elif refs.get(head):
                    # 슬롯을 넘고 **참조가 있으면 꼬리로 재배치**한다(docstring 의 수법).
                    move.append((lba, head, s, kr, slot))
                else:
                    # 참조가 없으면 옮길 수 없다(무참조 = 우리가 모르는 방법으로 읽힌다).
                    # 온점을 떼서라도 제자리에 넣는다 — 안 들어가면 원문이 남아 일본어가
                    # 화면에 나가므로 그게 최악이다.
                    if kr.endswith(".") and len(_enc(kr)) <= slot:
                        fit.append((lba, head, s, kr[:-1], slot))
                    else:
                        over.append((lba, head, s, kr, slot))
            i = j + 1
    return fit, move, over, none


def _relocate(buf, orig, moves):
    """`moves` 를 꼬리로 빼고 오버레이 참조를 갱신한다. 반환: (새 buf, 옮긴 수).

    게이트 셋 — 셋 다 실측 사고에서 나왔다:
    ① 갱신할 명령이 **원본 바이트 그대로**인지 대조(다르면 다른 패치와 충돌).
    ② `lui` 상위가 바뀌는 경우 그 `lui` 를 **다른 대상과 공유하면 즉시 실패**.
    ③ 문자열 슬롯·꼬리 밖(= 코드)은 **한 바이트도 안 바뀌었는지** 마지막에 대조.
    """
    refs, lui_use = overlay_refs(orig)
    out = bytearray(buf)
    touched = []  # 우리가 쓰는 [lo,hi) — 게이트 ③ 이 이 밖을 대조한다
    cur = (len(out) + 3) & ~3
    out = out.ljust(cur, b"\x00")
    for off, _jp, kr, slot in moves:
        kb = _enc(kr) + b"\x00"
        dst = len(out)
        out += kb.ljust((len(kb) + 3) & ~3, b"\x00")
        touched.append((dst, len(out)))
        out[off : off + slot] = b"\x00" * slot  # 옛 슬롯은 비운다(참조는 전부 옮긴다)
        touched.append((off, off + slot))
        new = BASE + dst
        lo = new & 0xFFFF
        for imm_off, lui_off, op in refs[off]:
            w_imm = struct.unpack_from("<I", orig, imm_off)[0]
            w_lui = struct.unpack_from("<I", orig, lui_off)[0]
            assert struct.unpack_from("<I", out, imm_off)[0] == w_imm, hex(imm_off)
            assert struct.unpack_from("<I", out, lui_off)[0] == w_lui, hex(lui_off)
            # ori 는 무부호, addiu 는 lo ≥ 0x8000 이면 lui +1 (docstring 의 부호확장 규칙)
            hi = (new >> 16) if op == MIPS_ORI else (new >> 16) + (1 if lo & 0x8000 else 0)
            old_hi = w_lui & 0xFFFF
            if old_hi != hi:
                others = lui_use[lui_off] - {off}
                assert not others, (
                    f"0x{imm_off:X}: lui 공유({[hex(BASE + o) for o in others]}) — 재배치 불가"
                )
                struct.pack_into("<I", out, lui_off, (w_lui & 0xFFFF0000) | hi)
                touched.append((lui_off, lui_off + 4))
            struct.pack_into("<I", out, imm_off, (w_imm & 0xFFFF0000) | lo)
            touched.append((imm_off, imm_off + 4))
    return bytes(out), touched


def _update_dir_size(f, group, newsize):
    """ISO 디렉터리의 크기 필드(양 엔디언) 갱신 — `reinsert_kr_pilot` 과 같은 수법."""
    bdir = bytearray(extract(BIN_DIR_LBA, 2048, path=IMG))
    want = f"ED2MON{group}.BIN;1".encode("ascii")
    i = 0
    while i < len(bdir) and bdir[i]:
        nlen = bdir[i + 32]
        if bdir[i + 33 : i + 33 + nlen] == want:
            bdir[i + 10 : i + 14] = newsize.to_bytes(4, "little")
            bdir[i + 14 : i + 18] = newsize.to_bytes(4, "big")
            write_user_data(f, BIN_DIR_LBA, bytes(bdir), label="ISO 디렉터리 크기")
            return
        i += bdir[i]
    raise SystemExit(f"BIN 디렉토리에 ED2MON{group}.BIN 없음")


def main():
    fit, move, over, none = plan()
    if "--plan" in sys.argv:
        for _lba, off, jp, kr, slot in fit:
            print(f"  {off:#07x} [{slot:>3}B] {jp} → {kr}")
        for _lba, off, jp, kr, slot in move:
            print(f"  ↪ 꼬리 {off:#07x} [{slot}B] {jp} → {kr} ({len(_enc(kr)) + 1}B)")
        for _lba, off, jp, kr, slot in over:
            print(f"  ⚠ 넘침 {off:#07x} [{slot}B] {jp} → {kr} ({len(_enc(kr)) + 1}B)")
        for group, off, jp in none:
            print(f"  ⚠ 문안 없음 ED2MON{group} {off:#07x} {jp}")
        print(
            f"\n제자리 {len(fit)} · 꼬리 재배치 {len(move)} · 넘침 {len(over)} · 문안 없음 {len(none)}"
        )
        return 0

    by_lba, mv_lba = {}, {}
    for lba, off, _jp, kr, slot in fit:
        by_lba.setdefault(lba, []).append((off, kr, slot))
    for lba, off, jp, kr, slot in move:
        mv_lba.setdefault(lba, []).append((off, jp, kr, slot))
    total = moved = 0
    for group, (lba, size) in sorted(MON.items()):
        if lba not in by_lba and lba not in mv_lba:
            continue
        orig = bytes(extract(lba, size))
        buf = bytearray(extract(lba, size, path=IMG))
        slots = []
        for off, kr, slot in by_lba.get(lba, ()):
            b = _enc(kr) + b"\x00"
            buf[off : off + slot] = b + b"\x00" * (slot - len(b))
            slots.append((off, off + slot))
        new, touched = _relocate(buf, orig, mv_lba.get(lba, ()))
        moved += len(mv_lba.get(lba, ()))
        # 게이트 ③ — 코드 구간 무변경: 우리가 쓴 자리 밖은 빌드 이전과 byte 동일해야 한다
        touched += slots
        marks = bytearray(len(new))
        for lo, hi in touched:
            for k in range(lo, min(hi, len(marks))):
                marks[k] = 1
        base = bytes(extract(lba, size, path=IMG)).ljust(len(new), b"\x00")
        for k in range(len(new)):
            assert marks[k] or new[k] == base[k], f"ED2MON{group} 코드 구간 변형 @0x{k:X}"
        assert (len(new) + 2047) // 2048 == (size + 2047) // 2048, f"ED2MON{group} 섹터 증가"
        with open(IMG, "r+b") as f:
            total += write_user_data(f, lba, new, label=f"ED2MON{group} 전투 대사")
            if len(new) != size:
                _update_dir_size(f, group, len(new))
    total += _apply_sha_table()
    print(
        f"ED2MON: 섹터 {total}개 수정 — 전투 대사 {len(fit)}건 제자리 + {moved}건 꼬리 재배치"
        f" (넘침 {len(over)} · 문안 없음 {len(none)})"
    )
    return 0


SHA_TABLE = os.path.join(ROOT, "script", "ED2MON_LINES.json")


def _apply_sha_table():
    """`script/ED2MON_LINES.json`(sha1 키) 를 **제자리 치환**한다.

    ⚠ **위 열거가 절반을 못 본다.** 널 구분으로 조각을 뜨는데 대사 앞에 이진이 붙으면
    조각째 디코드가 깨져 통째로 버려진다(디코드 실패 43,993건 실측 2026-08-16). 그래서
    이 표는 **빌드 이미지에서 꼬리를 훑어** 원문을 찾는다 — `patch_scn_orphans` 와 같은 수법.

    ⚠ **원문은 리포에 안 남긴다** — 키가 JP sha1 앞 10자다(`monster_lines_ed2.json` 은
    JP 를 그대로 키로 쓰는 옛 표라, 이 방식으로 옮겨 가야 한다).
    """
    if not os.path.exists(SHA_TABLE):
        return 0
    with open(SHA_TABLE, encoding="utf-8") as f:
        table = json.load(f)
    n = 0
    with open(IMG, "r+b") as f:
        for _group, (lba, size) in sorted(MON.items()):
            # ⚠ **섹터 정렬 크기로 읽는다** — 원래 크기(size)로 읽고 다시 쓰면 재배치가
            # 붙인 **꼬리를 0 으로 밀어 버린다**(2026-08-17 실측: 재배치 20건이 조용히
            # 사라지고 빌드는 통과했다).
            cap = (size + 2047) // 2048 * 2048
            data = bytearray(extract(lba, cap, path=IMG))
            here = {}
            for part in bytes(data).split(b"\x00"):
                if not (4 <= len(part) <= 1024):
                    continue
                for k in range(len(part) - 3):
                    try:
                        t = part[k:].decode("cp932")
                    except UnicodeDecodeError:
                        continue
                    here.setdefault(hashlib.sha1(t.encode()).hexdigest()[:10], t)
            hits = 0
            for key, kr in table.items():
                jp = here.get(key)
                if jp is None:
                    continue
                jb, kb = jp.encode("cp932"), _enc(kr)
                for m in list(re.finditer(re.escape(jb), bytes(data))):
                    i, e = m.start(), m.end()
                    nxt = e
                    while nxt < len(data) and data[nxt] == 0:
                        nxt += 1
                    if nxt == e:  # 널종단이 아니면 남의 문자열 한복판이다
                        continue
                    if len(kb) + 1 > nxt - i:
                        continue
                    data[i:nxt] = (kb + b"\x00").ljust(nxt - i, b"\x00")
                    hits += 1
            if hits:
                n += write_user_data(f, lba, bytes(data), label=f"ED2MON 대사(표) {hits}곳")
    return n


if __name__ == "__main__":
    sys.exit(main())
