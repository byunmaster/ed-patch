"""실행파일 안 낱말 표의 **재삽입 경로** — 오프셋 표를 찾아 길이 예산을 연다.

맵 대사(`SC*.DAT`)와 **컨테이너가 다르다.** 낱말(인물·아이템·마법·몬스터·지명·메뉴)은
실행파일 안에 종결 바이트로 갈린 문자열로 앉아 있고, 그 앞에 **u16 오프셋 표**가 붙어 있다.
규격은 ED4 의 대사 멤버와 **똑같다**(`scriptmap.LAYOUT_TABLE`):

```
[base]        u16 표 N개   N = 표[0] / 2      ← **첫 항목이 곧 표 자신의 길이다**
[base+2N]     문자열 풀    문자열 i = base + 표[i]
```

🔴 그 규칙을 모르는 동안 **표 자신을 문자열 하나로 세고 있었다**(2026-09-03).
   ED4 인물 표의 0번이 「１ＢＪａあがざっねふめるェアヴィン」으로 읽혔는데, 그건 표 26바이트를
   글자로 디코드한 것이었다. 그래서 조각 합(170B)이 span(160B)을 넘었고 「꼬리 공유가 있다」고
   오진했다. ⇒ **자리를 「그럴듯함」으로 넓히지 말고 규격으로 정한다.**

🔴 **길이는 「예산」이지 「고정」이 아니다.** 문자열이 연속으로 붙어 있어 하나를 늘리면 뒤가
   전부 밀리므로, **구역 전체의 총량**이 원래 풀을 넘지 않으면 된다. 짧은 이름에서
   빌려 긴 이름에 쓸 수 있다. 넘으면 거절한다 — 뒤에 무엇이 있는지 모른다.

⚠ 표를 못 찾은 구역은 **길이 고정**으로 다룬다(ED4 타이틀 메뉴 PoC 가 그 경우였다).

## 🔴 빈틈은 닻이다

표가 **안 가리키는** 문자열이 풀 안에 섞여 있다(실측: ED4 계급 표 안의 「力」 4B,
무기 표 안의 16B). 코드가 절대 주소로 그걸 가리킬 수 있으니 **아무것도 빈틈을 넘어
움직이면 안 된다.** 그래서 풀을 빈틈으로 끊어 **칸마다 따로 예산**을 본다(`chunks`).
⇒ 예산은 span 이 아니라 **칸의 합**이다.

⚠ 되읽기 검산은 **코드표를 안 본다**(`raw_string`). 미해독 한자가 낀 항목을 코드표로 읽으면
  늘 「다르다」가 나와, 정작 그 항목을 빠뜨리게 된다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textenc

TERM_ZERO = 0x0000
TERM_FFFF = 0xFFFF
PREFIX = 6  # 차분 앞부분 이만큼으로 후보를 좁힌다


class ExeTextError(Exception):
    pass


def is_term(w):
    """`dump_names.is_term` 과 같은 규약 — 최상위 비트가 선 코드도 종결이다."""
    return w in (TERM_ZERO, TERM_FFFF) or bool(w & 0x8000)


def is_start(data, off, pool):
    """그 자리가 **문자열의 시작**인가 — 풀의 첫 자리이거나, 바로 앞이 종결이거나.

    🔴 이게 빠지면 **가짜 표가 통과한다.** 문자열 한복판을 가리켜도 「거기서부터 읽으면
       종결이 나온다」는 늘 참이기 때문이다. 실측(2026-09-03): ED3 실행파일에서 그렇게
       걸린 표가 하나 있었는데, 항목들이 「ち切りの剣」·「の指輪」처럼 **꼬리만** 가리켰다.
       항등 재구축은 통과한다(같은 걸 도로 쓰니까) — **게이트가 엉뚱한 이유로 초록**이었다.
    """
    if off == pool:
        return True
    if off < 2 or off - 2 < pool:
        return False
    return is_term(struct.unpack_from("<H", data, off - 2)[0])


def raw_string(data, off, limit=64):
    """(코드열, 종결값) — **코드표를 안 본다.** 미해독 한자가 껴도 문자열은 문자열이다.

    🔴 재삽입은 전부 이걸로 한다. 코드표를 끼우면 「우리가 아직 못 읽는 글자」가 든 항목을
       조용히 빠뜨리게 되고, 그러면 그 자리가 통째로 밀린다.
    """
    codes = []
    p = off
    for _ in range(limit):
        if p + 1 >= len(data):
            return None, None
        v = struct.unpack_from("<H", data, p)[0]
        if is_term(v):
            return codes, v
        codes.append(v)
        p += 2
    return None, None


def string_end(data, off, limit=64):
    """종결 **바로 다음** 오프셋. 코드표는 안 본다(모르는 한자가 껴도 문자열은 문자열이다)."""
    p = off
    for _ in range(limit):
        if p + 1 >= len(data):
            return None
        if is_term(struct.unpack_from("<H", data, p)[0]):
            return p + 2
        p += 2
    return None


def read_string(data, off, cm, limit=64):
    """(코드열, 종결값) — 종결까지. 모르는 코드가 있으면 None."""
    codes = []
    while len(codes) < limit and off + 1 < len(data):
        v = struct.unpack_from("<H", data, off)[0]
        if is_term(v):
            return codes, v
        if v not in cm:
            return None, None
        codes.append(v)
        off += 2
    return None, None


def table_at(data, base, cm, min_n=4):
    """base 가 표의 시작인가 — 맞으면 N, 아니면 None. **규격으로만 판정한다.**

    1. `N = 표[0] / 2` 이고 표가 그만큼 이어진다.
    2. 항목이 **비감소**이고 전부 표 뒤(`>= N*2`)를 가리킨다.
    3. 항목이 가리키는 자리가 전부 **종결로 끝난다**, 그리고 **대부분**(≥85%) 은 코드표로
       읽힌다. ⚠ 「전부 읽힌다」로 조이면 안 된다 — 표 안에 미해독 한자가 낀 문자열이 하나만
       있어도 표가 통째로 안 보인다(실측: 그 조건 하나로 15구역 → 3구역이 됐다).
       🔴 문턱은 **0.5** 다. 0.85 로 뒀더니 ED4 지명 표(100항목)가 **67%** 라 통째로 안 보였다 —
       지명엔 우리가 아직 못 읽는 한자가 많다. 구조 쪽 조건(1·2 + 종결)이 이미 세서
       읽힘 비율은 「글자 표가 맞나」를 거드는 정도로만 쓴다.
    """
    if base + 2 > len(data):
        return None
    t0 = struct.unpack_from("<H", data, base)[0]
    if t0 % 2 or t0 < min_n * 2 or base + t0 > len(data):
        return None
    n = t0 // 2
    ent = struct.unpack_from(f"<{n}H", data, base)
    if any(ent[i] > ent[i + 1] for i in range(n - 1)) or ent[0] != t0:
        return None
    good = 0
    for x in ent:
        if base + x >= len(data) or string_end(data, base + x) is None:
            return None
        if not is_start(data, base + x, base + ent[0]):
            return None
        if read_string(data, base + x, cm)[0] is not None:
            good += 1
    return n if good >= n * 0.5 else None


def scan_tables(data, cm, min_n=4):
    """실행파일 전체에서 규격에 맞는 표를 찾는다 — 구역 라벨에 기대지 않는다.

    ⚠ 짧은 표는 우연히 맞을 수 있어 `min_n` 아래는 안 본다.
    """
    out = []
    base = 0
    while base + 2 <= len(data):
        n = table_at(data, base, cm, min_n)
        if n:
            out.append({"table": base, "base": base, "n": n})
            base += n * 2
        else:
            base += 2
    return out


# 🔴 **표가 풀에서 떨어져 있는 자리** — `scan_tables` 는 「표[0] = 표 자신의 길이」(표 = base)인
#    규격만 찾는다. 아이템 이름은 그 규격이 아니다: 표는 0x096F36 에, 오프셋의 기준(base)은
#    0x09702C(표 안쪽)에 있다. 스캐너가 못 찾자 빌드는 이 구역을 「표 없음 → 길이 고정」으로 보고
#    **통째로 건너뛰어** 화면에 일본어 아이템명이 남았다(2026-09-27 마스터 캡처 「布の服」·「短剣」).
#    찾은 법: 이름 사이 간격(6·10·16B)과 같은 차이를 가진 u16 배열을 실행파일 전체에서 훑었다.
#    항목 0~121 이 전부 문자열 시작을 가리킨다(122~130 은 0 = 빈 이름이라 안 넣는다).
#    둘째(0x09D0F6, base = 표 끝 0x09D188, 73항목)는 **소지품 창** 한 벌 — 見る/読む/使う/捨てる ·
#    수첩 목차 · 種別：/効果： 라벨 · 장비 갈래(短剣…盾) · 주문 이름 · 귀중품 설명 · 버리기 확인.
#    표를 몰라 「길이 고정」으로 보던 자리라 1자 칸에 「盾」→「방패」가 못 들어갔다(같은 찾기로 발견).
DETACHED = {"ed3": [(0x096F36, 0x09702C, 122), (0x09D0F6, 0x09D188, 73)]}

# 🔴 **인물 이름은 표가 아니라 고정폭 칸**이다 — 14B(7워드) 칸 14개: 글자 ≤6 + 0 채움 + 마지막
#    워드 0xFFFF. 칸 간격이 전부 14B 이고 어느 쪽 가리킴(u16·u32)도 없다 — 코드가 `기준 + 번호×14`
#    로 곧바로 찾는다. 상태 창 머리·대상 선택·파티 목록이 다 여기서 읽는다(「ジュリオ」 세 곳).
FIXED_SLOTS = {"ed3": [(0x096E54, 14, 7)]}  # (첫 칸, 칸 수, 칸 워드 수)


def detached_tables(data, disc):
    """[{table, base, n}] — `DETACHED` 를 **규격으로 다시 확인**하고 돌려준다(원본이 다르면 운다)."""
    out = []
    for tbl, base, n in DETACHED.get(disc, []):
        ents = struct.unpack_from(f"<{n}H", data, tbl)
        pool = base + min(ents)
        for x in ents:
            if string_end(data, base + x) is None or not is_start(data, base + x, pool):
                raise ExeTextError(f"떨어진 표 0x{tbl:X}: 0x{base + x:X} 가 문자열 시작이 아니다")
        out.append({"table": tbl, "base": base, "n": n})
    return out


def fixed_slots(data, disc):
    """[(칸 주소, 칸 워드 수, 글자 코드)] — 모양(글자 · 0 채움 · 마지막 워드)이 다르면 운다."""
    out = []
    for first, count, words in FIXED_SLOTS.get(disc, []):
        for i in range(count):
            off = first + i * words * 2
            w = struct.unpack_from(f"<{words}H", data, off)
            n = next((k for k, x in enumerate(w) if is_term(x)), None)
            if n is None or any(x != TERM_ZERO for x in w[n : words - 1]) or w[-1] != TERM_FFFF:
                raise ExeTextError(f"고정 칸 0x{off:X} 모양이 다르다: {[hex(x) for x in w]}")
            out.append((off, words, list(w[:n])))
    return out


def write_fixed_slot(data, off, words, codes):
    """칸 하나를 다시 쓴다 — 글자 뒤는 0 으로, 마지막 워드(0xFFFF)는 그대로. 넘치면 운다."""
    if len(codes) > words - 1:
        raise ExeTextError(f"고정 칸 0x{off:X}: {len(codes)}코드는 {words - 1}칸을 넘는다")
    struct.pack_into(
        f"<{words}H", data, off, *codes, *([TERM_ZERO] * (words - 1 - len(codes))), TERM_FFFF
    )


def gap_strings(data, tables, start, end):
    """[(오프셋, 코드열, 종결값)] — `[start, end)` 안에서 **어느 표도 안 가리키는** 문자열(= 빈틈의 닻).

    월드맵 장소 패널의 「ディーネ / シャリネ」 같은 것이다(마스터 실기 10-08) — 코드가 절대 주소로 읽으니 **자리·길이를 못 바꾼다**
    (`write_in_place`). 종결 바로 뒤의 종결 워드(0x0000)는 문자열 사이 간격이라 따로 안 센다.
    """
    pointed = set()
    for t in tables:
        pointed.update(t["base"] + x for x in struct.unpack_from(f"<{t['n']}H", data, t["table"]))
    out, p = [], start
    while p < end:
        codes, term = raw_string(data, p)
        if codes is None:
            break
        if codes and p not in pointed:
            out.append((p, codes, term))
        p += 2 * (len(codes) + 1)
        while p < end and is_term(struct.unpack_from("<H", data, p)[0]):
            p += 2
    return out


def write_in_place(data, off, old_codes, term, new_codes):
    """문자열을 **제자리에서** 바꾼다 — 새 글이 더 짧거나 같을 때만(넘치면 운다). 남는 칸은 0 으로 채우고 종결은 원래 값."""
    if len(new_codes) > len(old_codes):
        raise ExeTextError(f"제자리 0x{off:X}: {len(new_codes)}코드는 {len(old_codes)}칸을 넘는다")
    got, t = raw_string(data, off)
    if got != old_codes or t != term:
        raise ExeTextError(f"제자리 0x{off:X}: 원본이 달라졌다")
    n = len(old_codes) + 1
    struct.pack_into(
        f"<{n}H", data, off, *new_codes, term, *([TERM_ZERO] * (len(old_codes) - len(new_codes)))
    )


def glued_entries(data, tables):
    """[(오프셋, [짝 오프셋…])] — 표가 가리키는데 **바로 앞이 종결이 아닌** 문자열과, 주소로 그 뒤 항목들.

    🔴 **표 바로 뒤 첫 항목은 구역 스캐너 눈에 안 보인다**(2026-09-27). 표의 마지막 워드(오프셋
       값)가 종결이 아니라서 `dump_names.strings()` 가 표와 첫 문자열을 **한 덩어리**로 읽고, 그
       덩어리엔 표 값이 섞여 있어 통째로 버린다. 그래서 표마다 첫 항목 하나씩이 게이트·UI 자리·
       「쓰는 코드」 셈에서 빠져 있었다 — `ページ`(페이지 1)·`イノシシ`·`フォルティア`·`ハチよせ`·
       `戦闘設定`. 짝 오프셋은 **갈래(kind)를 정하는 데** 쓴다 — 스캐너가 찾은 첫 짝의 구역 라벨이
       곧 이 항목의 갈래다(주소로는 앞 구역 라벨에 걸려 틀린다). ⚠ 바로 다음 짝이 빈 문자열이면
       스캐너가 안 세므로(`フォルティア` 뒤가 그랬다) 몇 개를 넘겨 준다 — `kind_of` 로 고른다.
    """
    out = []
    for t in tables:
        ents = sorted(set(struct.unpack_from(f"<{t['n']}H", data, t["table"])))
        offs = [t["base"] + x for x in ents]
        for i, off in enumerate(offs):
            if off < 2 or is_term(struct.unpack_from("<H", data, off - 2)[0]):
                continue
            if i + 1 < len(offs):
                out.append((off, offs[i + 1 : i + 6]))
    return out


def kind_of(mates, kind_at):
    """짝들 중 스캐너가 라벨을 붙인 첫 자리의 갈래 — 없으면 None."""
    return next((kind_at[m] for m in mates if kind_at.get(m)), None)


def table_of(data, offs, cm, tables=None):
    """(표 주소, base, N) — 그 구역의 문자열을 담는 표. 없으면 None.

    ⚠ **구역 근처를 뒤지지 않는다.** 라벨이 붙인 경계는 사람 눈이 정한 것이라 표의 시작과
      안 맞고(실측: ED4 인물 표는 `アヴィン` 부터인데 라벨은 `マイル` 부터였다), 표가
      풀에서 멀리 떨어져 있기도 하다. **파일 전체에서 규격에 맞는 표를 먼저 찾아 두고**
      「그 구역의 문자열을 가장 많이 담은 표」를 고른다.
    """
    if not offs:
        return None
    if tables is None:
        tables = scan_tables(data, cm)
    want = set(offs)
    best = None
    for t in tables:
        ent = struct.unpack_from(f"<{t['n']}H", data, t["table"])
        hit = len(want & {t["base"] + x for x in ent})
        if hit and (best is None or hit > best[0]):
            best = (hit, t)
    if best is None:
        return None
    t = best[1]
    return t["table"], t["base"], t["n"]


def span(data, tbl, base, n):
    """(풀 시작, 풀 끝) — 표가 가리키는 문자열이 차지한 바이트 범위."""
    ents = struct.unpack_from(f"<{n}H", data, tbl)
    lo = base + min(ents)
    hi = lo
    for x in ents:
        e = string_end(data, base + x)
        if e is not None:
            hi = max(hi, e)
    return lo, hi


def chunks(data, tbl, base, n):
    """[(시작, 끝, [옛 시작…])] — 풀을 **빈틈으로 끊어** 예산 칸을 나눈다.

    🔴 **빈틈은 닻이다.** 표가 안 가리키는 문자열이 풀 안에 섞여 있다(실측: ED4 계급 표
       안의 「力」 4B, 무기 표 안의 16B). 코드가 절대 주소로 그걸 가리킬 수 있으니
       **아무것도 빈틈을 넘어 움직이면 안 된다.** 칸마다 따로 예산을 잡는다.
    """
    starts = sorted(set(struct.unpack_from(f"<{n}H", data, tbl)))
    out, cur = [], []
    prev_end = None
    for x in starts:
        off = base + x
        end = string_end(data, off)
        if end is None:
            raise ExeTextError(f"0x{off:X} 가 종결로 안 끝난다")
        if prev_end is not None and off != prev_end:
            out.append((cur[0][0], prev_end, [o for o, _ in cur]))
            cur = []
        cur.append((off, end))
        prev_end = end
    if cur:
        out.append((cur[0][0], prev_end, [o for o, _ in cur]))
    return out


def _share_tails(starts, base, want, terms, lo):
    """(풀 바이트, {옛 x: 새 x}) | None — 꼬리가 같은 이름을 한 문자열로 겹친다.

    긴 것부터 놓고, 나머지가 **이미 놓은 문자열의 꼬리(종결 포함)** 면 그 가운데를 가리킨다.
    같은 종결을 쓰는 것끼리만 겹친다. 결정적이다(길이 내림차순, 같으면 주소 순).
    """
    order = sorted((off - base for off in starts), key=lambda x: (-len(want[x]), x))
    pool, remap, placed = bytearray(), {}, []  # placed: [(codes, term, 풀 안 시작 바이트)]
    for x in order:
        codes, term = want[x], terms[x]
        hit = None
        for pc, pt, at in placed:
            if pt == term and len(pc) > len(codes) and pc[len(pc) - len(codes) :] == codes:
                hit = at + 2 * (len(pc) - len(codes))
                break
        if hit is None:
            hit = len(pool)
            placed.append((codes, term, hit))
            pool += struct.pack(f"<{len(codes)}H", *codes) + struct.pack("<H", term)
        remap[x] = lo - base + hit
    return bytes(pool), remap


def rebuild(data, tbl, base, n, new_codes, cm=None, pad_code=None):
    """표와 풀을 다시 싼다. `new_codes` 는 표 순서대로 N개.

    🔴 **표 순서가 곧 배치 순서는 아니다.** 표가 같은 문자열을 두 번 가리키기도 하므로
       **주소 순으로 유일한 조각만** 다시 싸고 표는 그 새 자리를 가리키게 한다.
    🔴 **빈틈을 넘어 움직이지 않는다**(`chunks`) — 칸마다 따로 예산을 본다.
    🔴 종결 바이트는 **원본 것을 그대로 쓴다** — 표마다 다르고(`0x8002`·`0xFFFF`·`0x0000`)
       바꾸면 그 문안이 화면에 안 붙는다(새턴 ED3 에서 겪은 사고와 같은 종류다).
    ⚠ 같은 자리를 가리키는 항목엔 **같은 문안**을 줘야 한다 — 다르면 어느 쪽인지 정할 수 없다.

    🔴 **`pad_code` 없이 칸이 줄면 남는 자리를 `TERM_FFFF` 로 채운다 — 이게 일부 UI 목록에서
       사고를 낸다.** 실측(ED3, 2026-09-26): 시스템 설정·메시지속도 목록은 **표를 안 보고
       종결마다 다음 문자열로 이어 읽는 순차 스캔**이다. 그 목록이 참조하는 문자열 하나가
       이 표의 칸 끝에 걸려 있었는데, 문안이 짧아져 생긴 슬랙을 `TERM_FFFF`(빈 문자열
       두 개)로 채우자 순차 스캐너가 **빈 문자열 = 목록 끝**으로 읽어 4줄이 2줄로 잘렸다
       (`docs/devlog.md` 09-26 참조). `pad_code` 를 주면 슬랙을 **그 칸의 마지막 조각 자신의
       글자열**에 이어 붙여(종결 앞으로) 채운다 — 안 보이는 채움 글자(스페이스)라 화면엔
       안 보이면서 순차 스캐너 눈엔 "빈 문자열"이 아니라 "긴 문자열 하나"로 남는다.
       ⚠ **칸 안에서 빌려주는 구간(여러 조각)이면 해당 없다** — 마지막 조각에만 닿는다.
    반환: (새 바이트열, 칸마다 남은 자리 합)
    """
    if len(new_codes) != n:
        raise ExeTextError(f"조각 수가 다르다: {len(new_codes)} (표 {n})")
    ents = struct.unpack_from(f"<{n}H", data, tbl)
    want, terms = {}, {}
    for i, x in enumerate(ents):
        _, t = raw_string(data, base + x)
        if t is None:
            raise ExeTextError(f"{i}번이 종결로 안 끝난다 (0x{base + x:X})")
        codes = list(new_codes[i])
        if x in want and want[x] != codes:
            raise ExeTextError(f"같은 자리(0x{base + x:X})에 서로 다른 문안이 왔다")
        want[x], terms[x] = codes, t

    out = bytearray(data)
    remap, slack, tail_pad = {}, 0, {}
    for lo, hi, starts in chunks(data, tbl, base, n):
        tail_shared = False
        pool = bytearray()
        for off in starts:
            x = off - base
            remap[x] = lo - base + len(pool)
            pool += struct.pack(f"<{len(want[x])}H", *want[x]) + struct.pack("<H", terms[x])
        if lo + len(pool) > hi:
            # 🔴 넘칠 때만 **꼬리 공유** — 한 이름이 다른 이름의 꼬리(종결까지)와 같으면 따로 두지 않고 그 가운데를 가리킨다
            #    (「철열쇠」 ⊂ 「강철열쇠」). 표 포인터라 가운데를 가리켜도 된다. 넘치지 않는 칸은 배치가 그대로다
            #    (그래서 지금까지의 빌드 바이트가 안 바뀐다).
            shared = _share_tails(starts, base, want, terms, lo)
            if shared is None:
                raise ExeTextError(f"예산 초과: 칸 0x{lo:X} 에 {len(pool)}B (자리는 {hi - lo}B)")
            pool, remap_part = shared
            remap.update(remap_part)
            tail_shared = True
            if lo + len(pool) > hi:
                raise ExeTextError(f"예산 초과: 칸 0x{lo:X} 에 {len(pool)}B (자리는 {hi - lo}B)")
        extra_words = (hi - lo - len(pool)) // 2
        if pad_code is not None and extra_words and starts and not tail_shared:
            last_x = starts[-1] - base
            term_bytes = pool[-2:]
            pool = pool[:-2] + struct.pack(f"<{extra_words}H", *([pad_code] * extra_words))
            pool += term_bytes
            tail_pad[last_x] = extra_words
        out[lo : lo + len(pool)] = pool
        for i in range(lo + len(pool), hi, 2):  # 그래도 남는 자리는 종결로 채운다
            struct.pack_into("<H", out, i, TERM_FFFF)
        slack += hi - lo - len(pool)
    if max(remap.values()) > 0xFFFF:
        raise ExeTextError("오프셋이 u16 을 넘었다")
    struct.pack_into(f"<{n}H", out, tbl, *(remap[x] for x in ents))

    # 🔴 되읽어 검산한다 — 「썼다」와 「다시 읽힌다」는 다른 말이다.
    back = struct.unpack_from(f"<{n}H", bytes(out), tbl)
    for i, x in enumerate(back):
        codes, term = raw_string(bytes(out), base + x)
        want_codes = list(new_codes[i]) + [pad_code] * tail_pad.get(ents[i], 0)
        if codes != want_codes or term != terms[ents[i]]:
            raise ExeTextError(f"되읽은 {i}번이 넣은 것과 다르다")
    return bytes(out), slack


def decode_table(data, tbl, base, n, disc):
    cm = textenc.charmap(disc)
    out = []
    for x in struct.unpack_from(f"<{n}H", data, tbl):
        codes, _ = read_string(data, base + x, cm)
        out.append(textenc.decode(codes or [], disc))
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────
def survey(disc):
    """[(구역, 갈래, 표 정보 or 사유)] — 실행파일 낱말 구역의 재삽입 경로."""
    import common
    import dump_names

    cm = textenc.charmap(disc)
    lba, size = common.iso_files(disc)[dump_names.EXE[disc]]
    data = common.read_lba(disc, lba, size)
    labels = dump_names.REGIONS[disc]
    regs = dump_names.split(dump_names.regions(dump_names.strings(data, cm)), labels)
    tables = scan_tables(data, cm)
    out = []
    for r in sorted(regs, key=lambda r: r["start"]):
        kind = labels.get(r["start"], "?")
        if kind not in dump_names.WORD_KINDS:
            continue
        t = table_of(data, r["offs"], cm, tables)
        if t:
            tbl, base, n = t
            budget = sum(hi - lo for lo, hi, _ in chunks(data, tbl, base, n))
            out.append((r, kind, {"table": tbl, "base": base, "n": n, "budget": budget}))
        else:
            dl = [r["offs"][i + 1] - r["offs"][i] for i in range(len(r["offs"]) - 1)]
            fixed = dl and all(x == dl[0] for x in dl)
            out.append((r, kind, {"fixed": dl[0] if fixed else None}))
    return data, cm, out


def main():
    import argparse

    import common

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--disc", choices=common.DISC_NAMES, default="ed3")
    ap.add_argument("--check", action="store_true", help="항등 재구축이 바이트 동일한가")
    a = ap.parse_args()
    common.verify_source(a.disc)
    data, cm, rows = survey(a.disc)
    tabled = [r for r in rows if "table" in r[2]]
    fixed = [r for r in rows if r[2].get("fixed")]
    print(
        f"{a.disc}: 낱말 구역 {len(rows)} — 표(예산 자유) {len(tabled)} · "
        f"고정폭 {len(fixed)} · 미상 {len(rows) - len(tabled) - len(fixed)}"
    )
    fail = 0
    for r, kind, info in rows:
        if "table" not in info:
            note = (
                f"고정폭 {info['fixed']}B" if info.get("fixed") else "미상 (길이 고정으로 다룬다)"
            )
            print(f"  0x{r['start']:06X} {kind:7s} {len(r['offs']):4d}개 → {note}")
            continue
        tbl, base, n, budget = info["table"], info["base"], info["n"], info["budget"]
        starts = set(struct.unpack_from(f"<{n}H", data, tbl))
        used = sum(2 * len(raw_string(data, base + x)[0] or []) + 2 for x in starts)
        # ⚠ 예산은 span 이 아니라 **칸의 합**이다 — 빈틈을 넘어 못 움직이므로(`chunks`).
        print(
            f"  0x{r['start']:06X} {kind:7s} {len(r['offs']):4d}개 → 표 0x{tbl:06X} N={n:3d} "
            f"예산 {budget}B (지금 {used}B)"
        )
        if a.check:
            cur = [
                raw_string(data, base + x)[0] or [] for x in struct.unpack_from(f"<{n}H", data, tbl)
            ]
            try:
                out, slack = rebuild(data, tbl, base, n, cur, cm)
            except ExeTextError as e:
                print(f"     🔴 항등 재구축 실패: {e}")
                fail = 1
                continue
            lo, hi = span(data, tbl, base, n)
            if out[lo:hi] != data[lo:hi] or out[tbl : tbl + n * 2] != data[tbl : tbl + n * 2]:
                print("     🔴 항등 재구축이 바이트 동일이 아니다")
                fail = 1
    # 🔴 떨어진 표(`DETACHED`)·고정 칸(`FIXED_SLOTS`)도 같은 검산을 받는다 — 구역 스캐너가
    #    그 자리를 「미상」으로 보므로 위 루프만으론 **빌드가 쓰는 표가 검사 밖**이었다(09-27).
    if a.check:
        for t in detached_tables(data, a.disc):
            tbl, base, n = t["table"], t["base"], t["n"]
            cur = [
                raw_string(data, base + x)[0] or [] for x in struct.unpack_from(f"<{n}H", data, tbl)
            ]
            try:
                out, _ = rebuild(data, tbl, base, n, cur)
            except ExeTextError as e:
                print(f"     🔴 떨어진 표 0x{tbl:06X} 항등 재구축 실패: {e}")
                fail = 1
                continue
            same = out == data
            print(f"  0x{tbl:06X} 떨어진 표 N={n:3d} → 항등 재구축 {'✓' if same else '🔴'}")
            fail |= not same
        slots = fixed_slots(data, a.disc)  # 모양이 다르면 여기서 운다
        if slots:
            print(f"  고정 칸 {len(slots)} → 모양 ✓")
    if a.check and fail:
        print("  🔴 실행파일 낱말 표 — 파서가 구조를 잘못 읽고 있다")
    return fail


if __name__ == "__main__":
    sys.exit(main())
