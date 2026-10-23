"""구조 흐름 추적 대조 — 기준 롬(ED_RELOC_OFF=*)과 번역 롬의 `trace.txt` 를 단위별로 맞댄다.

번역 롬은 쪽이 더 쪼개져 같은 프레임 안에 덜 가므로 한쪽이 **다른 쪽의 앞부분**이면 같다고 본다(프레임 상한에서 끊긴 것). 끝(`END … ret`)까지 간 단위는 통째로 같아야 한다.
메시지 진입(`M`)의 `$A6` 가 확장 영역($D8~$DF — 사전 이름 호출)이면 비교에서 뺀다.

    python3 trace_diff.py <기준 trace.txt> <번역 trace.txt>
"""

import sys


def parse(path):
    units, cur = {}, None
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if ln.startswith("UNIT"):
            cur = ln.split()[2]
            units[cur] = {"seq": [], "end": None}
        elif cur and ln.startswith("T "):
            if int(ln.split()[1], 16) < 0xD80000:  # 사전 문자열의 끝 토큰(`$06`)도 같은 이유로 뺀다
                units[cur]["seq"].append(ln)
        elif cur and ln.startswith("M "):
            a = int(ln.split()[1], 16)
            if a < 0xD80000:  # 확장 영역 진입(사전 이름 호출 `$E0/$E1`)은 번역이 이름을 글자로 적거나 어미로 풀 수 있어(check_rules 와 같은 이유) 비교에서 뺀다
                units[cur]["seq"].append(ln)
        elif cur and ln.startswith("END"):
            units[cur]["end"] = ln.split()[2]
    return units


def main() -> int:
    base, kr = parse(sys.argv[1]), parse(sys.argv[2])
    bad = 0
    for u in base:
        b, k = base[u]["seq"], kr.get(u, {"seq": [], "end": None})["seq"]
        n = min(len(b), len(k))
        same = b[:n] == k[:n]
        full = base[u]["end"] == "ret" and kr[u]["end"] == "ret"
        ok = same and (len(b) == len(k) if full else True) and n > 0
        bad += not ok
        first = next((i for i in range(n) if b[i] != k[i]), None)
        print(f"{u}: 기준 {len(b)} · 번역 {len(k)} 토큰/호출 · 앞 {n}개 {'같다' if same else '다르다 @%d %s | %s' % (first, b[first], k[first])} · 끝 {base[u]['end']}/{kr.get(u, {}).get('end')}")
    print(f"흐름 어긋남 {bad}/{len(base)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
