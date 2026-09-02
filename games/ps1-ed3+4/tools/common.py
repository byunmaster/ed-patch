"""공용: 두 디스크(ED3·ED4)의 경로·지문, 섹터 상수, ISO9660 워커, GMF 아카이브, 쓰기 가드.

⚠ **이 게임 코드베이스는 디스크가 둘이다.** ED3·ED4 는 이미지가 따로지만 **같은 엔진(GMF)**
이라 아카이브 포맷·문자 코드표·재삽입 경로가 같다. 그래서 한 코드베이스에 둘을 둔다 —
경로를 고르는 인자가 `disc`("ed3"/"ed4")다. (`ps1-ed1+2` 가 「한 이미지에 두 게임」이라면
여기는 「두 이미지에 한 엔진」이다.)
"""

import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # games/ps1-ed3+4
REPO = os.path.dirname(os.path.dirname(ROOT))


def main_repo():
    """워크트리에서도 **본 트리**를 가리킨다 — `.git` 이 파일이면 그 안의 gitdir 를 따라간다.

    ⚠ 워크트리의 `REPO` 는 워크트리 자신이라, 다른 게임 트리(로제타 등)를 찾을 때 쓰면
    조용히 빈손이 된다.
    """
    g = os.path.join(REPO, ".git")
    if os.path.isfile(g):
        with open(g, encoding="utf-8") as f:
            line = f.read().strip()
        if line.startswith("gitdir:"):
            gd = line.split(":", 1)[1].strip()
            # …/<main>/.git/worktrees/<name>
            return os.path.dirname(os.path.dirname(os.path.dirname(gd)))
    return REPO


WORK_DIR = os.path.join(ROOT, "work")


def _build_tag():
    """빌드 산출물을 가르는 꼬리표 — 기본은 현재 git 브랜치(`ED_BUILD_TAG` 로 덮어씀)."""
    tag = os.environ.get("ED_BUILD_TAG")
    if not tag:
        try:
            with open(os.path.join(REPO, ".git", "HEAD"), encoding="utf-8") as f:
                ref = f.read().strip()
            tag = ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else ref[:7]
        except OSError:
            tag = "local"
    return "".join(c if (c.isalnum() or c in "-_.") else "-" for c in tag) or "local"


BUILD_TAG = _build_tag()
BUILD_DIR = os.path.join(WORK_DIR, "build", BUILD_TAG)
OUT_DIR = os.path.join(WORK_DIR, "derived")  # ⚠ 빌드가 **읽는** 입력
REVIEW_DIR = os.path.join(WORK_DIR, "review")  # ⚠ 원문 포함 — 커밋 금지
DIST_DIR = os.path.join(WORK_DIR, "dist")

# ── 원본 지문 — 오프셋·LBA 가 이 덤프들에 결박돼 있다 (체크리스트 1) ──────────
DISCS = {
    "ed3": {
        "dir": os.path.join(REPO, "originals", "jp", "ps1-ed3"),
        "bin": "Legend of Heroes III, The - Shiroki Majo - "
        "Mouhitotsu no Eiyuutachi no Monogatari (Japan).bin",
        "size": 473_742_192,
        "crc32": "10805100",
        "md5": "3661074303cab6330f342992ed82643e",
        "sha1": "1e9e1d83d0fac933e2499a3ee8bda810bfbb98ab",
        "sha256": "d4bc7170a3f1ca0f564b4e1a7397f0c368f15dfdba8c9658e2a7e511985b6ed7",
        "label": "Eiyuu Densetsu III (KR)",
    },
    "ed4": {
        "dir": os.path.join(REPO, "originals", "jp", "ps1-ed4"),
        "bin": "Legend of Heroes IV, The - Akai Shizuku (Japan).bin",
        "size": 521_852_352,
        "crc32": "ABA2CAB1",
        "md5": "8ea48e0efa7e2a2dd823e2bd51e80224",
        "sha1": "26140482c805008e2aaf5523bc83b4d18d6b5ee0",
        "sha256": "194857afeecee2ded864c613da7f3161a9c90484f1c3bc02370dd29b2699a28f",
        "label": "Eiyuu Densetsu IV (KR)",
    },
}
DISC_NAMES = tuple(DISCS)


