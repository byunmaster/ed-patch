"""pce-ed1 빌드 — 원본을 그대로 복사한 뒤 **선언한 자리만** 고쳐 쓴다.

    python3 games/pce-ed1/tools/build.py            # work/build/<꼬리표>/ed1.iso + .cue
    python3 games/pce-ed1/tools/build.py --edits work/edits_poc.json   # 개발/PoC 입력(커밋 안 함)

규율(루트 CLAUDE.md 「빌드 규율」· docs/patcher-checklist.md):
  · 원본은 읽기만(지문 확인) · 출력은 새 파일 · 실패하면 산출물을 `*.failed` 로 무효화
  · 쓰기는 `shared.disc.mode1.write_user_data`(EDC/ECC 재계산 + `expect` 사전조건)로만
  · **무변경 구간**: 고치겠다고 선언한 섹터 밖은 원본과 byte 대조
  · **되읽기**: 구운 이미지의 컨테이너를 다시 풀어 의도한 블록과 대조하고, 참조표·개수가 그대로인지 본다

⚠ 지금은 씬 컨테이너만 고친다. 폰트 후킹·글리프 뱅크·할당기 패치는 status.md 9절 설계대로 뒤에 붙인다.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import containers
import font
import hook
import lz
import sysbuild
import translate

from shared.disc import mode1

SLOT_SECTORS = 16  # 컨테이너 한 칸(실측: 참조표 간격 16섹터 = 32KB)
BANK = 0x2000  # 풀린 블록은 뱅크 0x76 하나에 들어가야 한다


class BuildError(Exception):
    pass


def assemble(entries: list[tuple[int, bytes]]) -> bytes:
    """(id, 풀린 블록) 목록 → 컨테이너 바이트. 같은 블록은 한 번만 싣고 src 를 나눠 갖는다(rel 1,444 꼴)."""
    for id_, blk in entries:
        if len(blk) > BANK:
            raise BuildError(f"블록 id {id_} 가 {len(blk)}B — 뱅크(8KB)를 넘는다")
    packed: dict[bytes, bytes] = {}
    for _, blk in entries:
        if blk not in packed:
            packed[blk] = lz.encode(blk)
    dir_len = len(entries) * containers.ENTRY + 1
    src_of: dict[bytes, int] = {}
    pos = dir_len
    body = bytearray()
    for blk, pk in packed.items():
        src_of[blk] = pos
        body += pk
        pos += len(pk)
    d = bytearray()
    for id_, blk in entries:
        s = src_of[blk]
        d += bytes([id_, s & 0xFF, s >> 8, len(blk) & 0xFF, len(blk) >> 8])
    d.append(containers.DIR_END)
    out = bytes(d) + bytes(body)
    # 자기 검산 — 우리 디코더로 되풀어 같은가(코덱 A 조건)
    ents, _ = containers.parse_dir(out[:2048])
    for (id_, blk), (id2, src, ln) in zip(entries, ents, strict=True):
        assert id_ == id2 and ln == len(blk)
        got, _ = lz.decode(out[src:], ln)
        assert got == blk, f"재조립 검산 실패 id {id_}"
    return out


def load_edits(path: Path, table: dict[str, bytes]):
    """PoC 편집 입력: [{rel, id, find_hex, replace_hex | replace_text}] → {(rel,id): [(find, replace)]}.

    `replace_text` 는 우리 문안(한글 + 전각) — 글리프 표는 빌드가 정본 전체에서 뽑아 넘긴다.
    """
    raw = json.loads(path.read_text())
    out: dict[tuple[int, int], list[tuple[bytes, bytes]]] = {}
    for e in raw:
        rep = (
            bytes.fromhex(e["replace_hex"])
            if "replace_hex" in e
            else font.encode(e["replace_text"], table)
        )
        out.setdefault((e["rel"], e["id"]), []).append((bytes.fromhex(e["find_hex"]), rep))
    return out


# ─── 코드 패치(rel:offset, 기대 바이트 → 새 바이트) ─────────────────────────────────────
# 좌표는 전부 rel:offset(유저 데이터 2048B 안). 뱅크 → rel 은 본 프로그램(rel 34, 뱅크 0x68 부터 4섹터씩).
def _main(bank: int, off: int) -> tuple[int, int]:
    return 34 + (bank - 0x68) * 4 + off // common.USER, off % common.USER


ONLY: set[str] | None = None  # 진단용 — 패치 그룹 부분집합("cache" · "font")만 건다


def code_patches() -> list[tuple[str, int, int, bytes, bytes]]:
    """(라벨, rel, offset, 기대, 새값). 기대가 어긋나면 그 자리에서 죽는다(쓰기 사전조건)."""
    p = []
    want = lambda g: ONLY is None or g in ONLY
    # 1. 본 프로그램 진입: JSR $5798 → JSR 스텁
    if want("font"):
        p.append(
            (
                "entry JSR→stub",
                *_main(0x68, 0x000F),
                b"\x20\x98\x57",
                b"\x20" + hook.STUB_ADDR.to_bytes(2, "little"),
            )
        )
        # 2. 스텁(뱅크 0x69 패딩)
        stub = hook.init_stub()
        p.append(("init stub", *_main(0x69, 0x1852), b"\0" * len(stub), stub))
    if want("cache"):
        # 3. 할당기: 캐시 16 → 13 슬롯 (뱅크 0x85~0x87 을 글리프에 내준다) — status 9절
        p.append(("cache init free=13", *_main(0x68, 0x14FB), b"\xa9\x90", b"\xa9\x8d"))
        for off in (0x151F, 0x15D1, 0x15F2, 0x163A, 0x1783):
            p.append((f"cache CPX 13 @{off:04X}", *_main(0x68, off), b"\xe0\x10", b"\xe0\x0d"))
        p.append(("cache LDA 13 @15FC", *_main(0x68, 0x15FC), b"\xa9\x10", b"\xa9\x0d"))
    if want("hook"):
        # 4. EX_GETFNT 호출부(본 프로그램 4곳) → $3B00
        tgt = hook.HOOK_ADDR.to_bytes(2, "little")
        p.append(("dialog JMP $7044", *_main(0x6C, 0x1044), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("name JMP $93A3", *_main(0x6D, 0x13A3), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("JSR 6C+0F5A", *_main(0x6C, 0x0F5A), b"\x20\x60\xe0", b"\x20" + tgt))
        p.append(("JSR 78+0932", *_main(0x78, 0x0932), b"\x20\x60\xe0", b"\x20" + tgt))
    return p


def apply_code_patches(
    f, glyph_bank: bytes, table: dict[str, bytes], touched: list[tuple[int, int]]
):
    for label, rel, off, old, new in code_patches():
        assert len(old) == len(new), label
        lba = common.T2_SECTOR + rel
        mode1.write_at(f, lba, common.USER, off, new, label=label, expect=old)
        touched.append((lba, 1))
    # 5. 글리프 뱅크 → rel 114~125(뱅크 0x7C~0x7E 적재분, 원본 0), 후킹 루틴 → rel 126 앞 256B
    if ONLY is not None and "font" not in ONLY:
        return
    lba = common.T2_SECTOR + 114
    mode1.write_user_data(f, lba, glyph_bank, label="glyph banks", expect=b"\0" * len(glyph_bank))
    touched.append((lba, 12))
    # 루틴 + 조사 오프셋표 + 받침 비트맵 둘 — 스텁이 통째로 $3B00 으로 옮긴다(0x300B)
    payload = bytearray(hook.hook_routine())
    payload += b"\0" * (hook.JOSA_OFF_ADDR - hook.HOOK_ADDR - len(payload))
    payload += font.josa_offsets(table)
    payload += b"\0" * (hook.BATCHIM_ADDR - hook.HOOK_ADDR - len(payload))
    has, rieul = font.batchim_tables(font.build_table.order)
    payload += has
    payload += b"\0" * (hook.RIEUL_ADDR - hook.HOOK_ADDR - len(payload))
    payload += rieul
    payload += b"\0" * (0x300 - len(payload))
    lba = common.T2_SECTOR + 126
    mode1.write_user_data(
        f, lba, bytes(payload), label="hook routine + josa tables", expect=b"\0" * len(payload)
    )
    touched.append((lba, 1))
    routine = payload
    print(
        f"  코드 패치 {len(code_patches())}곳 + 글리프 {len(glyph_bank.rstrip(b'\0'))}B + 루틴 {len(routine.rstrip(b'\0'))}B"
    )


def apply_edits(block: bytes, edits: list[tuple[bytes, bytes]], where: str) -> bytes:
    b = block
    for find, rep in edits:
        n = b.count(find)
        if n != 1:
            raise BuildError(
                f"{where}: 찾는 바이트가 {n}번 나온다(정확히 1번이어야) — {find.hex()}"
            )
        b = b.replace(find, rep)
    return b


def build(edits_path: Path | None) -> Path:
    common.verify_originals()
    out_dir = common.BUILD_DIR / common.BUILD_TAG
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = out_dir / "ed1.iso"
    cue = out_dir / "ed1.cue"
    for p in (iso, cue, out_dir / "ed1.iso.failed"):
        if p.exists():
            p.unlink()
    try:
        _build(edits_path, iso, cue)
    except Exception:
        if iso.exists():
            iso.rename(out_dir / "ed1.iso.failed")
        raise
    return iso


def _build(edits_path, iso: Path, cue: Path):
    shutil.copyfile(common.ORIG_ISO, iso)
    cue.write_text(common.ORIG_CUE.read_text().replace(common.ORIG_ISO.name.upper(), "ed1.iso"))
    # 원본 cue 의 FILE 줄은 대문자 파일명 — 위 치환이 안 먹으면 여기서 죽는다
    if "ed1.iso" not in cue.read_text():
        raise BuildError("cue 의 FILE 이름을 못 바꿨다")
    # 글리프 표 = 번역 정본 전체 + PoC 편집의 음절(결정적). 표를 따로 두지 않는다(폰트 전략 §3.2)
    chars = translate.all_glyph_chars() | sysbuild.all_glyph_chars()
    raw = json.loads(edits_path.read_text()) if edits_path else []
    chars |= {ch for e in raw for ch in e.get("replace_text", "") if font.needs_glyph(ch)}
    table, glyph_bank = font.build_table(chars)
    edits = load_edits(edits_path, table) if edits_path else {}
    found = containers.scan()
    by_rel = {c["rel"]: c for c in found}
    touched: list[tuple[int, int]] = []  # (첫 파일 섹터, 섹터 수)
    intended: dict[tuple[int, int], bytes] = {}
    refs = containers.referenced()
    slot_of = {r: n for r, n in refs}  # 참조표가 말하는 섹터 수
    with open(iso, "r+b") as f:
        apply_code_patches(f, glyph_bank, table, touched)
        print("  시스템 문구:", sysbuild.apply(f, table, touched))
        translated_ids = {int(p.stem[3:]) for p in translate.M.SCRIPT_DIR.glob("scn*.json")}
        n_msgs = 0
        for rel, c in sorted(by_rel.items()):
            hit = {k for k in edits if k[0] == rel} or {
                b["id"] for b in c["blocks"]
            } & translated_ids
            if not hit:
                continue
            entries = []
            for b in c["blocks"]:
                blk = b["data"]
                if b["id"] in translated_ids:
                    blk, n = translate.translate_block(b["id"], blk, table)
                    n_msgs += n
                if (rel, b["id"]) in edits:
                    blk = apply_edits(blk, edits[(rel, b["id"])], f"rel {rel} id {b['id']}")
                if blk != b["data"]:
                    intended[(rel, b["id"])] = blk
                entries.append((b["id"], blk))
            data = assemble(entries)
            slot = slot_of[rel] * common.USER
            if len(data) > slot:
                raise BuildError(
                    f"컨테이너 rel {rel}: {len(data)}B > 칸 {slot}B(참조표 {slot_of[rel]}섹터)"
                )
            data = data + b"\0" * (slot - len(data))
            orig = common.track_data(rel, slot_of[rel])
            lba = common.T2_SECTOR + rel
            mode1.write_user_data(f, lba, data, label=f"container rel {rel}", expect=orig)
            touched.append((lba, slot_of[rel]))
            print(
                f"  컨테이너 rel {rel}: {len(entries)}블록 → {len(data.rstrip(b'\0'))}B / {slot}B"
            )
    print(f"  번역 메시지 {n_msgs}건(컨테이너마다 다시 셈) · 글리프 {len(chars)}자")
    verify_immutable(iso, touched)
    verify_readback(iso, intended, found)
    bad = mode1.selftest(
        iso,
        lbas=(
            common.T2_SECTOR + 2,
            common.T2_SECTOR + 34,
            common.T2_SECTOR + 1252,
            common.T22_SECTOR + 1,
        ),
    )
    if bad:
        raise BuildError(f"EDC/ECC 자기검증 실패: {bad}")
    print(f"빌드 OK: {iso}  sha1 {common.sha1_of(iso)}")


def verify_immutable(iso: Path, touched: list[tuple[int, int]]):
    """선언한 섹터 밖은 원본과 byte 동일해야 한다."""
    allowed = set()
    for lba, n in touched:
        allowed.update(range(lba, lba + n))
    with open(common.ORIG_ISO, "rb") as a, open(iso, "rb") as b:
        chunk = 4096 * common.RAW
        lba = 0
        while True:
            x = a.read(chunk)
            y = b.read(chunk)
            if not x and not y:
                break
            if x != y:
                for i in range(0, len(x), common.RAW):
                    if (
                        x[i : i + common.RAW] != y[i : i + common.RAW]
                        and (lba + i // common.RAW) not in allowed
                    ):
                        raise BuildError(
                            f"무변경 구간이 바뀌었다: 파일 섹터 {lba + i // common.RAW}"
                        )
            lba += chunk // common.RAW
    print(f"  무변경 대조 OK (허용 {len(allowed)}섹터 밖 동일)")


def verify_readback(iso: Path, intended, found_orig):
    data = iso.read_bytes()
    track = b"".join(
        data[
            (common.T2_SECTOR + r) * common.RAW + common.USER_OFF : (common.T2_SECTOR + r)
            * common.RAW
            + common.USER_OFF
            + common.USER
        ]
        for r in range(common.T2_LEN)
    )
    got = containers.scan(track)
    if [c["rel"] for c in got] != [c["rel"] for c in found_orig]:
        raise BuildError("되읽기: 컨테이너 목록이 달라졌다")
    blocks = {(c["rel"], b["id"]): b["data"] for c in got for b in c["blocks"]}
    for k, blk in intended.items():
        if blocks.get(k) != blk:
            raise BuildError(f"되읽기: rel {k[0]} id {k[1]} 이 의도와 다르다")
    # 안 고친 블록은 원본 그대로
    orig_blocks = {(c["rel"], b["id"]): b["data"] for c in found_orig for b in c["blocks"]}
    for k, blk in orig_blocks.items():
        if k not in intended and blocks.get(k) != blk:
            raise BuildError(f"되읽기: 안 고친 블록 rel {k[0]} id {k[1]} 이 바뀌었다")
    print(f"  되읽기 OK (고친 블록 {len(intended)} · 컨테이너 {len(got)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", type=Path, help="PoC 편집 입력 JSON (work/ 아래, 커밋 안 함)")
    ap.add_argument("--only", help="진단용: 패치 그룹만(cache,font,hook 쉼표 구분)")
    a = ap.parse_args()
    global ONLY
    if a.only:
        ONLY = set(a.only.split(","))
    build(a.edits)


if __name__ == "__main__":
    main()
