"""ED4 실행파일 낱말 표 — 표 찾기 · 칸 예산 · 재구축(ps1-ed3 `exetext` 의 표 몫을 ED4 로 옮겼다 — 둘째 소비자가 ps1-ed3 라 **공용 후보**다).

실행파일 안 문자열은 **u16 오프셋 표 + 문자열 풀**로 앉아 있다(대본 멤버와 같은 규격 `[base] u16 표 N개(N=표[0]/2) · [base+2N] 풀`).
UI 문자열을 출력하는 함수(`0x80017334`)의 호출자 60곳은 대부분 `표 기준 + 오프셋` 을 `addu` 로 더해 문자열 주소를 만든다 — 그래서 **정적 포인터 검색이 0건**이었다.
표 항목만 고치면 문자열을 **새 자리로 옮기고 길이를 바꿀 수 있다**(칸 = 풀을 빈틈으로 끊은 구간이 예산).

🔴 빈틈은 닻이다 — 표가 안 가리키는 문자열이 풀 안에 섞여 있다. 아무것도 빈틈을 넘어 움직이지 않는다(`chunks`).
🔴 `rebuild(pad_code=…)` — 칸이 줄면 남는 자리를 **그 칸 마지막 조각 글자열 끝에** 안 보이는 채움 글자로 채운다. 종결 워드로 채우면 「표를 안 보고 종결마다
   다음 문자열로 이어 읽는 순차 스캔 목록」이 빈 문자열을 목록 끝으로 읽어 줄이 잘린다(ED3 실측 09-26).
"""

import struct

TERM_ZERO = 0x0000
TERM_FFFF = 0xFFFF


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


def raw_string(data, off, limit=400):
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


def string_end(data, off, limit=400):
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
    return [(lo, hi, st) for lo, hi, st in out]


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
    for lo_ext, hi, starts in chunks(data, tbl, base, n):
        tail_shared = False
        pool = bytearray()
        rel = {}
        for off in starts:
            x = off - base
            rel[x] = len(pool)
            pool += struct.pack(f"<{len(want[x])}H", *want[x]) + struct.pack("<H", terms[x])
        # 🔴 왼쪽 여유(`POOL_LEFT_SLACK`)는 **모자랄 때만** 쓴다 — 안 모자라면 원래 시작에 두어 배치가 그대로다(항등 재구축·옛 빌드 바이트 보존).
        lo = starts[0] if starts[0] + len(pool) <= hi else lo_ext
        for x, r in rel.items():
            remap[x] = lo - base + r
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


def write_in_place(data, off, old_codes, term, new_codes, pad_code=None):
    """문자열을 **제자리에서** 바꾼다 — 새 글이 더 짧거나 같을 때만(넘치면 운다). 종결은 원래 값.

    🔴 **남는 칸은 `pad_code`(안 보이는 스페이스)로 글자열 끝에 채운다** — 종결 뒤를 0 으로 채우면 문자열 **구조**가 원본과 달라진다
       (`글자 종결 0` → `글자 종결 0 0 0`). 월드맵 장소 패널 목록은 표를 안 보고 종결마다 다음 문자열로 이어 읽는 순차 스캔이라
       빈 문자열·낯선 구조에서 목록이 끊긴다(마스터 실기 10-08 「목록이 완전히 빔」). 채움 글자는 화면엔 안 보이고 종결 뒤 바이트는 안 건드린다.
       `pad_code=None`(옛 동작)이면 종결 뒤를 0 으로 채운다.
    """
    if len(new_codes) > len(old_codes):
        raise ExeTextError(f"제자리 0x{off:X}: {len(new_codes)}코드는 {len(old_codes)}칸을 넘는다")
    got, t = raw_string(data, off)
    if got != old_codes or t != term:
        raise ExeTextError(f"제자리 0x{off:X}: 원본이 달라졌다")
    n = len(old_codes) + 1
    gap = len(old_codes) - len(new_codes)
    if pad_code is not None:
        struct.pack_into(f"<{n}H", data, off, *new_codes, *([pad_code] * gap), term)
    else:
        struct.pack_into(f"<{n}H", data, off, *new_codes, term, *([TERM_ZERO] * gap))