def orig_bin(disc):
    d = DISCS[disc]
    return os.path.join(d["dir"], d["bin"])


def build_bin(disc):
    return os.path.join(BUILD_DIR, DISCS[disc]["label"] + ".bin")


def build_cue(disc):
    return os.path.join(BUILD_DIR, DISCS[disc]["label"] + ".cue")


SECTOR = 2352  # raw MODE2/2352
USER_OFF = 24  # sync(12)+header(4)+subheader(8) → Mode2 Form1 유저 데이터
USER_SIZE = 2048


def digests(path):
    """{size, crc32, md5, sha1, sha256} — 배포 표기·원본 확인에 같이 쓴다."""
    import hashlib
    import zlib

    h = {n: hashlib.new(n) for n in ("md5", "sha1", "sha256")}
    crc = size = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            for x in h.values():
                x.update(chunk)
    return {
        "size": size,
        "crc32": f"{crc & 0xFFFFFFFF:08X}",
        **{k: v.hexdigest() for k, v in h.items()},
    }


def verify_source(disc, strict=None):
    """원본이 오프셋을 박아 둔 그 덤프인지 확인한다 (크기부터 → 같으면 sha1).

    `ALLOW_NONCANONICAL_SRC=1` 이 명시적 탈출구다(경고만 하고 통과).
    """
    if strict is None:
        strict = os.environ.get("ALLOW_NONCANONICAL_SRC") != "1"
    d = DISCS[disc]
    path = orig_bin(disc)
    n = os.path.getsize(path)
    if n != d["size"]:
        bad = f"크기 {n:,} (기대 {d['size']:,})"
    else:
        got = digests(path)["sha1"]
        bad = None if got == d["sha1"] else f"sha1 {got} (기대 {d['sha1']})"
    if not bad:
        return True
    msg = (
        f"⚠ {disc} 원본이 정본 덤프와 다르다 — {bad}\n"
        f"  오프셋·LBA 가 그 덤프에 결박돼 있어 **엉뚱한 자리를 고쳐 쓸 수 있다**.\n"
        f"  알고도 계속하려면 `ALLOW_NONCANONICAL_SRC=1`."
    )
    if strict:
        raise SystemExit(msg)
    print(msg)
    return False


# ── ISO9660 (MODE2/2352 raw) ────────────────────────────────────────────────
def read_lba(disc, lba, size, path=None):
    """ISO 파일의 유저 데이터(2048/섹터)를 이어붙여 추출."""
    out = bytearray()
    with open(path or orig_bin(disc), "rb") as f:
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            f.seek((lba + i) * SECTOR + USER_OFF)
            out += f.read(USER_SIZE)
    return bytes(out[:size])


