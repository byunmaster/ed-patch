"""파일을 **꼬리 섹터까지** 늘려 넣을 자리를 만든다 — LBA 는 안 건드린다.

    python3 tools/expand_files.py            # 계획·검산만
    python3 tools/expand_files.py --apply    # 빌드 이미지의 ISO 디렉터리를 고친다

⚠ 순서상 **자막 바로 다음**이다 — 뒤 패처들이 늘어난 크기를 보고 자리를 잡는다.

## 왜 필요한가

`/BIN/ED2MON*.BIN` 은 꽉 차 있어 재배치할 0런이 **사실상 0**(ED2MON01·02 는 0바이트).
그래서 출현 문구 19줄이 자리에 못 들어갔다(2026-08-27). 본편 대사(44.5만 자)까지 가면
훨씬 크게 모자란다.

## 공짜 여유가 이미 디스크에 있다

CD 는 **섹터(유저 2048B) 단위**로 파일을 놓는다. 파일 크기가 섹터 배수가 아니면 마지막
섹터의 나머지는 **아무도 안 쓴다** — 실측 648~1832B/파일, ED2MON 열 파일 합쳐 ~11KB.

    ED2MON01  0x5410(21,520B) → 11섹터(22,528B)  ⇒ 꼬리 1,008B 놀고 있다

**LBA 를 안 바꾼다.** 다음 파일이 이미 그 다음 섹터에서 시작하므로(실측으로 확인한다)
크기 필드만 늘리면 겹치지 않는다. ISO 재빌드도, 뒤 파일 밀기도 필요 없다.

## 🔴 안전 조건 셋 — 전부 **코드로 검산한다**

체크리스트 10 「0 으로 차 있다고 빈 공간이 아니다」를 거꾸로 읽은 자리다. 여기 꼬리는
**게임이 아예 안 읽던 영역**이다(파일 크기 밖). 우리가 크기를 늘려야 비로소 읽는다.
그래서 위험은 「남의 자료를 덮나」가 아니라 **「적재된 뒤 남의 메모리를 밟나」**다.

1. **디스크에서 안 겹친다** — 다음 파일 LBA ≥ 우리 LBA + 새 섹터 수.
2. **적재해도 안 밟는다** — 같은 주소에 올라가는 파일군의 **최대 원본 크기**를 넘지 않는다.
   그만큼은 **원판도 이미 올린다**(그 파일이 정상 동작한다) → 뒤가 비어 있다는 증거다.
3. **크기가 코드에 안 박혀 있다** — 박혀 있으면 늘려도 그만큼만 읽는다. ED·ED2 본체를
   훑어 크기(4B)·섹터 수 상수가 **0회**임을 확인한다(실측 2026-08-27).

⚠ 늘린 꼬리는 **0 으로 채운다.** 원본 잔재가 남으면 문자열 스캔이 헛것을 잡는다.
"""

import itertools
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import dump_scn

# 늘릴 파일군 — (패턴, 그 파일들이 올라가는 주소). 같은 주소면 「최대 원본 크기」가 상한이다.
GROUPS = [re.compile(r"^/BIN/ED2MON\d+\.BIN$")]
USER = common.USER_SIZE


def dir_records(mm):
    """`{경로: (레코드 오프셋(디렉터리 익스텐트 안), 디렉터리 LBA, LBA, 크기)}`.

    ⚠ `common.iso_files` 는 목록만 준다 — **고치려면 레코드가 어디 있는지**를 알아야 한다.
    """
    pvd = common.sector_user(mm, 16)
    assert pvd[0] == 1 and pvd[1:6] == b"CD001", "PVD 시그니처 불일치"
    root = pvd[156 : 156 + 34]
    out = {}
    _walk(
        mm, int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "", out, 0
    )
    return out


