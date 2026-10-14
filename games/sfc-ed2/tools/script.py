"""sfc-ed2 대사 문법 — 롬 `$C0:A7xx~AExx`(대사 출력 루틴 `$C0:A870` 주변)를 읽어 얻은 토큰 규칙(2026-10-12).

대사는 **포인터 표가 아니라 스트림**이다 — 한 메시지는 `[$A6]` 24비트 포인터로 읽히는 토큰열이고,
조건(`$11~$14` 플래그 검사 → 참이면 다음 3바이트 건너뜀) · 점프(`$0F lo hi`, 같은 뱅크) · 호출(`$10 lo hi`)이
글 사이에 끼어 있다. 그래서 재삽입 때 **같은 뱅크 안 16비트 주소(`$0F`·`$10`·`$E0`~)** 를 모두 고쳐야 한다.

토큰 종류(arg = 뒤따르는 바이트 수):
  $00 끝 · $01 줄바꿈 · $02 키 대기 · $03 공백+대기 · $04 색 복귀 · $05 쪽 넘김 · $06 부분문자열 끝(리턴)
  $07 줄바꿈 후 끝 · $08 쪽 넘김 · $09 arg1 · $0A $0B · $0C arg2 · $0D $0E
  $0F arg2 점프 · $10 arg2 호출 · $11/$12/$13/$14 arg2 플래그(→ 다음 3바이트를 건너뜀 여부)
  $15 arg3 네이티브 호출 · $16/$17 · $18~$1F 색(코드−$18)
  $20~$7F 반각 · $80~$87 전각 2바이트 · $88~$DF 1바이트 글자 · $E0/$E1 arg1 사전(`$CB:346F`/`$CB:354D` 3바이트 표)
  $E2~$EF 2바이트 글자(추정) · $F0~$F9 스크립트(arg 표 `F_ARGS`) · $FA~ 없음

    python3 games/sfc-ed2/tools/script.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

CTRL_ARGS = {
    0x09: 1,
    0x0C: 2,
    0x0F: 2,
    0x10: 2,
    0x11: 2,
    0x12: 2,
    0x13: 2,
    0x14: 2,
    0x15: 3,
}
# $F0~$F9 — 핸들러(`$C0:AA42` 표) 읽기: F2·F6·F8 은 조건이 참이 아니면 3바이트를 더 건너뛴다(그건 다음 토큰이라 따로 센다)
F_ARGS = {0xF0: 1, 0xF1: 1, 0xF2: 2, 0xF3: 2, 0xF4: 4, 0xF5: 2, 0xF6: 3, 0xF7: 0, 0xF8: 4, 0xF9: 2}
ENDS = {0x00, 0x06, 0x07, 0x16, 0x17}  # 이 토큰에서 메시지(또는 부분문자열)가 끝난다


def token_len(d: bytes, i: int) -> int | None:
    """i 위치 토큰의 바이트 길이. 문법에 없으면 None."""
    b = d[i]
    if b < 0x20:
        return 1 + CTRL_ARGS.get(b, 0)
    if b < 0x80:
        return 1
    if b < 0x88:
        return 2
    if b < 0xE0:
        return 1
    if b < 0xE2:
        return 2
    if b < 0xF0:
        return 2
    if b in F_ARGS:
        return 1 + F_ARGS[b]
    return None


def tokens(d: bytes, start: int, limit: int | None = None) -> list[tuple[int, int]]:
    """start 부터 끝 토큰($00 등)까지 (오프셋, 길이) 목록. 문법 밖 바이트를 만나면 마지막 항목을 (오프셋, 0)으로."""
    out, i = [], start
    n = len(d) if limit is None else min(limit, len(d))
    while i < n:
        ln = token_len(d, i)
        if ln is None:
            out.append((i, 0))
            break
        out.append((i, ln))
        i += ln
        if d[i - ln] in ENDS:
            break
    return out


def msg_start(d: bytes, a: int, floor: int) -> int:
    """글자 덩이 a 앞의 머리 토큰(색·화자·플래그 검사 등)까지 포함한 메시지 시작.

    앞 바이트가 끝 토큰($00 $06 $07)이고, 거기서부터 읽어 끝 토큰 없이 정확히 a 에 닿는 가장 먼 자리."""
    best = a
    for back in range(1, 90):
        s = a - back
        if s < floor:
            break
        if d[s - 1] not in (0x00, 0x06, 0x07):
            continue
        i, ok = s, True
        while i < a:
            ln = token_len(d, i)
            if ln is None or d[i] in ENDS:
                ok = False
                break
            i += ln
        if ok and i == a:
            best = s
    return best


def a6_targets(d: bytes) -> set[int]:
    """`$C0~$C1` 코드가 대사 출력기 포인터(`$A6~$A8`)에 즉치로 넣는 $C0/$C1 뱅크 주소 — UI 쪽 대사형 문자열(전투 문장 조각·시스템 메시지)의 시작."""
    import re

    out = set()
    pat = re.compile(rb"\xa9(.)\x8d\xa6\x00\xa9(.)\x8d\xa7\x00\xa9([\xc0-\xdf])", re.S)
    for m in pat.finditer(d[: common.ROM_SIZE]):
        out.add(m.group(3)[0] << 16 | m.group(2)[0] << 8 | m.group(1)[0])
    return out


def has_glyph(d: bytes, a: int, limit: int = 400) -> bool:
    ts = tokens(d, a, a + limit)
    return any(0x80 <= d[o] < 0x88 or 0x88 <= d[o] < 0xE0 for o, _ in ts)


# `$C0`·`$C1` 안의 대사형 문자열 구간(전투 문장 조각 풀·시스템 메시지) — 대사 출력기(`$C0:A691`)가 읽는다. 끝은 마지막 글자 토큰 뒤(그 너머는 코드).
EXTRA_REGIONS = (
    (0xC17CCF, 0xC18117),  # 전투 문장 조각 풀(이름 뒤에 이어 붙는 조각 · 상태이상 · 레벨업 · 승패)
    (0xC0EB8D, 0xC0EBE8),  # 주문 익히기 질문·결과
    (0xC0F241, 0xC0F2B0),  # 포인트 능력 올리기
    (0xC1E98F, 0xC1E9FC),  # 아이템 획득·버리기
    (0xC1E518, 0xC1E531),  # 워프 안내
    (0xC0C00E, 0xC0C013),  # 「たち」
    (0xCB3869, 0xCB3C1D),  # 상점·시스템 문구 풀($E1 사전 항목이 가리키는 곳 포함)
    (0xCB74B3, 0xCB7792),  # 무기고·주문서 상점 대사
)


def region_units(d: bytes) -> list[tuple[int, int]]:
    out = []
    for a, b in EXTRA_REGIONS:
        i, end = common.snes2off(a), common.snes2off(b)
        while i < end:
            ts = tokens(d, i, end)
            e = ts[-1][0] + ts[-1][1]
            if not ts[-1][1]:
                raise SystemExit(f"구간 {common.fmt(a)} 의 {common.fmt(common.off2snes(ts[-1][0]))} 가 문법 밖이다")
            out.append((i, e))
            i = e
    return out


def units(d: bytes) -> tuple[list[tuple[int, int]], int]:
    """$C2~$CA 뱅크의 메시지 단위 (시작, 끝) 오프셋 목록과 문법 밖에서 끊긴 덩이 수.
    $C0·$C1 의 글자 덩이는 UI 문자열(`$C0:9395` 출력기)이라 제외한다 — 문법이 다르다."""
    import scan_text

    out, bad, pos = [], 0, 0
    for a, b, _c in scan_text.find_runs(d):
        if a < 0x20000 or b <= pos:
            continue
        # 앞 단위가 이 덩이의 앞머리를 먹었으면(덩이가 사전 참조·제어에서 갈렸을 때) 남은 꼬리를 pos 부터 이어 읽는다 — 예전엔 통째로 건너뛰어 대사 수백 줄이 번역 대상에서 빠졌다
        i = pos if a < pos else msg_start(d, a, pos)
        while i < b:
            t = tokens(d, i)
            if not t[-1][1]:
                bad += 1
                pos = t[-1][0]
                break
            e = t[-1][0] + t[-1][1]
            out.append((i, e))
            i = pos = e
    return out, bad


def all_units(d: bytes) -> list[tuple[int, int]]:
    """번역 대상 메시지 단위 전부 — $C2~$CA 스캔 단위 + $C0/$C1 대사형 구간."""
    u, _bad = units(d)
    out: list[tuple[int, int]] = []
    for s, e in sorted(u + region_units(d)):
        if out and s < out[-1][1]:  # 앞 단위 안에 든 중복(스캔 단위와 구간 목록이 겹친다)
            continue
        out.append((s, e))
    return out


DICTS = ((0xCB346F, 74), (0xCB354D, 30))  # `$E0` · `$E1` 사전 표(3바이트 포인터, 항목 수는 표 간격에서)
DICTS_BY_NAME = {"E0": 0xCB346F, "E1": 0xCB354D}


def glyph_char(code: int) -> str:
    """2바이트 코드 → 글자(글리프표). 표 밖은 `？`."""
    import glyphmap

    i = code - 0x8000
    return glyphmap.TABLE[i] if 0 <= i < len(glyphmap.TABLE) else "？"


def decode(d: bytes, s: int) -> list[str]:
    """메시지 한 단위를 줄 목록으로(글자만). 줄바꿈($01)·쪽 넘김($02 $05 $08)·끝으로 가른다.
    $E0/$E1 사전 참조는 `〈E0:nn〉` 로 남긴다 — 문안이 아니라 표식이다. 1바이트 글자($88~$DF)는 히라가나다."""
    lines, cur = [], []
    for o, _ln in tokens(d, s):
        b = d[o]
        if 0x80 <= b < 0x88 or 0xE2 <= b < 0xF0:
            cur.append(glyph_char((b << 8) | d[o + 1]))
        elif 0x20 <= b < 0x80:
            cur.append(chr(b))
        elif b in (0xE0, 0xE1):
            cur.append(f"〈E{b - 0xE0}:{d[o + 1]}〉")
        elif 0x88 <= b < 0xE0:
            import glyphmap

            cur.append(glyphmap.HALF_TABLE[b - 0x88])
        elif b in (0x01, 0x02, 0x05, 0x08, 0x00, 0x06, 0x07):
            if cur:
                lines.append("".join(cur))
            cur = []
    if cur:
        lines.append("".join(cur))
    return lines


def dict_entries(d: bytes) -> list[tuple[str, int, str]]:
    """사전 표 항목 → (표 이름, 번호, 글자). 번호는 1부터(`$E0 nn` 의 nn)."""
    out = []
    for k, (base, n) in enumerate(DICTS):
        o = common.snes2off(base)
        for i in range(n):
            p = int.from_bytes(d[o + 3 * i : o + 3 * i + 3], "little")
            t = "".join(decode(d, common.snes2off(p)))
            out.append((f"E{k}", i + 1, t))
    return out


def render(d: bytes, s: int) -> str:
    """메시지 한 단위를 사람이 읽는 줄로 — 전각은 `{색인}`, 반각은 그대로, 제어는 `<hex hex>`.
    (글리프→글자 표가 아직 없다: 글꼴 순서는 JIS 가 아니라 음독 순이라 색인으로 적는다.)"""
    out = []
    for o, ln in tokens(d, s):
        b = d[o]
        if 0x80 <= b < 0x88:
            out.append("{%d}" % (((b << 8) | d[o + 1]) - 0x8000))
        elif 0x20 <= b < 0x80:
            out.append(chr(b))
        else:
            out.append("<" + d[o : o + max(ln, 1)].hex(" ") + ">")
    return "".join(out)


def dump(path: Path) -> int:
    d = common.rom_bytes()
    u, _bad = units(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for s, e in u:
            f.write(f"${common.off2snes(s):06X}\t{render(d, s)}\n")
    return len(u)


if __name__ == "__main__":
    common.verify_originals()
    d = common.rom_bytes()
    if "--dump" in sys.argv:
        out = common.OUT_DIR / "script" / "units.tsv"
        print(f"{dump(out):,}개 → {out}")
        raise SystemExit
    u, bad = units(d)
    nch = sum(1 for s, e in u for o, ln in tokens(d, s) if 0x80 <= d[o] < 0x88)
    print(f"메시지 단위 {len(u):,}개 · 전각 글자 {nch:,} · 문법 밖에서 끊긴 덩이 {bad}")
