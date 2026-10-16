"""pce-ed2 빌드 — 원본을 그대로 복사한 뒤 **선언한 자리만** 고쳐 쓴다 (pce-ed1 `build.py` 와 같은 규율).

    python3 games/pce-ed2/tools/build.py --edits work/edits_poc.json   # 개발/PoC 입력(커밋 안 함)
    python3 games/pce-ed2/tools/build.py --edits … --trim             # 트랙 1~2 만(에뮬용, 123MB)

규율(루트 CLAUDE.md 「빌드 규율」 · docs/patcher-checklist.md):
  · 원본은 읽기만(지문 확인) · 출력은 새 파일 · 실패하면 산출물을 `*.failed` 로 무효화
  · 쓰기는 `shared.disc.mode1.write_at`(EDC/ECC 재계산 + `expect` 사전조건)로만
  · 🔴 **데이터 트랙 거울**(rel 2~12,285 ↔ +36,864)은 **두 사본을 같은 바이트로** 쓴다(어느 쪽이 읽히는지 미확정)
  · **무변경 구간**: 쓰겠다고 선언한 섹터 밖은 원본과 byte 대조 · **덮어쓰기 장부** · **되읽기**(덩이 경계 · 글리프 풀)

편집 입력(PoC): [{"pkg": rel, "find_hex": 풀린 대본의 바이트열(패키지 안에서 정확히 한 번), "replace_text": 우리 문안 | "replace_hex": …}]
  — 문안의 한글은 글리프 풀에 실린다(번호순 = 코드포인트순, 결정적). 공백은 게임의 `60`.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font
import hook
import lz
import package
import repack

from shared.disc import mode1

MIRROR = 36864
MIRROR_SPAN = (2, 12286)  # 거울이 같은 rel 범위(common.py 게이트가 확인)
PKG_SECTORS = 128  # 패키지 칸(간격) — 실제 로드는 78섹터지만 칸 전체를 다룬다


class BuildError(Exception):
    pass


class Writer:
    """쓰기 장부 · 무변경 대조용 섹터 집합 · 거울 이중 쓰기를 한 곳에 모은다."""

    def __init__(self, f):
        self.f = f
        self.spans: list[
            tuple[int, bytes, str]
        ] = []  # (선형 바이트, 새 바이트, 라벨) — 덮어쓰기 검사용
        self.touched: set[int] = set()  # 파일 섹터(LBA)

    @staticmethod
    def mirrored(linear: int, n: int) -> bool:
        lo, hi = MIRROR_SPAN
        return lo * common.USER <= linear and linear + n <= hi * common.USER

    def put(self, linear: int, new: bytes, expect: bytes | None, label: str) -> None:
        """선형 유저 데이터 바이트 `linear`(= rel×2048+오프셋)에 쓴다. 거울이 있으면 거울에도 같은 바이트."""
        targets = [linear]
        if self.mirrored(linear, len(new)):
            targets.append(linear + MIRROR * common.USER)
        for t in targets:
            lba = common.T2_SECTOR + t // common.USER
            off = t % common.USER
            mode1.write_at(
                self.f,
                lba,
                1 << 40,
                off,
                new,
                label=label + (" (거울)" if t != linear else ""),
                expect=expect,
            )
            self.spans.append((t, new, label))
            first = common.T2_SECTOR + t // common.USER
            last = common.T2_SECTOR + (t + len(new) - 1) // common.USER
            self.touched.update(range(first, last + 1))

    def verify(self, iso: Path) -> int:
        """**다 쓴 뒤에도 각 쓰기의 바이트가 그대로인가** — 뒤 단계가 앞 단계를 덮었으면 운다."""
        errs = []
        with open(iso, "rb") as f:
            for lin, data, label in self.spans:
                got = bytearray()
                lba, off = divmod(lin, common.USER)
                while len(got) < len(data):
                    f.seek((common.T2_SECTOR + lba) * common.RAW + common.USER_OFF)
                    got += f.read(common.USER)[off:]
                    lba, off = lba + 1, 0
                if bytes(got[: len(data)]) != data:
                    errs.append(f"「{label}」 @{lin} 가 덮였다")
        if errs:
            raise BuildError("쓴 바이트가 나중에 덮였다:\n  " + "\n  ".join(errs[:10]))
        return len(self.spans)


def load_edits(path: Path):
    raw = json.loads(path.read_text())
    return raw


def glyph_chars(raw) -> list[str]:
    return font.order(ch for e in raw for ch in e.get("replace_text", "") if ch not in " \n")


def apply_pkg_edits(w: Writer, raw, table: dict[str, int]) -> dict:
    """패키지마다 덩이를 고쳐 다시 싣는다. 반환: 되읽기 대조용 {rel: (새 패키지 바이트, {새 시작: 풀린 내용})}."""
    intended = {}
    for rel in sorted({e["pkg"] for e in raw}):
        pkg = bytes(common.track_data(rel, PKG_SECTORS))
        ch = [(a, b) for a, b in package.chunks(pkg) if pkg[a : a + 8] != package.SENTINEL]
        decoded = {a: package.decode_chunk(pkg, a, b)[0] for a, b in ch}
        orig_decoded = dict(decoded)
        for e in (x for x in raw if x["pkg"] == rel):
            find = bytes.fromhex(e["find_hex"])
            hits = [(a, d.count(find)) for a, d in decoded.items() if find in d]
            if len(hits) != 1 or hits[0][1] != 1:
                raise BuildError(
                    f"패키지 {rel}: 찾는 바이트가 정확히 한 번이 아니다 {hits} — {find.hex()}"
                )
            a = hits[0][0]
            rep = (
                bytes.fromhex(e["replace_hex"])
                if "replace_hex" in e
                else font.encode(e["replace_text"], table)
            )
            decoded[a] = decoded[a].replace(find, rep)
        changed = {a: d for a, d in decoded.items() if d != orig_decoded[a]}
        try:
            new, place = repack.repack(pkg, changed)
        except repack.RepackError as ex:
            raise BuildError(f"패키지 {rel}: {ex}") from ex
        diff = [i for i in range(len(pkg)) if pkg[i] != new[i]]
        lo, hi = diff[0], diff[-1] + 1
        w.put(rel * common.USER + lo, new[lo:hi], pkg[lo:hi], f"package rel {rel} text +{lo}")
        intended[rel] = (new, {place[a]: d for a, d in changed.items()})
        moved = sum(1 for a in changed if place[a] != a)
        print(
            f"  패키지 rel {rel}: 덩이 {len(changed)}개 교체(이사 {moved}) · 바뀐 바이트 {len(diff)}"
        )
    return intended


def apply_hook(w: Writer, glyph24: list[bytes]) -> None:
    for lin, new, old, label in hook.build(glyph24):
        w.put(lin, new, old, label)
    print(f"  후킹 루틴 + 글리프 풀 {len(glyph24)}자")


def verify_readback(iso: Path, intended: dict, glyph24: list[bytes]) -> None:
    """구운 이미지를 다시 읽어: 패키지가 의도한 바이트이고(거울 포함) · 고친 덩이가 의도대로 풀리고 · 글리프 풀이 `font` 와 같다."""

    def track(rel, n):
        with open(iso, "rb") as f:
            out = bytearray()
            for i in range(n):
                f.seek((common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF)
                out += f.read(common.USER)
        return bytes(out)

    n = 0
    for rel, (want, chunks) in sorted(intended.items()):
        for r in [rel] + ([rel + MIRROR] if MIRROR_SPAN[0] <= rel < MIRROR_SPAN[1] else []):
            got = track(r, PKG_SECTORS)
            if got != want:
                raise BuildError(f"되읽기: rel {r} 패키지가 의도와 다르다")
            for start, d in chunks.items():
                back, _ = lz.decode(got, start, len(d))
                if back != d:
                    raise BuildError(f"되읽기: rel {r} 덩이 {start} 가 의도와 다르다")
                n += 1
    for lin, new, _old, label in hook.build(glyph24):
        rel = lin // common.USER
        got = track(rel, (lin % common.USER + len(new) + common.USER - 1) // common.USER)[
            lin % common.USER :
        ][: len(new)]
        if got != new:
            raise BuildError(f"되읽기: {label} 가 다르다")
    print(f"  되읽기 OK (고친 덩이 {n} · 글리프 {len(glyph24)})")


def verify_immutable(iso: Path, touched: set[int], limit_sectors: int | None) -> None:
    """선언한 섹터 밖은 원본과 byte 동일해야 한다."""
    n = 0
    with open(common.ORIG_ISO, "rb") as a, open(iso, "rb") as b:
        chunk = 4096 * common.RAW
        lba = 0
        while True:
            x = a.read(chunk)
            y = b.read(chunk)
            if limit_sectors is not None and lba * common.RAW >= limit_sectors * common.RAW:
                break
            if not y:
                break
            x = x[: len(y)]
            if x != y:
                for i in range(0, len(y), common.RAW):
                    if (
                        x[i : i + common.RAW] != y[i : i + common.RAW]
                        and (lba + i // common.RAW) not in touched
                    ):
                        raise BuildError(
                            f"무변경 구간이 바뀌었다: 파일 섹터 {lba + i // common.RAW}"
                        )
            lba += chunk // common.RAW
            n = lba
    print(f"  무변경 대조 OK (허용 {len(touched)}섹터 밖 동일, 대조 {n}섹터)")


def build(edits_path: Path | None, trim: bool) -> Path:
    common.verify_originals()
    out_dir = common.BUILD_DIR / common.BUILD_TAG
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = out_dir / "ed2.iso"
    cue = out_dir / "ed2.cue"
    for p in (iso, cue, out_dir / "ed2.iso.failed"):
        if p.exists():
            p.unlink()
    try:
        _build(edits_path, iso, cue, trim)
    except Exception:
        if iso.exists():
            iso.rename(out_dir / "ed2.iso.failed")
        raise
    return iso


def _build(edits_path, iso: Path, cue: Path, trim: bool) -> None:
    limit = common.T2_SECTOR + common.T2_LEN  # 트랙 1~2 의 파일 섹터 수
    if trim:
        with open(common.ORIG_ISO, "rb") as a, open(iso, "wb") as b:
            b.write(a.read(limit * common.RAW))
        cue.write_text(
            'FILE "ed2.iso" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
            "  TRACK 02 MODE1/2352\n    PREGAP 00:03:00\n    INDEX 01 00:44:71\n"
        )
    else:
        shutil.copyfile(common.ORIG_ISO, iso)
        text = common.ORIG_CUE.read_text().replace(common.ORIG_ISO.name.upper(), "ed2.iso")
        if "ed2.iso" not in text:
            raise BuildError("cue 의 FILE 이름을 못 바꿨다")
        cue.write_text(text)
    raw = load_edits(edits_path) if edits_path else []
    chars = glyph_chars(raw)
    table = {ch: i for i, ch in enumerate(chars)}
    glyph24 = [font.glyph(ch) for ch in chars]
    with open(iso, "r+b") as f:
        w = Writer(f)
        apply_hook(w, glyph24)
        intended = apply_pkg_edits(w, raw, table)
    print(f"  덮어쓰기 없음 (쓰기 구간 {w.verify(iso)})")
    verify_immutable(iso, w.touched, limit if trim else None)
    verify_readback(iso, intended, glyph24)
    bad = mode1.selftest(
        iso, lbas=(common.T2_SECTOR + 2, common.T2_SECTOR + 386, common.T2_SECTOR + 4098)
    )
    if bad:
        raise BuildError(f"EDC/ECC 자기검증 실패: {bad}")
    print(f"빌드 OK: {iso}  sha1 {common.sha1_of(iso)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", type=Path, help="PoC 편집 입력 JSON (work/ 아래, 커밋 안 함)")
    ap.add_argument("--trim", action="store_true", help="트랙 1~2 만(에뮬용)")
    a = ap.parse_args()
    build(a.edits, a.trim)


if __name__ == "__main__":
    main()
