"""씬 대사 재삽입 — **자유 구간 안에서 다시 깔고 포인터를 고친다**.

    python3 tools/patch_scn.py --check     # 🔴 항등 검증: 원문을 그대로 다시 깔아 바이트 동일인가
    python3 tools/patch_scn.py             # 우리 문안으로 계획·검산만
    python3 tools/patch_scn.py --apply     # 빌드 이미지에 넣는다

⚠ 순서상 **UI 다음**이다 — 씬 파일은 UI 가 지명 헤더를 이미 고쳤다.

## 🔴 착수 전에 읽은 것 — 「구조 계약」(`docs/reference/our-findings.md`)

PS1 에서 이 층은 **소프트락을 여러 번** 냈다. 새턴도 같은 팔콤 툴체인이고, 오늘 나누기
함수에서 **`%c` 가 이미 1바이트 제어코드로 치환된 것**을 봤다 — 즉 여기도 sprintf 구조다.
그래서 PS1 의 계약 넷을 그대로 가져온다:

    ① 창 수      — 재조립본의 `%c` 가 원본보다 **적으면 소프트락**(엔진이 원본 개수만큼 읽는다)
    ② 인자 수·순서 — `%s`·`%d` 는 인자 소비 스텝이다. 줄면 뒤 인자가 전부 밀린다
    ③ 미참조 핀   — 「포인터로 참조되지도, 번역되지도 않는 블록」은 **이동 금지**
    ④ 위치       — 구조가 같아도 **블록이 줄어 뒤가 당겨지면** 이벤트가 깨진다(실측: −12B 정상,
                   −20B 목적지 어긋남, −32B 락). 그래서 **자유 구간 단위로 원본 길이를 고정**한다

## 이 도구가 지금 하는 일 — **항등 검증까지**

번역 저본이 아직 없다(`line_dict.json` 은 PS1 재작성 대기 — status 「남은 일」 1).
그래서 먼저 **파이프라인의 정확성**을 못 박는다:

    원문을 그대로 다시 깔았을 때 **이미지가 바이트 하나 안 틀리면**,
    자르기·재배치·포인터 갱신이 전부 맞다는 뜻이다.

이게 통과해야 문안을 얹을 수 있다. 통과 못 하면 **번역이 아니라 도구가 범인**이다.

## 자리 — 자유 구간

씬 파일은 `[지명 헤더 12B][SH-2 코드][텍스트]` 가 지역 단위로 반복된다(status 3절).
**텍스트 구간만** 다시 깐다. 구간의 경계는 **포인터가 가리키는 블록들의 앞뒤**이고,
구간 길이는 **원본 그대로 유지**한다(계약 ④) — 짧으면 0 으로 채운다.
"""

import json
import os
import re
import subprocess
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
from text.line_key import key as line_key

DUMP = os.path.join(common.OUT_DIR, "scn_jp")
# 🔴 저본은 **PS1 이 만드는 사전** 하나뿐이다 — `script/` 는 43%(ED1)·93%(ED2)가 정발
#    유래라 못 쓴다(status 4절). 키는 공용(`shared/text/line_key`)이라 덤퍼 표기가 달라도
#    붙는다 — 실측 84.2%(ED1SCN 95.6% · ED2SCN 96.0%).
#    ⚠ 그 파일은 **PS1 게임 트리**에 있고 아직 main 에 안 올라와 이 브랜치에서는 안 보인다.
#      그래서 **그쪽 브랜치의 커밋된 blob** 을 읽는다(`git show`).
#
# 🔴 **PS1 워크트리의 파일을 직접 읽지 않는다**(2026-08-29 전환). 그건 남의 세션이 **저장할
#    때마다** 우리 이미지를 바꾼다 — 실측으로 한 시간 사이 사전이 18,146→18,251 이 되며
#    저본 미비가 1,440→1,422 로 움직였다. 레포 **제1 원칙(빌드는 결정적이어야 한다)** 에
#    정면으로 걸리고, 저장 중인 반쪽짜리 파일을 읽을 위험도 있다. 커밋 단위면 그 둘이 없어진다.
#    (조판 지문 도구가 남의 브랜치 값을 읽는 방식과 같다 — `scripts/check/typeset_fingerprint.py`)
# ⚠ 완전한 못박기(커밋 sha 고정)까지는 안 간다 — 그쪽 인게임 QA 의 문안 수정이 안 들어와
#   손해가 크다. 대신 **어느 커밋을 읽었는지 찍는다**(수치를 적을 때 같이 적는다).
_ROOT = os.path.dirname(os.path.dirname(common.GAME_DIR))
LINE_DICT = os.path.join(_ROOT, "games", "ps1-ed1+2", "line_dict.json")
LINE_DICT_REF = "game/ps1-ed1+2:games/ps1-ed1+2/line_dict.json"
# 🔴 **본체 둘도 대사를 갖는다** — ED2 오프닝 프롤로그가 `/ED2.BIN` 안에 있다(실측: 저본이
#    ED.BIN 419 · ED2.BIN 145 블록에 붙는다). 씬 파일이 아니라고 빼 두면 그만큼이 영영
#    일본어로 남는다. 대신 그 둘은 **주인이 여럿**이라(시스템 메시지 · 표 · 고유명사 ·
#    자막 · 훅) 「이미 쓰인 자리엔 안 쓴다」 장치가 필수다(`already_written`).
SCN_RE = re.compile(r"^(/BIN/(ED1SCN|ED2SCN|ED2MON)\d+|/ED2?)\.BIN$")
FMT = re.compile(r"%[csd]")

# 🔴 **구간을 어디서 끊나** — 블록 사이 빈틈으로 가른다. 실측 분포가 깨끗하게 둘로 갈린다:
#    **1~4B**(널 종단 + 4바이트 정렬, 925건)와 **64B 초과**(사이에 SH-2 코드가 낀 자리, 83건).
#    그 사이 값은 6B 하나뿐이다. 그래서 8B 를 경계로 둔다 — 넘으면 **다른 구간**이다.
#    ⚠ 이걸 안 가르면 구간이 파일 전체가 되어 **코드까지 덮어쓴다**(첫 시도가 그랬다).
MAX_GAP = 8


def contract(text):
    """구조 계약 지문 — `('%c%s%d…' 순서열, 개수)`. 이게 어긋나면 넣지 않는다.

    🔴 **규칙은 `typeset_scn` 이 정본이다** — 조판기가 자기 계약을 보는 그 함수와 같아야
       한다. 여기서 따로 세면 「조판기는 통과시키고 재삽입이 거절하는」 어긋남이 생긴다.
    """
    from typeset_scn import contract as seq_of

    seq = seq_of(text)
    return seq, len(seq)


