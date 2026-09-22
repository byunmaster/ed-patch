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

# ⚠ **전체 파일을 옮겨도 안전한 이유** — 로더가 이 파일을 "표 13+g 번째"로 찾아 **파일
# 전체를 통짜로** 0x8014A000 에 올린다(디스패처는 그 RAM 주소 기준 `jal` 만 쓴다, 위
# 모듈 docstring 참조). 그래서 **내부 바이트 배치**(문자열·코드 상대 오프셋)만 안
# 흔들면, 파일이 디스크 **어느 LBA 에서** 오든 무관하다 — reinsert_kr_pilot 의 SCN
# DUMMY 재배치와 같은 논리다. 반대로 파일 내부에서 문자열을 밀어내는 건(재삽입기
# docstring 의 "밀어내기 재packing 은 하지 말 것") 여전히 금지 — 그건 내부 상대
# 오프셋이 흔들려 `jal` 대상이 어긋난다. 이 함수가 하는 "그룹 재배치"는 내부는 안
# 건드리고 **디스크 위치만** 옮기는 것이라 다른 종류의 안전이다.
#
# ⚠ **SCN 재배치(`reinsert_kr_pilot.DUMMY_LBA=91700`)와 자리를 나눈다** — 같은
# DUMMY.;1(LBA 91700~107205, 31.7MB) 안이지만 SCN 은 91700 부터 순차로 자라므로,
# 그 성장분과 안 겹치게 반대편 끝에서부터 예약한다(2026-09-19, 마스터 요청으로
# ED2MON 그룹 파일에도 DUMMY 재배치를 추가하며 신설). ED2MON 여섯 파일은 각각
# 5~46KB 라(`MON` 참조) 합쳐도 300KB(150섹터) 를 안 넘는다 — 넉넉히 이격한다.
ED2MON_DUMMY_LBA = 106000  # DUMMY.;1 끝(107205)에서 1205섹터(2.4MB) 여유를 두고 시작


def _live_group_lba(path=None):
    """`MON`(정적 원본 LBA)이 아니라 **지금 이미지의 ISO 디렉터리**에서 그룹별 현재
    LBA·크기를 읽는다 — `{group: (lba, size)}`.

    🔴 **정적 `MON` 을 그대로 읽으면 다른 패처의 재배치를 놓친다**(2026-09-22 실측,
    마스터 QA 026 재조사). `patch_ed2_monsters.py`(이름표)가 이 `main()` 보다 **먼저**
    돌아 그룹을 DUMMY 로 옮길 수 있는데(`ED2MON3/4` 가 실제로 그랬다), 이 함수 이전엔
    아래 두 자리(`main()` 의 제자리 루프 · `_apply_sha_table()`)가 **정적 `MON` 으로
    읽고 썼다** — 그 결과 옛(버려진) LBA 에 새 문안을 얹고, 디렉터리는 이름표가 옮겨
    둔 새 LBA 를 그대로 가리켜 **문안 패치가 아무도 안 가리키는 자리에 고아로
    남았다**(대사표 되읽기 게이트가 44건까지 튀운 원인 — 내가 안 건드린 기존 문안도
    포함됐었다). ⇒ **이 함수가 모든 읽기/쓰기의 진짜 정본이다** — 매번 이미지에서
    다시 읽는다(캐시하지 않는다, 이전 패처가 방금 옮겼을 수 있다).
    """
    img = path or IMG
    bdir = bytes(extract(BIN_DIR_LBA, 2048, path=img))
    by_name = {}
    i = 0
    while i < len(bdir) and bdir[i]:
        nlen = bdir[i + 32]
        name = bytes(bdir[i + 33 : i + 33 + nlen]).decode("ascii", "replace")
        lba = int.from_bytes(bdir[i + 2 : i + 6], "little")
        size = int.from_bytes(bdir[i + 10 : i + 14], "little")
        by_name[name] = (lba, size)
        i += bdir[i]
    out = {}
    for g, (orig_lba, orig_size) in MON.items():
        out[g] = by_name.get(f"ED2MON{g}.BIN;1", (orig_lba, orig_size))
    return out


