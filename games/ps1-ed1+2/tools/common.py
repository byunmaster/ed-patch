"""공용: 경로, 섹터 상수, 추출/EDC 헬퍼. 모든 도구가 여기서 가져다 쓴다."""

import atexit
import hashlib
import json
import os
import re

# 이 실행이 이미지에 **쓰려 한 것**의 지문 — 되읽기 대조의 기준(`_flush_write_log`).
# ⚠ **섹터 단위**여야 한다. 쓰기 단위로 잡으면 같은 파일을 뒤에서 조금만 덧칠해도(패처들이
#   실제로 그런다) 앞의 큰 쓰기가 통째로 검증 밖으로 밀려난다 — 실측으로 커버리지가 38%
#   였고 **대사 씬 열아홉이 전부** 그 밖이었다. 섹터로 잡으면 마지막 쓴 사람이 자연히 이긴다.
WRITE_SECTORS = {}  # lba → [sha1(유저 2048B), 라벨]
WRITE_LOG = []  # 통계·라벨용(무엇을 몇 번 썼나)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # games/ps1-ed1+2
ORIG_DIR = os.path.join(ROOT, "..", "..", "originals", "jp", "ps1-ed1+2")  # 원본 이미지 (gitignore)
# 작업 산출물은 전부 `work/` 한 칸 아래로 모은다(gitignore 한 줄로 덮이고, `rm -rf work/`가
# 곧 리셋이다). 성격이 다르니 칸을 나눈다 —
WORK_DIR = os.path.join(ROOT, "work")  # 컨테이너



# ── 바깥 서비스 열쇠 ────────────────────────────────────────────────────────
# ⚠ **`ss-ed3/tools/common.py` 와 같은 몸**이다(2026-08-26). 둘째 소비자가 생겼으니
#   `shared/` 로 올릴 자리인데, **공용 코드는 main 에서만 고친다**(루트 CLAUDE.md)라
#   여기서는 게임 쪽에 둔다. main 작업 때 옮긴다.

def secrets_path():
    """`.local/keep/secrets.env` 를 **위로 올라가며** 찾는다 — 없으면 있을 자리를 돌려준다.

    ⚠ 열쇠는 `.local/` 에 둔다 — 이 레포가 이미 「머신 전용」으로 쓰는 자리이고
    `.gitignore` 에 들어 있다. **새 `.env` 규약을 만들지 않는다.**
    ⚠ **워크트리에는 `.local/` 이 따라오지 않는다** — 워크트리 루트에서 시작해 메인
    트리까지 거슬러 올라간다.
    """
    d = ROOT
    fallback = None
    for _ in range(6):
        p = os.path.join(d, ".local", "keep", "secrets.env")
        if os.path.exists(p):
            return p
        if fallback is None and os.path.isdir(os.path.join(d, ".local")):
            fallback = p
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return fallback or os.path.join(ROOT, ".local", "keep", "secrets.env")


def secret(name):
    """바깥 서비스 열쇠 — **환경변수 → `.local/keep/secrets.env`** 순. 없으면 빈 문자열.

    열쇠가 느는 자리가 이미 둘이다(`DEEPL_API_KEY` · `GEMINI_API_KEY`). 도구마다 읽는
    법을 따로 쓰면 곧 갈리므로 여기 하나로 둔다.
    ⚠ 값을 로그·오류 메시지에 찍지 않는다 — 있는지 없는지만 말한다.
    """
    v = os.environ.get(name)
    if v:
        return v
    p = secrets_path()
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def need_secret(name, how):
    """없으면 **어디에 어떻게 두는지** 알려주고 멈춘다."""
    v = secret(name)
    if v:
        return v
    raise SystemExit(
        f"{name} 가 없다. 둘 중 하나로 준다:\n"
        f"  ① {secrets_path()} 에\n"
        f"       {name}=여기에키\n"
        "     (`.local/` 은 gitignore 라 커밋되지 않는다. 권한은 600 으로)\n"
        f"  ② {name}=... 로 환경변수\n"
        f"  ⓘ {how}"
    )

