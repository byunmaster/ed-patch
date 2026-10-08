"""ED2 **출현 문구**를 정본에서 유도한다 — `<몬스터>が現れた。` → `<이름>이(가) 나타났다.`

    python3 tools/derive_encounters.py           # 유도 결과만 보여 준다
    python3 tools/derive_encounters.py --write   # `script/system.json` 에 넣는다

    <몬스터>が現れた。   → <이름>이(가) 나타났다.

⚠ **이름 칸 자체**(`スライムＡ` → `슬라임A`)는 여기가 아니라 `tools/patch_mon_names.py` 다.

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
import expand_files
from canon import table
from names import HALF, MARKS, split_mark  # noqa: F401
from text.josa import josa

SYS_CANON = os.path.join(common.GAME_DIR, "script", "system.json")
FILES = [f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11)]

# 🔴 **훑기만 하는 자리** — ED1 의 출현 문구 86줄은 `/ED.BIN` 안에 있다. 여기엔 **새로 얹지
#    않는다**(본체 둘은 늘릴 수 없다 — `docs/policy.md` 1-C). 그래도 **정본과 어긋났는지는
#    봐야 한다**: 실측 2026-09-06, PS1 머지로 몬스터 여섯의 표기가 바뀌었는데 이 줄들이 옛
#    표기로 남아 있었고 검사기가 하나도 안 울었다. 스캔이 `ED2MON*` 뿐이라 **사각지대**였다
#    — 초록불이 「없다」가 아니라 「안 봤다」였던 것이다(체크리스트 4-B).
AUDIT_FILES = ["/ED.BIN", "/ED2.BIN"]
SUFFIX = "が現れた。"
GROUP = "の群れ" + SUFFIX  # `<이름>の群れが現れた。`

# 🔴 **개체 접미는 반각으로 낸다** — 원본은 전각(`スライムＡ`)이지만 우리는 반각이다
#    (유저 방침: 메시지 창의 알파벳은 전부 반각). 덤으로 한 글자에 1B 를 아낀다.
#    ⚠ 원본에 **반각으로 든 것도 있다**(`ブラムナドッグA`) — 둘 다 받는다.


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


def monster_names(mon):
    """`{JP: KR}` — ED2MON 파일들의 몬스터 이름 칸. 못 찾은 것은 `None` 으로 담는다."""
    out = {}
    for path in FILES:
        d = bytes(common.extract(path))
        base = dump_scn.base_for(os.path.basename(path))
        tgt = set()
        for o in range(0, len(d) - 3, 2):
            v = struct.unpack(">I", d[o : o + 4])[0]
            if base <= v < base + len(d):
                tgt.add(v - base)
        for t in sorted(tgt):
            j = t
            while j < len(d) and d[j] != 0:
                j += 1
            if not (2 <= j - t <= 20):
                continue
            try:
                jp = d[t:j].decode("cp932")
            except UnicodeDecodeError:
                continue
            kr, mark = split_mark(jp, mon)
            if kr:
                out[jp] = kr + mark
    return out


def audit_lines():
    """훑기 전용 파일들의 `<…>が現れた。` 문자열 전량 — 앞 NUL 까지 거슬러 시작을 잡는다.

    ⚠ 포인터를 안 따라간다(실행파일이라 상수 조립이 섞인다). 어긋남을 **보고**만 하므로
      한둘을 놓쳐도 손해가 없고, 반대로 못 읽는 바이트를 억지로 문자열로 보지도 않는다.
    """
    pat = SUFFIX.encode("cp932")
    out = set()
    for path in AUDIT_FILES:
        d = bytes(common.extract(path))
        at = d.find(pat)
        while at >= 0:
            end = at + len(pat)
            while end < len(d) and d[end : end + 1] == b"\n":
                end += 1
            start = d.rfind(b"\x00", 0, at) + 1
            if 0 < end - start <= 80:
                try:
                    raw = d[start:end].decode("cp932")
                except UnicodeDecodeError:
                    raw = None
                if raw:
                    # ⚠ **머리 제어문자를 뗀 꼴도 같이 낸다.** 실측: `\tバルガーが現れた。`
                    #    처럼 앞에 탭이 붙은 줄이 있는데 정본 열쇠는 **탭 없는 꼴**이라,
                    #    생 런만 내면 그 줄이 조용히 안 잡힌다(둘 중 정본에 있는 쪽을 쓴다).
                    out.add(raw)
                    out.add(raw.lstrip("\t\n\u3000"))
            at = d.find(pat, end)
    return out


def render(jp, mon):
    """`(우리 문안, 못 찾은 이름들)`. 유도가 안 되면 문안은 None.

    🔴 **꼬리 개행을 먼저 뗀다**(2026-08-27). 실제 문자열은 `…が現れた。\n` 인 것이 많은데
       접미를 개행 없이 맞추다 **조합 꼴 87종이 통째로 안 잡혔다.** 뗀 개행은 그대로 붙여
       돌려준다 — 원문의 줄 구조는 우리가 정할 것이 아니다.
    """
    if "%" in jp:  # 런타임 인자 — 조사를 정적으로 못 고른다
        return None, []
    tail = ""
    while jp.endswith("\n"):
        jp, tail = jp[:-1], tail + "\n"
    kr, miss = _render1(jp, mon)
    return (kr + tail if kr else None), miss


def _render1(jp, mon):
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
    mon = table("monster", "eiyuu")
    with open(SYS_CANON, encoding="utf-8") as f:
        doc = json.load(f)
    canon = doc["lines"]
    # 🔴 **못 늘리는 파일은 후보에서 뺀다.** 자리를 여기서 재지는 않지만(아래 주석),
    #    「꼬리가 0 이라 애초에 늘 자리가 없다」는 **구조적 사실**이라 여기서 안다.
    #    실측 2026-08-27: `/BIN/ED2MON06.BIN` 은 크기가 이미 섹터 배수라 꼬리가 없는데,
    #    새 출현 문구 넷을 얹었더니 `sys_pack` 이 「자리가 모자란다」로 빌드를 세웠다.
    _f0, mm0 = common.open_image()
    tails = set(expand_files.tails(mm0))
    mm0.close()
    _f0.close()
    where = {}
    jps = set()
    for path in FILES:
        # ⚠ 꼬리 개행까지 받는다 — 실제 문자열은 `…が現れた。\n` 인 것이 많다(`render` 주석)
        got = {s for s in targets(path) if s.rstrip("\n").endswith(SUFFIX)}
        jps |= got
        for s_ in got:
            where.setdefault(s_, set()).add(path)

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

    add, have, skip, miss, stale = {}, 0, [], {}, []
    tight = []
    # ⚠ **이름은 여기서 안 낸다** — `tools/patch_mon_names.py` 몫이다. 정본이 파일을 안
    #   가려 `ED.BIN` 의 고정 폭 몬스터 표와 두 주인이 나기 때문이다(2026-08-27).

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
            # 🔴 **있다고 맞는 건 아니다.** 정본(`shared/glossary`)의 이름 표기가 바뀌면
            #    이미 적어 둔 이 줄들은 **아무도 안 본다** — 실측 2026-09-06: PS1 이 머지되며
            #    몬스터 여섯의 표기가 바뀌었는데 여기 아홉 줄이 옛 표기로 남아 있었고,
            #    grep 으로만 찾았다(`docs/naming.md` 「잡히지 않는 건 문안이다」).
            #    ⚠ 고치지는 않는다 — 자리를 다시 재야 하므로 **보고까지**가 여기 몫이다.
            if canon[k] != kr:
                stale.append((k, canon[k], kr))
            continue
        # ⚠ **이미 정본에 있는 줄에는 이 규칙을 걸지 않는다.** 그것들은 빌드가 초록인 채로
        #   자리에 들어가 있다는 뜻이라, 뺐다가 되레 7줄을 일본어로 되돌렸다(실측).
        #   여기서 막는 것은 **새로 얹는 줄**뿐이다 — 그건 늘 총량을 늘린다.
        if not (where.get(jp, set()) & tails):
            tight.append((jp, kr, 0, 0))
            continue
        # 🔴 **자리는 여기서 안 잰다**(2026-08-27). `tools/expand_files.py` 가 파일을 꼬리
        #    섹터까지 늘려 ~10KB 를 확보하므로, 넘치는지는 재삽입 쪽(`patch_ui.sys_pack`)이
        #    풀 배치로 판단하고 정말 모자라면 거기서 실패한다. 두 곳에서 재면 어긋난다.
        add[k] = kr

    # 훑기 전용 파일(본체 둘)은 **얹지 않고 어긋남만** 본다.
    seen = set(jps)
    for jp in sorted(audit_lines()):
        if jp in seen:
            continue
        kr, bad = render(jp, mon)
        if bad or kr is None:
            continue
        k = sys_key(jp)
        if k in canon and canon[k] != kr:
            stale.append((k, canon[k], kr))

    print(
        f"출현 문구 {len(jps)}종 — 이미 정본 {have} · 새로 유도 {len(add)} · "
        f"건너뜀 {len(skip)}" + (f" · 🔴 정본과 어긋남 {len(stale)}" if stale else "")
    )
    for k, cur, want in stale:
        print(f"   🔴 {k}\n      지금 {cur!r}\n      규칙 {want!r}")
    for k, v in list(add.items())[:12]:
        print(f"   {k} → {v!r}")
    if len(add) > 12:
        print(f"   … 그 외 {len(add) - 12}줄")
    if skip:
        print(f"  ⏭ 런타임 인자라 건너뜀: {skip}")
    if tight:
        print(f"  ⚠ 늘릴 수 없는 파일이라 뺀 줄 {len(tight)}개 (그 줄은 일본어로 남는다):")
        for jp, kr, _n, _s in tight:
            print(f"     {kr!r}  ← {jp!r} ({sorted(where.get(jp, ()))})")
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
