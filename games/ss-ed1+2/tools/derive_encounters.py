"""출현 문구를 **정본에서 유도한다** — `<몬스터>が現れた。` → `<이름>이(가) 나타났다.`

    python3 tools/derive_encounters.py           # 유도 결과만 보여 준다
    python3 tools/derive_encounters.py --write   # `script/system.json` 에 넣는다

## 왜 손으로 안 적나

이 꼴은 **몬스터 이름 + 정해진 접미**뿐이다. 손으로 적으면 (a) 이름 표기가 정본
(`shared/glossary` monster)과 갈라지고 (b) 조사를 사람이 고르다 틀린다. 이름과 조사를
정본·규칙에서 뽑으면 **두 이식판이 같은 이름을 쓰고** 조사도 늘 맞는다.

ED1 몫은 이미 이 형식으로 들어가 있다(`スライムの群れが現れた。` → `슬라임의 무리가
나타났다.`). 여기서는 같은 규칙으로 **ED2**(`/BIN/ED2MON*.BIN`) 몫을 낸다.

## 자리를 어떻게 찾나 — **포인터 대상만** 본다

`ED2MON*.BIN` 은 `[이름 표][SH-2 코드][텍스트]` 라 코드와 문자열이 NUL 없이 붙는다.
그래서 「NUL 로 자른 런」이 아니라 **BE32 포인터가 가리키는 자리**를 문자열의 시작으로
삼는다. ⚠ 이 파일군의 적재 주소는 **0x060E0000** 이다(`dump_scn.BASES`) — `ED.BIN` 의
0x06028000 을 쓰면 포인터가 한 곳도 안 잡힌다.

## 꼴 셋

    <이름>が現れた。            → <이름>이(가) 나타났다.
    <이름>の群れが現れた。       → <이름>의 무리가 나타났다.
    <A>と<B>が現れた。          → <A>과(와) <B>이(가) 나타났다.

⚠ `%c%s%c` 처럼 **런타임 인자**가 든 꼴은 건너뛴다 — 이름이 실행 중에 정해지므로 조사를
  정적으로 못 고른다(그건 조사 훅 몫이고 정본에 이미 병기로 들어 있다).
⚠ 정본에 없는 이름이 하나라도 있으면 **그 줄만** 건너뛰고 끝에 모아 보고한다. 조용히
  넘기지 않는다 — 한 줄만 일본어로 남아도 화면에서 바로 튄다.

## 🔴 자리도 여기서 잰다 — 이 파일들은 **총량이 늘면 못 넣는다**

`ED2MON*` 은 꽉 차 있어 재배치할 0런이 사실상 없다(ED2MON01·02 는 **0바이트**). 풀은
「우리 레코드 자리」가 전부라, 우리 문안 총량이 원본보다 커지면 재삽입이 죽는다.

그런데 우리 문안은 줄마다 **2바이트쯤 길다** — 원문 `が現れた。` 10B vs `이(가) 나타났다.`
12B(한국어는 띄어쓰기가 있다). 이름이 짧아진 만큼 상쇄되지만 다 상쇄되지는 않는다.

⚠ **문안을 줄여 맞추지 않는다.** PS1 도 `이(가) 나타났다.` 를 쓴다 — 여기서만 줄이면
  두 이식판의 표기가 갈린다. 대신 **자리에 안 들어가는 줄은 안 넣고 목록으로 보고**한다.
  그 줄은 일본어로 남지만, 어느 줄인지가 눈에 보인다.
"""

import json
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
from text.josa import josa

SYS_CANON = os.path.join(common.GAME_DIR, "script", "system.json")
FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]
SUFFIX = "が現れた。"
GROUP = "の群れ" + SUFFIX  # `<이름>の群れが現れた。`


def targets(path):
    """그 파일에서 **포인터가 가리키는** 문자열 전량 (cp932 로 읽히는 것만)."""
    d = bytes(common.extract(path))
    base = dump_scn.base_for(os.path.basename(path))
    assert base, path
    seen = set()
    for o in range(0, len(d) - 3, 2):
        v = struct.unpack(">I", d[o : o + 4])[0]
        if not (base <= v < base + len(d)):
            continue
        t = v - base
        j = t
        while j < len(d) and d[j] != 0:
            j += 1
        try:
            seen.add(d[t:j].decode("cp932"))
        except UnicodeDecodeError:
            pass
    return seen