def _build_tag():
    """빌드 산출물을 가르는 꼬리표 — 기본은 **현재 git 브랜치**다.

    ⚠ 한 이미지로 여러 갈래를 동시에 보긴 어렵다(ED1 QA 를 도는 사이 ED2 빌드가 덮어쓴다).
    그래서 `work/build/<꼬리표>/` 로 칸을 나눈다 — **도구는 하나도 안 고쳐도 된다.**
    열몇 개가 `BUILD_DIR` 밑의 파일명을 박아 쓰는데, 디렉터리만 갈리면 그대로 따라온다.

    `ED_BUILD_TAG` 로 덮어쓴다(브랜치와 무관한 실험용). 브랜치를 못 읽으면 `local`.

    ⚠ **워크트리에서는 `.git` 이 디렉터리가 아니라 파일**이다(`gitdir: …` 한 줄). 그대로
    `.git/HEAD` 를 열면 실패해 전부 `local` 로 떨어지는데, 갈래를 가르려고 만든 장치가
    **정작 갈래를 굴리는 자리에서만 안 도는** 꼴이 된다(2026-08-18 실측). 따라간다.
    """
    tag = os.environ.get("ED_BUILD_TAG")
    if not tag:
        git = os.path.join(ROOT, "..", "..", ".git")
        try:
            if os.path.isfile(git):  # 워크트리 — `gitdir: <실제 경로>`
                with open(git, encoding="utf-8") as f:
                    git = f.read().strip().split(":", 1)[1].strip()
            with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
                ref = f.read().strip()
            tag = ref.rsplit("/", 1)[-1] if ref.startswith("ref:") else ref[:7]
        except (OSError, IndexError):
            tag = "local"
    return "".join(c if (c.isalnum() or c in "-_.") else "-" for c in tag) or "local"


BUILD_TAG = _build_tag()
# 테스트 이미지(BIN/CUE) — 순수 출력. ⚠ **꼬리표별로 갈린다**(위 `_build_tag`).
BUILD_DIR = os.path.join(WORK_DIR, "build", BUILD_TAG)
OUT_DIR = os.path.join(WORK_DIR, "derived")  # 원본에서 파생 — ⚠ **빌드가 읽는다**(입력)
REVIEW_DIR = os.path.join(WORK_DIR, "review")  # 검토표·페이로드 — ⚠ 원문·정발 문안 포함
DIST_DIR = os.path.join(WORK_DIR, "dist")  # 배포 차분(xdelta/BPS) — 아직 미사용

ORIG_BIN = os.path.join(ORIG_DIR, "Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).bin")
ORIG_CUE = os.path.join(ORIG_DIR, "Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).cue")

# ── 원본 지문 — 이 덤프를 전제로 오프셋이 박혀 있다 ────────────────────────
# ⚠ **오프셋·LBA 가 전부 이 한 덤프에 결박돼 있다.** 다른 리비전·다른 지역판을 넣으면
# 조용히 엉뚱한 섹터를 고쳐 쓴다 — 실패하지 않고 **망가진 이미지가 나온다.** mcpads 패처들이
# README 에 체크섬 넷을 박고 CRC 가 다르면 경고 + 명시적 탈출구를 요구하는 이유가 이것이다.
# 해시는 저작물이 아니라 지문이라 커밋해도 된다(그쪽도 같은 관용).
SRC_SIZE = 252_498_960
SRC_CRC32 = "4BDCBF59"
SRC_MD5 = "7b7cf3a179cf65adbc62201808fbdd88"
SRC_SHA1 = "269032ba730f4dbe80b798a2c4c3b415e094f359"
SRC_SHA256 = "6270aaad9d35c0be4292f6aa10033a55c7e24c1ffbfb62277d54af6b44c2a15c"

SECTOR = 2352  # raw MODE2/2352
USER_OFF = 24  # sync(12)+header(4)+subheader(8) → Mode2 Form1 유저 데이터
USER_SIZE = 2048

# ED1SCN1.BIN (iso_files.txt) — 자주 쓰는 대상
ED1SCN1_LBA, ED1SCN1_SIZE = 1183, 206260
ED1SCN1_RAM_BASE = 0x8016A000  # 오버레이 로드 주소 (no$psx로 검증)


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


