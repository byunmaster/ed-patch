"""빌드 — 편집 목록을 이미지 하나로. **이게 유일한 굽는 자리다**(쓰기 통로도 하나: `common.write_user_data`).

    python3 tools/build.py                 # 🔴 무변경 왕복 — 아무것도 안 바꾸고 다시 굽는다. 결과 = 원본과 바이트 동일이어야 한다
    from build import build; build(edits)  # 편집이 있는 빌드(재삽입 시험 등)

`edits = {"script": {(아카이브, 멤버): {조각 색인: [코드…]}}, "members": {(아카이브, 멤버): 새 바이트열}, "exe": 함수(bytearray) | None}`

## 안전장치 (체크리스트 1·2·3·10)

- **원본 지문**(`common.verify_source`) · **쓰기 통로 하나 + 무변경 구간**(PS-EXE 헤더) · **쓰기 집합 게이트**(`ALLOWED_WRITES`).
- **항등 재구축 게이트** — 대본 멤버 전부(+ 아카이브 188)를 「안 바꾸고」 다시 싸 보고 **원본과 바이트 같음**을 센다. 이게 틀리면
  편집을 얹기 전에 파서·재구축이 이미 틀린 것이다.
- **이미지 검산**(`verify_image`) — 구운 이미지를 **다시 읽어** 바뀐 섹터가 선언한 자리(실행파일 · 쓴 아카이브 · 고친 디렉터리 레코드)뿐인지,
  파일 목록·LBA 가 원본과 같은지, 쓴 아카이브를 되읽으면 쓴 것과 같은지 본다.
- **실패하면 산출물을 무효화한다** — `*.failed`(낡은 이미지를 정상으로 오해하는 이 레포의 단골 사고).
- **결정성** — 같은 입력이면 같은 바이트(`check_determinism.py` 가 두 번 구워 sha 를 맞댄다).
"""

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choice
import common
import discgrow
import hangul
import typeset
from dump import SCRIPT_MEMBER

from shared.ps1 import gmf_arc
from shared.ps1 import gmf_script as scriptmap

# 이 빌드가 쓸 수 있는 파일 — 정규식(전체 일치). 늘리면 여기에 **이유와 함께** 적는다.
ALLOWED_WRITES = [
    r"/[A-KO]/SC\d+\.DAT",  # 대사 아카이브(대본 멤버 재삽입)
    r"/SLPS_015\.40",  # 실행파일(글리프·낱말)
]


def identity_gate(report):
    """🔴 대본 멤버 전부를 안 바꾸고 다시 싸서 **바이트 같음**을 센다 — 틀리면 파서·재구축이 이미 틀렸다.

    반환: {(아카이브, 멤버): 원본 멤버 바이트} — 편집 단계가 같은 읽기를 재사용한다.
    """
    members = {}
    bad = []
    with common.open_disc() as d:
        for path, lba, size in d.files():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            data = d.read_extent(lba, size)
            try:
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            try:
                if (
                    gmf_arc.repack(data, {})[0] != data
                ):  # 아카이브 항등 — 멤버를 안 바꾸면 재배치도 바이트 같아야 한다
                    bad.append(f"{path} (아카이브)")
            except gmf_arc.PackError as e:
                bad.append(f"{path}: {e}")
            for nm, off, sz in ents:
                if SCRIPT_MEMBER not in nm or not nm.endswith(".BIN") or sz < 8:
                    continue
                mem = data[off : off + sz]
                info = scriptmap.parse(mem)
                again, _ = scriptmap.rebuild(
                    mem, [list(c) for _, c in info["segments"]], event_data=True
                )
                if again != mem:
                    bad.append(f"{path}!{nm}")
                members[(path, nm)] = mem
    if bad:
        raise SystemExit(
            f"🔴 항등 재구축이 원본과 다르다 {len(bad)}개 — 편집 전에 파서가 틀렸다: {bad[:5]}"
        )
    report["identity_members"] = len(members)
    return members


