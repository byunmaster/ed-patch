"""`wintrace` 로그(json)들을 91곳 표(`docs/window-sites-1107.tsv`)에 합친다 — 덫에 잡힌 최장 문자열은 「관측」, 이름표에서 구한 값은 「계산」으로 갈라 적는다.

    python3 tools/wintrace_merge.py <로그.json>… (표의 앞 일곱 열은 그대로, 뒤 열을 다시 쓴다)
"""

import json
import sys

HERE = __file__.rsplit("/", 1)[0]
sys.path.insert(0, HERE)
sys.path.insert(0, HERE + "/../../..")
import common  # noqa: E402,F401
import hangul  # noqa: E402
import textenc  # noqa: E402

TSV = HERE + "/../docs/window-sites-1107.tsv"
CALC = {  # 이름표 최댓값으로 채운 칸(덫이 못 잡은 창) — 「계산」
    "0x80025828": "계산: 아이템 이름표 최장 102px",
    "0x80028664": "계산: 마법 이름표 최장 108px",
}


def main(files):
    cm = textenc.charmap()
    hm = {v: k for k, v in hangul.load().items()}
    half = set(hangul.half_codes())

    def px(c):
        return sum(6 if x in half else 12 for x in c)

    def txt(c):
        return "".join(hm.get(x) or cm.get(x, "?") for x in c)

    res = {}
    for f in files:
        opens = []
        for tag, a0, a1, a2, a3, ra, x, y, c, r, codes, *_raw in json.load(open(f)):
            if tag == 1:
                s = ra - 8
                opens.append((s, (a0, a1, a2, a3)))
                res.setdefault(s, {"strs": set(), "n": 0, "num": 0})
            elif tag in (2, 3, 4):
                for s, (oa0, oa1, oa2, _oa3) in reversed(opens):
                    if ((oa0 - 160) & 0xFFFF) == (x & 0xFFFF) and ((oa1 - 120) & 0xFFFF) == (y & 0xFFFF) and (oa2 & 0xFF) == c:
                        if tag == 4:
                            res[s]["num"] += 1
                        else:
                            res[s]["n"] += 1
                            if tag == 3 and _raw and _raw[0]:  # 이름 복사 버퍼: 첫 u16 은 머리(아이콘), 이름 코드열은 0xFFFF 로 끝난다
                                import struct

                                w = struct.unpack("<24H", bytes.fromhex(_raw[0]))[1:]
                                nm = []
                                for v in w:
                                    if v in (0xFFFF, 0, 0x8000, 0x8002) or v >= 0x4000:
                                        break
                                    nm.append(v)
                                codes = nm or None
                            if codes:
                                res[s]["strs"].add(tuple(codes))
                        break
    lines = open(TSV).read().splitlines()
    out = [lines[0], "\t".join(lines[1].split("\t")[:7]) + "\t덫(관측 — 이 순회에서 그려진 것 중 최장, 상한 아님: 열린 적·문자열 그림 수·숫자 그림 수·최장 px 문자열) | 계산(이름표)"]
    n_open = 0
    for ln in lines[2:]:
        c = ln.split("\t")[:7]
        s = int(c[0], 16)
        d = res.get(s)
        if d is None:
            t = "덫에 안 걸림(순회 경로 밖)"
        else:
            n_open += 1
            ss = sorted(((px(q), txt(q)) for q in d["strs"]), reverse=True)
            t = f"관측: 열림 · 문자열 {d['n']} · 숫자 {d['num']}" + (f" · 최장 {ss[0][0]}px {ss[0][1]}" if ss else "")
        if c[0] in CALC and not (d and d["strs"]):
            t += " | " + CALC[c[0]]
        out.append("\t".join(c) + "\t" + t)
    open(TSV, "w").write("\n".join(out) + "\n")
    print("열린 곳", n_open, "/", len(lines) - 2)


if __name__ == "__main__":
    main(sys.argv[1:])