# ── 목록 단위(unit) — 표 항목이 가리키는 것은 문자열 하나가 아니라 **목록의 머리**일 수 있다 ───────────────────────────────────
# 실측(ED4): 시스템 메뉴 목록은 `[魔 0][法 8000][道 0][具 8000]…[システム 8002]` 로 이어지고 표는 첫 조각만 가리킨다. 종결 워드가 읽는 법을 정한다:
#   `0x0000` = 같은 줄에 이어 그린다(조각) · `0x8000` = 다음 줄 · `0x8002` = 목록 끝. 머리만 옮기거나 중간 조각 길이만 바꾸면 순차 스캔이 끊기므로
#   **목록 전체가 한 단위**다 — 단위 안에서는 조각마다 길이가 자유이고 합이 칸 예산이다.
# ⚠ 단위를 어디까지로 보나는 규칙이다(추정): 머리 종결이 0 이면 `0x8000`/`0x8002` 가 나올 때까지 이어 보고, 안 나오면 머리 하나로 본다
#   (이름 표처럼 종결이 늘 0 인 표 뒤 빈틈 문자열을 단위로 삼키지 않으려는 안전장치). 다음 표 항목 시작을 만나면 거기서 끊는다.
LIST_END = 0x8002
LIST_CONT = (0x0000, 0x8000)


def unit_at(data, off, entry_starts, limit=40):
    """[(오프셋, 코드열, 종결)] — `off` 가 머리인 목록 단위. 종결 `0x0000` 은 같은 줄 조각, `0x8000` 은 줄 끝(목록 계속), 그 밖(`0x8002`·`0xFFFF`…)은 목록 끝."""
    pieces, p, seen_end = [], off, False
    for _ in range(limit):
        codes, term = raw_string(data, p)
        if codes is None:
            raise ExeTextError(f"0x{p:X} 가 종결로 안 끝난다")
        pieces.append((p, codes, term))
        p += 2 * (len(codes) + 1)
        if term != 0x0000:
            seen_end = True
        if term not in LIST_CONT or p in entry_starts:
            break
    if not seen_end:
        pieces = pieces[
            :1
        ]  # 줄 끝이 안 나오면 머리 하나(이름 표 — 종결이 늘 0 인 표 뒤 빈틈을 삼키지 않는다)
    return pieces


def units(data, tbl, base, n):
    """[{start, pieces, end}] — 표가 가리키는 **서로 다른** 머리마다(주소 순) 목록 단위."""
    entry_starts = {base + x for x in struct.unpack_from(f"<{n}H", data, tbl)}
    out = []
    for off in sorted(entry_starts):
        pieces = unit_at(data, off, entry_starts)
        end = pieces[-1][0] + 2 * (len(pieces[-1][1]) + 1)
        out.append({"start": off, "pieces": pieces, "end": end})
    return out


def unit_chunks(data, tbl, base, n):
    """[(시작, 끝, [단위…])] — 단위가 **바로 이어진** 덩어리가 예산 칸이다(사이 빈틈은 닻)."""
    out, cur = [], []
    for u in units(data, tbl, base, n):
        if cur and u["start"] != cur[-1]["end"]:
            out.append((cur[0]["start"], cur[-1]["end"], cur))
            cur = []
        cur.append(u)
    if cur:
        out.append((cur[0]["start"], cur[-1]["end"], cur))
    return out


