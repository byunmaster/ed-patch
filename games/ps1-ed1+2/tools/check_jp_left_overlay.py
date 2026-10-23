#!/usr/bin/env python3
"""**최종 이미지**의 ED2MON 오버레이·실행파일에서, 「일본어 가나가 그대로 남은 문자열을 코드·포인터 표가 **참조하는** 줄」이 있으면 실패한다.

**왜.** ss-ed1+2(10-19)에서 ED2MON 시스템 문안 꼬리 영역을 두 패처가 각자 풀로 써서 몬스터 행동 문구가 엉뚱한 칸을 가리켰다.
기존 일본어 잔존 게이트(`check_jp_left` · `check_scn_jp_left` · `check_ed2_sys_corpus` · `check_ptr_target_coverage`)는 **씬 문안·EXE 시스템
표**를 보고, 몬스터 오버레이(`ED2MON0~5.BIN`)의 **구운 결과 문자열을 참조 단위로** 보지는 않는다. 「문자열이 남았는가」만 세면 안 된다 — 다른
패처가 그룹 파일을 DUMMY 영역으로 옮기면 **옛 위치에 일본어 원본이 유령으로 남는데 아무도 읽지 않는다**(10-20 실측: 옛 ED2MON1 LBA 에
몬스터 행동 줄이 남아 있었으나 ISO 디렉터리는 새 LBA 를 가리켜 도달 불가). 그래서 **현재 ISO 디렉터리가 가리키는 파일**(`_live_group_lba`)만
읽고, 거기서 **참조되는** 일본어 줄만 센다.

**무엇을 보나.**
  · ED2MON0~5 — 오버레이 안의 `lui`+`addiu/ori`(BASE 0x8014A000) 참조와 오버레이 안 포인터 표(정렬 워드)
  · ED.EXE · ED2.EXE — RAM 0x80010000(=파일 0x800) 기준 같은 두 가지
  · 문자열 = NUL 로 끝나는 SJIS 열(길이 ≥ 4B) 중 **가나(히라가나·가타카나) 2자 이상**. 한글은 한자 영역 위에 구워져 같은 코드 대역이라
    **한글 슬롯 코드(`hangul_map.SYL_INDEX`)는 일본어로 세지 않는다.**
  · 문자열 범위 안(시작이 아니어도)을 가리키는 참조가 하나라도 있으면 「참조됨」 — 템플릿의 중간 조각도 잡는다.
ED1 은 몬스터 오버레이가 없다(`\\BIN` 에 ED2MON 만 있다 — ED1 몬스터·전투 문안은 ED.EXE 안이고 이 게이트의 ED.EXE 몫이다).

⚠ 이미지가 없거나 소스보다 낡으면 통과가 아니라 **「안 쟀다」로 실패**한다(코퍼스 없음과 같다).

  python3 tools/check_jp_left_overlay.py            # 검사
  python3 tools/check_jp_left_overlay.py -v         # 참조 안 된 일본어(죽은 데이터) 목록도
  python3 tools/check_jp_left_overlay.py --allow-stale   # 진단 전용
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hangul_map as H

HERE = os.path.dirname(os.path.abspath(__file__))

# ED2MON 오버레이 적재 주소 — patch_ed2_monster_lines.BASE(로더 0x800959F4 의 상수)와 같은 값
OVERLAY_BASE = 0x8014A000
EXE_RAM_BASE = 0x80010000
EXE_HDR = 0x800
MIN_LEN = 4
MIN_KANA = 2

# 🔴 허용 목록 — **{(대상 이름, 문자열 시작 파일 오프셋)}**. 비어 있어야 한다. 「참조되는데 일본어가 남은」 줄은 결함이다.
#    정말 일본어가 나가도 되는 자리(원문 시스템 문구를 일부러 둔 것 등)가 생기면 마스터 판정 뒤 여기에 사유와 함께 올린다.
ALLOWED = set()

_HAN = None


def _hangul_codes():
    global _HAN
    if _HAN is None:
        _HAN = {H.syllable_sjis(c) for c in H.SYL_INDEX}
    return _HAN


def _is_kana(c):
    return 0x829F <= c <= 0x82F1 or (0x8340 <= c <= 0x8396 and c != 0x837F)


def parse_string(buf, start):
    """NUL 앞까지 SJIS 로 읽는다. 읽을 수 없는 바이트가 있으면 None(= 문자열이 아니라 코드·데이터).

    반환: (길이, 가나 수). 한글 슬롯 코드는 가나가 아니다.
    """
    han = _hangul_codes()
    i, kana = start, 0
    n = len(buf)
    while i < n and buf[i] != 0:
        b = buf[i]
        if b < 0x20 and b not in (0x0A, 0x0D):
            return None
        if 0x20 <= b < 0x7F or b in (0x0A, 0x0D) or 0xA1 <= b <= 0xDF:
            i += 1
            continue
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC:
            if i + 1 >= n:
                return None
            t = buf[i + 1]
            if not (0x40 <= t <= 0xFC and t != 0x7F):
                return None
            c = (b << 8) | t
            if c not in han and _is_kana(c):
                kana += 1
            i += 2
            continue
        return None
    return i - start, kana


def jp_strings(buf):
    """[(시작 오프셋, 길이, 가나 수)] — 직전 바이트가 NUL(또는 파일 시작)인 NUL 종단 문자열 중 일본어 가나가 든 것."""
    out = []
    i, n = 0, len(buf)
    while i < n:
        if buf[i] == 0:
            i += 1
            continue
        e = buf.find(b"\0", i)
        e = n if e < 0 else e
        if i == 0 or buf[i - 1] == 0:
            r = parse_string(buf, i)
            if r and r[0] >= MIN_LEN and r[1] >= MIN_KANA:
                out.append((i, r[0], r[1]))
        i = e + 1
    return out


def code_refs(buf, base_ram, hdr):
    """{대상 파일 오프셋: 참조 수} — `lui`+`addiu/ori` 쌍 + 정렬 워드 포인터. base_ram 이 파일 오프셋 hdr 에 놓인다."""
    refs = {}
    lui = {}
    lim = len(buf) - hdr
    for p in range(0, len(buf) - 4, 4):
        w = struct.unpack_from("<I", buf, p)[0]
        op = w >> 26
        if op == 0x0F:
            lui[(w >> 16) & 31] = (w & 0xFFFF) << 16
        elif op in (0x09, 0x0D):
            rs = (w >> 21) & 31
            if rs in lui:
                imm = w & 0xFFFF
                if op == 0x09 and imm & 0x8000:
                    imm -= 0x10000
                a = lui[rs] + imm
                if base_ram <= a < base_ram + lim:
                    off = a - base_ram + hdr
                    refs[off] = refs.get(off, 0) + 1
        if base_ram <= w < base_ram + lim:
            off = w - base_ram + hdr
            refs[off] = refs.get(off, 0) + 1
    return refs


def analyze(name, buf, base_ram, hdr):
    """[(이름, 오프셋, 길이, 가나 수, 참조 수)] — 일본어가 남은 문자열마다."""
    refs = code_refs(buf, base_ram, hdr)
    rows = []
    for off, n, kana in jp_strings(buf):
        r = sum(c for o, c in refs.items() if off <= o < off + n)
        rows.append((name, off, n, kana, r))
    return rows


def judge(rows):
    """(실패 목록, 죽은 데이터 목록) — 참조됨 + 허용 밖 = 실패."""
    bad = [r for r in rows if r[4] and (r[0], r[1]) not in ALLOWED]
    dead = [r for r in rows if not r[4]]
    return bad, dead


def load_targets(img):
    """{이름: (버퍼, base_ram, hdr)} — 현재 ISO 디렉터리가 가리키는 ED2MON 그룹 + ED.EXE·ED2.EXE."""
    import check_glyph_pairs as G
    import patch_ed2_monster_lines as L
    from common import extract

    out = {}
    for g, (lba, size) in sorted(L._live_group_lba(img).items()):
        out[f"ED2MON{g}"] = (bytes(extract(lba, size, path=img)), OVERLAY_BASE, 0)
    for exe, (lba, size, _b, _g) in G.EXES.items():
        out[exe] = (bytes(extract(lba, size, path=img)), EXE_RAM_BASE, EXE_HDR)
    return out


def main(argv):
    from check_pointer_audit import image_path, stale_reason

    allow_stale = "--allow-stale" in argv
    img = image_path()
    why = stale_reason(img, allow_stale)
    if why:
        print(f"  ❌ 안 쟀다 — {why}")
        return 1
    try:
        targets = load_targets(img)
    except Exception as e:  # noqa: BLE001 — 구조가 바뀌어 못 읽으면 조용히 통과시키지 않는다
        print(f"  ❌ 이미지를 못 읽었다(오버레이 구조 변경?) — {type(e).__name__}: {e}")
        return 1
    rows = []
    for name, (buf, base, hdr) in targets.items():
        rows += analyze(name, buf, base, hdr)
    bad, dead = judge(rows)
    for name, off, n, kana, r in bad:
        print(f"  ❌ {name} 0x{off:X} — 일본어(가나 {kana}자, {n}B)가 남았고 코드·표가 {r}곳에서 참조한다")
    if "-v" in argv:
        for name, off, n, kana, _r in dead:
            print(f"  (참고) {name} 0x{off:X} 일본어 {n}B — 참조 없음(죽은 데이터)")
    if bad:
        print(f"  ❌ 참조되는 일본어 줄 {len(bad)}건 — 몬스터 행동·전투 문구 번역 누락 또는 패처 쓰기 겹침을 본다")
        return 1
    print(f"  ✅ 참조되는 일본어 줄 0건 ({len(targets)}개 대상 · 참조 없는 죽은 일본어 {len(dead)}건 — 도달 불가)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
