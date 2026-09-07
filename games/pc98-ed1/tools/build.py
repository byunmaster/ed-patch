"""빌드 — 원본에서 패치 이미지를 만든다. **이 레포의 첫 쓰기 경로다.**

🔴 **쓰기에는 사전조건이 붙는다**(`docs/patcher-checklist.md` 2). 여기서 지키는 것:

  ⑴ **원본은 읽기만 한다** — 지문을 먼저 확인하고, 산출물은 `work/build/<꼬리표>/` 로 나간다.
  ⑵ **claim 한 섹터 말고는 한 바이트도 안 바뀐다** — 다 쓰고 나서 **전 섹터를 대조**한다.
  ⑶ **섹터 ID·물리 순서를 보존한다** — d88 원본을 통째로 복사하고 **그 자리에만 덮는다**.
     🔴 이 디스크는 섹터 ID 가 장마다 다르고(0x10/0x20/0x30) 시나리오는 3:1 인터리브다.
     정규화해서 다시 쓰면 **로더가 디스크를 못 알아본다**(status.md 1절).
  ⑷ **claim 하는 자리가 정말 비어 있는지** 매번 확인한다 — 「비었겠지」는 이 레포의 단골
     사고다(`our-findings.md` 「빈 공간의 VAB 함정」).
  ⑸ **실패하면 산출물을 무효화한다**(`*.failed`) — 남은 낡은 이미지를 정상으로 오해하는
     사고를 막는다(루트 CLAUDE.md 「빌드 규율」).

지금 넣는 것은 **한글 글리프 표뿐**이다. 게임은 아직 그걸 안 읽으므로 **화면이 원본과
같아야 한다** — 그게 이 단계의 합격 조건이다(쓰기 경로가 아무것도 안 깨뜨렸다는 증거).
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import font
import patch_font_hook
import patch_scn

# 글리프 표를 놓을 자리 — `free_map.py` 가 「전부 0xFF 인 섹터」로 확인한 연속 구간.
# ⚠ 시작 섹터만 적고 길이는 표 크기에서 나온다. 자리를 옮기면 여기만 고친다.
# 🔴 표는 **시나리오 디스크**에 싣는다 — 두 부팅 경로(event 로 새로 시작 · program 으로
#   이어하기) **모두** 드라이브 2 에 시나리오를 꽂기 때문이다. event 에 두면 이어하기 때
#   못 읽는다. ⚠ **트랙 경계**(1008 = 트랙 126 첫 섹터)여야 한다 — 로더가 트랙 통째로 읽는다.
FONT_AT = {s["font_disk"]: s["font_sector"] for s in patch_font_hook.SITES.values()}
BLANK = b"\xff"


def claim(secs: list[dict], start: int, size: int) -> range:
    """`start` 부터 `size` 바이트를 담을 섹터 구간. **비어 있지 않으면 죽는다.**"""
    n = -(-size // common.SECTOR_SIZE)
    rng = range(start, start + n)
    for i in rng:
        if i >= len(secs):
            raise SystemExit(f"🔴 섹터 {i} 는 디스크 밖이다")
        if secs[i]["data"] != BLANK * common.SECTOR_SIZE:
            raise SystemExit(
                f"🔴 섹터 {i} 가 비어 있지 않다 — 남의 자료를 덮을 뻔했다.\n"
                f"   free_map.py 로 다시 보고 FONT_AT 를 고친다."
            )
    return rng


_SCN_MARKS = None


def patches_for(key: str) -> list[tuple[int, bytes, bytes]]:
    """(플랫 오프셋, 원본이어야 할 바이트, 새 바이트). ⚠ **expect 가 틀리면 죽는다.**

    🔴 **문안은 시나리오 디스크에만** 붙는다 — 대본이 거기 산다(`scn.py`).
    """
    out = patch_font_hook.build_patch(key) if key in patch_font_hook.SITES else []
    if key == "scenario":
        global _SCN_MARKS
        if _SCN_MARKS is None:
            _SCN_MARKS, st = patch_scn.plan()
            put = st["제자리"] + st["틈 건너뜀"] + st["공백 메움"] + st["밖으로"]
            put += st["밖으로:점프가 온다"]
            skip = sum(v for k, v in st.items() if k.startswith("건너뜀"))
            print(
                f"  문안 {put:,}블록 (밖으로 {st['밖으로'] + st['밖으로:점프가 온다']:,}"
                f" · 그중 점프가 오는 자리 {st['밖으로:점프가 온다']:,} · 건너뜀 {skip:,})"
            )
        out = out + _SCN_MARKS
    return out


def write_flat(raw: bytearray, secs: list[dict], off: int, data: bytes) -> None:
    """평면 오프셋에 쓴다 — 섹터 경계를 넘지 않는다고 보고 자른다."""
    for n, b in enumerate(data):
        i, k = (off + n) // common.SECTOR_SIZE, (off + n) % common.SECTOR_SIZE
        raw[secs[i]["file_off"] + k] = b


def build_disk(key: str, table: bytes, out_dir: Path) -> tuple[Path, range | None, list]:
    src = common.disk_path(key)
    dst = out_dir / f"{key}.d88"
    shutil.copyfile(src, dst)  # ⑶ 컨테이너를 통째로 들고 온다

    secs = common.read_sectors(src)
    raw = bytearray(dst.read_bytes())
    rng = None
    if key in FONT_AT:
        rng = claim(secs, FONT_AT[key], len(table))  # ⑷
        blob = table + BLANK * (len(rng) * common.SECTOR_SIZE - len(table))
        for n, i in enumerate(rng):
            off = secs[i]["file_off"]
            raw[off : off + common.SECTOR_SIZE] = blob[
                n * common.SECTOR_SIZE : (n + 1) * common.SECTOR_SIZE
            ]

    # 🔴 **덮어쓰기 사전조건** — 그 자리가 정말 우리가 아는 바이트인가(patcher-checklist 2).
    #    빗나가면 원본이 바뀐 것이고, 그대로 쓰면 **남의 코드를 뭉갠다.**
    marks = patches_for(key)
    flat = b"".join(x["data"] for x in secs)
    for off, expect, new in marks:
        got = flat[off : off + len(expect)]
        if got != expect:
            raise SystemExit(
                f"🔴 {key} {off:#07x}: 원본이 예상과 다르다\n"
                f"   want {expect.hex(' ')}\n   got  {got.hex(' ')}"
            )
        write_flat(raw, secs, off, new)

    dst.write_bytes(bytes(raw))
    return dst, rng, marks


def verify(key: str, dst: Path, rng: range | None, marks: list) -> None:
    """⑵ claim 한 섹터 말고는 한 바이트도 안 바뀌었나 — **전 섹터 대조**."""
    before = common.read_sectors(common.disk_path(key))
    after = common.read_sectors(dst)
    if len(before) != len(after):
        raise SystemExit(f"🔴 {key}: 섹터 수가 바뀌었다")
    claimed = set(rng or ())
    for a, b in zip(before, after, strict=True):
        if (a["c"], a["h"], a["r"], a["index"]) != (b["c"], b["h"], b["r"], b["index"]):
            raise SystemExit(f"🔴 {key}: 섹터 ID 가 바뀌었다 (논리 {a['index']})")
        if a["index"] in claimed:
            continue
        if a["data"] == b["data"]:
            continue
        # 패치가 든 섹터는 **바이트 단위로** 본다 — 섹터를 통째로 면제하면 그 안의 다른
        # 자리가 바뀌어도 안 잡힌다(무변경 선언의 뜻이 없어진다).
        allowed = set()
        for off, _e, new in marks:
            for n in range(len(new)):
                if (off + n) // common.SECTOR_SIZE == a["index"]:
                    allowed.add((off + n) % common.SECTOR_SIZE)
        bad = {k for k in range(common.SECTOR_SIZE) if a["data"][k] != b["data"][k]}
        if bad - allowed:
            raise SystemExit(
                f"🔴 {key}: 섹터 {a['index']} 에서 허락 안 한 자리가 바뀌었다 "
                f"({len(bad - allowed)}바이트)"
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=common.BUILD_TAG, help="빌드 꼬리표(기본 = 브랜치)")
    args = ap.parse_args()

    common.check_originals()
    _, base = font.build()
    if hashlib.sha1(base).hexdigest() != font.TABLE_SHA1:
        raise SystemExit("🔴 글리프 표 지문이 다르다 — font.py --check 부터 본다")
    table = patch_font_hook.ku128_table()  # ku 당 128칸으로 다시 깐다(산술을 없앤다)

    out_dir = common.BUILD_DIR / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    try:
        for key in common.DISKS:
            dst, rng, marks = build_disk(key, table, out_dir)
            made.append(dst)
            verify(key, dst, rng, marks)
            where = f"섹터 {rng.start}~{rng.stop - 1}" if rng else "그대로"
            extra = f" +패치 {len(marks)}" if marks else ""
            print(
                f"  {key:9s} {where:16s}{extra:9s} sha1 "
                f"{hashlib.sha1(dst.read_bytes()).hexdigest()}"
            )
    except SystemExit:
        for p in made:  # ⑸ 실패한 빌드는 산출물을 무효화한다
            p.rename(p.with_suffix(".d88.failed"))
        raise
    print(f"→ {out_dir}")
    print(
        f"⚠ JIS ku {patch_font_hook.KU_LO:#04x}~{patch_font_hook.KU_HI:#04x} "
        f"({patch_font_hook.KU_COUNT}구 = 완성형 2,350자)가 **한글로** 나온다 — "
        f"오프닝(event)과 인게임(program) 둘 다. 표는 각 경로가 **자기 드라이브**에서 "
        f"RAM {patch_font_hook.FONT_SEG:#06x} 로 올린다."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
