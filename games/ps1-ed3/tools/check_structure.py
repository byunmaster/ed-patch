"""구조 대조 정적 검사 — **원본과 구운 이미지의 대본 멤버를 제어 구조만 뽑아 한 블록씩 맞댄다**(마스터 10-22 「재배치사고 막는 정적검사」).

배경(ss-ed3 10-21): 재조판이 대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아 첫 장면 대사가 빠졌다 — 대사를 한 블록씩 띄우는 하네스·qa 로는
안 보이고 연속 재생에서만 드러났다. 재배치·꼬리 옮기기·채움을 하는 빌드는 모두 같은 위험이 있어, **글자 바이트를 뺀 제어 구조**를 원본과 맞댄다.

## 이 게임에서 「제어 구조」가 무엇인가 (디스어셈블·`scriptmap` 로 확인한 것)

대본 멤버 = `[u16 TEXT_BASE][스크립트 바이트 스트림][문자열 풀]`. 대사 흐름(개행 · 쪽 넘김 · 화자 · 다음 블록 호출/분기/점프 · 종결 · 인자)은
**전부 스크립트 구간**이 든다 — 풀의 코드는 글리프(+ 숫자 표식 `0xEEEE` + 종결 `0xFFFF`)뿐이다(코드 4~15 는 `？ ！ 々 ー …` 글리프다).
그래서 대조 대상은 넷이다.

 ① 스크립트 구간 `[0, TEXT_BASE)` — 풀린 포인터 자리(u16)만 달라야 한다. 나머지(못 푼 `0x90` 데이터·연산자·인자)는 바이트까지 같다.
 ② 포인터 — 자리 목록이 같고, 풀린 것은 **같은 번째 조각의 새 시작**을 가리키며 하위 비트(플래그)가 같다.
 ③ 조각 수·순서 — 같아야 한다. 풀은 새 조각을 `0xFFFF` 로 닫아 이은 것이어야 하고, 마지막 종결 뒤에는 **0 바이트 채움만** 올 수 있다.
 ④ 조각 안의 숫자 표식 — 원문의 `0xEEEE <값>`(엔진이 값을 숫자로 찍는다)은 번역에서 **같은 표식이 남거나, 같은 값의 숫자 글자로 풀려** 있어야 한다.
    그 밖의 `0x8000` 이상 코드가 번역 조각에 새로 생기면 허용 목록(조사 훅 표지)에 있어야 한다.

아카이브(`SC*.DAT`) 쪽: 멤버 목록·순서가 같고, 대본이 아닌 멤버는 바이트까지 같으며, 안 바뀐 멤버는 위치만 밀린다(`arcpack`).

## 허용 목록 — 의도한 변화와 엔진 근거

 - 포인터 재계산: 조각 길이가 바뀌면 `0x90 <V>` 의 V 가 새 시작으로 바뀐다. 근거: 어셈블러 `0x800384C4~0x800384FC` — 문자열 = TEXT_BASE + (V & ~1).
 - 꼬리 0 채움: 멤버 크기를 원본에 맞추려고 마지막 `0xFFFF` 뒤를 0 으로 채운다. 근거: 문자열은 포인터로만 닿고 `0xFFFF` 에서 끝난다(같은 구간) — 마지막 종결 뒤는 안 읽힌다.
 - `0xEEEE <값>` → 숫자 글자: 값이 상수라 번역이 글자로 직접 적는다. 근거: 줄 재생기 `0x80022C90` 은 `0xEEEE` 뒤 코드를 숫자로 찍고 계속한다(`poolpack` 문서).
 - 멤버 옮김(아카이브 안 뒤 멤버 밀기): `arcpack.repack` — TOC 오프셋·크기 갱신. 근거: GMF TOC(32B 항목, 오프셋 단위 4B).

장부(`relocations.tsv`)는 이 검사가 **이미지에서 직접 뽑는다** — 손으로 안 쓴다. 빌드에 있는데 장부에 (블록 키·종류)가 없는 재배치가 있으면 실패한다(숫자는 문안을 고칠 때마다 움직여 비교에서 뺀다).

사용: `check_structure.py <구운 .bin>` · `--write-ledger`(게이트에선 `STRUCT_WRITE_LEDGER=1`) 로 장부를 다시 쓴다(의도한 변화일 때만).
"""