def trace_lba(tag):
    """`ED2MON_TRACE=1` 일 때만 — 지금 이미지의 그룹→LBA 를 한 줄로 찍는다.

    🔴 **ED2MON 은 소비자가 셋이다**(이름표 `patch_ed2_monsters.main` · 대사표 이 파일의
    `main`+`_apply_sha_table` · 맨 뒤 `finalize_connector_space`). 그중 대사표만 파일을
    통째로 DUMMY 로 옮기므로(`_update_dir_entry`), **뒤에 오는 소비자가 정적 `MON` 을
    읽으면 유령 자리를 본다.** 단계별 좌표를 안 찍으면 최종 상태만 보고 "어디서
    갈렸는지"를 못 가른다 — 실측으로 되읽기 44건을 며칠 못 좁힌 게 그래서다.
    """
    if os.environ.get("ED2MON_TRACE") != "1":
        return
    live = _live_group_lba()
    moved = [f"{g}:{lba}{'*' if lba != MON[g][0] else ''}" for g, (lba, _s) in sorted(live.items())]
    print(f"  [ED2MON_TRACE] {tag:34s} " + " ".join(moved), flush=True)


def _update_dir_entry(f, fname, new_lba, new_size):
    """ISO 디렉터리의 LBA·크기(양 엔디언) 갱신 — `reinsert_kr_pilot` 의 dir_moves 와 같은 수법.

    `_update_dir_size` 와 달리 **LBA 도 옮긴다** — 그룹 파일 전체를 DUMMY 영역으로
    재배치할 때 쓴다(파일 자체는 안 건드리고 어디서 읽어 오는지만 바꾼다).
    """
    # 🔴 **읽기 전에 `f` 를 flush 한다.** 이 함수는 열린 핸들 `f` 로 쓰면서 읽기는
    # `extract(path=IMG)` 의 **별도 핸들**로 한다 — 앞선 호출이 쓴 내용이 파이썬 버퍼에
    # 남아 있으면 **디스크엔 아직 없어서 그 갱신을 못 보고 되돌린다.** 2026-09-22 계측으로
    # 확정: 대사표가 ED2MON3·4 를 연달아 DUMMY 로 옮겼는데 디렉터리엔 **4번만** 남고
    # 3번은 옛 LBA 그대로였다(→ 3번 그룹의 문안이 통째로 유령이 되어 되읽기 53건).
    f.flush()
    bdir = bytearray(extract(BIN_DIR_LBA, 2048, path=IMG))
    want = fname.encode("ascii")
    i = 0
    while i < len(bdir) and bdir[i]:
        nlen = bdir[i + 32]
        if bdir[i + 33 : i + 33 + nlen] == want:
            bdir[i + 2 : i + 6] = new_lba.to_bytes(4, "little")
            bdir[i + 6 : i + 10] = new_lba.to_bytes(4, "big")
            bdir[i + 10 : i + 14] = new_size.to_bytes(4, "little")
            bdir[i + 14 : i + 18] = new_size.to_bytes(4, "big")
            write_user_data(f, BIN_DIR_LBA, bytes(bdir), label="ISO 디렉터리 LBA·크기")
            return
        i += bdir[i]
    raise SystemExit(f"BIN 디렉토리에 {fname} 없음")


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
            # ⚠ `is_dialog` 의 「세 글자 미만은 자료다」가 `と` 한 글자(분열 메시지의 접속사,
            # 2026-09-13 마스터 QA `012`)를 자료로 오판해 스캔 밖으로 샜다 — 규칙을 안 풀고
            # **손으로 승인한 항목(`hand`)만** 길이 게이트를 건너뛰게 한다.
            if s and (is_dialog(s) or s in hand) and resolve_name(buf[i:j], names) is None:
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
    # 🔴 **읽기 전에 `f` 를 flush 한다.** 이 함수는 열린 핸들 `f` 로 쓰면서 읽기는
    # `extract(path=IMG)` 의 **별도 핸들**로 한다 — 앞선 호출이 쓴 내용이 파이썬 버퍼에
    # 남아 있으면 **디스크엔 아직 없어서 그 갱신을 못 보고 되돌린다.** 2026-09-22 계측으로
    # 확정: 대사표가 ED2MON3·4 를 연달아 DUMMY 로 옮겼는데 디렉터리엔 **4번만** 남고
    # 3번은 옛 LBA 그대로였다(→ 3번 그룹의 문안이 통째로 유령이 되어 되읽기 53건).
    f.flush()
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
    trace_lba("lines.main 진입")
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
    live = _live_group_lba()
    for group, (lba, orig_size) in sorted(MON.items()):
        if lba not in by_lba and lba not in mv_lba:
            continue
        # ⚠ **읽고 쓰는 자리는 정적 `lba` 가 아니라 `_live_group_lba()` 다** — `plan()`
        # 이 낸 `off`(그룹 안 상대 오프셋)는 정적 좌표로 구해도 유효하지만(재배치는
        # 그룹 파일의 시작 LBA 만 옮긴다), **읽고 쓸 실제 섹터**는 `patch_ed2_monsters.py`
        # (이 함수보다 먼저 돈다)가 이미 DUMMY 로 옮겨 놨을 수 있다(2026-09-22 실측 —
        # 옛 정적 lba 에 쓰면 디렉터리가 안 가리키는 자리에 문안이 고아로 남는다).
        cur_lba, size = live[group]
        # ⚠ **섹터 정렬 크기(`cap`)로 읽는다** — `size`로 읽으면 **이 그룹에 먼저 쓴 다른
        # 패처의 꼬리 재배치**(예: `patch_ed2_monsters.py`의 이름 재배치)를 통째로 잘라내고
        # 그 위에 되쓰게 된다(2026-09-13 실측: 모래두더지/불꽃의기사/육지해파리 이름이
        # 옛 슬롯도 새 자리도 없이 통째로 사라졌다 — 마스터 QA 052 RE 재현). `_apply_sha_table`
        # 은 이미 이 관용을 쓴다 — 여기만 안 맞춰져 있었다.
        cap = (size + 2047) // 2048 * 2048
        orig = bytes(extract(lba, orig_size))  # overlay_refs 대조 기준(원본 디스크, 빌드 아님)
        before = bytes(extract(cur_lba, cap, path=IMG))
        buf = bytearray(before)
        slots = []
        for off, kr, slot in by_lba.get(lba, ()):
            b = _enc(kr) + b"\x00"
            buf[off : off + slot] = b + b"\x00" * (slot - len(b))
            slots.append((off, off + slot))
        # "실제 쓰인 끝" 뒤에 붙인다 — cap 그대로 넘기면 이미 채워진 꼬리(다른 패처 것
        # 포함) 뒤에 또 이어 붙여 섹터를 넘긴다.
        used = max((k for k in range(len(buf) - 1, -1, -1) if buf[k]), default=-1) + 1
        used = (used + 3) & ~3
        new, touched = _relocate(bytearray(buf[:used]), orig, mv_lba.get(lba, ()))
        moved += len(mv_lba.get(lba, ()))
        content_len = len(new)  # 논리 길이 — 섹터 패딩(cap) 이전, 디렉터리 크기는 이걸 쓴다
        assert content_len <= cap, f"ED2MON{group}: 재배치 꼬리가 섹터 여유({cap}B)를 넘었다"
        new = new.ljust(cap, b"\x00")
        # 게이트 ③ — 코드 구간 무변경: 우리가 쓴 자리 밖은 빌드 이전과 byte 동일해야 한다
        touched += slots
        marks = bytearray(len(new))
        for lo, hi in touched:
            for k in range(lo, min(hi, len(marks))):
                marks[k] = 1
        base = before.ljust(len(new), b"\x00")
        for k in range(len(new)):
            assert marks[k] or new[k] == base[k], f"ED2MON{group} 코드 구간 변형 @0x{k:X}"
        with open(IMG, "r+b") as f:
            total += write_user_data(f, cur_lba, new, label=f"ED2MON{group} 전투 대사")
            if content_len != size:
                _update_dir_size(f, group, content_len)
    total += _apply_sha_table()
    print(
        f"ED2MON: 섹터 {total}개 수정 — 전투 대사 {len(fit)}건 제자리 + {moved}건 꼬리 재배치"
        f" (넘침 {len(over)} · 문안 없음 {len(none)})"
    )
    return 0