def _walk(mm, lba, size, path, out, depth):
    if depth > 8:
        return
    data = common.read_extent(mm, lba, size)
    pos = 0
    while pos < len(data):
        rec_len = data[pos]
        if rec_len == 0:
            pos = (pos // USER + 1) * USER
            continue
        rec = data[pos : pos + rec_len]
        ext_lba = int.from_bytes(rec[2:6], "little")
        ext_size = int.from_bytes(rec[10:14], "little")
        flags = rec[25]
        name = rec[33 : 33 + rec[32]]
        at = pos
        pos += rec_len
        if name in (b"\x00", b"\x01"):
            continue
        full = f"{path}/{name.decode('ascii', 'replace').split(';')[0]}"
        if flags & 0x02:
            _walk(mm, ext_lba, ext_size, full, out, depth + 1)
        else:
            out[full] = (at, lba, size, ext_lba, ext_size)


def plan(mm):
    """`[(경로, 레코드자리, 디렉터리(lba,size), LBA, 원 크기, 새 크기)]` — 안전 조건을 검산한다."""
    files = common.iso_files(mm)
    recs = dir_records(mm)
    lbas = sorted({lba for _p, lba, _s in files})
    nxt = dict(itertools.pairwise(lbas))
    out = []
    for pat in GROUPS:
        grp = [(p, lba, size) for p, lba, size in files if pat.match(p)]
        assert grp, f"패턴에 걸리는 파일이 없다: {pat.pattern}"
        cap = max(size for _p, _l, size in grp)  # ② 원판도 이 크기까지는 올린다
        for p, lba, size in grp:
            sectors = -(-size // USER)
            room = sectors * USER
            new = min(room, cap)
            if new <= size:
                continue
            # ① 디스크에서 안 겹친다
            after = nxt.get(lba)
            assert after is None or lba + sectors <= after, (
                f"{p}: LBA {lba}+{sectors} 가 다음 파일 {after} 를 침범한다"
            )
            at, dlba, dsize, elba, esize = recs[p]
            assert (elba, esize) == (lba, size), f"{p}: 디렉터리 레코드가 목록과 다르다"
            out.append((p, at, (dlba, dsize), lba, size, new))
    return out


def check_not_hardcoded(hosts=("/ED.BIN", "/ED2.BIN")):
    """③ 크기·섹터 수가 코드에 박혀 있으면 늘려도 소용없다 — 0회여야 한다."""
    _f, mm = common.open_image()
    sizes = {size for p, _l, size in common.iso_files(mm) if any(g.match(p) for g in GROUPS)}
    mm.close()
    _f.close()
    bad = []
    for host in hosts:
        d = bytes(common.extract(host))
        for size in sizes:
            for val, w in ((size, 4), (-(-size // USER), 4)):
                if val > 0xFFFF and d.count(val.to_bytes(w, "big")):
                    bad.append((host, val))
    assert not bad, f"크기·섹터 수가 코드에 박혀 있다: {bad}"


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    check_not_hardcoded()
    _f, mm = common.open_image()
    rows = plan(mm)
    total = sum(new - old for *_x, old, new in rows)
    for p, _at, _d, lba, old, new in rows:
        print(f"  {p}: 0x{old:X} → 0x{new:X}  (+{new - old}B · LBA {lba} 그대로)")
    print(f"  파일 {len(rows)}개 · 확보 {total}B")
    if not apply:
        mm.close()
        _f.close()
        print("  (계산만 — 실제로 넣으려면 `--apply`)")
        return

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")
    _fd, mmd = common.open_image(dst)
    cur = {
        p: bytes(common.read_extent(mmd, d[0], d[1])[at + 10 : at + 18]) for p, at, d, *_ in rows
    }
    mmd.close()
    _fd.close()
    with open(dst, "r+b") as f:
        for p, at, (dlba, dsize), lba, old, new in rows:
            # ⚠ **다시 돌려도 돌아야 한다** — 사전조건은 「원 크기이거나 이미 새 크기」다.
            want = struct.pack("<I", new) + struct.pack(">I", new)  # ISO9660 both-endian
            was = struct.pack("<I", old) + struct.pack(">I", old)
            assert cur[p] in (was, want), f"{p}: 크기 필드가 원본도 우리 것도 아니다"
            common.write_at(
                f, dlba, dsize, at + 10, want, label=f"{p} 크기 {old}→{new}", expect=cur[p]
            )
            # ⚠ 늘린 꼬리는 0 으로 — 원본 잔재가 남으면 문자열 스캔이 헛것을 잡는다
            common.write_at(f, lba, new, old, b"\x00" * (new - old), label=f"{p} 꼬리 비우기")
    verify(dst, rows)
    mm.close()
    _f.close()


def verify(dst, rows):
    """되읽기 — 크기가 그대로 들어갔고 꼬리가 0 인가."""
    _f2, mm2 = common.open_image(dst)
    got = {p: (lba, size) for p, lba, size in common.iso_files(mm2)}
    for p, _at, _d, lba, old, new in rows:
        assert got[p] == (lba, new), f"{p}: 되읽기 {got[p]} ≠ ({lba}, {new})"
        d = common.read_extent(mm2, lba, new)
        assert not any(d[old:new]), f"{p}: 늘린 꼬리가 0 이 아니다"
    print(f"  ✅ 되읽기 확장 {len(rows)}개 (LBA 불변 · 꼬리 0)")
    mm2.close()
    _f2.close()


def tails(mm):
    """`{경로: (원 크기, 새 크기)}` — 늘어난 꼬리를 **쓸 자리로 아는 쪽**이 이걸 본다."""
    return {p: (old, new) for p, _at, _d, _l, old, new in plan(mm)}


def load_base(path):
    """그 파일의 적재 주소 — 안전 조건 ②의 근거."""
    return dump_scn.base_for(os.path.basename(path))


if __name__ == "__main__":
    main()