def apply_script_edits(edits, members, report, member_edits=None):
    """{아카이브 경로: 새 아카이브 바이트열} — 편집이 있는 멤버만 다시 싸고 아카이브를 재배치한다.

    `member_edits` = {(아카이브, 멤버): 새 바이트열} — 대본이 아닌 멤버(그림 등)를 통째로 바꾼다(시험·타이틀 그림 재삽입 길).
    """
    by_arc = {}
    for (path, nm), per_seg in edits.items():
        by_arc.setdefault(path, {})[nm] = per_seg
    for path, _nm in member_edits or {}:
        by_arc.setdefault(path, {})
    out = {}
    for path, per_member in sorted(by_arc.items()):
        data = common.read_file(path)
        repl = {}
        for nm, per_seg in per_member.items():
            mem = members.get((path, nm), None)
            if mem is None:
                raise SystemExit(f"🔴 {path}!{nm}: 대본 멤버가 아니다")
            info = scriptmap.parse(mem)
            segs = [list(c) for _, c in info["segments"]]
            for i, codes in per_seg.items():
                if not 0 <= i < len(segs):
                    raise SystemExit(f"🔴 {path}!{nm}: 조각 {i} 가 없다 (0~{len(segs) - 1})")
                segs[i] = list(codes)
            # 🔴 줄이 사라질 쪽(한 조각 안 접힌 줄이 3줄 초과 · 쪽 도중 걸침) = 실패 — 화면에서 조용히 사라진다(`typeset.over_limit_pages`)
            if scriptmap.layout(mem) == scriptmap.LAYOUT_TABLE:
                bad = typeset.over_limit_pages(mem, {i: len(c) for i, c in enumerate(segs)})
                # 원본에서 이미 넘던 쪽은 편집한 조각이 낀 쪽만 본다
                bad = [(pg, n) for pg, n in bad if set(pg) & set(per_seg)]
                if bad:
                    raise SystemExit(
                        f"🔴 {path}!{nm}: 줄이 사라질 쪽 {len(bad)}곳(한 쪽 3줄 한도) — 쪽 {bad[0][0]} 의 조각 {bad[0][1]}"
                    )
            newmem, _ = scriptmap.rebuild(mem, segs, event_data=True)
            if scriptmap.layout(mem) == scriptmap.LAYOUT_TABLE:  # 선택지 창 열 — 한국어가 원문보다 길면 넓힌다(`choice.py`)
                newmem, clog = choice.patch_cols(newmem, scriptmap.parse_table(newmem)["base"], segs, frozenset(hangul.half_codes()))
                report["choice_cols"] = report.get("choice_cols", 0) + len(clog)
                badc = (
                    choice.verify(newmem, scriptmap.parse_table(newmem)["base"], segs, frozenset(hangul.half_codes()))
                    if choice.fit_enabled()
                    else []
                )
                if badc:  # 🔴 선택지 창 폭 ≠ 가장 긴 항목 폭 — 잘리거나 커서 상자가 멀리 간다(마스터 11-06)
                    raise SystemExit(f"🔴 {path}!{nm}: 선택지 창 폭 결함 {badc[:3]}")
            repl[nm] = newmem
            report["members"] = report.get("members", 0) + 1
            report["grown"] = report.get("grown", 0) + max(0, len(newmem) - len(mem))
        for (p2, nm), body in (member_edits or {}).items():
            if p2 == path:
                if nm in repl:
                    raise SystemExit(f"🔴 {path}!{nm}: 대본 편집과 멤버 교체가 겹친다")
                repl[nm] = bytes(body)
                report["swapped"] = report.get("swapped", 0) + 1
        try:
            packed, plan = gmf_arc.repack(data, repl)
        except gmf_arc.PackError as e:
            # 슬랙을 넘으면 이미지 끝으로 옮긴다(`discgrow`) — 다른 사유(멤버 없음 · 오프셋 단위)는 그대로 멈춘다
            if "섹터가 늘어난다" not in str(e):
                raise SystemExit(f"🔴 {path}: 재배치 실패 — {e}") from e
            try:
                packed, plan = discgrow.repack_grow(data, repl)
            except gmf_arc.PackError as e2:
                raise SystemExit(f"🔴 {path}: 재배치 실패 — {e2}") from e2
        report["repacked"] = report.get("repacked", 0) + (1 if plan["grow"] else 0)
        out[path] = packed
    return out


