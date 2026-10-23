"""창 단위 재조판 게이트(마스터 10-20 「어절단위 개행」, 규칙 2-6·2-10) — 번역 정본 + 원본 멤버로 **구울 줄을 미리 계산**해 어긴 자리를 센다.

  python3 tools/check_reflow.py            (원본 디스크가 있어야 한다 — 창은 원본 스크립트의 포인터 구조에서 온다)

어기면 실패: ① 줄이 24글리프·24칸을 넘음 ② 띄어 쓴 정본 이름이 두 줄에 걸침 ③ 글이 바뀜(공백·개행만 옮긴다) ④ 줄이 조각 수를 넘음.
세어서 알리는 것: 창 수 · 바뀐 창 · 원래 구조 유지(조사 병기·줄 늘어남 등)."""

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import josa_rt
import script as script_canon
import scriptmap
import typeset


def main():
    canon, _ = script_canon.load_effective("ed3")
    bound = typeset._bind_names()
    st = collections.Counter()
    bad = []
    for (path, nm), lines in sorted(canon.items()):
        lba, size = common.iso_files("ed3")[path]
        data = common.read_lba("ed3", lba, size)
        _, ents = common.arc_parse(data)
        off, sz = next((o, s) for n, o, s in ents if n == nm)
        mem = data[off : off + sz]
        info = scriptmap.parse(mem)
        chains = scriptmap.window_chains(mem, info)
        use = collections.Counter(i for c in chains for i in c)
        for c in chains:
            st["창"] += 1
            if any(i not in lines or use[i] != 1 for i in c):
                st["건너뜀(번역 없음·공유 조각)"] += 1
                continue
            old = [josa_rt.convert(lines[i]["kr"]) for i in c]
            rows = typeset.reflow(old, "ed3")
            where = f"{path}!{nm} #{c[0]}"
            if rows is None:
                st["원래 구조 유지"] += 1
                continue
            st["바뀐 창" if rows != old else "그대로"] += 1
            for r in rows:
                if len(r) > typeset.COLS["ed3"] or typeset.width_cells(r) > typeset.COLS["ed3"]:
                    bad.append(f"{where}: 줄이 격자를 넘는다({len(r)}글리프) {r!r}")
            joined = "\n".join(r for r in rows if r)
            for name, _b in bound:
                if name in " ".join(old) and name.replace(" ", "\n") in joined:
                    bad.append(f"{where}: 띄어 쓴 이름 「{name}」이 두 줄에 걸쳤다")
            if len([r for r in rows if r]) > len(c):
                bad.append(f"{where}: 줄이 조각 수를 넘는다")
            if "".join("".join(rows).split()) != "".join("".join(old).split()):
                bad.append(f"{where}: 글이 바뀌었다")
    print("   " + " · ".join(f"{k} {v}" for k, v in st.items()))
    for b in bad[:20]:
        print("   🔴", b)
    print(f"   창 재조판 — {'✅ 규칙을 지킨다' if not bad else f'🔴 위반 {len(bad)}'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
