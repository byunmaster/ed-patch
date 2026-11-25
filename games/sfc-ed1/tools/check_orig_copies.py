"""원판 대사 덩어리의 **사본** 점검 — 우리가 번역해 바꾼 자리(포인터가 부르는 대본·사전) 밖에 같은 바이트가 따로 있는가.

배경(마스터 11-17, PCE I 사고): 원판 이미지에 대사 블록 사본이 우리가 고친 자리 밖(맵별 레코드 안)에 따로 있었고 정상 진행이 그 사본을 읽어
장면 전체가 일본어로 나왔다. 빌드·게이트는 「고친 자리」만 분모로 봐서 못 잡았다. 여기서는 분모를 **원판 이미지 전체**로 넓힌다:

1. 영역 = 대본 조각(`work/derived/text/messages.json`, 4표 + 미니게임 런 + 추가 영역)과 사전 여섯 벌의 원판 바이트가 차지한 자리.
2. 영역 밖(원판 전체)에서 같은 바이트열(조각 8B↑·글자 6↑ / 사전 항목 5B↑)을 바이트 검색한다 — 사본 후보.
3. **제품 이미지**의 같은 오프셋이 여전히 원판 바이트 그대로면 「번역 안 된 사본」이다(이 게임은 롬 내용을 원판 위치에 남겨 두고 포인터만 돌리므로, 영역 안의 옛 자리는 포인터가 안 불러 무해 — 영역 밖 사본만 센다).
   확장 뱅크(원판 크기 밖)에서 원판 바이트가 그대로 나오는 것도 센다(번역 누락).

허용 목록은 **사본이 아님을 확인한 우연 일치**만(사유 필수). 값이 늘면 실패한다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text  # noqa: I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common

MSG_MIN_LEN = 8
MSG_MIN_KANA = 4  # 해독한 문자열에서 태그 밖 가나·한자 수 — 제어 인자 바이트(플래그·점프 주소)를 글자로 세지 않는다
DICT_MIN_LEN = 5

# 확인된 우연 일치 — 원판 오프셋 → 사유. 사본이 아님을 읽어 확인한 것만 둔다.
ALLOW = {
    0x26575: "팔레트 데이터(`3F 53 FF 7F DF 3E FA 29`)가 대사 조각 8바이트와 우연히 같다 — 글자가 아니다",
}
# 글자로 풀렸을 뿐인 이진 데이터 조각(조각 주소 → 사유) — 번역하면 구조가 깨져 원문 바이트가 맞다(`textmap/data_fragments.json` 예외와 같은 것).
ALLOW_BINARY = {
    "1ECA17": "상점 재고 표 — `CALL_NATIVE 88FE0B` 뒤 개수+아이템 ID(문장 아님)",
    "08A7C0": "상점 재고 표 — 같은 꼴",
    "0986E6": "상점 재고 표 — 같은 꼴",
    "0BE8AC": "alt3 포인터 표($0B:E8AB×19)가 글자로 풀린 것 — 표는 빌드가 제자리에서 다시 쓰고 이 조각은 이동된 사본이라 읽는 곳이 없다(data_fragments 845a77b0e9c3)",
}
# 지명 표(HUD 지명·세이브 슬롯 지명·디버그 메뉴 항목 이름 — 맵 ID → 10칸 가나 문자열). 번역은 읽는 쪽 코드를 훅으로 돌려 `places.json` 문자열을 쓰고
# 원판 표·문자열은 제자리에 남는다(11-17 확인: 원판 읽는 코드 3곳 `LDA $02:A8B1,X`·`$02:A793,X` 가 제품에선 없다). 그래서 영역이다 — 단 **읽는 곳이 다시 생기면 실패**(아래 `readers`).
PLACE_TABLES = {0x02A793: 143, 0x02A8B1: 149}


def _kana(raw: bytes) -> int:
    s = re.sub(r"<[^>]*>|\{[^}]*\}", "", text.decode(raw))
    return sum(1 for ch in s if "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff")


def _terr_and_payloads(orig: bytes):
    terr = bytearray(len(orig))
    pay: dict[bytes, str] = {}
    msgs = json.loads((common.OUT_DIR / "text" / "messages.json").read_text(encoding="utf-8"))
    for m in msgs:
        raw = bytes.fromhex(m["raw"])
        o = common.snes2off(int(m["addr"], 16))
        terr[o : o + len(raw)] = b"\x01" * len(raw)
        if m["addr"] not in ALLOW_BINARY and len(raw) >= MSG_MIN_LEN and _kana(raw) >= MSG_MIN_KANA:
            pay.setdefault(raw, f"조각 {m['addr']}")
    for taddr, n in PLACE_TABLES.items():
        base = common.snes2off(taddr)
        for i in range(n):
            o = common.snes2off(0x020000 | (orig[base + 2 * i] | (orig[base + 2 * i + 1] << 8)))
            e = orig.index(b"\xff", o)
            terr[o : e + 1] = b"\x01" * (e + 1 - o)
            if e - o >= DICT_MIN_LEN:
                pay.setdefault(orig[o:e], f"지명 표 ${taddr:06X}[{i}]")
    for code, (addr, n, name) in text.DICT_TABLES.items():
        base = common.snes2off(addr)
        bank = addr & 0xFF0000
        for i in range(n):
            p = orig[base + 2 * i] | (orig[base + 2 * i + 1] << 8)
            o = common.snes2off(bank | p)
            e = orig.index(b"\xff", o)
            terr[o : e + 1] = b"\x01" * (e + 1 - o)
            raw = orig[o:e]
            if len(raw) >= DICT_MIN_LEN:
                pay.setdefault(raw, f"사전 {code:02X}[{i}] {name}")
    return terr, pay


def scan(orig: bytes, prod: bytes | None = None) -> dict:
    """사본 후보 목록 — `outside`(영역 밖 원판 오프셋 · 제품에서도 원판 그대로인지) · `ext`(확장 뱅크의 원판 바이트)."""
    terr, pay = _terr_and_payloads(orig)
    outside, ext = [], []
    for raw, who in pay.items():
        for x in re.finditer(re.escape(raw), orig):
            if not terr[x.start()]:
                kept = prod is not None and prod[x.start() : x.start() + len(raw)] == raw
                outside.append((x.start(), who, len(raw), kept))
        if prod is not None and len(prod) > len(orig):
            for x in re.finditer(re.escape(raw), prod[len(orig) :]):
                ext.append((len(orig) + x.start(), who, len(raw)))
    return {"payloads": len(pay), "outside": sorted(outside), "ext": sorted(ext)}


def readers(prod: bytes) -> list[tuple[int, int]]:
    """제품 코드가 아직 원판 지명 표를 읽는 곳 — 긴 주소 `LDA/ADC/… long $02:A793·A8B1(+색인)`(opcode BF·AF·7F·6F·FF·EF·DF·CF + 24비트 주소 + 표 바이트 범위)."""
    out = []
    for taddr, n in PLACE_TABLES.items():
        lo, hi = taddr & 0xFFFF, (taddr & 0xFFFF) + 2 * n
        for m in re.finditer(
            rb"[\xbf\xaf\x7f\x6f\xff\xef\xdf\xcf]([\x00-\xff]{2})\x02", prod[:0x100000]
        ):
            a = m.group(1)[0] | (m.group(1)[1] << 8)
            if lo <= a < hi:
                out.append((m.start(), taddr))
    return out


def main() -> int:
    orig = common.rom_bytes()
    prod_path = common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu (KR).sfc"
    prod = prod_path.read_bytes() if prod_path.exists() else None
    r = scan(orig, prod)

    def ok(off: int) -> bool:
        return off in ALLOW

    bad = [o for o in r["outside"] if not ok(o[0])]
    allowed = [o for o in r["outside"] if ok(o[0])]
    print(
        f"  원판 사본 점검 [sfc-ed1] — 대조 덩어리 {r['payloads']} · 영역 밖 사본 {len(bad)} (허용 {len(allowed)}) · 원판 지명 표를 읽는 제품 코드 {len(readers(prod)) if prod is not None else '—'} · 확장 뱅크의 원문 바이트 {len(r['ext'])}"
    )
    rd = readers(prod) if prod is not None else []
    for off, taddr in rd:
        print(
            f"    ✗ 제품 코드 ${off:06X} 가 원판 지명 표 ${taddr:06X} 를 아직 읽는다 — 번역 안 된 지명이 나온다"
        )
    for off, who, n, kept in bad:
        print(
            f"    ✗ 영역 밖 ${off:06X} ({n}B) = {who} — 제품에서 {'원판 그대로(번역 안 됨)' if kept else '바뀜'}"
        )
    for off, who, n in r["ext"]:
        print(f"    ✗ 확장 뱅크 ${off:06X} ({n}B) = {who} — 원문 그대로")
    return 1 if (bad or r["ext"] or rd) else 0


if __name__ == "__main__":
    sys.exit(main())
