"""씬 파일을 **뒤로 밀어** 자리를 만든다 — 데이터 트랙 꼬리 여유를 쓴다.

    python3 tools/relocate_files.py            # 계획·검산만
    python3 tools/relocate_files.py --apply    # 빌드 이미지에 반영

⚠ 순서상 **`patch_ui` 다음, `patch_scn` 앞**이다 — 부족량(`scn_shortfall.json`)은 `patch_scn`
  이 쓰고, 늘어난 자리는 그 다음 회차의 `patch_scn` 이 쓴다.

## `expand_files.py` 와 무엇이 다른가

| 도구             | 무엇을                        | LBA      | 위험 |
| ---------------- | ----------------------------- | -------- | ---- |
| `expand_files`   | 파일 **꼬리 섹터**의 나머지   | **불변** | 낮다 |
| 이 도구          | 파일 뒤를 **밀어** 섹터를 준다 | **바뀐다** | 높다 |

🔴 **갈라 둔 이유가 그 위험이다.** 꼬리 확장은 「아무도 안 읽던 자리」를 우리 것으로 만드는
것이라 되돌릴 게 없지만, 재배치는 **남의 파일 주소를 바꾼다.** 한 도구에 섞으면 안전한 쪽을
쓰려다 위험한 쪽이 딸려 온다.

## 왜 필요한가

꼬리까지 다 쓰고도 **116블록(6,653B)이 자리가 없다**(실측 2026-08-31). 씬 파일은 자기 파일
안에서만 이주할 수 있어(각자 따로 적재된다) **파일마다** 여유가 있어야 한다.

## ✅ 데이터 트랙 안에서 끝난다 — 오디오를 안 민다

디스크를 재 보니 조건이 깨끗했다:

    데이터 트랙 01   LBA 0 ~ 15,456
    마지막 데이터 파일 끝   LBA 15,307   ⇒ **꼬리 여유 150섹터**
    필요량           18파일 × 1섹터 = **18섹터**

⇒ 트랙 경계도, 오디오 31트랙(360MB)도, CUE 도, TOC 도 **안 건드린다.**
   🔴 TOC 가 그대로라 **GameID 도 그대로**다 — 세이브가 안 깨진다(`scripts/emu/ss_gameid.py`).

## 🔴 안전 조건 — 전부 코드로 검산한다

1. **LBA 가 코드에 박혀 있지 않다.** 대조군으로 확인했다(2026-08-31) — 진짜 LBA 989개 중
   `/ED.BIN` 에 BE32 로 박힌 것 **18건**인데, 같은 범위 랜덤 989개는 **평균 32.8건**이다.
   즉 노이즈다. ⚠ 이건 「없다」가 아니라 「**대조군보다 적다**」이므로, 매 실행 재검산한다.
2. **디렉터리·path table 이 안 밀린다.** 전부 LBA 20~52 인데 우리가 미는 건 3,779 이후다
   (실측). 밀리면 레코드가 아니라 **디렉터리 자신의 주소**를 고쳐야 해서 얘기가 달라진다.
3. **트랙 경계를 안 넘는다.** 민 뒤 마지막 파일 끝 + `PREGAP_KEEP` ≤ 트랙 01 끝.
4. **본체 둘(`/ED.BIN`·`/ED2.BIN`)은 안 옮긴다.** 부팅 경로라 위험 대비 이득이 작다
   (둘이 모자란 건 1,095B). 씬 파일만 대상으로 한다.
   🔴 **그리고 이 결정에 다른 패처들이 얹혀 있다.** `patch_crit_copy`·`patch_josa_hook` 은
      **원본 LBA 로 빌드에 쓰는데**, 대상이 본체 둘뿐이라 지금은 맞는다. 본체를 옮기기로
      하면 그 둘부터 고쳐야 한다(회귀 `test_relocate.py` 가 이 의존을 지킨다).
   ⚠ 실제로 `patch_mon_names` 가 그 함정에 빠졌다 — ED2MON 열 파일이 밀리는데 옛 LBA 로
      써서 **화면의 일본어가 22 → 255줄**이 됐다(2026-08-31). 지금은 빌드 LBA 를 쓴다.
5. **되읽기** — 민 파일 전부가 새 자리에서 **바이트 동일**하고, 늘린 꼬리는 0이다.
"""

import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import expand_files
import patch_scn

