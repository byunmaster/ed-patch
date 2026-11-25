"""ps1-ed4 공용 — 경로·원본 지문·쓰기 통로. **상수와 얇은 래퍼만 둔다**(디스크 규격은 `shared/disc`·`shared/ps1`).

ED3 와 같은 GMF 엔진이라 아카이브·압축·섹터 쓰기는 공용(`shared.ps1.gmf_arc` · `shared.disc.mode2`)이 맡고,
여기에는 이 게임 것 — 원본 지문·작업 칸·무변경 구간 — 만 있다.
"""

import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # games/ps1-ed4
REPO = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, REPO)

from shared.build_tag import build_tag
from shared.disc import mode2
from shared.disc.guard import Guard
from shared.disc.iso9660 import MODE2_FORM1_USER_OFF, SECTOR, USER_SIZE, Disc

ARCHIVE_EXT = ".DAT"
EXE_PATH = "/SLPS_015.40"
EXE_HDR = 0x800  # PS-EXE 파일 머리 — 어떤 패치도 안 건드린다
EXE_TADDR = 0x80010000
LABEL = "Eiyuu Densetsu IV (KR)"

# ── 작업 칸 (`work/` 는 gitignore — 규칙은 루트 CLAUDE.md) ─────────────────────
WORK_DIR = os.path.join(ROOT, "work")
OUT_DIR = os.path.join(WORK_DIR, "derived")  # ⚠ 빌드가 **읽는** 입력
REVIEW_DIR = os.path.join(WORK_DIR, "review")  # ⚠ 원문 포함 — 커밋 금지
DIST_DIR = os.path.join(WORK_DIR, "dist")
# 🔴 꼬리표는 디스크(편) 기준이다 — 기본은 브랜치(`game/ps1-ed4` → `ps1-ed4`), 시험물은 `ED_BUILD_TAG=test-…`.
BUILD_TAG = build_tag()
BUILD_DIR = os.path.join(WORK_DIR, "build", BUILD_TAG)

# ── 원본 지문 — 오프셋·LBA 가 이 덤프에 결박돼 있다 (체크리스트 1) ──────────────
DISC_DIR = os.path.join(REPO, "originals", "jp", "ps1-ed4")
DISC_BIN = "Legend of Heroes IV, The - Akai Shizuku (Japan).bin"
DISC = {
    "size": 521_852_352,
    "crc32": "ABA2CAB1",
    "md5": "8ea48e0efa7e2a2dd823e2bd51e80224",
    "sha1": "26140482c805008e2aaf5523bc83b4d18d6b5ee0",
    "sha256": "194857afeecee2ded864c613da7f3161a9c90484f1c3bc02370dd29b2699a28f",
}


def orig_bin():
    return os.path.join(DISC_DIR, DISC_BIN)


def build_bin(suffix=""):
    return os.path.join(BUILD_DIR, f"{LABEL}{suffix}.bin")


def build_cue(suffix=""):
    return os.path.join(BUILD_DIR, f"{LABEL}{suffix}.cue")


def sha1_of(path, bufsize=1 << 22):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(bufsize):
            h.update(chunk)
    return h.hexdigest()


def verify_source(strict=None):
    """원본이 오프셋을 박아 둔 그 덤프인지 확인한다 (크기부터 → 같으면 sha1).

    `ALLOW_NONCANONICAL_SRC=1` 이 명시적 탈출구다(경고만 하고 통과).
    """
    if strict is None:
        strict = os.environ.get("ALLOW_NONCANONICAL_SRC") != "1"
    path = orig_bin()
    if not os.path.exists(path):
        raise SystemExit(f"원본 없음: {path}")
    n = os.path.getsize(path)
    if n != DISC["size"]:
        bad = f"크기 {n:,} (기대 {DISC['size']:,})"
    else:
        got = sha1_of(path)
        bad = None if got == DISC["sha1"] else f"sha1 {got} (기대 {DISC['sha1']})"
    if not bad:
        return True
    msg = (
        f"⚠ 원본이 정본 덤프와 다르다 — {bad}\n"
        f"  오프셋·LBA 가 그 덤프에 결박돼 있어 **엉뚱한 자리를 고쳐 쓸 수 있다**.\n"
        f"  알고도 계속하려면 `ALLOW_NONCANONICAL_SRC=1`."
    )
    if strict:
        raise SystemExit(msg)
    print(msg)
    return False


# ── 읽기 ────────────────────────────────────────────────────────────────────
def open_disc(path=None):
    """`with open_disc() as d:` — 원본(또는 `path` 의 이미지)을 MODE2 Form1 로 연다."""
    return Disc(path or orig_bin(), user_off=MODE2_FORM1_USER_OFF)


_FILES = {}


def iso_files(path=None):
    """{경로: (lba, size)} — 이미지의 파일 전량."""
    key = path or orig_bin()
    if key not in _FILES:
        with open_disc(key) as d:
            _FILES[key] = {p: (lba, sz) for p, lba, sz in d.files()}
    return _FILES[key]


def read_file(path_in_iso, image=None):
    lba, size = iso_files(image)[path_in_iso]
    with open_disc(image) as d:
        return d.read_extent(lba, size)


def dir_records(image=None):
    """{경로: (디렉터리 섹터 lba, 섹터 안 오프셋)} — 재배치로 파일 크기가 바뀔 때 디렉터리 레코드를 고치는 자리.

    공용 `Disc` 가 아직 이 위치를 안 낸다(공용 후보 — 둘째 소비자가 생기면 올린다).
    """
    out = {}
    with open_disc(image) as d:
        pvd = d.pvd()
        root = pvd[156 : 156 + 34]

        def walk(lba, size, prefix, depth):
            data = d.read_extent(lba, size)
            pos = 0
            while pos < len(data):
                ln = data[pos]
                if ln == 0:
                    pos = (pos // USER_SIZE + 1) * USER_SIZE
                    continue
                rec = data[pos : pos + ln]
                name = rec[33 : 33 + rec[32]]
                at = pos
                pos += ln
                if name in (b"\x00", b"\x01"):
                    continue
                full = f"{prefix}/{name.decode('ascii', 'replace').split(';')[0]}"
                if rec[25] & 2:
                    if depth < 8:
                        walk(
                            int.from_bytes(rec[2:6], "little"),
                            int.from_bytes(rec[10:14], "little"),
                            full,
                            depth + 1,
                        )
                else:
                    out[full] = (lba + at // USER_SIZE, at % USER_SIZE)

        walk(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "", 0)
    return out


# ── 쓰기 — 통로는 하나(`write_user_data`), 무변경 구간은 거기서 즉시 막는다 (체크리스트 2) ──
GUARD = Guard()


def write_user_data(f, lba, data, *, label, expect=None):
    return mode2.write_user_data(f, lba, data, label=label, expect=expect, guard=GUARD)


def set_file_size(f, dir_lba, at, new_size, *, label):
    return mode2.set_file_size(f, dir_lba, at, new_size, label=label, guard=GUARD)


def declare_immutable():
    """이 게임이 어떤 빌드에서도 안 바꾸는 구간 — PS-EXE 머리(진입점·크기)."""
    lba, size = iso_files()[EXE_PATH]
    GUARD.add(lba, size, [("PS-EXE 헤더", 0, EXE_HDR, "fixed")])


def write_manifest(out, kind):
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "disc": "ed4",
                "kind": kind,
                "out": os.path.basename(out),
                "sha1": sha1_of(out),
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            f,
            ensure_ascii=False,
            indent=1,
        )


def sectors(n):
    return (n + USER_SIZE - 1) // USER_SIZE


__all__ = ["SECTOR", "USER_SIZE"]
