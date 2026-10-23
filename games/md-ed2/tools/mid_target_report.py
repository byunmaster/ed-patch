"""한복판 목표 보고 — 원판에서 다른 스트림 범위 안에서 시작하는 스트림(목표)마다, 정본 번역이 바깥 스트림 번역의 꼬리인지 맞댄다.
게이트 아님(정보용 표). 같은 문장이 두 스트림에 따로 번역돼 낱말이 갈리는지 본다 — 롬 바이트 단위 대조는 다음 라운드(status).
사용: python3 mid_target_report.py [표.tsv]   종류: suffix-ok(꼬리 일치) · empty-inner(안쪽 번역 빔) · MISMATCH(꼬리가 아님 — 눈으로 가른다)
"""

import collections
import json
import re
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import archives
import common
import scene

orig = common.rom()
TAGR = re.compile(r"<[0-9a-f:]+>")


def plain(s):
    return re.sub(r"\s+", "", TAGR.sub("", s))


res = collections.Counter()
rows = []
for blk, k, om in archives.modules(orig):
    m = scene.parse_module(om)
    tag = f"{blk:03d}-{k}"
    sp = common.GAME_DIR / "script" / f"{tag}.json"
    if not sp.exists():
        continue
    sc = json.loads(sp.read_text(encoding="utf-8"))["streams"]
    sts = sorted(m.streams.items())
    for s2, st2 in sts:
        offs = [t.off for t in st2.tokens]
        for s, _st in sts:
            if s == s2:
                continue
            inside = st2.start < s < max(st2.end, st2.start)
            if not inside:
                continue
            kind = "boundary" if s in offs else "in-token"
            e = sc.get(f"{s2:04x}", {}).get("ours")
            i = sc.get(f"{s:04x}", {}).get("ours")
            if e is None or i is None:
                res[(kind, "no-script")] += 1
                rows.append((tag, hex(s2), hex(s), kind, "no-script"))
                continue
            if i == "":
                res[(kind, "empty-inner")] += 1
                rows.append((tag, hex(s2), hex(s), kind, "empty-inner"))
                continue
            pe, pi = plain(e), plain(i)
            # 안쪽 글(끝 제어 앞)이 바깥 글의 꼬리인가 — 꼬리 24자
            tail = pi.split("<")[0][:24] if False else pi[:24]
            ok = pi in pe or (len(pi) > 0 and pi[:20] in pe)
            res[(kind, "suffix-ok" if ok else "MISMATCH")] += 1
            if not ok:
                rows.append((tag, hex(s2), hex(s), kind, "MISMATCH", i[:40], e[-60:]))
print(res)
import csv

if len(sys.argv) > 1:
    with open(sys.argv[1], "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        for r in rows:
            w.writerow([str(x).replace("\t", " ").replace("\n", " ") for x in r])