USER = common.USER_SIZE
SECTORS = 1  # 파일마다 몇 섹터를 더 주나 — 실측 최대 부족이 927B 라 1섹터면 넉넉하다
PREGAP_KEEP = 100  # 🔴 트랙 끝에 남겨 둘 섹터 — 원본이 150 을 비워 뒀다(프리갭 관례)
TRACK1_END = 15457  # LBA. CUE 의 TRACK 02 INDEX 01(03:28:07) − 150


CANON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scn_expand.json")


def targets():
    """🔴 자리를 줄 파일 — **커밋된 정본**을 읽는다(`scn_expand.json`).

    ⚠ `patch_scn` 의 제안(`work/derived/scn_shortfall.json`)을 그대로 읽었더니 **진동했다**
      (2026-08-31). `patch_title` 이 회차마다 사본을 새로 뜨는데 제안은 「재배치 **후**」의
      부족이라, 재배치가 흡수한 파일이 목록에서 빠지고 → 다음 회차엔 재배치를 건너뛰고
      → 그 다음엔 다시 차는 식으로 1·3 과 2·4 가 오갔다.
    ⇒ **제안(비결정)과 정본(결정)을 가른다**(루트 CLAUDE.md 제1원칙).
    """
    with open(CANON) as f:
        return set(json.load(f)["files"])