import argparse
import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import scriptmap

DISC = "ed3"
TERM = 0xFFFF
NUM_MARK = 0xEEEE
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(HERE, "relocations.tsv")
ARCS = lambda files: sorted(p for p in files if p.startswith("/SCE") and p.endswith(".DAT"))

EVIDENCE = {
    "포인터": "0x800384C4~0x800384FC (문자열 = TEXT_BASE + (V & ~1))",
    "채움": "0x800384C4~0x800384FC · 줄 재생기 0x80022C90 (문자열은 포인터로만 닿고 0xFFFF 에서 끝남 — 마지막 종결 뒤는 안 읽힘)",
    "옮김": "GMF TOC 32B 항목 · 오프셋 단위 4B (arcpack.repack · common.arc_parse)",
}
REVERT = {
    "포인터": "되돌리기 수단 없음 — 조각 길이가 바뀌면 V 가 반드시 바뀐다(원 자리 방식 = 번역을 원문 길이로 되돌림)",
    "채움": "되돌리기 수단 없음 — 멤버 크기를 원본에 맞추는 0 채움이라 끌 이유가 없다(끄면 멤버가 짧아져 뒤 멤버가 당겨진다)",
    "옮김": "되돌리기 수단 없음 — 번역이 원본보다 커진 멤버의 자리다(멤버 번역을 원문 길이 안으로 줄여야 사라진다)",
}


def pool_end(mem, base):
    """풀을 `0xFFFF` 로 읽어 마지막 종결 **다음** 오프셋. 종결 없이 끝나면 None."""
    end = None
    i = base
    while i + 1 < len(mem):
        if struct.unpack_from("<H", mem, i)[0] == TERM:
            end = i + 2
        i += 2
    return end


def real_segments(mem, base):
    """종결(`0xFFFF`)로 닫힌 조각만 [(시작, [코드])]."""
    out, cur, start, i = [], [], base, base
    while i + 1 < len(mem):
        v = struct.unpack_from("<H", mem, i)[0]
        if v == TERM:
            out.append((start, cur))
            cur, start = [], i + 2
        else:
            cur.append(v)
        i += 2
    return out


def num_marks(codes):
    """[(표식 다음 값)] — `0xEEEE` 바로 뒤 코드."""
    return [codes[k + 1] for k, c in enumerate(codes) if c == NUM_MARK and k + 1 < len(codes)]