def load(path):
    """그 파일의 덤프 → `(base, [entry])`. 없으면 None."""
    name = os.path.basename(path).replace(".BIN", ".json")
    p = os.path.join(DUMP, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return int(d["source"]["base"], 16), d["entries"]


def runs(entries, size):
    """**자유 구간** — 포인터로 참조되는 블록들이 이어진 덩어리.

    🔴 구간 단위로 **원본 길이를 고정**한다(계약 ④). 한 블록만 고정하면 소용없다 —
       앞 블록이 줄면 같이 당겨진다.
    ⚠ `ptr_at` 이 빈 항목은 **핀**이다(계약 ③). 구간을 거기서 끊어 절대 안 옮긴다.
    """
    items = []
    for e in entries:
        off = int(e["file_offset"], 16)
        raw = bytes.fromhex(e["raw_hex"])
        items.append((off, len(raw), e))
    items.sort()
    out, cur = [], []
    for off, n, e in items:
        pinned = not e.get("ptr_at")
        if pinned:
            if cur:
                out.append(cur)
                cur = []
            continue
        if cur and not (0 <= _gap(cur[-1], off) <= MAX_GAP):
            out.append(cur)  # 사이에 코드가 낀다 — 여기서 끊는다(위 MAX_GAP 주석)
            cur = []
        cur.append((off, n, e))
    if cur:
        out.append(cur)
    return out


def _gap(prev, off):
    """앞 블록 끝과 다음 블록 시작 사이의 빈틈(널 패딩). 구간을 끊지 않는다."""
    return off - (prev[0] + prev[1])


def owned_elsewhere(path):
    """그 파일에서 **다른 패처가 주인인 오프셋** — 우리는 비켜 준다.

    🔴 `/BIN/ED2MON*` 의 **몬스터 이름 칸은 `patch_mon_names` 것**이다. 씬 덤프에도 같은
       자리가 블록으로 잡혀 저본이 붙는데(186칸 실측 2026-08-27), 그쪽 표기는 접미가
       **전각**(`불꽃의기사Ａ`)이라 전투 화면(반각 `A`)과 갈린다. 체인 순서상 뒤에 도는
       이름 패처가 이겨서 화면은 멀쩡했지만, **두 주인은 순서 하나로 뒤집힌다.**
    ⚠ 늦게 부른다 — `patch_mon_names` 가 `patch_ui` 를 거쳐 우리를 부른다(순환).
    """
    return _mon_slots(path) | _sys_slots(path) | _tab_slots(path)


_SYS = None


def _sys_slots(path):
    """`patch_ui` 가 시스템 메시지로 쓰는 자리 — 씬은 거기에 안 넣는다(두 주인 금지)."""
    global _SYS
    if _SYS is None:
        import patch_ui

        _f, mm = common.open_image()
        _SYS = {}
        for r in patch_ui.sys_rows(mm):
            _SYS.setdefault(r[0], set()).add(r[3])
        mm.close()
        _f.close()
    return frozenset(_SYS.get(path, ()))


_TAB = None


def _tab_slots(path):
    """`patch_ui` 의 **고정폭 UI 표**가 쓰는 자리 — 메뉴·전투 명령·능력치 라벨이다.

    🔴 이게 빠져 있었다(2026-08-29). 그 표는 `patch_ui.rows()` 가 **정본을 강제**해
       (없으면 assert) 한글을 쓰는데, 우리 쪽 「남의 자리」 목록에 없어서 **씬 스캐너가
       「저본에 없는 일본어」로 세고 있었다.** 실측: `戦う`·`強さ`·`買いたい` 등 일곱이
       이미 번역돼 있는데 번역 대상으로 페이로드에 실렸다 — 하마터면 **이미 있는 것을
       또 번역**할 뻔했다(파일럿에서 잡은 사고와 같은 종류다).
    ⚠ 스트라이드 안의 **첫 바이트만** 담는다 — 씬 덤프도 그 자리를 블록 시작으로 잡는다.
    """
    global _TAB
    if _TAB is None:
        import dump_ui
        import patch_ui  # noqa: F401  (표 정의는 dump_ui 가 든다)

        _TAB = {}
        for key, fpath in dump_ui.FILES.items():
            buf = common.extract(fpath)
            col = 0 if key == "ED" else 1
            for _name, ed, ed2, stride, n, n2 in dump_ui.TABLES:
                off = (ed, ed2)[col]
                if off is None:
                    continue
                cnt = n2 if (col == 1 and n2) else n
                for jp, at, _slack in dump_ui.read_table(buf, off, stride, cnt):
                    if jp:
                        _TAB.setdefault(fpath, set()).add(at)
    return frozenset(_TAB.get(path, ()))


def _mon_slots(path):
    if not path.startswith("/BIN/ED2MON"):
        return frozenset()
    import patch_mon_names
    from glossary import table

    return frozenset(t for t, _jp, _kr in patch_mon_names.slots(path, table("monster")))


# 🔴 **옮기면 안 되는 자리** — 코드가 포인터가 아니라 **절대주소로 집는** 칸이 있다.
#    실측 2026-08-28: `/ED.BIN` 0x44BC8 의 HUD 접미 표(`入口`·`付近`·`北`…)는 2~4B 이고
#    포인터도 있는데, 조립 루틴이 그 자리에서 4B 를 직접 집는다. 비워서 남에게 내줬더니
#    화면에 `メ§電 リ…처` 가 떴다. **표는 잘고 산문은 길다**를 경계로 쓴다(`VACATE_MIN`).
#    ⚠ 여기에 하나 더 — **같은 간격으로 이어지는 블록은 표로 본다**(색인으로 집힌다).
STRIDE_RUN = 4  # 같은 간격이 이만큼 이어지면 표


def _stride_table(run):
    """같은 간격으로 이어지는 블록들의 오프셋 — **표**라 안 옮긴다."""
    out = set()
    i = 0
    while i < len(run) - 1:
        step = run[i + 1][0] - run[i][0]
        j = i + 1
        while j < len(run) - 1 and run[j + 1][0] - run[j][0] == step:
            j += 1
        if j - i + 1 >= STRIDE_RUN:
            out.update(run[k][0] for k in range(i, j + 1))
        i = max(j, i + 1)
    return out


def _movable(off, n, e, table=frozenset()):
    """그 블록을 **옮겨도 되나** — 포인터가 있고, 잘지 않고, 표가 아니어야 한다.

    🔴 **마크업이 없으면 표로 본다**(2026-09-04). 대사 블록은 창 종단 `%c` 를 갖는데
       아이템·몬스터 **이름 칸**은 맨 이름뿐이다. 그리고 그 이름들은 코드가 **색인으로**
       집는다 — 옮기면 포인터를 고쳐도 화면이 **한 글자 밀려** 읽는다.
       실측 2026-09-04: 구간 압축을 넣자 `/ED.BIN` 의 아이템·몬스터 이름 표가 통째로
       밀려 인벤토리에 「디논A」(= 「오디논A」의 뒤 세 글자)가 떴다.
    ⚠ 이건 08-28 에 세운 「표는 잘고 산문은 길다」(`VACATE_MIN`)의 확장이다 — 그때는
      2~4B 라 길이로 갈렸는데, 이름 칸은 8~14B 라 길이로는 안 갈린다.
    """
    return (
        bool(e.get("ptr_at")) and n >= VACATE_MIN and off not in table and "%c" in e.get("text", "")
    )


def _needs_pack(run, canon, d, skip_offs, built, sites):
    """이 구간에 **제 칸을 넘는 블록**이 있나 — 있으면 구간을 통째로 다시 깐다."""
    if not canon:
        return False
    for idx, (off, n, e) in enumerate(run):
        if off in skip_offs:
            continue
        span = (run[idx + 1][0] - off) if idx + 1 < len(run) else n
        jp = e.get("text", "")
        kr = canon_of(canon, jp, (sites or {}).get(off))
        if kr is None or contract(kr) != contract(jp):
            continue
        if len(_encode(kr)) + 1 > span:
            return True
    return False


def rebuild(
    run, canon, d, skip_offs=frozenset(), built=None, spare=None, sites=None, done=None, spans=None
):
    """`(새 바이트, [(ptr_at, 새 주소 오프셋)], [건너뛴 이유])` — 구간을 다시 깐다.

    ⚠ **구간 총 길이는 원본 그대로**다. 남으면 0 으로 채운다(계약 ④).

    ⚠ `spare` 에 리스트를 주면 **문안이 짧아져 남는 칸 뒷부분**을 `(오프셋, 크기)` 로 담아
      준다. 그 자리는 살아 있는 칸 안이지만 **종단 NUL 뒤라 엔진이 안 읽고**, 포인터가
      안쪽을 가리키는 칸도 없다(실측 0건). 이주 풀의 셋째 원천이다 — 82,003B.
    """
    start = run[0][0]
    end = run[-1][0] + run[-1][1]
    room = end - start
    blob = bytearray()
    moves, skipped = [], []
    # 🔴 **한 칸이라도 넘치면 그 구간은 통째로 다시 깐다**(2026-09-04). 블록을 제 칸에 두면
    #    남는 자리가 **칸마다 조각**으로 갈려, 총량이 남는데도 큰 문안이 갈 데가 없다 —
    #    실측: ED2 프롤로그 구간(145블록)은 우리 문안이 원본보다 **1,007B 작은데도** 넷이
    #    못 들어갔다(각자 제 칸에서 2~11B 씩 넘쳐서).
    #    ⇒ 넘치는 구간만 **모든 옮길 수 있는 블록**을 이주 풀에 넘긴다. 배치는 `migrate` 가
    #      한다(FFD · 짝수 주소 · 인접 병합 · 못 놓은 것의 칸은 안 내주는 고정점).
    #    ⚠ **안 넘치는 구간은 손대지 않는다** — 옮길 이유가 없는데 옮기면 포인터만 흔든다.
    packed = _needs_pack(run, canon, d, skip_offs, built, sites)
    table = _stride_table(run) if packed else frozenset()
    for idx, (off, n, e) in enumerate(run):
        # 🔴 **블록은 자기 칸에 머문다 — 당기지 않는다.** 칸은 `(내용+NUL)` 을 4바이트
        #    올린 크기인데(실측 676/676), 그 **꼬리 마지막 바이트가 `0x09` 인 자리가 많다**
        #    (`00 00 00 09` 182건 · `00 00 09` 138건). 그건 패딩이 아니라 **다음 블록의
        #    시작 마커**다 — 블록을 앞으로 당기면 이 마커가 통째로 어긋난다.
        #    ⇒ 꼬리는 **원본 바이트를 그대로** 두고, 내용만 칸 안에서 바꾼다.
        #    ⚠ 그래서 이 도구는 「칸 안에서만」이다. 칸을 넘는 문안은 **확장 영역 이주**가
        #      따로 필요하다(PS1 이 쓴 2단계 — 원본 자리엔 JP 를 남기고 참조만 새 주소로).
        span = (run[idx + 1][0] - off) if idx + 1 < len(run) else n
        raw = bytes.fromhex(e["raw_hex"])
        jp = e.get("text", "")
        site = (sites or {}).get(off)
        kr = None if off in skip_offs else canon_of(canon, jp, site)
        use = raw
        if kr is not None:
            if contract(kr) != contract(jp):
                skipped.append((off, "구조 계약이 다르다", jp[:18], e, None))
            elif len(_encode(kr)) > n:
                # 🔴 한계는 칸(span)이 아니라 **원문 바이트 수(n)** 다 — 칸 꼬리에는 다음
                #    블록의 시작 마커(`0x09`)가 들어 있어 그만큼은 못 쓴다. `span-1` 로
                #    쟀다가 꼬리가 2B 인 자리에서 1B 넘쳤다(실측 ED1SCN12 0x4854).
                # ⚠ 인코딩을 **여기서 들고 나간다** — 확장 영역으로 이주할 쪽이 다시
                #   조판·인코딩하면 두 곳에서 갈릴 수 있다(같은 문안을 두 번 만들지 않는다).
                enc = _encode(kr)
                skipped.append((off, f"칸을 넘는다 {len(enc)}B > {n}B", jp[:18], e, enc))
            elif packed and _movable(off, n, e, table):
                # 구간을 다시 깐다 — 자리는 `migrate` 가 정하고 여기선 원본을 남긴다
                skipped.append((off, "구간을 다시 깐다", jp[:18], e, _encode(kr)))
            else:
                use = _encode(kr)
                if done is not None:
                    done.append(off)
        # 🔴 **남이 이미 쓴 자리엔 안 넣는다** — 본체 둘은 시스템 메시지·표·고유명사·자막이
        #    같은 파일을 나눠 갖는다. 주인 목록을 손으로 들면 새 패처가 생길 때마다 조용히
        #    새므로 **구조로 묻는다**: 빌드가 원본과 다르고 **우리 것도 아니면** 남의 것이다.
        #    ⚠ 「우리 것도 아니면」이 핵심이다. 빌드 사본은 회차 사이에 남으므로(patch_title 은
        #      없을 때만 복사한다) 그 조건을 빼면 **지난 회차의 우리 문안까지** 남의 것으로
        #      보고 전부 비켜 간다 — 실측 2026-08-27: 삽입이 997 → 5 로 내려앉았다.
        if built is not None:
            cur = built[off : off + n]
            if cur != raw and cur != use + b"\x00" * (n - len(use)):
                use = raw
                skipped.append((off, "남이 이미 쓴 자리다", jp[:18], e, None))
                if done is not None and done and done[-1] == off:
                    done.pop()
        moves.append((e.get("ptr_at", []), start + len(blob)))
        # 칸 = [내용][NUL 채움][원본 꼬리]. 🔴 꼬리를 **끝에 붙여야** 마커가 제자리다 —
        # `d[off+len(use):]` 로 이어 붙이면 짧아진 만큼 원본이 밀려 들어와 **아무것도 안
        # 바뀐 것처럼** 된다(합성 시험이 잡았다).
        # 🔴 **남는 자리는 칸 꼬리까지다**(2026-09-04). 꼬리(NUL + 0 채움 + 이따금 `0x09`)를
        #    빼고 세면 조각이 1~4B 씩 잘려 나가 **총량이 남는데도 못 넣는** 상태가 된다.
        #    `0x09` 가 무의미하다는 건 실기로 확인했다 — 「그 바이트가 무엇인가」 절.
        if spare is not None and use is not raw and span - len(use) - 1 >= 2:
            spare.append((off + len(use) + 1, span - len(use) - 1))
        if spans is not None:
            spans[off] = span
        tail = d[off + n : off + span]
        blob += use + b"\x00" * (span - len(use) - len(tail)) + tail
    assert len(blob) == room, f"구간 0x{start:X}: {len(blob)}B ≠ {room}B"
    return bytes(blob), moves, skipped


def all_texts(mm=None):
    """조판까지 끝난 **씬 문안 전량** — 슬롯 계획을 세우는 쪽(`patch_ui`)이 부른다.

    🔴 슬롯 계획은 **모든 소비자를 한 번에** 받아야 한다. 씬 문안만으로 `--refresh` 를
       돌렸다가 UI 글자 10자가 밀려났다(2026-08-27) — `slot_plan` 은 `need` 에 없는
       글자를 버린다.
    ⚠ 여기서 `patch_ui` 를 import 하지 않는다(순환) — 계획은 저쪽이 만들고 우리는 읽는다.
    """
    canon = load_canon(quiet=True)
    if not canon:
        return []
    close = mm is None
    if close:
        _f, mm = common.open_image()
    canon = augment_names(canon, mm)  # 슬롯 계획도 그 이름들의 글자를 받아야 한다
    out = []
    for path, _lba, _size in common.iso_files(mm):
        if not SCN_RE.match(path):
            continue
        got = load(path)
        if not got:
            continue
        sites = sites_for(path)
        for e in got[1]:
            kr = canon_of(canon, e.get("text", ""), sites.get(int(e["file_offset"], 16)))
            if kr:
                out.append(kr)
    if close:
        mm.close()
        _f.close()
    return out


def load_canon(quiet=False):
    """`{JP 원문: 우리 문안}` — 사전을 **원문 그대로** 못 들고 있으므로 키로 붙인다.

    ⚠ 사전은 다른 게임 트리(`games/ps1-ed1+2/line_dict.json`)에 있다. 이 트리에 있으면
      그걸 쓰고(=main 에 올라왔다), 없으면 **PS1 브랜치의 커밋된 blob** 을 읽는다.
      둘 다 없으면 빈 것을 돌려준다 — 사전 없이도 항등 검증은 돌아야 한다.
    """
    if os.path.exists(LINE_DICT):
        with open(LINE_DICT, encoding="utf-8") as f:
            raw, where = f.read(), "이 트리"
    else:
        r = subprocess.run(
            ["git", "show", LINE_DICT_REF], cwd=_ROOT, capture_output=True, text=True, check=False
        )
        if r.returncode or not r.stdout.strip():
            if not quiet:
                print("  ⚠ 저본을 못 찾았다 — 원문 그대로 둔다 (PS1 의 `line_dict.json`)")
            return {}
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "game/ps1-ed1+2"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        raw, where = r.stdout, f"game/ps1-ed1+2 {sha}"
    lines = json.loads(raw)["lines"]
    got = {k: v["t"] for k, v in lines.items() if isinstance(v, dict) and v.get("t")}
    # 🔴 **새턴 전용 문안을 덮어 얹는다** — PS1 사전이 영영 못 채우는 자리다(781블록:
    #    이식판이 갈린 문안 763 + 저작권 분류로 막힌 19). 겹치면 우리 것이 이긴다.
    # ⚠ **정본 이름과 통째로 같은 블록**은 사전을 안 거친다 — 아이템·지명이 한 블록으로
    #   따로 놓인 자리다(실측: ED2 마법서 23종 `フラムの書`). 사전은 문장을 담으니 여기엔
    #   영영 안 온다. 규칙 한 줄로 잇는다 — 정본이 곧 답이다.
    #   🔴 사전을 **안 덮는다** — 같은 원문이 문장으로도 쓰이면 문장 쪽이 옳다.
    named = name_keys()
    add = {k: v for k, v in named.items() if k not in got}
    got.update(add)
    ours = load_ours()
    got.update(ours)
    if not quiet:
        print(
            f"  저본 {len(got):,}원문 — {where} + 정본 이름 {len(add):,} + 새턴 전용 {len(ours):,}"
        )
    return got


def _names():
    """고유명사 정본 — ⚠ `typeset_scn` 이 임포트 시점에 우리를 부르므로 여기서 늦게 읽는다."""
    from typeset_scn import _names as f

    return f()


_NAMEKEY = None


def name_keys():
    """`{열쇠: 우리 표기}` — 정본 이름과 **통째로 같은 블록**을 잇는다.

    사전은 문장을 담으니 이름 한 덩어리인 블록엔 영영 안 온다(마법서 23종 · 항로 라벨 ·
    반각 가나 몬스터 칸). ⚠ 개체 접미(`Ａ`~`Ｊ`·`♀♂`)는 떼어 밑말로 찾고 **반각**으로 다시
    붙인다 — 전각으로 붙이면 전투 화면(반각)과 갈린다(`patch_mon_names` 와 같은 규약).
    """
    global _NAMEKEY
    if _NAMEKEY is None:
        _NAMEKEY = {line_key(jp): kr for jp, kr in _names().items()}
    return _NAMEKEY


def augment_names(canon, mm):
    """이미지의 **이름 한 덩어리 블록**을 정본에 붙여 `canon` 을 불린다 — 새 사전을 돌려준다.

    🔴 여기서 하는 이유: `_canon_get`·`rebuild` 는 **인자로 받은 사전만** 봐야 한다.
       거기서 정본을 직접 들추면 같은 입력에 다른 답이 나오고, 합성 시험(원본 없이 도는
       회귀)이 진짜 정본을 끌어와 깨진다(실측 2026-08-29).
    ⚠ 이미지 쪽 변종은 **열거할 수 없다**(폭 맞춤 공백이 임의로 낀다). 그래서 정본에서
      변종을 만들어 내는 게 아니라 **이미지의 문자열을 정규화해 정본에 붙인다.**
    """
    add = {}
    for path, _lba, _size in common.iso_files(mm):
        if not SCN_RE.match(path):
            continue
        got = load(path)
        if not got:
            continue
        for e in got[1]:
            jp = e.get("text", "")
            if not jp:
                continue
            k = line_key(jp)
            if k in canon or k in add:
                continue
            kr = name_for(jp)
            # 🔴 **반각 가나가 섞인 것은 내부 키다 — 건드리면 자료를 부순다.**
            #    `patch_ui._internal_key` 가 이미 못 박아 둔 규칙인데 우리가 안 보고
            #    번역했다(실측 2026-08-29: 19곳. `ｴﾙｱｽﾀ` · `ﾃﾞｽ･ｶﾞｰﾃﾞｨｱﾝＢ` …).
            #    화면에 나가는 이름은 **원본이 전부 전각**이라, 반각 가나가 하나라도
            #    섞였으면 그건 코드가 찾는 열쇠다.
            if kr and not _internal_key(jp):
                add[k] = kr
    if add:
        canon = dict(canon)
        canon.update(add)
    return canon


def _internal_key(jp):
    """**게임 내부 키**인가 — 🔴 규칙은 `names.internal_key` 가 정본이다."""
    from names import internal_key

    return internal_key(jp)


def name_for(jp):
    """원문 한 덩어리 → 우리 표기. 반각·공백·개체 접미를 흡수한다. 없으면 None.

    🔴 규칙은 `names.py` 가 정본이다 — 여기·`patch_mon_names`·`derive_encounters` 가 각자
       표를 들다 **답이 갈렸다**(2026-08-29). 우리는 조회만 한다.
    """
    from names import lookup

    return lookup(jp, _names())


SCN_CANON = os.path.join(common.GAME_DIR, "script", "scn.json")


def load_ours():
    """`{키: 우리 문안}` — 새턴 전용 씬 문안(`script/scn.json`)."""
    if not os.path.exists(SCN_CANON):
        return {}
    with open(SCN_CANON, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f)["lines"].items() if v}