def render(jp, mon):
    """`(우리 문안, 못 찾은 이름들)`. 유도가 안 되면 문안은 None."""
    if "%" in jp:  # 런타임 인자 — 조사를 정적으로 못 고른다
        return None, []
    if jp.endswith(GROUP):
        name = jp[: -len(GROUP)]
        kr = mon.get(name)
        return (f"{kr}의 무리가 나타났다." if kr else None), ([] if kr else [name])
    if not jp.endswith(SUFFIX):
        return None, []
    body = jp[: -len(SUFFIX)]
    if not body:
        return None, []
    parts = body.split("と")
    krs, miss = [], []
    for p in parts:
        kr = mon.get(p)
        (krs if kr else miss).append(kr or p)
    if miss:
        return None, miss
    # `A과(와) B이(가) 나타났다.` — 조사는 규칙이 고른다
    head = "".join(f"{k}{josa(k, '과/와')} " for k in krs[:-1])
    last = krs[-1]
    return f"{head}{last}{josa(last, '이/가')} 나타났다.", []


def main():
    common.verify_source()
    write = "--write" in sys.argv
    mon = table("monster")
    with open(SYS_CANON, encoding="utf-8") as f:
        doc = json.load(f)
    canon = doc["lines"]
    jps = set()
    for path in FILES:
        jps |= {s for s in targets(path) if s.endswith(SUFFIX)}

    from patch_ui import sys_key

    # 파일별로 「우리 자리 총량」과 「우리 문안 총량」을 견줘 넘치는 줄을 뺀다
    room = {}
    for path in FILES:
        d = bytes(common.extract(path))
        base = dump_scn.base_for(os.path.basename(path))
        for o in range(0, len(d) - 3, 2):
            v = struct.unpack(">I", d[o : o + 4])[0]
            if not (base <= v < base + len(d)):
                continue
            t = v - base
            j = t
            while j < len(d) and d[j] != 0:
                j += 1
            e = j
            while e < len(d) and d[e] == 0:
                e += 1
            try:
                room.setdefault(path, {})[d[t:j].decode("cp932")] = e - t
            except UnicodeDecodeError:
                pass

    add, have, skip, miss = {}, 0, [], {}
    tight = []
    for jp in sorted(jps):
        kr, bad = render(jp, mon)
        if bad:
            miss.setdefault(tuple(bad), []).append(jp)
            continue
        if kr is None:
            skip.append(jp)
            continue
        k = sys_key(jp)
        if k in canon:
            have += 1
            continue
        span = max((r.get(jp, 0) for r in room.values()), default=0)
        need = len(kr.encode("utf-8")) // 3 * 2 + sum(1 for c in kr if c.isascii()) + 1
        need = sum(1 if c.isascii() else 2 for c in kr) + 1
        if span and need > span:
            tight.append((jp, kr, need, span))
            continue
        add[k] = kr

    print(f"출현 문구 {len(jps)}종 — 이미 정본 {have} · 새로 유도 {len(add)} · 건너뜀 {len(skip)}")
    for k, v in list(add.items())[:12]:
        print(f"   {k} → {v!r}")
    if len(add) > 12:
        print(f"   … 그 외 {len(add) - 12}줄")
    if skip:
        print(f"  ⏭ 런타임 인자라 건너뜀: {skip}")
    if tight:
        print(f"  ⚠ 자리에 안 들어가 뺀 줄 {len(tight)}개 (그 줄은 일본어로 남는다):")
        for jp, kr, need, span in sorted(tight, key=lambda x: -(x[2] - x[3])):
            print(f"     +{need - span}B  {kr!r}  ({need}B > {span}B)  ← {jp!r}")
    if miss:
        print(f"  ❌ 정본에 없는 이름 {len(miss)}종 — 그 줄은 안 넣었다:")
        for names, lines in miss.items():
            print(
                f"     {list(names)} ← {lines[0]!r}{f' 외 {len(lines) - 1}' if len(lines) > 1 else ''}"
            )

    if not write:
        print("\n  (보기만 — 넣으려면 `--write`)")
        return
    canon.update(add)
    doc["lines"] = dict(sorted(canon.items()))
    with open(SYS_CANON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"\n  → {SYS_CANON} 에 {len(add)}줄 넣었다")


if __name__ == "__main__":
    main()
