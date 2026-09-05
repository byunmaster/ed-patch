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
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import containers
import lz
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


def load_edits(path: Path) -> dict[tuple[int, int], list[tuple[bytes, bytes]]]:
    """PoC 편집 입력: [{rel, id, find_hex, replace_hex}] → {(rel,id): [(find, replace)]}."""
    out: dict[tuple[int, int], list[tuple[bytes, bytes]]] = {}
    for e in json.loads(path.read_text()):
        out.setdefault((e["rel"], e["id"]), []).append((bytes.fromhex(e["find_hex"]), bytes.fromhex(e["replace_hex"])))
    return out


def apply_edits(block: bytes, edits: list[tuple[bytes, bytes]], where: str) -> bytes:
    b = block
    for find, rep in edits:
        n = b.count(find)
        if n != 1:
            raise BuildError(f"{where}: 찾는 바이트가 {n}번 나온다(정확히 1번이어야) — {find.hex()}")
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
    edits = load_edits(edits_path) if edits_path else {}
    found = containers.scan()
    by_rel = {c["rel"]: c for c in found}
    touched: list[tuple[int, int]] = []  # (첫 파일 섹터, 섹터 수)
    intended: dict[tuple[int, int], bytes] = {}
    refs = containers.referenced()
    slot_of = {r: n for r, n in refs}  # 참조표가 말하는 섹터 수
    with open(iso, "r+b") as f:
        for rel, c in sorted(by_rel.items()):
            hit = {k for k in edits if k[0] == rel}
            if not hit:
                continue
            entries = []
            for b in c["blocks"]:
                blk = b["data"]
                if (rel, b["id"]) in edits:
                    blk = apply_edits(blk, edits[(rel, b["id"])], f"rel {rel} id {b['id']}")
                    intended[(rel, b["id"])] = blk
                entries.append((b["id"], blk))
            data = assemble(entries)
            slot = slot_of[rel] * common.USER
            if len(data) > slot:
                raise BuildError(f"컨테이너 rel {rel}: {len(data)}B > 칸 {slot}B(참조표 {slot_of[rel]}섹터)")
            data = data + b"\0" * (slot - len(data))
            orig = common.track_data(rel, slot_of[rel])
            lba = common.T2_SECTOR + rel
            mode1.write_user_data(f, lba, data, label=f"container rel {rel}", expect=orig)
            touched.append((lba, slot_of[rel]))
            print(f"  컨테이너 rel {rel}: {len(entries)}블록 → {len(data.rstrip(b'\0'))}B / {slot}B")
    verify_immutable(iso, touched)
    verify_readback(iso, intended, found)
    bad = mode1.selftest(iso, lbas=(common.T2_SECTOR + 2, common.T2_SECTOR + 34, common.T2_SECTOR + 1252, common.T22_SECTOR + 1))
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
                    if x[i : i + common.RAW] != y[i : i + common.RAW] and (lba + i // common.RAW) not in allowed:
                        raise BuildError(f"무변경 구간이 바뀌었다: 파일 섹터 {lba + i // common.RAW}")
            lba += chunk // common.RAW
    print(f"  무변경 대조 OK (허용 {len(allowed)}섹터 밖 동일)")


def verify_readback(iso: Path, intended, found_orig):
    data = iso.read_bytes()
    track = b"".join(
        data[(common.T2_SECTOR + r) * common.RAW + common.USER_OFF : (common.T2_SECTOR + r) * common.RAW + common.USER_OFF + common.USER]
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
    a = ap.parse_args()
    build(a.edits)


if __name__ == "__main__":
    main()