_NAMES = None


def _canon_get(canon, jp, jp_mark=None, why=None):
    """원문 → **조판까지 끝난** 우리 블록. 없거나 조판이 안 되면 None.

    🔴 사전은 **문안만** 담는다(화자·창 전환·개행이 없다). 그대로 넣으면 구조 계약이
       깨져 소프트락이 나므로 `typeset_scn` 이 원문 마크업을 다시 입힌다.
    ⚠ **찾는 원문과 조판하는 원문이 다를 수 있다**(`jp_mark`). 주입 `%c` 쌍이 든 블록은
      사전 열쇠가 **쌍이 든 꼴**이고(PS1 덤프도 같다), 조판은 **글자를 되살린 꼴**로 해야
      이름칸이 정본에 붙는다(`inject_pairs`).
    """
    if not canon:
        return None
    kr = canon.get(line_key(jp))
    if kr is None:
        return None
    global _NAMES
    if _NAMES is None:
        import typeset_scn

        _NAMES = typeset_scn._names()
    import typeset_scn

    built, _bad = typeset_scn.typeset(jp_mark or jp, kr, _NAMES, why)
    return built


_SITES = None


def sites_for(path):
    """그 파일의 **주입 `%c` 쌍** 정본 → `{블록 오프셋: 자리}`. 없으면 빈 것."""
    global _SITES
    if _SITES is None:
        from inject_pairs import load_canon as _load

        _SITES = {}
        for v in _load().values():
            _SITES.setdefault(v["file"], {})[int(v["at"], 16)] = v
    return _SITES.get(path, {})