def verify_image(built, fs, arcs, exe_changed, dirpos, resized, moves):
    """🔴 구운 이미지를 **다시 읽어** 검산한다 — 「썼다」와 「다시 읽힌다」는 다르다."""
    common._FILES.pop(built, None)
    tree = common.iso_files(built)
    if set(tree) != set(fs):
        raise SystemExit(
            f"🔴 이미지 검산: 파일 목록이 달라졌다 — {sorted(set(tree) ^ set(fs))[:5]}"
        )
    for path, (lba, size) in fs.items():
        want = (moves[path], len(arcs[path])) if path in moves else (lba, resized.get(path, size))
        if tree[path] != want:
            raise SystemExit(f"🔴 이미지 검산: {path} 이 {tree[path]} (기대 {want})")
    allowed = set()
    if exe_changed:
        lba, size = fs[common.EXE_PATH]
        allowed |= set(range(lba, lba + common.sectors(size)))
    for path in arcs:
        if path in moves:
            continue  # 옮긴 아카이브는 옛 자리를 안 건드린다 — 새 자리는 이미지 끝(아래에서 따로 검산)
        lba, size = fs[path]
        allowed |= set(range(lba, lba + common.sectors(max(size, resized.get(path, size)))))
    allowed |= {dirpos[p][0] for p in resized} | {dirpos[p][0] for p in moves}
    if moves:
        allowed.add(16)  # PVD — 볼륨 크기
    changed = set()
    sz = common.SECTOR
    tail = sum(common.sectors(len(arcs[p])) for p in moves) * sz  # 이미지 끝에 덧붙인 바이트
    if os.path.getsize(built) != os.path.getsize(common.orig_bin()) + tail:
        raise SystemExit("🔴 이미지 검산: 이미지 길이가 (원본 + 덧붙인 섹터)와 다르다")
    with open(common.orig_bin(), "rb") as fo, open(built, "rb") as fb:
        lba = 0
        while True:
            a1, b1 = fo.read(sz * 256), fb.read(sz * 256)
            if not a1:
                break
            if len(a1) != len(b1) and len(b1) < len(a1):
                raise SystemExit("🔴 이미지 검산: 이미지가 원본보다 짧다")
            b1 = b1[: len(a1)]
            if a1 != b1:
                for k in range(len(a1) // sz):
                    if a1[k * sz : (k + 1) * sz] != b1[k * sz : (k + 1) * sz]:
                        changed.add(lba + k)
            lba += len(a1) // sz
    stray = sorted(changed - allowed)
    if stray:
        raise SystemExit(f"🔴 이미지 검산: 선언 안 된 섹터 {len(stray)}곳이 바뀌었다 — {stray[:8]}")
    with common.open_disc(built) as d:
        for path, data in arcs.items():
            lba = moves[path] if path in moves else fs[path][0]
            if d.read_extent(lba, len(data)) != data:
                raise SystemExit(f"🔴 이미지 검산: {path} 을 되읽은 것이 쓴 것과 다르다")
    return len(changed)


def build(edits=None, *, kind="identity", suffix=""):
    """편집을 얹어 이미지를 굽는다. 반환 = (출력 경로, 리포트). 실패하면 `*.failed` 로 남기고 예외."""
    edits = edits or {}
    common.verify_source()
    common.declare_immutable()
    report = {}
    members = identity_gate(report)
    fs = common.iso_files()
    arcs = apply_script_edits(edits.get("script", {}), members, report, edits.get("members"))

    exe_lba, _exe_size = fs[common.EXE_PATH]
    exe = bytearray(common.read_file(common.EXE_PATH))
    exe_orig = bytes(exe)
    if edits.get("exe"):
        edits["exe"](exe)
    exe_changed = bytes(exe) != exe_orig

    # 🔴 쓰기 집합 게이트 — 선언된 파일만 쓴다
    targets = list(arcs) + ([common.EXE_PATH] if exe_changed else [])
    unexpected = sorted(
        p for p in targets if not any(re.fullmatch(pat, p) for pat in ALLOWED_WRITES)
    )
    if unexpected:
        raise SystemExit(
            f"🔴 선언 안 된 파일에 쓰려 했다: {unexpected[:5]} — ALLOWED_WRITES 를 확인한다"
        )

    os.makedirs(common.BUILD_DIR, exist_ok=True)
    out = common.build_bin(suffix)
    tmp = out + ".part"
    shutil.copyfile(common.orig_bin(), tmp)
    dirpos = common.dir_records()
    moves = discgrow.plan_moves(fs, arcs)
    resized = {}
    n = 0
    try:
        with open(tmp, "r+b") as f:
            if exe_changed:
                n += common.write_user_data(f, exe_lba, bytes(exe), label="실행파일")
            for path, data in sorted(arcs.items()):
                if path in moves:
                    continue
                lba, osize = fs[path]
                n += common.write_user_data(f, lba, data, label=path)
                if (
                    len(data) != osize
                ):  # 재배치로 길어진 아카이브 — ISO 디렉터리의 파일 크기만 고친다(섹터 수는 같다)
                    n += common.set_file_size(
                        f, *dirpos[path], len(data), label=f"{path} 디렉터리 레코드"
                    )
                    resized[path] = len(data)
            if moves:  # 슬랙을 넘은 아카이브 — 이미지 끝에 덧붙이고 디렉터리·PVD 를 고친다
                f.seek(0, 2)
                appended, fixed = discgrow.apply(f, moves, arcs, fs, dirpos)
                n += appended + fixed
    except Exception:
        os.replace(tmp, out + ".failed")  # 🔴 실패한 빌드는 산출물을 무효화한다
        raise
    try:
        changed = verify_image(tmp, fs, arcs, exe_changed, dirpos, resized, moves)
        if not edits and changed:
            raise SystemExit(f"🔴 무변경 왕복인데 섹터 {changed}개가 바뀌었다")
    except BaseException:
        os.replace(tmp, out + ".failed")
        raise
    os.replace(tmp, out)
    from shared.disc import mode2

    mode2.write_cue(common.build_cue(suffix), os.path.basename(out))
    common.write_manifest(out, kind)
    report.update(
        written_sectors=n, changed_sectors=changed, resized=len(resized), moved=len(moves)
    )
    return out, report


def main():
    out, rep = build()
    same = common.sha1_of(out) == common.DISC["sha1"]
    print(
        f"무변경 왕복: 대본 멤버 {rep['identity_members']} 항등 재구축 일치 · 쓴 섹터 {rep['written_sectors']} · 바뀐 섹터 {rep['changed_sectors']}\n"
        f"  sha1 {common.sha1_of(out)} {'= 원본과 같다 ✅' if same else '≠ 원본 🔴'}\n→ {out}"
    )
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