def rebuild_units(data, tbl, base, n, edits, pad_code=None):
    """표와 풀을 다시 싼다 — `edits` = {조각 원래 오프셋: 새 코드열}(없는 조각은 원본 그대로). 반환 (새 바이트열, 남은 바이트 합).

    🔴 단위(목록) 전체를 순서대로 이어 놓고 표 항목은 새 머리 자리를 가리킨다. 종결 워드는 조각마다 **원본 값 그대로**.
    🔴 칸이 남으면 **마지막 조각의 글자열 끝**(종결 앞)을 안 보이는 채움 글자로 채운다(`pad_code`) — 종결 워드로 채우면 순차 스캔이 끊긴다.
    칸 예산(바이트)을 넘으면 `ExeTextError`. 빈틈(닻)은 안 움직인다.
    """
    ents = struct.unpack_from(f"<{n}H", data, tbl)
    out = bytearray(data)
    remap = {}
    slack = 0
    for lo, hi, us in unit_chunks(data, tbl, base, n):
        blob = bytearray()
        starts = {}
        for u in us:
            starts[u["start"]] = lo + len(blob)
            for off, codes, term in u["pieces"]:
                new = list(edits.get(off, codes))
                blob += struct.pack(f"<{len(new) + 1}H", *new, term)
        if lo + len(blob) > hi:
            raise ExeTextError(f"예산 초과: 칸 0x{lo:X} 에 {len(blob)}B (자리는 {hi - lo}B)")
        extra = (hi - lo - len(blob)) // 2
        if extra and pad_code is not None:
            # 🔴 채움은 **칸 마지막 조각이 원래 가졌던 길이까지만**(그보다 길어지면 창에서 자동으로 접혀 빈 줄이 늘 수 있다) — 남는 자리는 종결 뒤 0
            last = us[-1]["pieces"][-1]
            last_new = len(edits.get(last[0], last[1]))
            extra = min(extra, max(0, len(last[1]) - last_new))
        if extra and pad_code is not None:
            term_b = bytes(blob[-2:])
            blob = blob[:-2] + struct.pack(f"<{extra}H", *([pad_code] * extra)) + term_b
        out[lo : lo + len(blob)] = blob
        slack += hi - lo - len(blob)
        remap.update(starts)
        for i in range(lo + len(blob), hi, 2):
            struct.pack_into("<H", out, i, TERM_ZERO)
    if max(remap.values()) - base > 0xFFFF:
        raise ExeTextError("오프셋이 u16 을 넘었다")
    struct.pack_into(f"<{n}H", out, tbl, *(remap[base + x] - base for x in ents))
    return bytes(out), slack


# ── 표 통째로 옮기기 — 기준 상수(`lui+addiu`)를 고친다 ───────────────────────────────────────────────────────────────
# 호출자들은 표 시작 주소를 `lui rt,hi · addiu rd,rt,lo`(또는 `ori`)로 만들어 `기준 + u16 오프셋` 으로 문자열을 찾는다. 표와 풀을 다른 곳으로 옮기려면 그 상수를 새 주소로 바꾼다.
# 🔴 같은 `lui` 를 다른 상수 계산이 같이 쓰면(컴파일러가 `lui` 하나를 여러 `addiu` 가 공유) `lui` 를 바꿀 수 없다 — 그땐 `addiu` 만 고쳐 닿는지 보고, 안 닿으면 **옮기지 않고 운다**.
ADDR_BASE_OFF = 0x800  # 파일 오프셋 = RAM 주소 - 0x80010000 + 0x800
ADDR_BASE = 0x80010000 - 0x800


def _w(data, i):
    return struct.unpack_from("<I", data, 4 * i)[0]