def canon_of(canon, jp, site=None, why=None):
    """조판까지 끝난 우리 블록 — 주입 쌍이 있으면 되살렸다 되돌린다.

    🔴 **`_canon_get` 을 직접 부르지 않는다.** 부르는 자리가 넷인데(재삽입 · 슬롯 계획 ·
       집계 · 이주) 한 곳만 빠뜨리면 **그 자리에서만 이름이 일본어**가 되거나 글리프가
       계획에서 빠진다(화면에서 글자가 사라진다).
    """
    if not site:
        return _canon_get(canon, jp, why=why)
    import inject_pairs as ip

    pairs = sorted((int(i), ch) for i, ch in site["glyphs"].items())
    jp_mark, tails = ip.restore(jp, pairs)
    kr = _canon_get(canon, jp, jp_mark, why)
    return None if kr is None else ip.reinsert(kr, tails)


def _moved(entries, ptrs, at):
    """그 포인터가 가리키던 자리가 실제로 바뀌었나 — 안 바뀌었으면 쓰지 않는다."""
    if not ptrs:
        return False
    for e in entries:
        if e.get("ptr_at") == ptrs:
            return int(e["file_offset"], 16) != at
    return True


_PLAN = None


def _encode(kr, plan=None):
    """우리 문안 → 바이트 — 🔴 규칙은 `font.to_bytes` 가 정본이다.

    ⚠ `patch_ui` 와 **같은 계획**을 써야 폰트와 어긋나지 않는다(계획은 저쪽이 만든다).
    """
    from font import to_bytes

    return to_bytes(kr, plan if plan is not None else _PLAN)


