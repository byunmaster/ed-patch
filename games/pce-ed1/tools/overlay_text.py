"""씬 54(오델로 노인 집) 코드 오버레이 안 인라인 대사 번역 — 11-21.

배경: 씬 54 이미지(zone_image)의 뒷부분 3943B(`$A924~`)는 원판 6502 코드이고, 그 안에 노인의 **수 읽는 말**(리버시 중 한 수마다 무작위로 뜨는 혼잣말 12종)이
SJIS 인라인 문자열로 박혀 있다(`0A` 종료 · `01` 줄바꿈 · 코드가 `LDA #lo/hi → $10/$11` 로 가리킨다). 컨테이너 블록 밖이라 `scn054.json` 열쇠 체계·`messages.parse`·
일본어 게이트가 모두 못 봤다(마스터 11-20 「노부부의집 게임중에 일본어 대사가 꽤 섞여서 나오네」).

방식: 같은 자리·같은 길이 안에서 제자리 교체 — 새 문안 + `0A` 종료, 남는 자리는 `0A` 로 채운다(데드 바이트). 문자열은 코드가 앞 `RTS` 뒤에 둔 데이터 섬이라 안 닿는다.
정본 = `script/ov054.json`(키 = 오버레이 안 오프셋, `jp_len`·`jp_sha1` = 원판 바이트 검증용 — 원문 일본어는 저장소에 안 둔다).
"""

import json

import common
import font

SCRIPT = common.GAME_DIR / "script" / "ov054.json"
NL = 0x01
END = 0x0A


class OverlayTextError(Exception):
    pass


def load() -> dict[int, dict]:
    raw = json.loads(SCRIPT.read_text("utf-8"))["strings"]
    return {int(k): v for k, v in sorted(raw.items(), key=lambda kv: int(kv[0]))}


def chars() -> set[str]:
    """이 문안이 쓰는 우리 글리프 글자 — `translate.body_chars(54)` 가 합친다(상주/동적 가름에 들어간다)."""
    return {ch for v in load().values() for ch in font.expand_packed(v["t"]) if font.needs_glyph(ch)}


def _sha(b: bytes) -> str:
    import hashlib

    return hashlib.sha1(b).hexdigest()[:16]


def apply(overlay: bytes, table: dict[str, bytes]) -> bytes:
    """원판 오버레이 → 번역 오버레이(같은 길이). 원문이 안 맞거나 길이가 넘치면 죽는다."""
    out = bytearray(overlay)
    for off, v in load().items():
        end = off + v["jp_len"]
        if _sha(bytes(overlay[off:end])) != v["jp_sha1"] or overlay[end] != END:
            raise OverlayTextError(f"오버레이 +{off}: 원문이 기대와 다르다(원판 지문이 바뀌었나)")
        new = font.encode(v["t"], table, msg=True) + bytes([NL])  # 끝 줄바꿈 — 뒤 메시지가 같은 줄에 이어 붙어 어절 계산이 틀어지지 않게
        if len(new) > v["jp_len"]:
            raise OverlayTextError(f"오버레이 +{off}: 번역 {len(new)}B > 원문 {v['jp_len']}B — 자리가 모자란다: {v['t']!r}")
        out[off:end] = new + bytes([END]) * (v["jp_len"] - len(new))
    return bytes(out)


def jp_left(overlay: bytes) -> list[tuple[int, str]]:
    """번역 오버레이에 남은 SJIS 가나·한자 덩이(≥2자) — 일본어 게이트. 코드 바이트 오탐을 피하려고 `ov054.json` 이 아는 자리 밖은 가나 3연속 이상만 센다."""
    import re

    pat = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){3,}")
    return [(m.start(), m.group().decode("cp932", "replace")) for m in pat.finditer(overlay)]