SHA_TABLE = os.path.join(ROOT, "script", "ED2MON_LINES.json")
# ⚠ **`_apply_sha_table` 은 재배치 경로가 없다** — 슬롯이 모자라면 `continue` 뿐이고
# 그 사실을 어디에도 보고하지 않는다(2026-09-13 실측: 283건 중 119건, 41%가 조용히
# 건너뛰어졌다 — 041①이 "107곳 병기 결정"으로 올린 표 태반이 화면에 안 들어갔다).
# `check_scn_jp_left`(build.py 의 화면 게이트)도 `ED2MON*.BIN` 을 스캔 범위 밖에 둬서
# 못 잡는다 — 이 파일군엔 그 축의 게이트가 아예 없었다.
# ⇒ **기준선 파일**로 대신한다(조판 지문과 같은 꼴) — 늘 찍고, 늘면 실패, 줄면 알린다
# (0 을 목표로 삼지 않는다 — 지금 세우면 이 브랜치가 통째로 빨간불이 되고, 그럼 아무도
# 안 본다). **수만이 아니라 (group, offset) 목록까지 굳힌다** — 하나 늘고 하나 줄면
# 수는 그대로라 수만 보면 조용히 지나간다.
# 🔴 **`script/` 안의 모든 키는 `_`로 시작해야 한다** — `reinsert_kr_pilot._load_script()` 가
# `script/*.json` 전부를 "씬"으로 읽어 `_` 로 안 가린 키를 블록 취급한다(실측: `_ids`(list)를
# `ids`로 처음 냈다가 `AttributeError: 'list' object has no attribute 'replace'`로 빌드가
# 죽었다 — `_load_overrides()` 가 리스트를 문안으로 읽으려 한 것). `ED2MON_LINES.json` 이
# 안 죽는 건 우연이다(값이 전부 문자열이라 `.replace()` 가 통과한다).
SKIP_BASELINE = os.path.join(ROOT, "script", "ed2mon_sha_skip_baseline.json")


