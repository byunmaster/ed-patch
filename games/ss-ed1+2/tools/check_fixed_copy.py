"""**고정 길이 복사** 자리를 전수로 훑어, 우리 문안이 그 칸에 맞는지 본다.

    python3 tools/check_fixed_copy.py          # 빌드 이미지를 검사
    python3 tools/check_fixed_copy.py --list   # 자리 목록만 (원본 기준)

## 왜 필요한가 (2026-08-27, 「7격」에서 배웠다)

이 게임은 문자열을 `mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2` 언롤로 **정확히 N바이트**
퍼 나르는 자리가 많다(ED 9 · ED2 13). N 은 그 자리의 **원본 문자열에 딱 맞춰** 박혀 있다.

    회심  `会心の一撃!!\\n` 13B + NUL = 14B  → 복사 14B (종단까지 들어간다)
    이름  `セリオス`        8B  (NUL 없음)  → 복사 8B  (고정 폭 필드)

그래서 우리 문안이 **1바이트만 어긋나도** 조용히 깨진다:

- **길면** 뒤가 잘린다 — 회심은 NUL 이 잘려 **직전 메시지의 꼬리**가 화면에 이어졌다
  (유저 캡처의 「7격」 = `a7 88a5`).
- **짧으면** 남은 칸에 **옛 바이트가 그대로 남는다**.

🔴 **빌드도 되고 단위 테스트도 통과한다.** 인게임에서 그 상황(회심의 일격 등)을 만나야만
   보이고, 확률에 걸리면 QA 를 몇 바퀴 돌아도 안 나온다. 그래서 정적으로 잡는다.

## 어떻게 재나 — 정본 매핑 없이 **빌드 이미지에서 직접**

원본에서 자리(언롤 길이 · 소스 리터럴)를 찾고, **같은 리터럴을 빌드 이미지에서 다시 읽어**
그것이 가리키는 문자열을 잰다. 포인터가 재배치됐어도 따라간다 — 정본 표를 안 들어도 된다.

⚠ 우리가 **루프로 바꾼 자리**(`patch_crit_copy.py`)는 제약이 없어졌으므로 건너뛴다.
⚠ 소스 후보에 `%d` 같은 인자 문자열이 섞인다. 판정은 **원본과 우리 것의 길이 관계**로만
  하므로(원본이 그 칸에 어떻게 맞았는지를 기준으로 삼는다) 섞여도 오탐이 안 난다.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_crit_copy

LOAD_BASE = 0x06028000
FILES = ("/ED.BIN", "/ED2.BIN") + tuple(f"/BIN/ED2MON{i:02d}.BIN" for i in range(1, 11))
UNIT = bytes.fromhex("631472012230")  # mov.b @r1+,r3 · add #1,r2 · mov.b r3,@r2
TAIL = bytes.fromhex("611072012210")  # mov.b @r1,r1 · add #1,r2 · mov.b r1,@r2
MIN_RUN = 4  # 이보다 짧은 언롤은 문자열 복사로 보지 않는다
LOOKBACK = 0x30  # 소스 리터럴을 찾을 앞 범위
MAXLEN = 64  # 문자열 길이를 재는 상한


def _strlen(d, ram, cap=MAXLEN):
    """`ram` 이 가리키는 문자열의 내용 길이. 못 재면 None."""
    off = ram - LOAD_BASE
    if not (0 <= off < len(d) - 1):
        return None
    z = bytes(d[off : off + cap]).find(0)
    return None if z <= 0 else z


def sites(d):
    """`[(언롤 오프셋, 복사 길이, [(리터럴 주소, 소스 주소, 원본 길이)])]`."""
    out, i = [], 0
    while i < len(d) - 6:
        if bytes(d[i : i + 6]) != UNIT:
            i += 2
            continue
        n = 1
        while bytes(d[i + 6 * n : i + 6 * n + 6]) == UNIT:
            n += 1
        if n >= MIN_RUN:
            cap = 1 + n + (1 if bytes(d[i + 6 * n : i + 6 * n + 6]) == TAIL else 0)
            srcs = []
            for pc in range(max(0, i - LOOKBACK), i, 2):
                # ⚠ **`r1` 로 적재한 것만** 소스다 — 언롤이 `mov.b @r1+,r3` 로 읽는다.
                #   앞 범위의 pc 상대 로드를 전부 후보로 보면 남의 인자까지 딸려 와
                #   「원본 61B 인데 칸 5B」 같은 오탐이 난다(실측).
                w = (d[pc] << 8) | d[pc + 1]
                if (w & 0xFF00) != 0xD100:  # mov.l @(disp,pc),r1
                    continue
                lit = ((LOAD_BASE + pc + 4) & ~3) + (w & 0xFF) * 4
                if not (0 <= lit - LOAD_BASE < len(d) - 4):
                    continue
                v = struct.unpack(">I", bytes(d[lit - LOAD_BASE : lit - LOAD_BASE + 4]))[0]
                ln = _strlen(d, v)
                if ln is not None and ln <= cap:  # 칸보다 긴 원본은 그 자리의 소스가 아니다
                    srcs.append((lit, v, ln))
            if srcs:
                out.append((i, cap, srcs))
        i += 6 * n
    return out


# ── 의미 검사: 복사 자리를 **돌려서** 잰다 (2026-10-19) ────────────────────────────────
#
# 위 `sites`/`check` 는 `add #1,r2` 연속 꼴 하나만 안다. 그런데 몬스터 슬롯 B·C 이름은 **고정 오프셋**으로 한 바이트씩 쓴다
#
#     mov.b @r1+,r2 · add #104,r3 · mov.b r2,@r3 · mov r7,r3     (… #105, #106 … 로 이어 간다)
#
# 이 꼴은 UNIT 에 안 걸려 검산에서 통째로 빠졌다 → 「나무인愛」·「지팡이품」(이름 뒤가 잘림)이 화면까지 갔다.
# 꼴을 하나씩 더 외우면 다음 변형에서 또 샌다 — 그래서 **꼴이 아니라 효과**를 잰다: `mov.l @(d,pc),r1`
# 로 소스를 적재하는 자리마다 작은 해석기로 돌려, 그 소스 문자열의 바이트가 **어디로 몇 개 나가는지** 센다.
# 레지스터 값은 모르는 채(기호)로 두고 소스 바이트에만 꼬리표를 단다. 분기·루프·지연 슬롯·중간 진입(`bra`)도 같은 눈금이다.
SIM_STEPS = 400
SIM_MIN_COPY = 3  # 이보다 적게 나가면 문자열 복사가 아니다


def _sx8(v):
    return v - 256 if v & 0x80 else v


class _Stop(Exception):
    pass


def simulate(d, base, start, faults=None):
    """`start` 의 `mov.l @(d,pc),r1` 부터 돌려 `[(목적지, 소스 주소, 바이트)]` 와 소스 시작 주소를 낸다.

    - 목적지: 정수(절대) 또는 `("rN", 오프셋)`(들어올 때 레지스터 기준 — 몬스터 슬롯 base 가 이쪽이다)
    - 소스 바이트는 파일에서 **실제로** 읽는다(우리 문안이 들어간 빌드 이미지에서도 같은 눈금)
    - `r1` 을 다른 것으로 덮으면(다음 복사의 시작) 거기서 멈춘다 · 모르는 명령도 멈춘다
    """
    n = len(d)

    def word(a):
        o = a - base
        return (d[o] << 8) | d[o + 1] if 0 <= o < n - 1 else None

    def lit32(a):
        o = a - base
        return int.from_bytes(bytes(d[o : o + 4]), "big") if 0 <= o <= n - 4 else None

    # 레지스터는 전부 **같은 기호 기준**(`"R"`)에서 시작한다 — 슬롯 base 가 r7·r8·r5 중 무엇이든 `r3 = rB` 로 시작하는
    # 원본 언롤과 `mov rB,r3` 로 시작하는 우리 루프가 같은 목적지(`R+104`)로 읽혀야 비교가 된다.
    R = [("R", 0) for _ in range(16)]
    writes = []

    def add(v, c):
        if isinstance(v, int):
            return (v + c) & 0xFFFFFFFF
        if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], str):
            return (v[0], v[1] + c)
        raise _Stop

    def val(r):
        return R[r]

    T = None
    pc = start
    src0 = None

    def step_one(pc_):
        """한 명령. `(다음 pc 오버라이드 또는 None, 분기 종류)` — 분기는 호출부가 지연 슬롯을 돌린다."""
        nonlocal T, src0
        w = word(pc_)
        if w is None:
            raise _Stop
        op, a, b, lo = w >> 12, (w >> 8) & 15, (w >> 4) & 15, w & 15
        imm = w & 0xFF
        if w == 0x0009:  # nop
            return None
        if op == 0xD:  # mov.l @(disp,pc),Rn
            v = lit32(((pc_ + 4) & ~3) + imm * 4)
            if v is None:
                raise _Stop
            if a == 1:
                if src0 is not None:
                    raise _Stop  # 다음 복사의 시작
                src0 = v
            R[a] = v
            return None
        if op == 0x9:  # mov.w @(disp,pc),Rn
            o = pc_ + 4 + imm * 2 - base
            if not (0 <= o < n - 1):
                raise _Stop
            R[a] = (((d[o] << 8) | d[o + 1]) ^ 0x8000) - 0x8000 & 0xFFFFFFFF
            if a == 1 and src0 is not None:
                raise _Stop
            return None
        if op == 0xE:  # mov #imm,Rn
            if (
                a == 1 and imm != 0
            ):  # `mov #0,r1` 은 우리 루프의 꼬리 — 뒤로 흘러내리는지 보려면 계속 돈다
                raise _Stop
            R[a] = _sx8(imm) & 0xFFFFFFFF
            return None
        if op == 0x7:  # add #imm,Rn
            if a == 1 and not (src0 is not None and isinstance(R[1], int)):
                raise _Stop
            R[a] = add(R[a], _sx8(imm))
            return None
        if op == 0x6:
            if lo == 3:  # mov Rm,Rn
                if a == 1:
                    raise _Stop
                R[a] = R[b]
                return None
            if lo in (0, 4):  # mov.b @Rm(+),Rn
                addr = R[b]
                if not isinstance(addr, int):
                    raise _Stop
                o = addr - base
                if not (0 <= o < n):
                    # 🔴 주소 0 근처를 읽으면 **낙하**다 — 한 루프가 끝나 다음 루프로 흘러들어가 r1 이 어긋난 것
                    #   (2026-10-19 나무인간C 이름이 통째로 빈 사고). 정상 코드는 널 지대를 안 읽는다.
                    if faults is not None and addr < 0x01000000:
                        faults.append(pc_)
                    raise _Stop
                if lo == 4 and a != b:
                    R[b] = add(R[b], 1)
                R[a] = ("b", addr, d[o])
                return None
            raise _Stop
        if op == 0x2:
            if lo == 0:  # mov.b Rm,@Rn
                v = R[b]
                if isinstance(v, tuple) and v[0] == "b":
                    writes.append((R[a], v[1], v[2]))
                return None
            if lo == 8:  # tst Rm,Rn
                x, y = R[a], R[b]
                if isinstance(x, tuple) and x[0] == "b":
                    x = x[2]
                if isinstance(y, tuple) and y[0] == "b":
                    y = y[2]
                if not (isinstance(x, int) and isinstance(y, int)):
                    raise _Stop
                T = (x & y) == 0
                return None
            raise _Stop
        if op == 0x8 and a in (0x9, 0xB, 0xD, 0xF):  # bt · bf · bt/s · bf/s
            if T is None:
                raise _Stop
            take = T if a in (0x9, 0xD) else not T
            tgt = pc_ + 4 + _sx8(imm) * 2
            return ("cond", take, tgt, a in (0xD, 0xF))
        if op == 0xA:  # bra
            return ("bra", True, pc_ + 4 + (((w & 0xFFF) ^ 0x800) - 0x800) * 2, True)
        raise _Stop

    try:
        for _ in range(SIM_STEPS):
            r = step_one(pc)
            if r is None:
                pc += 2
                continue
            _k, take, tgt, has_delay = r
            if has_delay:
                r2 = step_one(pc + 2)
                if r2 is not None:
                    raise _Stop
            pc = tgt if take else pc + (4 if has_delay else 2)
    except _Stop:
        pass
    return writes, src0


def copy_sites(d, base):
    """`[(시작 pc, 소스 주소, 쓰기 목록)]` — 소스 문자열 바이트를 `SIM_MIN_COPY` 개 이상 내보내는 자리."""
    out = []
    for pc in range(0, len(d) - 4, 2):
        if d[pc] != 0xD1:
            continue
        writes, src0 = simulate(d, base, base + pc)
        if src0 is None:
            continue
        mine = [w for w in writes if src0 <= w[1] < src0 + 64]
        if len(mine) >= SIM_MIN_COPY:
            out.append((base + pc, src0, mine))
    return out


def semantic_check(orig, built, base):
    """`([(시작 pc, 원본 길이, 우리 길이, 나간 바이트 수, 왜)], 본 자리 수)` — 우리 이름이 **잘리는** 자리.

    기준은 위 `check` 와 같다(원본이 NUL 까지 넣던 자리는 우리도 넣어야 · 고정 폭이면 칸을 넘지 말아야). 다른 건
    **우리 것을 실제로 돌린** 결과로 잰다는 것 — 루프로 바꾼 자리는 NUL 까지 나가므로 저절로 통과한다.
    """
    bad, seen = [], 0
    for pc, src0, wr in copy_sites(orig, base):
        seen += 1
        o_nul = any(b == 0 for _d, _s, b in wr)
        o_len = bytes(orig[src0 - base : src0 - base + 64]).find(0)
        flt = []
        got = simulate(built, base, pc, flt)
        if flt:
            bad.append(
                (
                    pc,
                    o_len,
                    -1,
                    0,
                    f"낙하 — 0x{flt[0]:08X} 에서 널 주소를 읽는다(루프가 끝나고 다음 루프로 흘러들었다)",
                )
            )
            continue
        bw = [w for w in got[0] if got[1] is not None and got[1] <= w[1] < got[1] + 64]
        if got[1] is None:
            bad.append((pc, o_len, -1, 0, "시작이 사라졌다 — 복사 자리가 바뀌었다"))
            continue
        z = bytes(built[got[1] - base : got[1] - base + 64]).find(0)
        our = 64 if z < 0 else z
        nul = any(b == 0 for _d, _s, b in bw)
        # 목적지가 그대로여야 한다 — 루프가 엉뚱한 곳에 쓰면 NUL 이 나가도 이름이 안 간다
        if bw and wr and bw[0][0] != wr[0][0]:
            bad.append((pc, o_len, our, len(bw), f"목적지가 바뀌었다 {wr[0][0]} → {bw[0][0]}"))
            continue
        if o_nul and not nul:
            bad.append(
                (
                    pc,
                    o_len,
                    our,
                    len(bw),
                    "종단이 안 나간다 — 이름 뒤가 잘리고 직전 내용이 이어진다",
                )
            )
        elif not o_nul and our > len(bw):
            bad.append((pc, o_len, our, len(bw), "칸을 넘는다 — 뒤가 잘린다"))
    return bad, seen


def _has_halfwidth_kana(b):
    """SJIS 바이트열에 **단독 반각 가나**(0xA1~0xDF)가 있나 — 2바이트 글자의 뒷바이트는 안 센다."""
    i = 0
    while i < len(b):
        c = b[i]
        if 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC:
            i += 2
        elif 0xA1 <= c <= 0xDF:
            return True
        else:
            i += 1
    return False


def kana_sources(orig, built, base):
    """`[(시작 pc, 소스 주소, 길이)]` — 복사 소스가 **빌드에서도 반각 가나**인 자리(번역이 안 간 이름).

    🔴 복사 코드가 맞아도 퍼 나르는 문자열이 일본어면 화면에 그대로 나간다(2026-10-19 ED1 「ｼﾞｬｰﾃﾞｲﾝｿﾞﾝﾋﾞA」 — 길이는 맞아서
       위 두 검사가 다 통과했다). 원본 소스가 반각 가나가 아니었던 자리는 안 센다.
    """
    out = []
    for pc, src, _wr in copy_sites(orig, base):
        got = simulate(built, base, pc)
        if got[1] is None:
            continue
        z = bytes(built[got[1] - base : got[1] - base + 64]).find(0)
        o = bytes(orig[src - base : src - base + 64])
        if _has_halfwidth_kana(
            bytes(built[got[1] - base : got[1] - base + z])
        ) and _has_halfwidth_kana(o[: max(o.find(0), 0)]):
            out.append((pc, got[1], z))
    return out


def check(fname, orig, built, skip):
    """`([(리터럴, 원본길이, 우리길이, 복사길이, 왜)], [못 잰 리터럴]) — 어긋난 것만."""
    bad, unread = [], []
    for at, cap, srcs in sites(orig):
        if at in skip:
            continue
        # 우리가 NUL 종단 루프로 바꾼 자리(`patch_namecopy`)는 제약이 없다 — 빌드에서 언롤이 사라졌다
        if bytes(built[at : at + 6]) != UNIT:
            continue
        for lit, _v, ln in srcs:
            off = lit - LOAD_BASE
            nv = struct.unpack(">I", bytes(built[off : off + 4]))[0]
            our = _strlen(built, nv)
            if our is None:
                # 🔴 **「못 쟀다」와 「볼 게 없다」를 가른다**(2026-09-04). 주소가 파일 밖이면
                #    문자열이 아니라 볼 게 없는 것이지만, `MAXLEN` 안에 NUL 이 없어서 못 쟀다면
                #    그건 **검사를 건너뛴 것**이다. 조용히 넘기면 초록불이 「없다」가 아니라
                #    「안 봤다」가 된다(체크리스트 4-B — 같은 꼴을 `scan_untranslated` 에서
                #    실제로 물렸다). 지금은 0건이라 실패로 안 치고 세어 보고만 한다.
                o2 = nv - LOAD_BASE
                if 0 <= o2 < len(built) - 1 and bytes(built[o2 : o2 + MAXLEN]).find(0) < 0:
                    unread.append(lit)
                continue
            # 🔴 기준은 **원본이 그 칸에 어떻게 맞았나**다.
            #    ⚠ 「우리 것이 짧다」는 결함이 아니다 — 짧으면 NUL 이 함께 복사돼 목적지가
            #      거기서 끊긴다. 오히려 안전하다. 처음엔 이걸 실패로 쳤다가 오탐 9곳을
            #      냈다(이름 여섯 · `ＥＰ` 셋). 늘 빨간불인 게이트는 아무도 안 본다.
            if ln + 1 <= cap:  # 원본이 NUL 까지 넣던 자리 — 우리도 넣어야 한다
                if our + 1 > cap:
                    bad.append((lit, ln, our, cap, "종단이 잘린다 — 직전 내용이 이어진다"))
            elif our > cap:  # 원본이 NUL 없이 꽉 채우던 고정 폭 필드
                bad.append((lit, ln, our, cap, "칸을 넘는다 — 뒤가 잘린다"))
    return bad, unread


def main():
    common.verify_source()
    listing = "--list" in sys.argv
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    if not listing and not os.path.exists(dst):
        raise SystemExit(f"먼저 빌드한다 — {dst} 가 없다")
    _f, mm = (None, None) if listing else common.open_image(dst)
    files = {} if listing else {p: (lba, s) for p, lba, s in common.iso_files(mm)}

    total, fails = 0, 0
    global LOAD_BASE
    import patch_ui

    for fname in FILES:
        orig = common.extract(fname)
        # 🔴 오버레이(`ED2MON*`)는 적재 주소가 다르다 — 리터럴을 파일 오프셋으로 바꿀 때 쓴다(2026-10-09)
        LOAD_BASE = patch_ui.ptr_base(fname)
        # 우리가 루프로 바꾼 자리는 제약이 없다 — 건너뛴다
        if fname in ("/ED.BIN", "/ED2.BIN"):
            cat, _size = patch_crit_copy.find_copy(orig)
            skip = {at for at, _cap, _s in sites(orig) if cat <= at <= cat + 0x80}
        else:
            skip = set()
        if listing:
            print(f"=== {fname} ===")
            for at, cap, srcs in sites(orig):
                mark = " (루프로 바꿈)" if at in skip else ""
                print(f"  0x{LOAD_BASE + at:08X} 복사 {cap}B{mark}")
                for _lit, v, ln in srcs:
                    kind = "NUL 포함" if ln + 1 == cap else ("고정 폭" if ln == cap else "-")
                    s = bytes(orig[v - LOAD_BASE :][:ln])
                    try:
                        txt = s.decode("cp932")
                    except UnicodeDecodeError:
                        txt = s.hex()
                    print(f"      0x{v:08X} {txt!r} {ln}B [{kind}]")
            continue
        n = len(sites(orig))
        total += n
        built = common.read_extent(mm, *files[fname])
        bad, unread = check(fname, orig, built, skip)
        fails += len(bad)
        # 🔴 꼴이 아니라 **효과**로 한 번 더 잰다 — 위 `check` 가 못 보는 꼴(고정 오프셋 · 공유 런 중간 진입 · 짧은 런)
        sem, seen = semantic_check(orig, built, LOAD_BASE)
        fails += len(sem)
        if sem:
            print(f"  ❌ {fname}: 의미 검사 — 복사 {seen}곳 중 {len(sem)}곳에서 이름이 잘린다")
            for pc, ln, our, n, why in sem:
                print(f"     0x{pc:08X}: 원본 {ln}B · 우리 {our}B · 복사 {n}B — {why}")
        else:
            print(f"  ✅ {fname}: 의미 검사 — 복사 {seen}곳 전부 NUL 까지 나간다")
        kana = kana_sources(orig, built, LOAD_BASE)
        fails += len(kana)
        for pc, src, ln in kana:
            print(
                f"  ❌ {fname}: 0x{pc:08X} 복사 소스 0x{src:08X} 가 반각 가나 {ln}B — 번역이 안 갔다"
            )
        if unread:
            # ⚠ 「못 쟀다」는 실패가 아니라 **안 본 것**이다 — 조용히 넘기지 않는다
            print(
                f"  ⚠ {fname}: 길이를 못 잰 자리 {len(unread)}곳 (MAXLEN {MAXLEN}B 안에 NUL 이 없다)"
            )
        if bad:
            print(f"  ❌ {fname}: 고정 복사 {len(bad)}곳이 어긋난다")
            for lit, ln, our, cap, why in bad:
                print(f"     0x{lit:08X}: 원본 {ln}B · 우리 {our}B · 칸 {cap}B — {why}")
        else:
            print(f"  ✅ {fname}: 고정 복사 {n}곳 — 전부 칸에 맞는다")
    if mm:
        mm.close()
        _f.close()
    if fails:
        raise SystemExit(f"고정 길이 복사 {fails}곳이 어긋난다 — 화면이 조용히 깨진다")


if __name__ == "__main__":
    main()