# 🔴 **본체 파일 안의 0런은 자리로 쓰지 않는다** — 계측으로는 안전을 증명할 수 없다.
#
#    2026-08-28 에 실기로 재서 셋을 골랐었다(`/ED.BIN` 0x7AA83·0x87300·0x7EF45, ED2 대응).
#    「필드 이동 + 전투를 통째로 도는 동안 쓰기 0건」이 근거였다. **틀렸다.**
#    2026-08-30 실측: 그 셋은 **프롤로그·타이틀 국면에서 살아 있다** — 시작 메뉴에 선 채로
#    workramh 를 되읽으니 0x7AA83 뒤쪽 ~510B 에 **SH-2 코드**(오버레이)가, 0x87300 에는
#    **포인터 표**(0x0609xxxx·0x060Afxxx)가, 0x7EF45 에는 비트맵성 자료가 들어 있었다.
#    ⇒ 우리 문안이 그 위에 깔리면 **프롤로그 뒤 화면이 검게 죽는다**(유저 보고, ED1·ED2 둘 다).
#
#    🔴 **뿌리는 「계측 국면이 좁았다」가 아니라 「계측으로는 못 센다」다.** 안 밟은 국면이
#       하나라도 있으면 초록불이 「없다」가 아니라 「아직 안 봤다」가 된다
#       (`docs/patcher-checklist.md` 4-B). 국면을 넓혀도 다음 사고를 못 막는다 —
#       세이브 직후·엔딩·특정 이벤트를 전부 도는 계측은 사실상 불가능하다.
#    ⇒ **자리는 「안 쓰는 걸 봤다」가 아니라 「구조가 우리 것이다」로만 얻는다** —
#       ISO 꼬리 섹터(`expand_files.py`) · 비워진 칸 · 짧아져 남은 칸.
#    대가는 **자리 없음 73 → 115 블록**(42블록)이다. 늘리려면 계측이 아니라
#       **파일 확장·LBA 재배치**로 얻는다.
#
# 🔴 이보다 작은 칸은 비워도 안 쓴다 — 표일 수 있다(위 `migrate` 주석).
VACATE_MIN = 8

# ⚠ **비어 있다.** 위 주석이 이유다 — 다시 채우려면 계측이 아니라 구조적 근거가 필요하다.
#   회귀 테스트 `test_no_measured_free_runs` 가 이 표가 다시 차는 것을 막는다.
_MEASURED_RAW = {}
_MFREE = None


def _hook_span(path):
    """조사 훅이 실제로 차지하는 `(시작, 끝)` — 없으면 `None`.

    ⚠ 훅 모듈에서 **자리와 실제 길이를 물어본다.** 상수로 베끼면 훅이 자랄 때 또 겹친다.
    🔴 2026-08-30 사고: 훅 루틴이 2,045B → 2,051B 로 자라며 옛 `_MEASURED_RAW` 의
       `(0x07EF45, 451)` 과 **6B 겹쳤고**(ED2 는 9B) 게임이 ED1·ED2 둘 다 오프닝 뒤에
       **널로 점프해 죽었다**(PC=0). 두 도구가 같은 0런을 **각자 표로** 들고 있었던 것이
       뿌리다. 표는 지금 비었지만(위) 다시 채운다면 이 뺄셈이 다시 살아 있어야 한다.
    """
    try:
        import patch_josa_hook as H
    except Exception:  # noqa: BLE001  (훅이 없어도 재삽입은 돌아야 한다)
        return None
    got = H.FREE.get(path)
    if not got:
        return None
    off, size = got
    return off, off + size  # 🔴 **0런 전체**를 훅 것으로 본다 — 길이는 문안 따라 자란다


def _measured_free(path):
    """실측 0런에서 **훅이 쓰는 구간을 뺀** 나머지."""
    global _MFREE
    if _MFREE is None:
        _MFREE = {}
        for p, runs in _MEASURED_RAW.items():
            span = _hook_span(p)
            out = []
            for a, n in runs:
                b = a + n
                if span and max(a, span[0]) < min(b, span[1]):
                    a2 = max(a, span[1])  # 훅 뒤로 민다
                    if a2 >= b:
                        continue
                    a, n = a2, b - a2
                out.append((a, n))
            _MFREE[p] = out
    return _MFREE.get(path, [])