def _apply_sha_table():
    """`script/ED2MON_LINES.json`(sha1 키) 를 **제자리 치환 + 넘치면 꼬리 재배치**한다.

    ⚠ **위 열거가 절반을 못 본다.** 널 구분으로 조각을 뜨는데 대사 앞에 이진이 붙으면
    조각째 디코드가 깨져 통째로 버려진다(디코드 실패 43,993건 실측 2026-08-16). 그래서
    이 표는 **빌드 이미지에서 꼬리를 훑어** 원문을 찾는다 — `patch_scn_orphans` 와 같은 수법.

    ⚠ **원문은 리포에 안 남긴다** — 키가 JP sha1 앞 10자다(`monster_lines_ed2.json` 은
    JP 를 그대로 키로 쓰는 옛 표라, 이 방식으로 옮겨 가야 한다).

    🔴 **재배치는 `plan()`/`_relocate()` 와 같은 길을 그대로 쓴다**(2026-09-13, 041① 퇴보
    이후 신설) — 새로 짜지 않는다. 참조(`overlay_refs`)가 있는 자리만 꼬리로 옮기고,
    없는 자리는 예전처럼 제자리 유지(슬롯 부족 기준선으로 보고)한다.

    🔴 **그룹 자체가 넘치면 파일 전체를 DUMMY 영역으로 재배치한다**(2026-09-19 신설,
    마스터 요청 — 그룹4 재배치 여유가 4B 까지 좁혀진 걸 보고 "더미로 옮기는 것도
    테스트해보자"). 내부 배치는 그대로 두고 **디스크 위치만** 옮기므로 `jal` 안전
    규칙(모듈 docstring)을 안 건드린다 — ISO 디렉터리 LBA·크기만 갱신하면 로더가
    새 자리에서 그대로 읽는다.
    """
    if not os.path.exists(SHA_TABLE):
        return 0
    with open(SHA_TABLE, encoding="utf-8") as f:
        table = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    n = moved_total = 0
    skipped = []  # [(id, group, key, slot, need)] — 참조가 없어 재배치도 못 하는 자리
    # ⚠ **`ED2MON_DUMMY_LBA` 에서 맨손으로 다시 시작하지 않는다** — `patch_ed2_monsters.py`
    # (이름표)가 이 함수보다 먼저 돌아 이미 그 자리에 그룹을 옮겨 뒀을 수 있다(2026-09-22
    # 실측). 그대로 시작하면 그 그룹을 덮어쓴다 — **이미 쓰인 DUMMY 영역 뒤에서** 잇는다.
    trace_lba("lines._apply_sha_table 진입")
    live0 = _live_group_lba()
    dummy_cursor = ED2MON_DUMMY_LBA
    for g_lba, g_size in live0.values():
        if g_lba >= ED2MON_DUMMY_LBA:
            dummy_cursor = max(dummy_cursor, g_lba + (g_size + 2047) // 2048)
    dir_entries = []  # [(fname, new_lba, new_size)] — 그룹 전체를 DUMMY 로 옮긴 것들
    with open(IMG, "r+b") as f:
        for group, (lba, orig_size) in sorted(MON.items()):
            # ⚠ **정적 `lba` 가 아니라 `_live_group_lba()`** — `patch_ed2_monsters.py`
            # 가 이미 DUMMY 로 옮겨 놨을 수 있다(경위는 `_live_group_lba` 독스트링).
            cur_lba, size = live0[group]
            # ⚠ **섹터 정렬 크기로 읽는다** — 원래 크기(size)로 읽고 다시 쓰면 재배치가
            # 붙인 **꼬리를 0 으로 밀어 버린다**(2026-08-17 실측: 재배치 20건이 조용히
            # 사라지고 빌드는 통과했다).
            cap = (size + 2047) // 2048 * 2048
            before = bytes(extract(cur_lba, cap, path=IMG))
            data = bytearray(before)
            orig = bytes(extract(lba, orig_size))  # 원본(JP, 디스크) — 대조 기준
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
            slots = []  # 제자리로 쓴 [(off, off+slot)] — 뒤 안전대조에서 "우리가 쓴 자리"로 뺀다
            moves = []  # 슬롯 부족+참조 있음 → 꼬리로 뺄 [(off, jp, kr, slot)]
            refs = None
            for key, kr in table.items():
                jp = here.get(key)
                if jp is None:
                    continue
                jb, kb = jp.encode("cp932"), _enc(kr)
                for m in list(re.finditer(re.escape(jb), bytes(data))):
                    i, e = m.start(), m.end()
                    # ⚠ **머리도 널 경계여야 한다** — 안 그러면 짧은 키가 **더 긴 다른
                    # 문안 한복판에 우연히 박힌 부분열**로 걸린다(끝만 널 검사하던 시절의
                    # 사각). 2026-09-13 실측: `%c%s%cは興奮した。\n`(302c06afb2)가
                    # `攻撃を受けた%c%s%cは興奮した。\n`(3c1ee910cd)의 **꼬리와 겹쳐**
                    # 제자리 치환이 그 안쪽을 덮어써 3c1ee910cd 쪽이 조용히 깨졌다
                    # (되읽기로 발각 — 도구 집계엔 하나도 안 걸렸다).
                    if i != 0 and data[i - 1] != 0:
                        continue
                    nxt = e
                    while nxt < len(data) and data[nxt] == 0:
                        nxt += 1
                    if nxt == e:  # 널종단이 아니면 남의 문자열 한복판이다
                        continue
                    need, slot = len(kb) + 1, nxt - i
                    if need > slot:
                        if refs is None:
                            refs, lui_use = overlay_refs(orig)
                        # ⚠ **lui 를 다른 대상과 나눠 쓰면 재배치 불가**다(`_relocate` 의
                        # 게이트) — 그 lui 의 상위값을 바꾸면 그 lui 를 같이 쓰는 다른
                        # 참조까지 엉뚱한 주소를 가리킨다. 미리 걸러 `_relocate` 를 통째로
                        # 죽이지 않는다(2026-09-13 실측: `0xD574` 공유로 배치 전체가 멈췄다).
                        shared = i in refs and any(
                            len(lui_use[lui_off]) > 1 for _imm_off, lui_off, _op in refs[i]
                        )
                        if i in refs and not shared:
                            moves.append((i, jp, kr, slot))
                        else:
                            skipped.append((f"{group}:{i:#x}", group, key, slot, need))
                        continue
                    data[i:nxt] = (kb + b"\x00").ljust(nxt - i, b"\x00")
                    hits += 1
                    slots.append((i, nxt))
            if not hits and not moves:
                continue
            # ⚠ **꼬리는 "실제 쓰인 끝" 뒤에 붙인다** — cap 그대로 넘기면 `_relocate` 가
            # 패딩 전부를 "이미 쓰인 것"으로 보고 그 뒤에 또 이어 붙여 섹터를 넘긴다.
            used = max((k for k in range(len(data) - 1, -1, -1) if data[k]), default=-1) + 1
            used = (used + 3) & ~3
            new = bytes(data[:used])
            if moves:
                new, mv_touched = _relocate(bytearray(new), orig, moves)
                moved_total += len(moves)
            else:
                mv_touched = []
            touched = list(mv_touched) + slots
            if len(new) > cap:
                # ⚠ **그룹 재배치 여유(cap)까지 넘었다** — 꼬리를 더 못 늘리니 파일
                # 전체를 DUMMY 영역으로 옮긴다. 내부 배치는 그대로라 무변경 대조는
                # 의미가 없다(원본 LBA 는 손도 안 대고 버려둔다 — 디렉터리가 더 이상
                # 그쪽을 안 가리키므로 무해하다).
                new_size = len(new)
                new_cap = (new_size + 2047) // 2048 * 2048
                new_lba = dummy_cursor
                dummy_cursor += new_cap // 2048
                n += write_user_data(
                    f,
                    new_lba,
                    new.ljust(new_cap, b"\x00"),
                    label=f"ED2MON{group} 전투 대사(표) {hits}건 (DUMMY 재배치)",
                )
                dir_entries.append((f"ED2MON{group}.BIN;1", new_lba, new_size))
                print(f"  ED2MON{group}: {cap}→{new_size}B, LBA {cur_lba}→{new_lba} (DUMMY 재배치)")
                continue
            new_size = len(new)
            new = new.ljust(cap, b"\x00")
            marks = bytearray(len(new))
            for lo, hi in touched:
                for k in range(lo, min(hi, len(marks))):
                    marks[k] = 1
            for k in range(len(new)):
                assert marks[k] or new[k] == before[k], (
                    f"ED2MON{group} 코드/데이터 무변경 위반 @0x{k:X}"
                )
            n += write_user_data(
                f, cur_lba, new, label=f"ED2MON{group} 전투 대사(표) {hits}건 제자리"
            )
            if new_size != size:
                _update_dir_size(f, group, new_size)
        for fname, new_lba, new_size in dir_entries:
            _update_dir_entry(f, fname, new_lba, new_size)
    _check_skip_baseline(skipped)
    if moved_total:
        print(f"  ED2MON 대사(표): 꼬리 재배치 {moved_total}건")
    return n


def _check_skip_baseline(skipped):
    """건너뜀을 **기준선과 대조**한다 — 조판 지문과 같은 꼴(늘 찍고, 늘면 실패, 줄면 알린다).

    0 을 목표로 삼지 않는다 — 지금(2026-09-13) 119건이라 0 으로 걸면 이 브랜치가 통째로
    빨간불이 되고, 그럼 아무도 안 본다(`CLAUDE.md`: "늘 빨간불이면 아무도 안 본다").
    """
    ids = sorted(s[0] for s in skipped)
    print(f"  ⚠ ED2MON 대사(표): 슬롯 부족으로 건너뜀 {len(ids)}건")
    if not os.path.exists(SKIP_BASELINE):
        print(
            f"    (기준선 없음 — {os.path.relpath(SKIP_BASELINE, ROOT)} 를 만들어 두면 회귀를 잡는다)"
        )
        return
    with open(SKIP_BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    base_ids = set(base["_ids"])
    new = sorted(set(ids) - base_ids)
    gone = sorted(base_ids - set(ids))
    print(f"    기준선 {len(base_ids)}건 대비 — 새로 건너뜀 {len(new)} · 해소됨 {len(gone)}")
    if gone:
        print(f"    ℹ 해소된 자리(기준선을 손으로 갱신할 것): {', '.join(gone)}")
    if new:
        detail = {s[0]: s for s in skipped}
        lines = [
            f"      {i}  key={detail[i][2]} slot={detail[i][3]}B need={detail[i][4]}B" for i in new
        ]
        raise SystemExit(
            "ED2MON 대사(표): 새로 건너뛴 자리가 생겼다 — 화면에 일본어가 남는다\n"
            + "\n".join(lines)
            + f"\n기준선: {os.path.relpath(SKIP_BASELINE, ROOT)} (의도된 변화면 이 파일을 갱신한다)"
        )


if __name__ == "__main__":
    sys.exit(main())