def verify_source(path=ORIG_BIN, strict=None):
    """원본이 오프셋을 박아 둔 그 덤프인지 확인한다.

    `strict` — None 이면 환경변수 `ALLOW_NONCANONICAL_SRC` 로 정한다(1 이면 경고만).
    ⚠ **크기부터 본다.** 크기가 다르면 해시를 안 재고 바로 실패해도 되고(241MB 읽기 절약),
    같으면 sha1 로 확정한다.
    """
    if strict is None:
        strict = os.environ.get("ALLOW_NONCANONICAL_SRC") != "1"
    n = os.path.getsize(path)
    bad = None
    if n != SRC_SIZE:
        bad = f"크기 {n:,} (기대 {SRC_SIZE:,})"
    else:
        got = digests(path)["sha1"]
        if got != SRC_SHA1:
            bad = f"sha1 {got} (기대 {SRC_SHA1})"
    if not bad:
        return True
    msg = (
        f"⚠ 원본이 정본 덤프와 다르다 — {bad}\n"
        f"  오프셋·LBA 가 전부 그 덤프에 결박돼 있어 **엉뚱한 자리를 고쳐 쓸 수 있다**.\n"
        f"  알고도 계속하려면 `ALLOW_NONCANONICAL_SRC=1`."
    )
    if strict:
        raise SystemExit(msg)
    print(msg)
    return False


def extract(lba, size, path=ORIG_BIN):
    """ISO 파일의 유저 데이터(2048/섹터)를 이어붙여 추출."""
    out = bytearray()
    with open(path, "rb") as f:
        for i in range((size + USER_SIZE - 1) // USER_SIZE):
            f.seek((lba + i) * SECTOR + USER_OFF)
            out += f.read(USER_SIZE)
    return bytes(out[:size])


# ── MIPS 절대주소 참조 스캐너 (lui+addiu/ori/lw 쌍) ──────────────────────────
# lui rt,hi 뒤 6워드 내에 rt를 rs로 쓰는 load/addiu가 오면 hi<<16 + lo로 주소 조립.
# addiu(0x09)·lw(0x23)는 lo 부호확장, ori(0x0D)는 안 함.
MIPS_LUI, MIPS_ADDIU, MIPS_ORI, MIPS_LW = 0x0F, 0x09, 0x0D, 0x23


MIPS_MEM_LOADS = frozenset((0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26))  # lb/lh/lwl/lw/lbu/lhu/lwr


def iter_lui_pairs(data, load_ops):
    """lui + (load_ops 중 하나) 쌍을 (imm_off, lui_off, op, addr)로 순회.

    메모리 로드가 레지스터를 덮어쓰면(예: `lw t0,..(t0)` 뒤 `addiu x,t0,imm`) 그
    레지스터의 lui 상위값이 무효가 되므로 페어링에서 제외 — 스테일 레지스터가
    우연한 텍스트 주소를 만들어 잘못 패치되는 것을 막는다. R-type 산술
    (`addu at,at,idx` 인덱싱)은 상위값을 보존하므로 무효화하지 않는다(점프 테이블 패턴).
    jal은 $ra만 덮으므로 베이스 레지스터에 무해."""
    words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data) - 3, 4)]
    recent_lui = {}
    for idx, w in enumerate(words):
        op = w >> 26
        if op == MIPS_LUI:
            recent_lui[(w >> 16) & 0x1F] = (idx, w & 0xFFFF)
            continue
        if op in load_ops:
            rs = (w >> 21) & 0x1F
            if rs in recent_lui:
                lui_idx, hi = recent_lui[rs]
                if idx - lui_idx <= 6:
                    lo = w & 0xFFFF
                    addr = (hi << 16) + (lo - 0x10000 if lo >= 0x8000 and op != MIPS_ORI else lo)
                    yield idx * 4, lui_idx * 4, op, addr
        if op in MIPS_MEM_LOADS:  # rt를 메모리값으로 재정의 → 상위값 소실
            recent_lui.pop((w >> 16) & 0x1F, None)


def edc_compute(data):
    """Mode2 Form1 EDC (subheader+data = 섹터 16~2071 대상, 2072에 LE 저장)."""
    edc = 0
    for b in data:
        edc ^= b
        for _ in range(8):
            edc = (edc >> 1) ^ (0xD8018001 if edc & 1 else 0)
    return edc