def migrate(over, base, tail_at, tail_end, spare=(), spans=None):
    """칸을 넘는 블록을 옮긴다 → `([(오프셋, 바이트)], [(ptr, 새 주소)], 남은 것)`.

    🔴 **원본 칸을 앞으로 당기지 않는다.** PS1 이 쓴 2단계다 — 참조만 새 주소로 돌린다.
       칸을 늘려 뒤를 밀면 다음 블록의 시작 마커(`0x09`)가 어긋난다.

    ## 자리는 둘이다 — 꼬리 **와 비워진 칸**

    🔴 **참조를 옮긴 순간 원본 칸을 가리키는 건 아무것도 없다.** 처음엔 거기 JP 를 그냥
       남겨 뒀는데, 그건 자리를 버리는 것이었다(실측 2026-08-27: **63,699B**). 꼬리만
       쓰면 85파일 중 31이 26,912B 모자라 509블록이 화면에 일본어로 남았다. 비워진 칸을
       풀에 넣으면 **모자란 파일이 7 · 부족 688B** 로 줄어든다.
    ⇒ `patch_mon_names` 가 이름 칸에 쓰는 것과 같은 기법이다(칸을 풀로 묶어 다시 깔기).

    ⚠ **칸의 글자 자리(`n`)만 우리 것**이다. 그 뒤 꼬리에는 다음 블록의 시작 마커가 들어
      있어 건드리면 안 된다.
    ⚠ 자리는 **파일마다 따로**다 — 같은 군이 같은 주소에 올라가도 한 번에 하나만 올라간다.
    ⚠ **긴 것부터 넣는다**(first-fit decreasing). 작은 것부터 깔면 큰 게 갈 데가 없어진다.
      ⚠ 그래도 **결정적**이다 — 같은 길이는 오프셋 순으로 갈린다(제1원칙).
    """
    # 🔴 **자리를 못 얻어 제자리에 남는 블록의 칸은 풀이 아니다**(2026-09-03).
    #    「참조를 옮기면 그 칸은 아무도 안 본다」는 **옮겨졌을 때만** 참이다. 못 옮긴 블록은
    #    포인터가 제자리를 가리킨 채 남는데, 그 칸을 남에게 내주면 **화면에 딴 문장이 뜬다.**
    #    ⚠ 증상이 「일본어가 남았다」가 아니라 **「한국어인데 다른 대사」**라 스캐너가 못 본다
    #      — 실측 2026-09-03: 32블록이 그 상태였다(ED2 프롤로그·아이템 이름 포함).
    #    ⇒ 「누가 남나」와 「어디에 놓나」가 서로를 물고 있으니 **고정점까지 돈다.**
    #      풀이 줄면 남는 것은 늘기만 하므로(단조) 반드시 멈춘다.
    blocked = set()
    for _ in range(len(over) + 1):
        puts, ptrs, left = _place(over, base, tail_at, tail_end, spare, blocked, spans or {})
        now = {o for o, _jp in left}
        if now == blocked:
            break
        blocked = now
    return puts, ptrs, left


def _place(over, base, tail_at, tail_end, spare, blocked, spans):
    """`migrate` 의 한 회차 — `blocked` 의 칸은 풀에 안 넣는다."""
    # 풀 = [꼬리] + [비워질 칸] + [짧아져 남은 칸 뒷부분]. 칸은 자기 글자 자리만 낸다.
    free = [[tail_at, tail_end - tail_at]] if tail_end > tail_at else []
    free += [[a, n] for a, n in spare]
    for off, _why, _jp, e, _enc in over:
        n = len(bytes.fromhex(e["raw_hex"]))
        # 🔴 **작은 칸은 안 비운다**(2026-08-28). 「참조를 옮기면 그 칸은 아무도 안 본다」는
        #    **포인터로만 읽는 자리에서만** 참이다. 코드가 그 주소에서 직접 집으면 참조를
        #    옮겨도 원래 자리를 읽는다.
        #    실측: `/ED.BIN` 0x44BC8 의 HUD 접미 표(`入口`·`付近`·`北`·`南`·`東`·`西`)는
        #    2~4B 블록이고 **포인터도 있는데**, 조립 루틴(0x44BE8)은 그 자리에서 4B 를
        #    직접 집는다. 비워서 남에게 내줬더니 화면에 `メ§電 リ…처` 가 떴다.
        #    ⇒ **표는 잘고 산문은 길다**를 경계로 쓴다. 대사 한 줄이 8B 미만일 수는 없다.
        if n >= VACATE_MIN and off not in blocked:
            # 비우는 칸도 **꼬리까지** 낸다(위 `rebuild` 주석과 같은 이유)
            free.append([off, spans.get(off, n)])
    # 🔴 **맞닿은 조각은 합친다** — 안 합치면 총량이 남는데도 조각이 작아 큰 문안이 갈 데가
    #    없다(`patch_ui.sys_pack` 이 먼저 물린 함정이다). 꼬리를 풀에 넣으면 칸들이 실제로
    #    맞닿으므로 여기서 비로소 효과가 난다.
    free.sort()
    merged = []
    for a, n in free:
        if merged and merged[-1][0] + merged[-1][1] == a:
            merged[-1][1] += n
        else:
            merged.append([a, n])
    free = merged
    puts, ptrs, left = [], [], []
    for off, _why, jp, e, enc in sorted(over, key=lambda r: (-len(r[4]), r[0])):
        blob = enc + b"\x00"
        free.sort(key=lambda h: (-h[1], h[0]))
        # 🔴 **짝수 주소에만 놓는다**(2026-08-28). 어떤 화면은 두 바이트를 한 글자로 **고정**
        #    해 읽어서, 홀수 자리에 놓으면 거기서만 통째로 밀려 깨진다(`patch_ui` 같은 사고).
        i = next((k for k, (a_, n_) in enumerate(free) if n_ - (a_ & 1) >= len(blob)), None)
        if i is None:
            left.append((off, jp))
            continue
        a, n = free.pop(i)
        if a & 1:
            a, n = a + 1, n - 1
        puts.append((a, blob))
        for q in e.get("ptr_at", []):
            ptrs.append((int(q, 16) if isinstance(q, str) else q, base + a))
        ro, rn = a + len(blob), n - len(blob)
        if ro & 1:  # 남는 조각도 짝수에서 시작하게
            ro, rn = ro + 1, rn - 1
        if rn >= 2:  # 남는 조각은 다시 풀로
            free.append([ro, rn])
    puts.sort()
    return puts, ptrs, left


def _diffs(new, old):
    """`[(시작, 끝)]` — 두 바이트열이 **다른 구간들**. 남의 자리를 안 밟게 여기로만 쓴다."""
    out, i = [], 0
    n = len(new)
    while i < n:
        if new[i] == old[i]:
            i += 1
            continue
        j = i
        while j < n and new[j] != old[j]:
            j += 1
        out.append((i, j))
        i = j
    return out


