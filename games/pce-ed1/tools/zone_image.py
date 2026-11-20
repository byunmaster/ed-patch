"""씬 54(2장 노부부의 집) 「블록이 자기 위에 원판 이미지를 다시 덮어쓴다」 고침 — 11-19.

원인(BP 실측, status 「씬 54 일본어의 원인」): 씬 54 블록의 초기화 코드(`$A251`~`$A2C3`)가 지도 구역 묶음(rel 1135, AD_TRANS 9섹터 → ADPCM `$A000`~)
안의 LZ 스트림(1141:1772, 원판 압축 4359B)을 `$188B`=6283B 풀어 `$A000`(= 블록 자신)에 덮어쓴다. 그 이미지 = 원판 블록 54(2340B) + 6502 코드 오버레이 3943B(`$A924`~).
번역 블록이 컨테이너에서 바르게 올라와도 곧바로 원판(일본어)으로 되돌려졌다.

고침: 번역 이미지 = [번역 블록 앞 2340B][오버레이 3943B — 같은 자리·같은 바이트][꼬리(번역 꼬리 이음·스텁)] 를 다시 LZ 로 묶어 같은 자리(1141:1772)에 쓴다.
 · 오버레이는 절대주소(`$A924`~)를 쓰므로 **제자리에 둔다** — 번역이 넘쳐 잇는 꼬리·동적 글리프 스텁은 오버레이 **뒤**로(`messages.PAD`: splice 가 처음부터 그만큼 띄우고 시작한다).
 · 압축이 묶음 여유(13B)를 넘으므로 묶음 섹터 수를 9 → 10 으로(rel 43:1512 의 구역 길이 표 — ADPCM `$E800`~`$EFFF` 는 비어 있다 · 1144 는 구역 칸(13섹터) 안의 안 쓰는 꼬리).
 · 초기화 루프의 복사 길이(`LDA #$8B`/`#$18` = 0x188B)를 새 이미지 길이로 — **컨테이너 블록과 이미지 둘 다**(둘의 앞 0x2C4B 는 같아야 한다: 루프가 도는 자기 코드를 덮어쓰므로).
"""

import lz
import messages as M

import common
import containers

SCENE = 54
CONTAINER_REL = 1332
ZONE_REL = 1135
STREAM_OFF = 0x36EC  # 묶음 안 스트림 시작(= 1141:1772)
ORIG_LEN = 6283  # 원판 이미지 길이(블록 2340 + 오버레이 3943)
BLOCK_LEN = 2340  # 원판 블록 길이
COUNT_OFFS = (0x295, 0x299)  # 블록 안 `LDA #lo`/`LDA #hi` 의 즉시값(복사 길이 → $FC/$FD)
COUNT_OLD = (b"\x8b", b"\x18")
ZONE_SECTORS_OLD = 9
ZONE_SECTORS_NEW = 10
COUNT_TABLE = (43, 1512)  # 구역 길이 표(rel 43 오프셋 1484 의 13개 섹터 수) 셋째 칸 — 구역 rel 1135
SPARE_SECTORS = range(1144, 1148)  # 구역 칸(13섹터) 안 안 쓰는 꼬리


class ZoneError(Exception):
    pass


def original_image() -> bytes:
    """원판 묶음에서 씬 54 스트림을 풀어 낸 6283B — 원판 블록과 앞 2340B 가 같아야 한다."""
    zone = b"".join(common.user_sector(r) for r in range(ZONE_REL, ZONE_REL + ZONE_SECTORS_OLD))
    img, used = lz.decode(zone[STREAM_OFF:], ORIG_LEN)
    blk = next(b["data"] for c in containers.scan(common.track_data()) for b in c["blocks"] if b["id"] == SCENE)
    if img[:BLOCK_LEN] != blk:
        raise ZoneError("묶음 스트림 앞부분이 원판 씬 54 블록과 다르다 — 원판 지문이 바뀌었나")
    if STREAM_OFF + used > ZONE_SECTORS_OLD * common.USER:
        raise ZoneError("원판 스트림이 묶음 밖으로 나간다")
    return img


def overlay() -> bytes:
    return original_image()[BLOCK_LEN:]


class pad:
    """`with zone_image.pad(table):` 안에서 `messages.splice` 가 오버레이만큼 띄우고 꼬리를 놓는다. `table`(블록 전용 글자표)을 주면 오버레이 안 인라인 대사를 번역해 넣는다(`overlay_text`)."""

    def __init__(self, table=None):
        self.table = table

    def __enter__(self):
        import overlay_text

        ov = overlay()
        M.PAD = overlay_text.apply(ov, self.table) if self.table is not None else ov
        return self

    def __exit__(self, *a):
        M.PAD = b""


def patch_count(blk: bytes, n: int) -> bytes:
    """블록 안 복사 길이 즉시값을 `n` 으로(같은 길이 제자리 교체). 기대 바이트가 다르면 죽는다."""
    out = bytearray(blk)
    new = (n & 0xFF, n >> 8)
    for off, old, v in zip(COUNT_OFFS, COUNT_OLD, new, strict=True):
        if out[off - 1] != 0xA9 or bytes(out[off : off + 1]) != old:
            raise ZoneError(f"씬 54 복사 길이 자리 +{off:#x} 가 기대(`A9 {old.hex()}`)와 다르다: {bytes(out[off-1:off+1]).hex()}")
        out[off] = v
    return bytes(out)


def compose(image: bytes) -> tuple[bytes, list[tuple[int, int, bytes, bytes]]]:
    """번역 이미지 → (압축 스트림, 쓰기 목록 [(rel, 섹터 안 오프셋, 기대 원판, 새 바이트)]). 묶음 확장분(1144)은 원판 꼬리 위에 덮는다."""
    packed = lz.encode_optimal(image)
    dec, used = lz.decode(packed, len(image))
    if dec != image or used != len(packed):
        raise ZoneError("재압축 왕복 불일치")
    first_rel, first_off = ZONE_REL + STREAM_OFF // common.USER, STREAM_OFF % common.USER
    end = STREAM_OFF + len(packed)
    n_sec = -(-end // common.USER)
    if n_sec > ZONE_SECTORS_NEW:
        raise ZoneError(f"재압축 {len(packed)}B — 묶음 {ZONE_SECTORS_NEW}섹터({ZONE_SECTORS_NEW * common.USER}B)에 안 든다(끝 {end:#x})")
    writes = []
    pos = STREAM_OFF
    while pos < end:
        rel = ZONE_REL + pos // common.USER
        off = pos % common.USER
        take = min(common.USER - off, end - pos)
        old = common.user_sector(rel)[off : off + take]
        writes.append((rel, off, old, packed[pos - STREAM_OFF : pos - STREAM_OFF + take]))
        pos += take
    return packed, writes