# ── Mode2 Form1 ECC (P/Q Reed-Solomon 패리티) ────────────────────────────────
# EDC만 고치고 ECC를 두면 에뮬은 넘어가지만(무시) **실기 CD 컨트롤러는 하드웨어 정정을
# 수행**해서, 스테일 패리티가 멀쩡한 유저 데이터를 "정정"해 오히려 깨뜨릴 수 있다.
# GF(2^8) 생성다항식 0x11D — ecm/cdrdao 표준 알고리즘.
_ECC_F = bytearray(256)  # i → i*2 (GF)
_ECC_B = bytearray(256)  # (i ^ i*2) → i (역룩업)
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
    """섹터(2352B bytearray)의 P(0x81C~)·Q(0x8C8~) 패리티를 제자리 재계산.

    Mode2는 헤더(12~15)를 0으로 두고 계산한다(ecc 대상 = 12~2075의 2064B)."""
    hdr = bytes(sec[12:16])
    sec[12:16] = b"\x00\x00\x00\x00"
    src = memoryview(sec)[12:]
    _ecc_block(src, 86, 24, 2, 86, sec, 0x81C)  # P
    _ecc_block(src, 52, 43, 86, 88, sec, 0x8C8)  # Q
    sec[12:16] = hdr


# ── 마크업 한 벌 ─────────────────────────────────────────────────────────────
# `{…}` 태그와 `\xNN` 이스케이프. **정본은 여기 하나다**(2026-08-29 통합).
# ⚠ 예전엔 여섯 파일이 사본을 들었고 그중 둘(`past_review_align`·`align_jp_kr`)은 **대문자
#   헥스만** 봤다(`[0-9A-F]`). 지금 덤프가 전부 대문자라 안 샜을 뿐, 덤퍼가 소문자를
#   내는 순간 그 둘만 조용히 갈린다 — 같은 규칙의 사본은 이렇게 갈린다.
MARKUP = re.compile(r"\{[^}]*\}|\\x[0-9A-Fa-f]{2}")


# ── 절대 안 바뀌어야 하는 구간 (파일 오프셋, 반열림) ──────────────────────
# 클리어 범위를 잘못 잡아 **남의 자료를 지우는** 사고를 잡는다(2026-08-02 실측:
# OPEN1 포인터 테이블 0x938~0x973 말소).
# mode: "bytes" = 통째로 동일 · "script" = 텍스트 포인터 슬롯만 예외(재packing 으로 정당히 바뀜)
IMMUTABLE = {
    # (LBA, 크기): [(이름, 시작, 끝, mode), …]
    (69, 96256): [
        ("OPEN1 포인터 테이블", 0x938, 0x974, "bytes"),
        ("OPEN1 ED2 오프닝 내레이션", 0xEF0, 0x1B14, "bytes"),
        ("OPEN1 표시 스크립트 커맨드", 0x145A0, 0x147BC, "script"),
    ],
}
TEXT_PTR = range(0x80010000, 0x80011000)  # "script" 모드에서 정당히 바뀌는 슬롯


def _guards():
    """[(lo, hi, 이름, mode)] — 유저데이터 **절대** 오프셋(lba*2048 + 파일 안쪽 오프셋)."""
    out = []
    for (lba, _size), regions in IMMUTABLE.items():
        base = lba * USER_SIZE
        out += [(base + a, base + b, name, mode) for name, a, b, mode in regions]
    return out


class WriteGuard(Exception):
    """무변경 구간을 바꾸려 했다 — 쓰기를 취소하고 그 자리에서 실패."""


def _check_guard(lo, old, new, label):
    """[lo, lo+len) 구간의 old→new 변경이 무변경 구간을 건드리는지."""
    for g_lo, g_hi, name, mode in _guards():
        a, b = max(lo, g_lo), min(lo + len(old), g_hi)
        if a >= b:
            continue
        for o in range(a - lo, b - lo):
            if old[o] == new[o]:
                continue
            if mode == "script":
                w = (o - (g_lo - lo)) & ~3  # 워드 정렬 (구간 기준)
                s = (g_lo - lo) + w
                if int.from_bytes(old[s : s + 4], "little") in TEXT_PTR:
                    continue  # 텍스트 포인터 슬롯 — 재packing 으로 정당히 바뀐다
            raise WriteGuard(
                f"무변경 구간 침범 — `{label}` 이 「{name}」 @0x{lo + o:X}"
                f"(유저데이터 절대) 를 {old[o]:02X}→{new[o]:02X} 로 바꾸려 했다"
            )


