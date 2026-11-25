"""원판 텍스트 사본 점검 — 우리가 번역해 바꾼 원판 문안 덩어리가 제품 롬 어딘가에 원판 바이트 그대로 남았나(마스터 11-17, PCE I 「맵별 레코드 안의 대사 사본」 사고).

PCE I: 원판 디스크에 대사 블록 사본이 우리가 고친 자리 밖에 따로 있었고, 정상 진행이 그 사본을 읽어 장면 전체가 일본어로 나왔다 — 빌드·게이트는 고친 자리만 분모로 봐서 못 잡았다.
여기서는 번역해 바꾼 구간(segments.json 에서 keep 아닌 것) · 고정 길이 문안(spans·cells)의 **원판 바이트 전체**를 제품 롬 전체에서 찾는다.
찾아지면 ① 제자리가 안 바뀐 것(그 구간이 실제 번역 안 됐거나 채움 누락) 또는 ② 사본이 따로 있는 것 — 어느 쪽이든 실패다(예외는 `ORIG_COPY_OK` 에 사유와 함께).
롬 전체 탐색은 구간 수(수천) × 2MB 이므로 12바이트 접두 해시 색인으로 한 번에 센다.

사용: python3 check_orig_copies.py [--rom 제품롬]   (종료 0 = 사본 0)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import kr
import segs

# 사유와 함께 둔다 — 짧아서 우연히 같은 꼴 · 원판과 같게 남기기로 한 자리. 키는 구간 id.
ORIG_COPY_OK: dict[str, str] = {
    "cells$C0C469": "「ON OFF」 칸 — 번역해도 원판과 같은 글자라 바이트가 같다(살아 있는 문안)",
}
BASELINE = Path(__file__).resolve().parents[1] / "orig_copies_baseline.json"  # 알려진 옛 사본(래칫) — 늘면 실패, 줄면 --freeze

WHY = (
    "기준선 = 번역한 문안의 원판 바이트가 제품 롬에 남은 옛 사본(포인터를 새 자리로 돌린 뒤 지우지 않은 것 · 짧은 이름 조각이 다른 표에 같은 꼴로 있는 것). "
    "11-17 읽힘 추적(Mesen 읽기 콜백 — 엔딩 전 흐름 + 새 게임 오프닝, $D7 이후 읽은 45,389 + 6,896바이트): 사본과 겹친 읽기 0. $C1~$CB 쪽 사본과 일반 필드·전투 경로는 추적 못 했다."
)
ERASE_WHY = (
    "번역한 문안의 옛 사본(원판 바이트 그대로 남은 곳)을 빌드가 0xFF 로 지운다(마스터 11-17 — PCE I 사본 사고, MD I 와 같은 처방). "
    "근거: 지명 표 64·몬스터 이름 표 119 전부 새 자리로 포인터 이동, 아이템 이름 표는 읽는 코드 6곳을 새 표로 돌림, $D7 오프닝·엔딩 문안은 새 자리로 포인터 이동. "
    "읽기 감시(Mesen 읽기 콜백, 양성 대조 통과): 엔딩 전 흐름·새 게임 오프닝·전투 99군에서 사본 읽기 0. 못 본 것: 필드 일반 진행·메뉴·가게의 읽힘."
)
MIN_LEN = 8  # 이보다 짧으면 우연 일치(코드 조각)가 많아 센다 해도 의미가 없다
MIN_KANA = 3  # 가나·한자 글리프 바이트(0x80~0x87·0xE2~0xEF 첫 바이트)가 이만큼은 있어야 문안으로 본다


def kana_count(b: bytes) -> int:
    i = n = 0
    while i < len(b):
        t = b[i]
        if 0x80 <= t < 0x88 or 0xE2 <= t < 0xF0:
            n += 1
            i += 2
        else:
            i += 1
    return n


def default_rom() -> Path:
    return common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"


def blobs(orig: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    tm = kr.load("segments")
    keep = set(kr.load("keep").get("ids", []))
    for a, b in segs.segments(orig):
        sid = segs.seg_id(a)
        if sid in keep or sid not in tm:
            continue
        out.append((sid, bytes(orig[a:b])))
    for name in ("spans", "cells"):
        for key in kr.load(name):
            try:
                a = common.snes2off(int(key.lstrip("$"), 16))
            except Exception:
                continue
            n = kr.load(name)[key].get("n")
            if n:
                out.append((f"{name}{key}", bytes(orig[a : a + n])))
    return out


def scan(orig: bytes, prod: bytes) -> list[tuple[str, int, list[int]]]:
    """[(구간 id, 길이, 제품 롬 안 발견 위치들)] — 12바이트 접두가 제품에 한 번도 없으면 건너뛴다."""
    hits = []
    for sid, blob in blobs(orig):
        if len(blob) < MIN_LEN or kana_count(blob) < MIN_KANA or sid in ORIG_COPY_OK:
            continue
        pos, start = [], 0
        while True:
            j = prod.find(blob, start)
            if j < 0:
                break
            if orig[j : j + len(blob)] == blob:  # 그 자리가 원판 바이트 그대로일 때만 — 빌드가 새로 쓴 자리(번역문이 원문과 같은 줄 · 옮긴 표)는 사본이 아니다
                pos.append(j)
            start = j + 1
        if pos:
            hits.append((sid, len(blob), pos))
    return hits


ERASE = Path(__file__).resolve().parents[1] / "textmap" / "orig_erase.json"  # 빌드가 지우는 옛 사본 범위(0xFF) — 아래 --write-erase 로 만든다


def merged_spans(hits) -> list[tuple[int, int]]:
    """사본 위치(파일 오프셋)를 겹침·맞닿음 없이 합친 [시작, 끝) 목록."""
    sp = sorted((p, p + ln) for _sid, ln, pos in hits for p in pos)
    out: list[list[int]] = []
    for a, b in sp:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=str(default_rom()))
    ap.add_argument("--write-erase", action="store_true", help="지금 롬의 사본 위치로 textmap/orig_erase.json(빌드가 0xFF 로 지우는 범위)을 쓴다 — 지우기 전 롬에서만")
    ap.add_argument("--freeze", action="store_true", help="지금 사본 집합을 기준선으로 굳힌다(줄었을 때만 — 늘면 먼저 원인을 본다)")
    a = ap.parse_args()
    orig = common.rom_bytes()
    prod = Path(a.rom).read_bytes()
    n_blob = sum(1 for _s, b in blobs(orig) if len(b) >= MIN_LEN and kana_count(b) >= MIN_KANA)
    hits = scan(orig, prod)
    if a.write_erase:
        sp = merged_spans(hits)
        ERASE.write_text(json.dumps({"why": ERASE_WHY, "spans": [{"a": f"${common.off2snes(x):06X}", "n": y - x} for x, y in sp]}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"지울 범위 {len(sp)}개 저장")
        return 0
    now = sorted({f"{sid}@${common.off2snes(p):06X}" for sid, _ln, pos in hits for p in pos})
    if a.freeze:
        BASELINE.write_text(json.dumps({"why": WHY, "copies": now}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"기준선 {len(now)}개 저장")
        return 0
    base = set(json.loads(BASELINE.read_text(encoding="utf-8"))["copies"]) if BASELINE.exists() else set()
    new = [x for x in now if x not in base]
    print(f"원판 텍스트 사본 — 번역한 구간·칸 {n_blob}개의 원판 바이트를 제품 롬 전체에서 탐색: 사본 {len(now)}개(기준선 {len(base)} · 새로 생김 {len(new)})")
    for x in new[:60]:
        print(f"  ✗ {x} — 번역한 문안의 원판 바이트가 제품 롬에 남았다(제자리 미번역 · 따로 있는 사본). 읽히는 경로면 장면이 일본어로 나온다")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