def find_base_refs(data, ram, window=16):
    """[{lui, use, rt, rd, op, shared}] — `ram`(RAM 주소) 상수를 만드는 `lui+addiu/ori` 쌍. `shared` = 같은 `lui` 값을 **다른** 명령도 읽는다(`lui` 를 못 바꾼다)."""
    hi = ((ram >> 16) + (1 if (ram & 0xFFFF) >= 0x8000 else 0)) & 0xFFFF
    lo = ram & 0xFFFF
    n = len(data) // 4
    out = []
    for i in range(n):
        w = _w(data, i)
        if (w >> 26) != 0xF or (w & 0xFFFF) != hi:
            continue
        rt = (w >> 16) & 31
        uses = []
        others = 0
        for k in range(1, window + 1):
            if i + k >= n:
                break
            v = _w(data, i + k)
            op, rs, rd_t = v >> 26, (v >> 21) & 31, (v >> 16) & 31
            reads = rs == rt or (op == 0 and ((v >> 16) & 31) == rt)
            if op in (9, 0xD) and rs == rt and (v & 0xFFFF) == lo:
                # 🔴 같은 `lui` 뒤 **여러 번** 쓰일 수 있다 — 분기 앞뒤 두 길(`bne` 지연 슬롯의 `lui` + 두 `addiu`)이면 둘째를 놓쳐 옛 표를 읽는다(11-07 실측, 0x8004A0A0·0x8004A388)
                uses.append({"lui": i, "use": i + k, "rt": rt, "rd": rd_t, "op": op})
                continue  # 분기 뒤 길은 줄 순서로 이어지지 않는다 — rt 가 덮일 때까지 같은 상수 사용을 다 모은다
            if reads:
                others += 1
            if rd_t == rt and op in (9, 0xD, 0xF, 0x23, 0x21, 0x25, 0x24, 0x20) and not reads:
                break  # rt 가 덮였다
        for u in uses:
            u["shared"] = others > 0 or len(uses) > 1
            out.append(u)
    return out


def patch_base_refs(data, refs, new_ram):
    """`find_base_refs` 결과를 새 RAM 주소로 고친다 — 바이트열을 돌려준다.

    🔴 **`lui` 는 건드리지 않는다** — 같은 `lui` 를 다른 상수 계산이 같이 쓰기도 한다(`shared`). `addiu` 의 16비트 부호 범위가 `lui` 값 기준 [-0x8000, 0x7FFF] 이므로
       새 주소가 그 안에 들어야 한다(안 들면 `ExeTextError` — 새 자리를 `lui` 가까이 잡는다). `ori` 는 [0, 0xFFFF].
    """
    out = bytearray(data)
    for r in refs:
        lw = _w(out, r["lui"])
        uw = _w(out, r["use"])
        imm = new_ram - ((lw & 0xFFFF) << 16)
        ok = (-0x8000 <= imm <= 0x7FFF) if r["op"] == 9 else (0 <= imm <= 0xFFFF)
        if not ok:
            raise ExeTextError(
                f"기준 상수(코드 0x{0x80010000 + r['use'] * 4 - 0x800:08X}): 새 주소 0x{new_ram:08X} 가 `lui` 0x{(lw & 0xFFFF):04X} 의 16비트 범위 밖이다"
            )
        struct.pack_into("<I", out, 4 * r["use"], (uw & ~0xFFFF) | (imm & 0xFFFF))
    return bytes(out)


def _unit_bytes(u, edits):
    """단위(목록) 하나의 새 바이트열."""
    out = b""
    for off, codes, term in u["pieces"]:
        new = list(edits.get(off, codes))
        out += struct.pack(f"<{len(new) + 1}H", *new, term)
    return out