def compare_member(x, y, kr_dec, allow_hi):
    """(오류 목록, 정보 dict) — x 원본 멤버, y 구운 멤버."""
    errs, info = [], {}
    if x == y:
        return errs, {"same": True}
    try:
        i, j = scriptmap.parse(x), scriptmap.parse(y)
    except Exception as e:  # noqa: BLE001
        return [f"파싱 실패: {e}"], info
    base = i["base"]
    if j["base"] != base:
        return [f"TEXT_BASE 달라짐 {base:#x} → {j['base']:#x}"], info
    # ① 스크립트 구간 — 풀린 포인터 자리만 다르다
    sites_i = {at: V for at, V in i["pointers"]}
    sites_j = {at: V for at, V in j["pointers"]}
    if list(sites_i) != list(sites_j):
        errs.append("포인터 자리 목록이 다르다")
    starts_i = {s: k for k, (s, _) in enumerate(real_segments(x, base))}
    resolved = {at for at, V in i["pointers"] if base + (V & ~1) in starts_i}
    touched = set()
    for at in resolved:
        touched.update((at, at + 1))
    bad = [k for k in range(2, base) if k not in touched and x[k] != y[k]]
    if bad:
        errs.append(f"스크립트 바이트 {len(bad)}곳이 포인터 자리가 아닌데 바뀜 (첫 {bad[0]:#x})")
    # ③ 풀 — 조각 수 · 닫힘 · 꼬리 채움
    sx, sy = real_segments(x, base), real_segments(y, base)
    if len(sx) != len(sy):
        errs.append(f"조각 수 {len(sx)} → {len(sy)}")
    ex, ey = pool_end(x, base), pool_end(y, base)
    if ex is None or ey is None:
        errs.append("풀이 0xFFFF 로 안 닫힘")
    else:
        fx, fy = x[ex:], y[ey:]
        if any(fx):
            errs.append("원본 꼬리에 0 이 아닌 바이트")
        if any(fy):
            errs.append("구운 꼬리에 0 이 아닌 바이트(채움이 0 이 아님)")
        info["fill"] = len(fy)
        info["fill_orig"] = len(fx)
    # ② 포인터 서수·플래그
    if len(sx) == len(sy):
        ys = {k: s for k, (s, _) in enumerate(sy)}
        ptr_changed = 0
        for at, V in i["pointers"]:
            old = base + (V & ~1)
            if old not in starts_i:
                if sites_j.get(at) != V:
                    errs.append(f"못 푼 포인터 {at:#x} 값이 바뀜")
                continue
            got = sites_j.get(at)
            if got is None:
                continue
            if base + (got & ~1) != ys[starts_i[old]] or (got & 1) != (V & 1):
                errs.append(f"포인터 {at:#x} 가 {starts_i[old]}번째 조각의 새 시작을 안 가리킴")
            if got != V:
                ptr_changed += 1
        info["ptr"] = ptr_changed
        # ④ 조각 안 숫자 표식 · 새 상위 코드
        marks = 0
        for k, ((_, c1), (_, c2)) in enumerate(zip(sx, sy, strict=True)):
            if c1 == c2:
                continue
            v1 = num_marks(c1)
            if v1 and num_marks(c2) != v1:
                txt = kr_dec(c2)
                runs = re.findall(r"[0-9]+", txt)
                for v in v1:
                    if v >= 0x8000:  # 두 코드에 걸친 큰 수(32비트) — 아래 글자와 직접 못 맞춘다
                        info["wide"] = info.get("wide", 0) + 1
                    elif runs and str(v) not in runs:
                        errs.append(f"조각 {k}: 원문 숫자 표식 값 {v} ↔ 번역의 숫자 {runs}")
                    elif not runs:
                        info["spelled"] = (
                            info.get("spelled", 0) + 1
                        )  # 한글 수사·조각 재배치 — 숫자 글자가 없어 못 잰다(눈으로)
                marks += len(v1)
            for c in c2:
                if c >= 0x8000 and c != TERM and c not in allow_hi(c) and c != NUM_MARK:
                    errs.append(f"조각 {k}: 허용 목록에 없는 상위 코드 {c:#06x}")
                    break
        info["marks"] = marks
    info["size"] = (len(x), len(y))
    return errs, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("--write-ledger", action="store_true")
    a = ap.parse_args()
    import hangul_map
    import pair_table

    need = list(hangul_map.EXTRA) + hangul_map.needed_chars(DISC)
    table, _ = hangul_map.assign(DISC, hangul_map.test_slots(DISC), chars=need)
    kdec = pair_table.kr_decoder(table)

    def allow_hi(c):
        return {c} if (c & 0x7FFF) < 0x1000 or (c & 0x7000) == 0x7000 else set()

    of = common.iso_files(DISC)
    bf, _ = common.iso_tree(a.bin)
    st = collections.Counter()
    rows, errors = [], []
    for p in ARCS(of):
        if p not in bf:
            errors.append(f"{p}: 구운 이미지에 없다")
            continue
        lba, size = of[p]
        x = common.read_lba(DISC, lba, size)
        lb, sb = bf[p]
        y = common.read_lba(DISC, lb, sb, a.bin)
        _, ea = common.arc_parse(x)
        _, eb = common.arc_parse(y)
        if [n for n, _, _ in ea] != [n for n, _, _ in eb]:
            errors.append(f"{p}: 멤버 목록·순서가 다르다")
            continue
        for (n, ox, sx_), (_, oy, sy_) in zip(ea, eb, strict=True):
            mx, my = x[ox : ox + sx_], y[oy : oy + sy_]
            key = f"{p}!{n}"
            st["멤버"] += 1
            is_script = n.upper().startswith("..\\DATA\\") and n.upper().endswith(".BIN")
            if mx == my:
                st["같음"] += 1
            elif not is_script:
                errors.append(f"{key}: 대본이 아닌 멤버가 바뀜")
                continue
            else:
                st["대본 대조"] += 1
                errs, info = compare_member(mx, my, kdec, allow_hi)
                for e in errs:
                    errors.append(f"{key}: {e}")
                st["숫자 표식(한글 수사·재배치 — 수동)"] += info.get("spelled", 0)
                if info.get("ptr"):
                    st["포인터"] += 1
                    rows.append(
                        (
                            key,
                            "포인터",
                            f"@{ox}+{sx_}",
                            f"@{oy}+{sy_}",
                            f"조각 길이 변화 · 포인터 {info['ptr']}개 재계산",
                            EVIDENCE["포인터"],
                            REVERT["포인터"],
                        )
                    )
                if info.get("fill"):
                    st["채움"] += 1
                    rows.append(
                        (
                            key,
                            "채움",
                            f"@{ox}+{sx_}",
                            f"@{oy}+{sy_}",
                            f"멤버 크기 유지 · 꼬리 0 {info['fill']}B",
                            EVIDENCE["채움"],
                            REVERT["채움"],
                        )
                    )
        moved = [(n, ox, oy) for (n, ox, _), (_, oy, _) in zip(ea, eb, strict=True) if ox != oy]
        if moved:
            st["옮김 아카이브"] += 1
            rows.append(
                (
                    p,
                    "옮김",
                    f"멤버 {len(moved)}개 첫 @{moved[0][1]}",
                    f"@{moved[0][2]}",
                    "번역이 원본보다 커진 멤버 뒤를 밀음",
                    EVIDENCE["옮김"],
                    REVERT["옮김"],
                )
            )
    rows.sort()
    head = "블록 키\t종류\t원래 좌표\t새 좌표\t사유\t엔진 근거\t되돌리면"
    text = head + "\n" + "\n".join("\t".join(r) for r in rows) + "\n"
    kinds = collections.Counter(r[1] for r in rows)
    print(
        f"  구조 대조 — 멤버 {st['멤버']}개 중 대본 대조 {st['대본 대조']}개(나머지 {st['같음']}개는 바이트 동일) · 어긋남 {len(errors)}"
    )
    print(
        f"  숫자 표식 {st['숫자 표식(한글 수사·재배치 — 수동)']}곳은 숫자 글자가 없어(한글 수사·조각 재배치) 값 대조를 못 했다 — 인게임 QA 목록"
    )
    print(
        "  재배치 장부 — "
        + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
        + f" (총 {len(rows)}행)"
    )
    for e in errors[:30]:
        print("   🔴", e)
    if a.write_ledger:
        with open(LEDGER, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"  장부 기록 → {os.path.relpath(LEDGER)}")
    elif os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as fh:
            have = {tuple(ln.split("\t")[:2]) for ln in fh.read().splitlines()[1:] if ln}
        now = {(r[0], r[1]) for r in rows}
        extra = sorted(now - have)
        stale = sorted(have - now)
        if extra:
            print(
                f"   🔴 장부에 없는 재배치 {len(extra)}건 (첫 {extra[0]}) — 의도한 변화면 STRUCT_WRITE_LEDGER=1 로 장부를 다시 쓴다"
            )
            errors.append("장부에 없는 재배치")
        if stale:
            print(
                f"   ⚠ 장부에만 있고 이번 빌드엔 없는 재배치 {len(stale)}건 — 장부를 다시 쓰면 정리된다"
            )
    else:
        print("   🔴 relocations.tsv 가 없다 — --write-ledger")
        errors.append("장부 없음")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