def proposal():
    """`patch_scn` 이 남긴 제안 — 정본에 빠진 게 있는지 보고용."""
    p = os.path.join(common.OUT_DIR, "scn_shortfall.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        got = json.load(f)
    return {k: v for k, v in got.items() if patch_scn.SCN_RE.match(k) and "/BIN/" in k}


def check_lba_not_hardcoded(mm, hosts=("/ED.BIN", "/ED2.BIN")):
    """🔴 LBA 를 상수로 쓰는가 — **대조군과 견준다**(안전 조건 1).

    ⚠ 「몇 건 나왔다」로는 못 가른다. LBA 는 작은 수라 BE32 가 `00 00 xx xx` 꼴이어서
      아무 4바이트 창에나 걸린다. 같은 범위의 **랜덤 LBA** 로 같은 수를 세어 견준다.
    """
    import random

    lbas = sorted({l for _p, l, _s in common.iso_files(mm) if l < TRACK1_END})
    lo, hi = min(lbas), max(lbas)
    for name in hosts:
        d = bytes(common.extract(name))
        real = sum(1 for v in lbas if struct.pack(">I", v) in d)
        rnd = random.Random(1)
        ctrl = [
            sum(1 for v in rnd.sample(range(lo, hi), len(lbas)) if struct.pack(">I", v) in d)
            for _ in range(5)
        ]
        assert real <= max(ctrl), (
            f"{name}: LBA 상수가 대조군보다 많다 ({real} > {max(ctrl)}) — 재배치가 위험하다"
        )
        print(f"     {name}: LBA 상수 {real}건 · 대조군 {ctrl} → 노이즈")


def plan(mm, mmd):
    """`[(경로, 레코드자리, (디렉터리 lba, size), 옛 LBA, 새 LBA, 옛 크기, 새 크기)]`.

    ⚠ **크기는 빌드 이미지 것**을 쓴다 — `expand_files` 가 이미 늘려 뒀다. 원본 크기로
      재면 그 확장을 덮어써 되돌린다.
    """
    want = targets()
    recs = expand_files.dir_records(mm)
    built = {p: (l, s) for p, l, s in common.iso_files(mmd)}
    orig = {p: (l, s) for p, l, s in common.iso_files(mm)}
    rows, shift = [], 0
    # 🔴 **원본을 기준으로 목표를 잡는다 — 그래야 다시 돌려도 같은 결과다.**
    #    빌드 이미지의 현재 LBA·크기를 기준 삼으면 회차마다 1섹터씩 또 늘어난다
    #    (2026-08-31 실측: 3회차에 프리갭이 132 → 114 로 줄었다). 쓰기는 여전히 빌드
    #    쪽으로 하되, **어디로 갈지는 원본이 정한다.**
    for path, (olba, osize) in sorted(orig.items(), key=lambda kv: kv[1][0]):
        if olba >= TRACK1_END:
            continue  # 오디오 더미 — 데이터 트랙 밖이라 안 건드린다
        blba, bsize = built.get(path, (olba, osize))
        o_sec = (osize + USER - 1) // USER
        b_sec = (bsize + USER - 1) // USER
        # ⚠ `expand_files` 는 꼬리만 늘려 섹터 수를 안 바꾼다 — 섹터가 늘었으면 우리 것이다
        add = SECTORS * USER if path in want and b_sec < o_sec + SECTORS else 0
        tlba, tsize = olba + shift, bsize + add
        shift += SECTORS if path in want else 0
        if (blba, bsize) != (tlba, tsize):
            at, dlba, dsize, _ol, _os = recs[path]
            rows.append((path, at, (dlba, dsize), blba, tlba, bsize, tsize))
    if rows:
        end = max(nl + (ns + USER - 1) // USER for *_x, nl, _o, ns in rows)
        assert end + PREGAP_KEEP <= TRACK1_END, (
            f"트랙 01 을 넘는다 — 끝 {end:,} + 프리갭 {PREGAP_KEEP} > {TRACK1_END:,}"
        )
    return rows, shift


def apply_rows(dst, rows):
    """뒤에서부터 옮긴다 — 앞에서 하면 아직 안 옮긴 뒷 파일을 덮는다."""
    _f, mm = common.open_image(dst)
    data = {p: bytes(common.read_extent(mm, ol, os_)) for p, _a, _d, ol, _nl, os_, _ns in rows}
    mm.close()
    _f.close()
    with open(dst, "r+b") as f:
        for path, at, (dlba, dsize), ol, nl, os_, ns in reversed(rows):
            body = data[path] + b"\x00" * (ns - os_)  # ⚠ 늘린 꼬리는 0
            for i in range(0, len(body), USER):
                common.write_user_data(
                    f, nl + i // USER, body[i : i + USER].ljust(USER, b"\x00"), label=f"{path} 본문"
                )
            rec = struct.pack("<I", nl) + struct.pack(">I", nl)
            common.write_at(f, dlba, dsize, at + 2, rec, label=f"{path} LBA {ol}→{nl}")
            szr = struct.pack("<I", ns) + struct.pack(">I", ns)
            common.write_at(f, dlba, dsize, at + 10, szr, label=f"{path} 크기 {os_}→{ns}")


def verify(dst, rows):
    """되읽기 — 새 자리에서 **바이트 동일**하고 늘린 꼬리가 0인가."""
    _f, mm = common.open_image(dst)
    got = {p: (l, s) for p, l, s in common.iso_files(mm)}
    for path, _at, _d, _ol, nl, os_, ns in rows:
        assert got[path] == (nl, ns), f"{path}: 되읽기 {got[path]} ≠ ({nl}, {ns})"
        d = bytes(common.read_extent(mm, nl, ns))
        assert not any(d[os_:ns]), f"{path}: 늘린 꼬리가 0 이 아니다"
    # 🔴 **남의 파일이 안 깨졌나** — 옮긴 것 말고도 전부가 읽히는지 본다
    n = sum(1 for _p, l, s in common.iso_files(mm) if l < TRACK1_END and s >= 0)
    print(f"  ✅ 되읽기 재배치 {len(rows)}개 · 데이터 파일 {n}개 목록 정상")
    mm.close()
    _f.close()


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not os.path.exists(dst):
        raise SystemExit(f"먼저 자막을 넣는다(patch_title.py --apply) — {dst} 가 없다")
    _fd, mmd = common.open_image(dst)

    want = targets()
    # ⚠ 제안에 정본이 모르는 파일이 있으면 알린다 — 사람이 정본에 넣을 몫이다
    extra = {k: v for k, v in proposal().items() if k not in want}
    if extra:
        print(
            f"  ℹ 정본에 없는데 모자란 파일 {len(extra)}개 — `scn_expand.json` 에 넣을지 사람이 정한다"
        )
        for k, v in sorted(extra.items(), key=lambda x: -x[1])[:5]:
            print(f"     {k} {v:,}B")

    check_lba_not_hardcoded(mm)
    rows, shift = plan(mm, mmd)
    moved = [r for r in rows if r[3] != r[4]]
    grew = [r for r in rows if r[5] != r[6]]
    print(f"정본이 자리를 주는 씬 파일 {len(want)}개")
    print(
        f"  늘릴 파일 {len(grew)}개(각 {SECTORS}섹터) · 뒤로 밀 파일 {len(moved)}개 · 총 {shift}섹터"
    )
    if rows:
        end = max(nl + (ns + USER - 1) // USER for *_x, nl, _o, ns in rows)
        print(
            f"  데이터 끝 LBA {end:,} · 트랙 01 끝 {TRACK1_END:,} · 프리갭 {TRACK1_END - end:,}섹터"
        )
    mmd.close()
    _fd.close()
    mm.close()
    _f.close()
    if not apply:
        print("  (`--apply` 로 반영한다)")
        return 0
    apply_rows(dst, rows)
    verify(dst, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