def apply_runs(dst, path, lba, size, base, plans, puts=(), mptrs=(), codes=()):
    """구간 바이트 + **바뀐 포인터**를 쓴다 → 쓴 포인터 수.

    🔴 **포인터를 안 고치면 옮긴 블록을 아무도 못 찾는다.** 구간 안에서 앞 블록이 짧아지면
       뒤가 통째로 당겨지므로, 옮겨진 블록마다 `ptr_at` 의 BE32 를 새 주소로 바꾼다.
    🔴 **구간을 통째로 쓰지 않는다 — 바뀐 토막만 쓴다.** 구간 안에는 우리가 안 건드리는
       블록도 있는데, 통째로 쓰면 그 자리에 **원문 JP 를 다시 깔아** 앞 단계가 넣어 둔
       한국어를 되돌린다. 실측 2026-08-27: `/BIN/ED2MON*` 에서 `patch_ui` 가 넣은 시스템
       메시지 **69줄이 일본어로 돌아가 있었다.** 게이트는 patch_ui 가 **먼저** 돌아 자기
       되읽기를 통과한 뒤라 아무도 못 봤다 — 체인은 순서만으로 안 지켜진다.
    ⚠ 안 바뀐 것은 안 쓴다 — 되읽기 대장이 「무엇이 실제로 움직였나」를 그대로 비춘다.
    """
    n = 0
    with open(dst, "r+b") as f:
        for start, blob, moves, orig in plans:
            for a, b in _diffs(blob, orig):
                common.write_at(
                    f, lba, size, start + a, blob[a:b], label=f"{path} 씬 0x{start + a:X}"
                )
            for ptrs, at in moves:
                want = (base + at).to_bytes(4, "big")
                for q in ptrs:
                    q = int(q, 16) if isinstance(q, str) else q
                    n += 1
                    common.write_at(f, lba, size, q, want, label=f"{path} 씬 포인터 0x{q:X}")
        # 이주분 — 꼬리에 새로 쓰고 참조만 돌린다(`migrate`)
        for at, blob in puts:
            common.write_at(f, lba, size, at, blob, label=f"{path} 이주 0x{at:X}")
        for q, addr in mptrs:
            n += 1
            common.write_at(
                f, lba, size, q, addr.to_bytes(4, "big"), label=f"{path} 이주 포인터 0x{q:X}"
            )
        # 주입 `%c` 쌍의 인자를 공백으로 — **그 블록을 실제로 번역했을 때만** 온다
        for at, word in codes:
            common.write_at(
                f, lba, size, at, word.to_bytes(2, "big"), label=f"{path} 주입 인자 0x{at:X}"
            )
    return n


def verify(dst, checks):
    """되읽기 — **쓴 자리와 포인터를 빌드 이미지에서 다시 읽는다.**

    🔴 이 단계만 되읽기가 없었다(2026-08-27). 체인의 다른 패처는 전부 갖고 있어 게이트
       출력에 `✅` 가 뜨는데 여기만 조용히 지나갔다 — 「돌았다」와 「들어갔다」는 다른 말이다
       (체크리스트 4 · 10-B). 씬은 13,314블록으로 가장 크니 구멍이 여기 있으면 안 된다.
    ⚠ **우리가 쓴 자리만** 본다. 안 바뀐 구간(`blob == orig`)은 안 쓰는데, 그 바이트의
      주인은 우리가 아니다 — `/BIN/ED2MON*` 은 이름 칸(`patch_mon_names`)과 시스템
      메시지(`patch_ui`)가 같은 파일을 나눠 갖는다. 거기까지 대조하면 「남이 정당하게 쓴
      것」을 실패로 부른다(실측 2026-08-27: ED2MON02 0x3B8).
    """
    _f2, mm2 = common.open_image(dst)
    nb = np = nm = nc = 0
    for path, lba, size, base, plans, puts, mptrs, codes in checks:
        d = bytes(common.read_extent(mm2, lba, size))
        # ⚠ **이주가 덮은 자리는 구간 대조에서 뺀다** — 그 바이트는 `blob`(구간 재조립 결과)이
        #   아니라 `puts` 가 주인이다. 안 빼면 「짧아져 남은 자리에 다른 블록을 깐」 곳마다
        #   운다. 이주분은 바로 아래에서 따로 되읽는다.
        covered = set()
        for at, blob_ in puts:
            covered.update(range(at, at + len(blob_)))
        for start, blob, moves, orig in plans:
            # ⚠ **우리가 쓴 토막만** 본다 — 구간 전체를 대조하면 안 건드린 블록에서
            #   남이 넣은 한국어를 「어긋났다」고 부른다(`apply_runs` 주석).
            for a, b in _diffs(blob, orig):
                if any(i in covered for i in range(start + a, start + b)):
                    continue
                assert d[start + a : start + b] == blob[a:b], (
                    f"{path} 0x{start + a:X}: 되읽기가 다르다"
                )
                nb += 1
            for ptrs, at in moves:
                want = (base + at).to_bytes(4, "big")
                for q in ptrs:
                    q = int(q, 16) if isinstance(q, str) else q
                    assert d[q : q + 4] == want, f"{path} 포인터 0x{q:X}: 되읽기가 다르다"
                    np += 1
        # 이주분 — **새 자리의 바이트 + 그리로 도는 참조**를 둘 다 본다.
        # 🔴 원본 칸은 **안 건드렸는지**도 본다. 손대면 다음 블록의 시작 마커가 어긋난다.
        for at, blob in puts:
            assert d[at : at + len(blob)] == blob, f"{path} 이주 0x{at:X}: 되읽기가 다르다"
            nm += 1
        for q, addr in mptrs:
            assert d[q : q + 4] == addr.to_bytes(4, "big"), f"{path} 이주 포인터 0x{q:X}"
            np += 1
        for at, word in codes:
            assert d[at : at + 2] == word.to_bytes(2, "big"), f"{path} 주입 인자 0x{at:X}"
            nc += 1
    mm2.close()
    _f2.close()
    print(f"  ✅ 되읽기 씬 구간 {nb:,} · 이주 {nm:,} · 포인터 {np:,} · 주입 인자 {nc}곳")