def _walk(f, lba, size, prefix, depth, out):
    data = bytearray()
    for i in range((size + USER_SIZE - 1) // USER_SIZE):
        f.seek((lba + i) * SECTOR + USER_OFF)
        data += f.read(USER_SIZE)
    i = 0
    while i < len(data):
        ln = data[i]
        if ln == 0:  # 섹터 경계까지 패딩
            i = (i // USER_SIZE + 1) * USER_SIZE
            continue
        rec = data[i : i + ln]
        ext, dsz, flags, nlen = (
            struct.unpack("<I", rec[2:6])[0],
            struct.unpack("<I", rec[10:14])[0],
            rec[25],
            rec[32],
        )
        name = rec[33 : 33 + nlen]
        i += ln
        if nlen == 1 and name in (b"\x00", b"\x01"):
            continue
        path = f"{prefix}/{name.decode('ascii', 'replace').split(';')[0]}"
        if flags & 2:
            if depth < 8:
                _walk(f, ext, dsz, path, depth + 1, out)
        else:
            out[path] = (ext, dsz)
    return out


def iso_files(disc):
    """{경로: (lba, size)} — 디스크의 파일 전량. PVD 에서 루트를 따라 걷는다."""
    with open(orig_bin(disc), "rb") as f:
        f.seek(16 * SECTOR + USER_OFF)
        pvd = f.read(USER_SIZE)
        root = pvd[156:190]
        rlba, rsz = struct.unpack("<I", root[2:6])[0], struct.unpack("<I", root[10:14])[0]
        return _walk(f, rlba, rsz, "", 0, {})


# ── GMF 아카이브 (SC*.DAT · M0*.DAT) ────────────────────────────────────────
# TOC 엔트리 32B = 이름[20] + u32 off + u32 size + u32 예약.
# ⚠ **off 의 단위가 파일마다 다르다** — SC*.DAT 은 4바이트 워드, M01.DAT 은 2048 섹터.
#   단위를 잘못 잡으면 예외가 아니라 **빈 슬라이스**가 나와 조용히 0바이트 멤버가 된다
#   (실측 2026-09-03: 595 멤버가 전부 빈 채로 통계까지 돌았다). 그래서 검증해서 고른다.
ARC_UNITS = (4, 2048, 1, 2)


class ArchiveError(Exception):
    pass


def arc_parse(data):
    """(unit, [(이름, 오프셋, 크기)]) — 단위는 파일 전체가 성립하는 것으로 고른다."""
    ents = []
    for i in range(0, len(data), 32):
        nm = data[i : i + 20].rstrip(b"\x00")
        if not nm or nm[0] == 0:
            break
        off, size, _ = struct.unpack("<III", data[i + 20 : i + 32])
        ents.append((nm.decode("ascii", "replace"), off, size))
    if not ents:
        raise ArchiveError("TOC 가 비었다")
    toc = len(ents) * 32
    for u in ARC_UNITS:
        offs = [o * u for _, o, _ in ents]
        if offs[0] < toc or offs != sorted(offs):
            continue
        if any(o + s > len(data) for o, (_, _, s) in zip(offs, ents, strict=True)):
            continue
        return u, [(n, o, s) for (n, _, s), o in zip(ents, offs, strict=True)]
    raise ArchiveError(f"오프셋 단위를 못 정했다 (엔트리 {len(ents)}, 길이 {len(data)})")


def arc_members(data):
    """{짧은이름: (오프셋, 크기)} — 멤버 이름은 `..\\DATA\\FT0000.BIN` 식 원본 경로다."""
    _, ents = arc_parse(data)
    return {n: (o, s) for n, o, s in ents}


# ── 쓰기 — 사전조건 + 무변경 구간 즉시 차단 (체크리스트 2) ───────────────────
# 아직 무변경 구간을 선언할 만큼 이미지를 모른다. 자리를 비워 두되 **통로는 지금 하나로
# 좁혀 둔다** — 나중에 붙이면 이미 여러 통로가 생겨 있어 못 막는다(체크리스트 4-C).
IMMUTABLE = {}  # {(disc, lba, size): [(이름, 시작, 끝, mode)]}


class WriteGuard(Exception):
    """무변경 구간을 바꾸려 했다 — 쓰기를 취소하고 그 자리에서 실패."""


def _guards(disc):
    out = []
    for (d, lba, _size), regions in IMMUTABLE.items():
        if d != disc:
            continue
        base = lba * USER_SIZE
        out += [(base + a, base + b, name, mode) for name, a, b, mode in regions]
    return out


def _check_guard(disc, lo, old, new, label):
    for g_lo, g_hi, name, _mode in _guards(disc):
        a, b = max(lo, g_lo), min(lo + len(old), g_hi)
        if a >= b:
            continue
        for o in range(a - lo, b - lo):
            if old[o] != new[o]:
                raise WriteGuard(
                    f"무변경 구간 침범 — `{label}` 이 「{name}」 @0x{lo + o:X}"
                    f"(유저데이터 절대) 를 {old[o]:02X}→{new[o]:02X} 로 바꾸려 했다"
                )


def edc_compute(data):
    """Mode2 Form1 EDC (섹터 16~2071 대상, 2072에 LE 저장)."""
    edc = 0
    for b in data:
        edc ^= b
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
    return edc


# GF(2^8) 0x11D — ecm/cdrdao 표준. EDC 만 고치고 ECC 를 두면 에뮬은 넘어가지만 실기
# CD 컨트롤러가 스테일 패리티로 멀쩡한 데이터를 "정정"해 깨뜨린다.
_ECC_F = bytearray(256)
_ECC_B = bytearray(256)
for _i in range(256):
    _j = ((_i << 1) ^ (0x11D if _i & 0x80 else 0)) & 0xFF
    _ECC_F[_i] = _j
    _ECC_B[_i ^ _j] = _i


def _ecc_block(src, major_count, minor_count, major_mult, minor_inc, dst, dst_off):
    size = major_count * minor_count
    for major in range(major_count):
        idx = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[idx]
            idx += minor_inc
            if idx >= size:
                idx -= size
            a ^= t
            b ^= t
            a = _ECC_F[a]
        a = _ECC_B[_ECC_F[a] ^ b]
        dst[dst_off + major] = a
        dst[dst_off + major + major_count] = a ^ b


def ecc_update(sec):
    """섹터(2352B bytearray)의 P(0x81C~)·Q(0x8C8~) 패리티를 제자리 재계산."""
    hdr = bytes(sec[12:16])
    sec[12:16] = b"\x00\x00\x00\x00"
    src = memoryview(sec)[12:]
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q
    sec[12:16] = hdr


def write_user_data(f, disc, lba, data, nsec=None, *, label, expect=None):
    """열린 r+b 핸들의 lba 부터 유저 데이터를 쓰고 EDC·ECC 를 다시 계산한다.

    `label` 필수 — 가드에 걸렸을 때 범인을 바로 알기 위해서다.
    `expect` — 쓰기 **사전조건**. bytes 면 현재 바이트가 정확히 그것, int 면 전 범위가 그 값.
    반환: 실제로 바뀐 섹터 수.
    """
    if nsec is None:
        nsec = (len(data) + USER_SIZE - 1) // USER_SIZE
    if expect is not None:
        cur = bytearray()
        for i in range(nsec):
            f.seek((lba + i) * SECTOR + USER_OFF)
            cur += f.read(USER_SIZE)
        n = len(data) if isinstance(expect, bytes) else nsec * USER_SIZE
        got = bytes(cur[:n])
        want = expect if isinstance(expect, bytes) else bytes([expect]) * n
        if got != want:
            o = next(i for i, (x, y) in enumerate(zip(got, want, strict=True)) if x != y)
            raise WriteGuard(
                f"쓰기 사전조건 불일치 — `{label}` @lba {lba}+0x{o:X}: "
                f"{got[o]:02X} (기대 {want[o]:02X})"
            )
    changed = 0
    for i in range(nsec):
        chunk = bytes(data[i * USER_SIZE : (i + 1) * USER_SIZE]).ljust(USER_SIZE, b"\x00")
        sec_base = (lba + i) * SECTOR
        f.seek(sec_base)
        sec = bytearray(f.read(SECTOR))
        old = bytes(sec[USER_OFF : USER_OFF + USER_SIZE])
        if old == chunk:
            continue
        _check_guard(disc, (lba + i) * USER_SIZE, old, chunk, label)
        assert not (sec[18] & 0x20), f"섹터 {lba + i}는 Form2 — 대상 아님"
        sec[USER_OFF : USER_OFF + USER_SIZE] = chunk
        sec[2072:2076] = edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
        ecc_update(sec)
        f.seek(sec_base)
        f.write(sec)
        changed += 1
    return changed


def write_cue(cue_path, bin_name):
    with open(cue_path, "w", encoding="ascii") as f:
        f.write(f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
