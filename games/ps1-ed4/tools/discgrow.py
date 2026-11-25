"""디스크 늘리기 — **슬랙을 넘는 아카이브를 이미지 끝으로 옮긴다**(번역이 원문보다 길어 아카이브가 섹터를 넘길 때).

왜: 대본 아카이브는 디스크에서 다음 파일과 맞붙어 있어 섹터 수를 못 늘린다(`gmf_arc.plan` 이 「섹터가 늘어난다」로 멈춘다). 한국어는 같은 뜻에 코드가 더 든다
(음절 단위 · 일본어 한자는 한 글자가 낱말 하나). 그래서 슬랙을 넘는 아카이브는 **새 LBA(이미지 끝)에 통째로 다시 쓰고** ISO 디렉터리 레코드의 위치·크기와
볼륨 크기(PVD)만 고친다. 옛 자리는 그대로 남는다(안 읽힌다). 실행파일이 LBA 를 박아 두지 않고 디렉터리로 파일을 찾는다는 전제 — 시험 빌드로 확인한다(`ED_FORCE_MOVE`).

    plan_moves(fs, arcs)                      # {경로: 새 LBA} — 늘어난 것만, 경로 순으로 이미지 끝부터 차례로
    apply(f, moves, arcs, fs, dirpos)         # 열린 `r+b` 이미지에 새 섹터를 덧붙이고 디렉터리·PVD 를 고친다

🔴 이 모듈이 바꾸는 곳: 덧붙인 섹터 · 해당 파일의 디렉터리 레코드 섹터 · PVD(섹터 16). 그 밖은 안 건드린다(`build.verify_image` 가 센다).
"""

import os
import struct

import common

from shared.disc import mode2
from shared.ps1 import gmf_arc

SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def _bcd(n):
    return ((n // 10) << 4) | (n % 10)


def _msf(lba):
    t = lba + 150
    return bytes([_bcd(t // 4500), _bcd(t // 75 % 60), _bcd(t % 75)])


def repack_grow(data, replacements):
    """`gmf_arc.repack` 와 같되 **섹터 수가 늘어도 된다**(슬랙 검사 없음) — (새 바이트열, 계획).

    ⚠ 임시 사본이다: 공용 `gmf_arc.plan/repack` 에 `allow_grow` 가 들어오면(shared-draft4) 이 함수를 걷는다.
    멤버를 원래 순서로 4바이트 정렬해 이어 붙이고 TOC 의 위치·크기만 고친다. 안 바뀐 멤버는 바이트 그대로.
    """
    unit, ents = gmf_arc.arc_parse(data)
    if unit != gmf_arc.UNIT:
        raise gmf_arc.PackError(f"오프셋 단위 {unit} — 이 도구는 {gmf_arc.UNIT}B 단위만 안다")
    sizes = {n: max(sz, len(replacements[n])) if n in replacements else sz for n, _, sz in ents}
    first = ents[0][1]
    out = bytearray(data[:first])
    new_ents = []
    for n, off, sz in ents:
        body = replacements.get(n)
        if body is None:
            body = data[off : off + sz]
        keep = sizes[n]
        out += b"\x00" * (-len(out) % gmf_arc.UNIT)
        new_ents.append((n, len(out), keep))
        out += bytes(body).ljust(keep, b"\x00")
    out += b"\x00" * (-len(out) % gmf_arc.SECTOR_DATA)  # 마지막 섹터까지 0 채움
    for i, (_n, off, keep) in enumerate(new_ents):
        out[i * 32 + 20 : i * 32 + 28] = struct.pack("<II", off // gmf_arc.UNIT, keep)
    out = bytes(out)
    u1, e1 = gmf_arc.arc_parse(out)
    if u1 != unit or [n for n, _, _ in e1] != [n for n, _, _ in ents]:
        raise gmf_arc.PackError("재배치 뒤 멤버 목록·단위가 달라졌다")
    for (n, o0, s0), (_, o1, s1) in zip(ents, e1, strict=True):
        got = out[o1 : o1 + s1]
        want = (
            bytes(replacements[n]).ljust(s1, b"\x00") if n in replacements else data[o0 : o0 + s0]
        )
        if got != want:
            raise gmf_arc.PackError(f"{n}: 재배치 뒤 되읽은 멤버가 다르다")
    return out, {"grow": len(out) - len(data)}


def image_sectors():
    return os.path.getsize(common.orig_bin()) // common.SECTOR


def plan_moves(fs, arcs):
    """{경로: 새 LBA} — `arcs`(경로 → 새 바이트열) 중 원래 섹터 수를 넘는 것. 이미지 끝에서부터 경로 순으로 이어 붙인다(결정적).

    `ED_FORCE_MOVE=/O/SC400.DAT,…` 는 **시험용** — 안 넘는 아카이브도 옮겨 「실행파일이 디렉터리로 파일을 찾는가」를 본다.
    """
    force = {p for p in os.environ.get("ED_FORCE_MOVE", "").split(",") if p}
    nxt = image_sectors()
    out = {}
    for path in sorted(arcs):
        _lba, osize = fs[path]
        if path in force or common.sectors(len(arcs[path])) > common.sectors(osize):
            out[path] = nxt
            nxt += common.sectors(len(arcs[path]))
    return out


def _template(f, lba):
    """파일 첫 섹터의 서브헤더(8B) — 새 섹터가 같은 규격(파일 번호·채널·Form1 데이터)을 갖게 한다."""
    f.seek(lba * common.SECTOR + 16)
    return f.read(8)


def append_extent(f, lba, data, sub):
    """`lba`(이미지 끝)부터 `data` 를 Form1 섹터로 덧붙인다. 마지막 섹터는 EOF·EOR 를 켠다(원본의 끝 섹터와 같은 꼴). 반환 = 섹터 수."""
    n = common.sectors(len(data))
    f.seek(lba * common.SECTOR)
    for i in range(n):
        chunk = bytes(data[i * common.USER_SIZE : (i + 1) * common.USER_SIZE]).ljust(
            common.USER_SIZE, b"\x00"
        )
        s = bytearray(common.SECTOR)
        s[:12] = SYNC
        s[12:15] = _msf(lba + i)
        s[15] = 2
        sh = bytearray(sub)
        if i == n - 1:
            sh[2] |= 0x81  # EOF · EOR
            sh[6] |= 0x81
        s[16:24] = sh
        s[24 : 24 + common.USER_SIZE] = chunk
        mode2.sector_fix(s)
        f.write(s)
    return n


def repoint(f, dir_lba, at, new_lba, new_size, *, label):
    """디렉터리 레코드(`dir_lba` 섹터의 `at`)의 파일 위치(LE·BE)와 크기(LE·BE)를 고친다."""
    sec = bytearray(mode2.read_user_data(f, dir_lba, common.USER_SIZE))
    if sec[at] < 34:
        raise ValueError(f"{label}: 디렉터리 레코드가 아니다 (@{at})")
    sec[at + 2 : at + 6] = struct.pack("<I", new_lba)
    sec[at + 6 : at + 10] = struct.pack(">I", new_lba)
    sec[at + 10 : at + 14] = struct.pack("<I", new_size)
    sec[at + 14 : at + 18] = struct.pack(">I", new_size)
    return common.write_user_data(f, dir_lba, bytes(sec), label=label)


def set_volume_size(f, total):
    """PVD(섹터 16)의 볼륨 공간 크기(오프셋 80, LE·BE)."""
    sec = bytearray(mode2.read_user_data(f, 16, common.USER_SIZE))
    sec[80:84] = struct.pack("<I", total)
    sec[84:88] = struct.pack(">I", total)
    return common.write_user_data(f, 16, bytes(sec), label="PVD 볼륨 크기")


def apply(f, moves, arcs, fs, dirpos):
    """이미지에 새 자리를 덧붙이고 디렉터리·PVD 를 고친다. 반환 = (덧붙인 섹터 수, 고친 섹터 수)."""
    if not moves:
        return 0, 0
    appended = fixed = 0
    end = image_sectors()
    for path in sorted(moves):
        lba, _osize = fs[path]
        appended += append_extent(f, moves[path], arcs[path], _template(f, lba))
        fixed += repoint(
            f, *dirpos[path], moves[path], len(arcs[path]), label=f"{path} 디렉터리(이동)"
        )
    fixed += set_volume_size(f, end + appended)
    return appended, fixed
