"""ED2 몬스터 **이름 칸**을 정본으로 바꾼다 — 전투 메시지의 `%s` 가 여기서 온다.

    python3 tools/patch_mon_names.py            # 계획·검산만
    python3 tools/patch_mon_names.py --apply    # 빌드 이미지에 넣는다

## 왜 별도 패처인가

이름은 `/BIN/ED2MON01~10.BIN` 안에 **개별 문자열**로 흩어져 있다(171칸, 실측). 시스템
메시지 경로(`patch_ui.sys_rows`)에 태워 봤더니 두 가지가 걸렸다:

🔴 **같은 이름이 `ED.BIN` 의 고정 폭 몬스터 표에도 있다.** 정본(`script/system.json`)은
   파일을 안 가리므로 **두 주인**이 되어 표가 덮인다(실측 2026-08-27:
   `/ED.BIN スライムＡ: 되읽기 '\\n'`). 「몬스터 이름이면 본체에서 건너뛴다」로 막아 봤더니
   이번엔 본체가 **정당하게** 갖고 있던 이름 27줄이 같이 막혔다.
⇒ 파일을 가리는 처리는 **파일을 아는 자리**에서 해야 한다. 그래서 이 패처다.

## 어떻게 바꾸나 — 제자리 우선, 넘치면 **칸끼리 자리를 바꾼다**

대개는 우리 이름이 짧다(`スライムＡ` 10B → `슬라임A` 7B). 그런데 **긴 것도 있다**
(`炎の騎士Ａ` 10B → `불꽃의기사A` 11B). 그 파일들은 꽉 차 재배치할 0런이 사실상 없으므로,
**이름 칸들만 한 풀로 묶어** 다시 깐다 — 짧아진 칸이 낸 여유를 긴 칸이 쓴다.
🔴 옮긴 칸은 **포인터를 갱신**한다. 이 이름들은 171칸 전부 포인터를 갖고 있어(실측)
   안전하다 — 「포인터 없이 색인으로 집는 표」가 아니다.
⚠ 총량이 넘치면 실패한다. 조용히 자르지 않는다.
⚠ 문안을 줄여 맞추지 않는다 — 정본은 PS1 과 공유하는 `shared/glossary` 다.

## 개체 접미는 반각으로

원본은 전각(`スライムＡ`)이지만 우리는 반각이다(유저 방침: 메시지 창의 알파벳은 전부 반각).
⚠ 원본에 **반각으로 든 것도 있다**(`ブラムナドッグA`) — 둘 다 받는다.
⚠ **통짜부터 본다** — `ゴドウィン２世` 처럼 끝 글자가 접미처럼 생긴 이름이 있다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import common
import dump_scn
from glossary import table
from patch_ui import slot_plan

FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]
# 🔴 **A~F 로는 모자란다**(2026-08-27 실측) — `ニュートハニーJ` 처럼 **Ｊ까지** 가고,
#    분열하는 몬스터는 **프라임**이 붙는다(`赤スライムA'` · `赤スライムＡ''`).
#    좁게 잡아 두면 그 이름들만 조용히 일본어로 남는다.
MARKS = "ＡＢＣＤＥＦＧＨＩＪABCDEFGHIJ"
PRIME = "'’"
HALF = {c: (chr(ord(c) - 0xFEE0) if "Ａ" <= c <= "Ｚ" else c) for c in MARKS}
HALF.update({"’": "'", "'": "'"})
MAXNAME = 20


def split_mark(jp, mon):
    """`(KR 이름, 반각 접미)` 또는 `(None, "")`.

    ⚠ **통짜부터 본다** — `ゴドウィン２世` 처럼 끝 글자가 접미처럼 생긴 이름이 있다.
    ⚠ 프라임은 개체 번호가 아니라 **분열체 표시**라 개수까지 지킨다(`A''` 는 둘째 분열).
    """
    if jp in mon:
        return mon[jp], ""
    body = jp
    prime = ""
    while len(body) > 1 and body[-1] in PRIME:
        body, prime = body[:-1], HALF[body[-1]] + prime
    if body in mon:  # 접미 없이 프라임만 붙는 꼴
        return mon[body], prime
    if len(body) > 1 and body[-1] in MARKS and body[:-1] in mon:
        return mon[body[:-1]], HALF[body[-1]] + prime
    return None, ""


def slots(path, mon):
    """`[(오프셋, JP, KR)]` — 그 파일의 이름 칸. **포인터 대상만** 본다."""
    d = bytes(common.extract(path))
    base = dump_scn.base_for(os.path.basename(path))
    assert base, path
    out = []
    for o in range(0, len(d) - 3, 2):
        v = struct.unpack(">I", d[o : o + 4])[0]
        if not (base <= v < base + len(d)):
            continue
        t = v - base
        if any(r[0] == t for r in out):
            continue
        j = t
        while j < len(d) and d[j] != 0:
            j += 1
        if not (2 <= j - t <= MAXNAME):
            continue
        try:
            jp = d[t:j].decode("cp932")
        except UnicodeDecodeError:
            continue
        kr, mark = split_mark(jp, mon)
        if kr:
            out.append((t, jp, kr + mark))
    return sorted(out)


def _ptrs_to(d, at, base):
    """파일 안에서 `at` 을 가리키는 BE32 포인터들의 오프셋."""
    pat = (base + at).to_bytes(4, "big")
    out, i = [], 0
    while (j := d.find(pat, i)) >= 0:
        out.append(j)
        i = j + 1
    return out


def encode(kr, plan):
    return b"".join(plan[c][0] if c in plan else c.encode("cp932") for c in kr)


def main():
    apply = "--apply" in sys.argv
    common.verify_source()
    mon = table("monster")
    plans = {p: slots(p, mon) for p in FILES}
    krs = [kr for rows in plans.values() for _t, _jp, kr in rows]
    plan = slot_plan(krs)  # ⚠ 슬롯 정본은 여기서 안 늘린다(`patch_ui --refresh` 몫)

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if apply and not os.path.exists(dst):
        raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
    _f, mm = common.open_image()
    files = {p: (lba, s) for p, lba, s in common.iso_files(mm)}

    total, moved = 0, 0
    placed = {}
    for path, rows in plans.items():
        d = bytes(common.extract(path))
        base = dump_scn.base_for(os.path.basename(path))
        # ── 칸 = 원문 + 그 뒤 NUL 들. 붙어 있으면 합친다(안 합치면 조각이 다 작다)
        spans = []
        for t, _jp, _kr in rows:
            j = t
            while j < len(d) and d[j] != 0:
                j += 1
            e = j
            while e < len(d) and d[e] == 0:
                e += 1
            spans.append((t, e - t))
        spans.sort()
        merged = []
        for a, n in spans:
            if merged and merged[-1][0] + merged[-1][1] == a:
                merged[-1][1] += n
            else:
                merged.append([a, n])
        free = sorted(([a, n] for a, n in merged), key=lambda b: -b[1])
        body = {a: bytearray(n) for a, n in merged}

        # 긴 것부터 (first-fit decreasing) — 작은 것부터면 큰 게 갈 데가 없어진다
        writes, ptrmoves = [], {}
        for t, jp, kr in sorted(rows, key=lambda r: -len(encode(r[2], plan))):
            blob = encode(kr, plan) + b"\x00"
            # 🔴 **짝수 주소에만 놓는다**(2026-08-28) — 두 바이트를 한 글자로 고정해 읽는
            #    화면이 있어(HUD) 홀수 자리는 거기서만 통째로 밀려 깨진다. 같은 사고를
            #    `patch_ui`·`patch_scn` 에서 먼저 밟았다.
            i = next((k for k, (a_, n_) in enumerate(free) if n_ - (a_ & 1) >= len(blob)), None)
            assert i is not None, f"{path}: 자리가 모자란다 — {kr!r} {len(blob)}B ({jp!r})"
            a, n = free.pop(i)
            if a & 1:
                a, n = a + 1, n - 1
            blk = max(x for x, _n in merged if x <= a)
            body[blk][a - blk : a - blk + len(blob)] = blob
            if a != t:
                moved += 1
                for q in _ptrs_to(d, t, base):
                    ptrmoves[q] = base + a
            ro, rn = a + len(blob), n - len(blob)
            if ro & 1:
                ro, rn = ro + 1, rn - 1
            if rn >= 3:
                free.append([ro, rn])
                free.sort(key=lambda b: -b[1])
            placed.setdefault(path, {})[jp] = (a, kr)
        for a, _n in merged:
            writes.append((a, bytes(body[a])))
        total += len(rows)
        print(f"  {path}: 이름 {len(rows)}칸 · 옮긴 포인터 {len(ptrmoves)}곳")
        if not apply:
            continue
        lba, size = files[path]
        with open(dst, "r+b") as f:
            for a, blob in writes:
                common.write_at(f, lba, size, a, blob, label=f"{path} 몬스터 이름 0x{a:X}")
            for q, v in ptrmoves.items():
                common.write_at(
                    f, lba, size, q, v.to_bytes(4, "big"), label=f"{path} 이름 포인터 0x{q:X}"
                )
    print(f"  이름 {total}칸 · 자리를 옮긴 것 {moved}")
    if apply:
        verify(dst, placed, plan, files)
    else:
        print("  (검산만 — 실제로 넣으려면 `--apply`)")
    mm.close()
    _f.close()


def verify(dst, placed, plan, files):
    """되읽기 — **자리를 옮겼으니 우리가 적은 자리**에서 읽는다."""
    inv = {sjis: ch for ch, (sjis, _i) in plan.items()}
    _f2, mm2 = common.open_image(dst)
    n = 0
    for path, rows in placed.items():
        d = common.read_extent(mm2, *files[path])
        for jp, (a, kr) in rows.items():
            j = a
            while j < len(d) and d[j] != 0:
                j += 1
            got = _decode(bytes(d[a:j]), inv)
            assert got == kr, f"{path} 0x{a:X} {jp}: 되읽기 {got!r} ≠ {kr!r}"
            n += 1
    mm2.close()
    _f2.close()
    print(f"  ✅ 되읽기 몬스터 이름 {n}칸 (자리 추적)")


def _decode(b, inv):
    out, i = "", 0
    while i < len(b):
        two = b[i : i + 2]
        if len(two) == 2 and two in inv:
            out += inv[two]
            i += 2
            continue
        try:
            out += two.decode("cp932")
            i += 2
        except UnicodeDecodeError:
            out += b[i : i + 1].decode("cp932", "replace")
            i += 1
    return out


if __name__ == "__main__":
    main()