def relocate_units(
    data, tbl, base, n, edits, dest_off, pad_code=None, units_off=None, force_all=False, patch_refs=True, reserve=0
):
    """표를 `dest_off`(파일 오프셋)로 옮긴다 — **넘치는 칸에서 필요한 만큼의 단위만** 새 자리로 빼고 나머지는 제자리에서 다시 싼다.

    새 표 = `dest_off` 에 u16 N개(오프셋은 새 기준 = 새 표 시작 기준), 바로 뒤에 새 자리로 뺀 단위들. 안 넘치는 칸은 제자리 재구축(`rebuild_units` 와 같다)이고
    넘치는 칸은 **고친 단위 중 모자란 만큼을 덜어낼 가장 작은 것부터** 빼낸다(옛 자리는 나머지 단위가 당겨 쓴다). 코드의 기준 상수(`lui+addiu`)는 새 주소로 고친다(`lui` 불변).
    반환: (새 바이트열, 쓴 끝 오프셋(= 뺀 단위들의 끝), 뺀 단위 수). 안 닿거나 기준 상수를 못 찾으면 `ExeTextError`.
    🔴 옛 표는 **그대로 남는다**(닻 문자열이 절대 주소로 읽힐 수 있다) — 옛 표만 죽은 자료다. 새 기준에서 안 빼낸 단위까지 u16 오프셋으로 닿아야 한다.
    """
    ram_old = base - ADDR_BASE_OFF + 0x80010000
    refs = find_base_refs(data, ram_old) if patch_refs else []
    if patch_refs and not refs:
        raise ExeTextError(f"표 0x{tbl:X}: 코드에서 기준 상수를 못 찾았다 — 옮길 수 없다")
    ents = struct.unpack_from(f"<{n}H", data, tbl)
    new_base = dest_off
    ram_new = dest_off - ADDR_BASE_OFF + 0x80010000
    out = bytearray(data)
    cur = dest_off + 2 * (n + reserve) if units_off is None else units_off  # `reserve` — 표 뒤에 비워 두는 항목 수(게시판 4줄 안이 새 색인을 덧붙인다)  # 🔴 `units_off` — 뺀 단위들을 표와 다른 자리(표 기준 u16 안)에 둔다(10-25: 먼저 옮긴 표의 죽은 u16 배열)
    placed = {}
    moved = 0
    for lo, hi, us in unit_chunks(data, tbl, base, n):
        size = {u["start"]: len(_unit_bytes(u, edits)) for u in us}
        stay = list(us)
        out_units = []
        need = sum(size.values())
        if force_all:  # 🔴 표 하나를 통째로 새 자리로(표 0xA38 — 스택에 복사되는 구조체) — 모든 단위를 빼고 제자리는 안 남긴다
            out_units, stay, need = list(us), [], 0
        while need > hi - lo:
            over = need - (hi - lo)
            edited = [u for u in stay if any(off in edits for off, _c, _t in u["pieces"])]
            if not edited:
                raise ExeTextError(f"칸 0x{lo:X}: 고친 단위가 없는데 {over}B 넘친다")
            fit = [u for u in edited if size[u["start"]] >= over]
            pick = (
                min(fit, key=lambda u: (size[u["start"]], u["start"]))
                if fit
                else max(edited, key=lambda u: (size[u["start"]], -u["start"]))
            )
            stay.remove(pick)
            out_units.append(pick)
            need -= size[pick["start"]]
        blob = bytearray()
        for u in stay:
            placed[u["start"]] = lo + len(blob)
            blob += _unit_bytes(u, edits)
        extra = (hi - lo - len(blob)) // 2
        if extra and pad_code is not None and stay:
            last = stay[-1]["pieces"][-1]
            extra = min(extra, max(0, len(last[1]) - len(edits.get(last[0], last[1]))))
            if extra:
                term_b = bytes(blob[-2:])
                blob = blob[:-2] + struct.pack(f"<{extra}H", *([pad_code] * extra)) + term_b
        out[lo : lo + len(blob)] = blob
        for i in range(lo + len(blob), hi, 2):
            struct.pack_into("<H", out, i, TERM_ZERO)
        for u in out_units:
            placed[u["start"]] = cur
            b = _unit_bytes(u, edits)
            out[cur : cur + len(b)] = b
            cur += len(b)
            moved += 1
    vals = []
    for x in ents:
        v = placed[base + x] - new_base
        if not 0 <= v <= 0xFFFF:
            raise ExeTextError(
                f"표 0x{tbl:X}: 새 기준에서 0x{placed[base + x]:X} 까지 {v} 바이트 — u16 을 넘는다"
            )
        vals.append(v)
    struct.pack_into(f"<{n}H", out, dest_off, *vals)
    if not patch_refs:
        return bytes(out), cur, moved
    res = patch_base_refs(bytes(out), refs, ram_new)
    left = find_base_refs(res, ram_old) if ram_new != ram_old else []
    if left:  # 🔴 게이트 — 옛 표 기준 상수가 코드에 남으면 그 길은 죽은 배열(다른 표의 단위가 앉는다)을 읽는다(11-07: 분기 뒤 둘째 `addiu` 둘을 놓쳤다)
        raise ExeTextError(
            f"표 0x{tbl:X}: 옛 기준 상수가 코드에 남았다 {[hex(x['use'] * 4 - 0x800 + 0x80010000) for x in left[:4]]}"
        )
    return res, cur, moved