def main():
    check = "--check" in sys.argv
    apply = "--apply" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    targets = [p for p, _l, _s in common.iso_files(mm) if SCN_RE.match(p)]
    canon = {} if check else load_canon()  # 항등 검증에서는 비운다(원문 그대로)
    if canon:
        canon = augment_names(canon, mm)  # 이미지의 이름 한 덩어리 블록을 정본에 붙인다
        # ⚠ 슬롯 계획은 **`patch_ui` 와 같은 것**을 쓴다 — 따로 뽑으면 폰트와 어긋난다.
        #   여기서 계획을 **늘리지 않는다**(`--refresh` 는 `patch_ui` 몫).
        from patch_ui import slot_plan

        global _PLAN
        _PLAN = slot_plan(all_texts(mm))  # ⚠ 저본 전량이 아니라 **실제로 넣을 것**만

    # 🔴 **빌드 이미지를 같이 연다** — 「이미 누가 쓴 자리인가」를 구조로 묻기 위해서다
    #    (`already_written`). 없으면(항등 검증·첫 계산) 그 장치 없이 돈다.
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    _fb = mmb = None
    built_files = {}
    if canon and os.path.exists(dst):
        _fb, mmb = common.open_image(dst)
        built_files = {p: (lba, sz) for p, lba, sz in common.iso_files(mmb)}

    files = ok = blocks = pinned = wrote = matched = moved = nofit = nofit_b = injected = 0
    bad, skipped, checks = [], [], []
    shortfall = {}
    for path in targets:
        got = load(path)
        if not got:
            continue
        _base, entries = got
        lba, size = next((l, s) for p, l, s in common.iso_files(mm) if p == path)
        d = bytes(common.read_extent(mm, lba, size))
        files += 1
        mine = owned_elsewhere(path) if canon else frozenset()
        # 주입 `%c` 쌍 — 🔴 정본이 **아직 이미지와 맞는지** 먼저 본다(체크리스트 1).
        isites = sites_for(path) if canon else {}
        if isites:
            import inject_pairs as _ip

            _ip.verify_sites(d, entries, isites, path)
        built = None
        if canon and built_files and path in built_files:
            built = bytes(common.read_extent(mmb, *built_files[path]))
        # 🔴 **원본으로 읽고 빌드로 쓴다** — 둘의 LBA 가 다를 수 있다.
        #    `expand_files` 는 크기만 바꿔(LBA 불변) 원본 LBA 로 써도 맞았지만,
        #    `relocate_files` 가 파일을 **뒤로 밀면서** LBA 가 갈렸다. 크기만 빌드 것으로
        #    가져오고 LBA 를 원본 것으로 두었더니 **엉뚱한 섹터에 쓰고 되읽기가 터졌다**
        #    (2026-08-31 실측: `/BIN/ED1SCN03.BIN 이주 0x77BC: 되읽기가 다르다`).
        # ⚠ 확장 영역(꼬리)은 원본 크기부터 빌드 크기까지 — 그게 우리 자리다.
        blba, bsize = built_files.get(path, (lba, size))
        over = []
        spare = []
        plans = []
        done = []  # 실제로 우리 문안이 들어간 블록 오프셋 — 주입 인자 패치의 조건이다
        spans = {}  # 블록 오프셋 → 칸 전체 길이(꼬리 포함) — 이주 풀이 꼬리까지 쓴다
        for run in runs(entries, size):
            blocks += len(run)
            matched += sum(
                1
                for o, _n, e in run
                if o not in mine and canon_of(canon, e.get("text", ""), isites.get(o))
            )
            blob, moves, dropped = rebuild(run, canon, d, mine, built, spare, isites, done, spans)
            start = run[0][0]
            orig = d[start : start + len(blob)]
            if blob == orig:
                ok += 1
            else:
                bad.append((path, start, len(blob)))
            skipped.extend(dropped)
            # 이주로 넘길 것 = **인코딩을 들고 나온** 것(칸을 넘었거나, 구간을 다시 깐다)
            over.extend(r for r in dropped if r[4] is not None)
            # 자리가 안 바뀐 포인터는 쓸 이유가 없다
            plans.append((start, blob, [(p, a) for p, a in moves if _moved(entries, p, a)], orig))
        pinned += sum(1 for e in entries if not e.get("ptr_at"))
        puts, mptrs, left = (
            migrate(over, _base, size, bsize, list(spare) + _measured_free(path), spans)
            if canon
            else ([], [], over)
        )
        moved += len(puts)
        nofit += len(left)
        # 🔴 **얼마나 모자라나**를 같이 센다 — 자리를 늘릴지 판단하는 값이다.
        #    ⚠ 여기서 재야 한다. 밖에서 `migrate` 를 다시 부르면 꼬리 확장분을 안 넘겨
        #      과다 계상된다(2026-08-31 실측: 116 을 466 으로 셌다).
        gap = sum(len(enc) + 1 for _o, _w, _j, _e, enc in over if _o in {x[0] for x in left})
        nofit_b += gap
        if gap:
            shortfall[path] = gap
        # 🔴 **이주한 블록도 「넣었다」**이다 — 원본 칸엔 JP 가 남지만 참조가 새 자리를 보므로
        #    화면에 나가는 것은 우리 문안이다. 여기서 안 세면 그 블록의 주입 인자가 그대로
        #    남아 이름 앞에 `ソ` 가 붙는다(PS1 이 실제로 그렇게 새어 나왔다).
        moved_offs = {o for o, _w, _j, _e, _enc in over} - {o for o, *_ in left}
        put = sorted(set(done) | moved_offs)
        codes = []
        for o in put:
            site = isites.get(o)
            if site:
                codes.extend((int(a, 16), int(w[1], 16)) for a, w in site["words"].items())
        injected += len(codes) // 2
        if apply:
            if not os.path.exists(dst):
                raise SystemExit(f"먼저 다른 패처를 돌린다 — {dst} 가 없다")
            wrote += apply_runs(dst, path, blba, bsize, _base, plans, puts, mptrs, codes)
            checks.append((path, blba, bsize, _base, plans, puts, mptrs, codes))

    print(f"씬 파일 {files}개 · 블록 {blocks} · 핀(참조 없음) {pinned}")
    real = [r for r in skipped if r[4] is None]  # 진짜 건너뛴 것 (이주 대상은 뺀다)
    if real:
        print(f"  ⏭ 구조 계약이 달라 건너뛴 블록 {len(real)}")
        for off, why, jp, _e, _enc in real[:6]:
            print(f"     0x{off:X} {why} — {jp!r}")
    if apply:
        print(f"  → 넣음 · 고친 포인터 {wrote}곳")
    if injected:
        print(f"  주입 %c 쌍 되살림 {injected}자리 — 콜사이트 인자를 공백으로")
    print(
        f"  이주(확장 영역) {moved:,} · 자리가 없어 남은 것 {nofit:,} ({nofit_b:,}B · {nofit_b / 2048:.1f}섹터)"
    )
    if apply:
        verify(dst, checks)
    if check:
        print(f"  항등 구간 {ok} · 어긋난 구간 {len(bad)}")
        for path, start, n in bad[:8]:
            print(f"     ❌ {path} 0x{start:X} ({n}B)")
        if bad:
            raise SystemExit(f"항등 재삽입이 {len(bad)}구간에서 어긋난다 — 도구가 범인이다")
        print("  ✅ 원문을 그대로 다시 깔아 **바이트 동일** — 자르기·재배치가 맞다")
    else:
        n = sum(1 for r in skipped if "칸을" in r[1])
        pk = sum(1 for r in skipped if r[1] == "구간을 다시 깐다")
        print(f"  넣을 수 있는 블록 {matched} · 칸을 넘어 건너뛴 것 {n} · 구간을 다시 깐 것 {pk}")
        print("  (`--apply` 로 넣는다 · `--check` 는 원문 항등만 본다)")
    if shortfall:
        # 🔴 **자리를 늘릴 도구가 읽는 값**(`relocate_files.py`). 파생물이라 `work/` 에 둔다 —
        #    같은 입력이면 같은 값이 나온다(제1원칙).
        os.makedirs(common.OUT_DIR, exist_ok=True)
        with open(os.path.join(common.OUT_DIR, "scn_shortfall.json"), "w") as fh:
            json.dump(dict(sorted(shortfall.items())), fh, indent=1)
    mm.close()
    _f.close()
    if mmb is not None:
        mmb.close()
        _fb.close()


if __name__ == "__main__":
    main()