def write_user_data(f, lba, data, nsec=None, *, label, expect=None):
    """열린 r+b 파일 핸들의 lba부터 유저 데이터를 기록하고 EDC·ECC 재계산.

    `label` — 무엇을 쓰는지(필수). 가드에 걸렸을 때 **범인을 바로 알려면** 있어야 한다.
    `expect` — 쓰기 **사전 조건**. `bytes` 면 대상 범위의 현재 바이트가 정확히 그것이어야
        하고, `int` 면 전 범위가 그 바이트여야 한다(빈 공간 확인용).

    ⚠ **사후 대조로는 늦다.** `build.py` 가 빌드 끝에 원본과 byte 대조하지만, 그때는 이미
    이미지가 망가져 있고 누가 언제 지웠는지는 안 나온다. 그래서 mcpads 의 `TrackedRom`
    (SFC 마도물어 — 모든 쓰기가 라벨 + `Expect` 사전조건을 요구한다)을 이 통로에 옮겼다.
    ⚠ 가드는 **범위가 아니라 값 변화**를 본다 — 무변경 구간을 품은 파일을 통째로 다시 쓰는
    건(그 바이트를 그대로 되쓰는) 정상이라 범위로 막으면 오탐이 난다.

    ⚠ **여기서 지문을 남긴다** — 「쓰려 한 것」을 기록해야 나중에 되읽어 대조할 수 있다.
    빌드가 끝난 뒤 이미지를 다시 읽어도 **의도를 모르면 비교 대상이 없다**(실측: 층 하나만
    재현해 맞대 봤더니 19씬 전부 어긋났는데, 정작 원인은 뒤 단계의 고아 문자열·폰트였다).
    공용 QA 규약 §8.9 의 readback 이 요구하는 게 이 짝이다 — `check_readback.py`.

    반환: 실제로 바뀐 섹터 수."""
    if nsec is None:
        nsec = (len(data) + USER_SIZE - 1) // USER_SIZE
    WRITE_LOG.append({"lba": lba, "nsec": nsec, "label": label, "len": len(data)})
    for i in range(nsec):
        _c = bytes(data[i * USER_SIZE : (i + 1) * USER_SIZE]).ljust(USER_SIZE, b"\x00")
        WRITE_SECTORS[lba + i] = [hashlib.sha1(_c).hexdigest(), label]
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
        _check_guard((lba + i) * USER_SIZE, old, chunk, label)
        assert not (sec[18] & 0x20), f"섹터 {lba + i}는 Form2 — 대상 아님"
        sec[USER_OFF : USER_OFF + USER_SIZE] = chunk
        sec[2072:2076] = edc_compute(bytes(sec[16:2072])).to_bytes(4, "little")
        ecc_update(sec)
        f.seek(sec_base)
        f.write(sec)
        changed += 1
    return changed


WRITE_MANIFEST = None  # 늦게 채운다 — OUT_DIR 이 아래에서 정의된다


def _flush_write_log():
    """이 프로세스가 **쓰려 한 것**을 지문표에 덧붙인다 — 되읽기 대조의 기준.

    ⚠ **덧붙이기**여야 한다. 빌드는 패처들을 **자식 프로세스로** 돌리므로 프로세스마다
    자기 몫만 안다 — 덮어쓰면 마지막 패처 것만 남는다. 표를 비우는 건 `build.py` 몫이다.
    ⚠ 안 쓰는 도구(검사기)는 `WRITE_LOG` 가 비어 있어 아무것도 안 남긴다.
    """
    if not WRITE_SECTORS:
        return
    path = WRITE_MANIFEST or os.path.join(OUT_DIR, "write_manifest.json")
    old = {"sectors": {}, "writes": []}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            pass
    old["sectors"].update({str(k): v for k, v in WRITE_SECTORS.items()})
    old["writes"] += WRITE_LOG
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old, f)


atexit.register(_flush_write_log)


def write_cue(cue_path, bin_name):
    with open(cue_path, "w", encoding="ascii") as f:
        f.write(f'FILE "{bin_name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
