"""엔진 패치 — 대사창 반각(공백·부호 6px)을 **타일 비트맵 합성**으로 (안 B, 2026-10-08). 지금은 ED3 만.

🔴 옛 방식(스프라이트 x·w 를 옮겨 칸을 좁힌다)은 걷었다 — 대사창 배경이 타일에 구워져 있어(칸 = 12px 격자 + VRAM 타일, 배경과 글자가
   한 몸) 칸을 움직이면 구멍·겹침·줄 끝 조각이 났다(`root-cause.md`). 이제 **스프라이트는 한 번도 안 건드리고** 글자를 픽셀 위치에 맞춰
   타일에 합성한다. 훅 본문·배치는 `tile_hook.py`, 모델(oracle)은 `tilecomp.py`, 해석기 대조는 `tests/test_tile_hook.py`.

## 렌더 구조 (2026-09-07, `ED3.EXE` 디스어셈블 + 에뮬 실측)

    창 열기   0x800174A0(x, y, cols, rows)  — 스프라이트 격자를 **글자를 모르는 채로** 미리 깐다. 대사창은 (4, 4|0x9E, 24, 4).
    글리프    0x80018758 op 2 — 코드 → 폰트 18B → 4bpp 12×13 타일을 VRAM 캐시 칸(slot)에 올린다.
              0x80018ACC 가 폰트 베이스를 만든다(`a1 + a0` 를 읽는다).                  ← 훅 자리
    배정      없다 — 격자를 깔 때 칸 k 의 UV 가 캐시 슬롯 base+k 로 **고정**된다.
    칸 색인   slot = 창.slotbase(+0xE) + 행(+0x14) × 열수(+6) + 열(+0x12)  (0x80039584)
    창 핸들   0x801D6498 부터 22B × 12 — +0 사용중 · +2 x · +4 y · +6 열 · +8 행 · +0xA 스프라이트 시작 · +0xE 슬롯 시작.

## 어디에 넣나

코드는 **죽은 함수** 0x8008DAD4(1,092B — jal 표적·점프표·참조·분기 유입이 없는 프롤로그), 자료(상태·표)는 SDK **오류 출력 함수 넷**
0x8008CD94(1,048B — 정상 플레이에서 안 돈다). 이미지 안의 0 런은 BSS 배열이라 못 쓴다. ⚠ 쓰기 전에 두 구간의 sha1 과 훅 자리의 원본 워드를
**대조한다** — 다른 덤프거나 두 번 적용하면 거기서 선다(체크리스트 2).

## 검산

손 인코딩이라 `verify` 가 capstone 으로 셋을 본다 — ① 끊김 없이 디코드 ② 지연 슬롯에 분기가 없다 ③ **로드 지연**(R3000 은 lw/lhu/lbu 바로
다음 명령이 그 레지스터를 못 읽는다). 그 위에 `tests/test_tile_hook.py` 가 훅을 해석기로 돌려 모델과 타일 단위로 대조한다.
"""

import hashlib
import re
import struct

import capstone
import font

# 격자 열 수 — `typeset.COLS` 가 같은 값을 쓴다(한 줄에 들어가는 글리프 수의 상한). 훅은 열 24 인 창(대사창)만 합성한다.
# 🔴 32 가 아니다 — 32 로 올리면 `▼`(다음 페이지)가 사라진다(2026-09-07 픽셀 대조로 확정, 원인 자리는 미발견).
COLS = 24

ED3 = {
    "site_a": 0x80018ACC,
    "site_a_orig": (0x3C05800A, 0x24A5E170),  # lui a1,0x800a · addiu a1,a1,-0x1e90
    "handles": 0x801D6498,  # 창 핸들 표 (22B × 12)
    "prims": 0x800CEA80,  # 스프라이트 배열 (20B × 0x400, 더블버퍼 +0x5000) — 안 B 는 안 건드린다(테스트가 지킨다)
    # 자료 자리 — SDK **오류 출력 함수 넷**(`0x8008CD94`~`0x8008D1AC`, printf 로 오류 문자열을 찍고 끝내는 길)이라 정상 플레이에서 안 돈다
    # (부팅·타이틀·첫 마을 대사·메뉴에서 exec BP 0회, 밖에서 들어오는 점프·포인터 없음). 상태·표 약 180B 를 둔다.
    "data": 0x8008CD94,
    "data_len": 0x418,
    "data_sha1": "d57a052cc38c14b23ed34fbc5cea4f24ffe48469",
    "dead": 0x8008DAD4,
    "dead_len": 1092,
    "dead_sha1": "748d1ea80bb0dd5c9e2798f31bcea3d07f4c2fbc",
}
PATCH = {"ed3": ED3}  # ED4 는 렌더러가 따로라(0x800164F0) 아직 안 찾았다 — 없으면 건너뛴다


# ── 손 어셈블러 (MIPS I · 리틀엔디언) — 쓰는 명령만 ─────────────────────────────────
_R = {
    n: i
    for i, n in enumerate(
        [
            "zero",
            "at",
            "v0",
            "v1",
            "a0",
            "a1",
            "a2",
            "a3",
            "t0",
            "t1",
            "t2",
            "t3",
            "t4",
            "t5",
            "t6",
            "t7",
            "s0",
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "s7",
            "t8",
            "t9",
            "k0",
            "k1",
            "gp",
            "sp",
            "fp",
            "ra",
        ]
    )
}
_LOADS = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25}
_STORES = {"sb": 0x28, "sh": 0x29, "sw": 0x2B}
_RTYPE = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "slt": 0x2A, "sltu": 0x2B}


def _reg(s):
    return _R[s.strip().lstrip("$")]


def _i(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _r(fn, rs, rt, rd, sa=0):
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | fn


def asm(text, base):
    """[워드] — 라벨 2-pass. 한 줄 한 명령, 지연 슬롯은 손으로 채운다."""
    lines = [ln.split("#")[0].strip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if ln]
    labels, body, pc = {}, [], base
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
            continue
        body.append((pc, ln))
        pc += 4
    words = []
    for pc, ln in body:
        op, _, rest = ln.partition(" ")
        a = [x.strip() for x in rest.split(",")] if rest else []

        def target(s):
            return labels[s] if s in labels else int(s, 0)

        if op == "nop":
            w = 0
        elif op in _LOADS or op in _STORES:
            m = re.match(r"(-?\w+)\((\$?\w+)\)", a[1])
            w = _i((_LOADS | _STORES)[op], _reg(m.group(2)), _reg(a[0]), int(m.group(1), 0))
        elif op == "addiu":
            w = _i(9, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op == "li":
            v = int(a[1], 0)
            assert -0x8000 <= v <= 0xFFFF, ln
            w = _i(9 if v < 0 else 0xD, 0, _reg(a[0]), v)
        elif op == "lui":
            w = _i(0xF, 0, _reg(a[0]), int(a[1], 0))
        elif op in ("ori", "andi", "slti", "sltiu"):
            w = _i(
                {"ori": 0xD, "andi": 0xC, "slti": 0xA, "sltiu": 0xB}[op],
                _reg(a[1]),
                _reg(a[0]),
                int(a[2], 0),
            )
        elif op in _RTYPE:
            w = _r(_RTYPE[op], _reg(a[1]), _reg(a[2]), _reg(a[0]))
        elif op == "move":
            w = _r(0x21, _reg(a[1]), 0, _reg(a[0]))
        elif op in ("sll", "sra", "srl"):
            w = _r({"sll": 0, "srl": 2, "sra": 3}[op], 0, _reg(a[1]), _reg(a[0]), int(a[2], 0))
        elif op == "div":
            w = _r(0x1A, _reg(a[1]), _reg(a[2]), 0)
        elif op == "mult":
            w = _r(0x18, _reg(a[0]), _reg(a[1]), 0)
        elif op in ("mflo", "mfhi"):
            w = _r(0x12 if op == "mflo" else 0x10, 0, 0, _reg(a[0]))
        elif op == "jr":
            w = _r(8, _reg(a[0]), 0, 0)
        elif op in ("j", "jal"):
            w = ((2 if op == "j" else 3) << 26) | ((target(a[0]) >> 2) & 0x3FFFFFF)
        elif op in ("beq", "bne"):
            w = _i(4 if op == "beq" else 5, _reg(a[0]), _reg(a[1]), (target(a[2]) - pc - 4) >> 2)
        elif op in ("blez", "bgtz", "bgez", "bltz"):
            code, rt = {"blez": (6, 0), "bgtz": (7, 0), "bgez": (1, 1), "bltz": (1, 0)}[op]
            w = _i(code, _reg(a[0]), rt, (target(a[1]) - pc - 4) >> 2)
        else:
            raise ValueError(f"모르는 명령: {ln}")
        words.append(w & 0xFFFFFFFF)
    return words, labels


_BRANCH = {"j", "jal", "jr", "jalr", "beq", "bne", "blez", "bgtz", "bgez", "bltz", "beqz", "bnez"}
_ALL_SRC = _BRANCH | {"sb", "sh", "sw", "div", "divu", "mult", "multu"}


def verify(words, base):
    """손 인코딩 검산 — ① 끊김 없이 디코드 ② 지연 슬롯에 분기 없음 ③ 로드 지연 위반 없음.

    ⚠ 재조립 대조까지는 못 한다(capstone 은 디스어셈블러다). 의미는 사람이 본다.
    """
    md = capstone.Cs(
        capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN
    )
    blob = b"".join(struct.pack("<I", w) for w in words)
    ins = list(md.disasm(blob, base))
    if len(ins) != len(words):
        raise AssertionError(f"디코드가 끊겼다 — {len(ins)}/{len(words)} (base {base:#x})")

    def regs(s):
        return set(re.findall(r"\$\w+", s))

    for k, i in enumerate(ins):
        nxt = ins[k + 1] if k + 1 < len(ins) else None
        if nxt is None:
            continue
        if i.mnemonic in _BRANCH and nxt.mnemonic in _BRANCH:
            raise AssertionError(f"{i.address:#x}: 지연 슬롯에 분기가 또 있다 ({nxt.mnemonic})")
        if i.mnemonic in _LOADS or i.mnemonic in ("mflo", "mfhi"):
            dest = i.op_str.split(",")[0].strip()
            ops = [x.strip() for x in nxt.op_str.split(",")]
            src = ops if nxt.mnemonic in _ALL_SRC else ops[1:]
            if dest in regs(", ".join(src)):
                raise AssertionError(
                    f"{i.address:#x}: 로드 지연 — {nxt.mnemonic} 이 {dest} 를 바로 읽는다"
                )
    return "\n".join(f"{i.address:08x}  {i.mnemonic:6s} {i.op_str}" for i in ins)




def _off(ram):
    return ram - font.EXE_TADDR + font.EXE_HDR


def _expect(exe, ram, words, what):
    got = struct.unpack_from(f"<{len(words)}I", exe, _off(ram))
    if tuple(got) != tuple(words):
        raise SystemExit(
            f"🔴 엔진 패치 사전조건 — {what} {ram:#x} 의 원본이 다르다: "
            f"{' '.join(f'{w:08x}' for w in got)} ≠ {' '.join(f'{w:08x}' for w in words)}"
        )


def half_codes(table):
    """반 칸(6px) 글자의 글리프 코드 — 공백 · 괄호(글리프 자리라 빌드마다 다르다) · 부호 원본 코드 `, . ? !`(= 1·2·4·5, `hangul_map.PUNCT`)."""
    # `…`(코드 3)는 전각 한 글자라 반 칸이 아니다 — `PUNCT` 값을 통째로 안 쓰고 쉼표·마침표·물음표·느낌표만 센다
    return [table[" "]] + [table[c] for c in "()" if c in table] + [0x01, 0x02, 0x04, 0x05]


def apply_panel(exe, disc):
    """월드맵 장소 패널 가운데 정렬 — 스텁을 자료 자리 뒤쪽에 놓고 패널 그리기 함수 세 군데를 `jal` 로 잇는다(`tile_hook.PANEL_SITES`)."""
    import tile_hook

    sites = tile_hook.PANEL_SITES.get(disc)
    if not sites:
        return ""
    for addr, orig, _label in sites:
        _expect(exe, addr, orig, "월드맵 패널 그리기")
    words, base, labels = tile_hook.panel_stubs(disc)
    p = PATCH[disc]
    off = _off(base)
    assert base - p["data"] + 4 * len(words) <= p["data_len"], "패널 스텁이 자료 자리를 넘는다"
    struct.pack_into(f"<{len(words)}I", exe, off, *words)
    for addr, orig, label in sites:
        jal = (3 << 26) | ((labels[label] >> 2) & 0x3FFFFFF)
        struct.pack_into(f"<{len(orig)}I", exe, _off(addr), jal, *([0] * (len(orig) - 1)))
    return f" · 월드맵 패널 가운데 정렬(스텁 {4 * len(words)}B @ {base:#x})"


# 전투 결과 창(승리·패배) — 창 생성 `jal 0x800174A0` 직전의 `addiu a2, zero, 8`(열 8 · 행 1, x=90 고정)이 **상수**라 원문 글자 수(戦闘に勝ちました=8)로 창이 정해진다.
#   한글 「전투에 이겼습니다」는 공백 포함 9칸이라 끝 「다」가 잘렸다(마스터 10-09) → 열을 9 로 넓힌다(창은 오른쪽으로 한 칸 자란다). 같은 함수 안 창 생성 호출 다섯 중 열을 상수 8 로 주는 건 이 둘뿐이다(15·10·레지스터 인자는 다른 창).
RESULT_WINDOWS = {
    "ed3": [(0x80070E50, "승리"), (0x80071134, "패배")],
}
RESULT_COLS = 10


# 필드 `square` 창(7×4 → 6×4) — 창 생성 상수(`0x8005C084~0x8005C090`: x=0x6A · y=0x54 · 열 7 · 행 4). 줄 글자 수가 4·6·5 라 열 7 이면 줄마다 반 칸 오차가 나는데(반 칸 공백은 커서 줄이 다시 그려지며 전각이 되어 못 쓴다 —
#   하이라이트 줄은 명령 종류 4 로 따로 그려져 안 B 훅(종류 1)을 안 탄다), **열 6 이면 4칸·6칸 줄이 정확히 가운데**다(5칸 「키설정변경」만 반 칸). x 를 6px 옮겨 화면 가운데를 지킨다.
SQUARE_WINDOW = {"ed3": ((0x8005C084, 0x2404006A, 0x24040070), (0x8005C08C, 0x24060007, 0x24060006))}  # (자리, 원본 워드, 새 워드)


# 「대열을 짤 수 없어 퇴각합니다.」 창(`0x80070B88`: x=50 · y=100 · 열 15 · 행 1) — 원문 15자 꼴이라 열이 15 상수다. 한글은 공백 포함 17칸이라 끝 두 글자가 칸이 없어 잘린다(칸 수 문제) → 열 17.
LINEUP_COLS = 17
LINEUP_WINDOW = {"ed3": (0x80070B80, 0x2406000F)}  # (`addiu a2, zero, 15` 자리, 원본 워드)


def apply_lineup_window(exe, disc):
    site = LINEUP_WINDOW.get(disc)
    if not site:
        return ""
    addr, orig = site
    _expect(exe, addr, (orig,), "대열 메시지 창 열 수")
    struct.pack_into("<I", exe, _off(addr), 0x24060000 | LINEUP_COLS)
    return f" · 대열 창 열 {LINEUP_COLS}"


def apply_square_window(exe, disc):
    sites = SQUARE_WINDOW.get(disc)
    if not sites:
        return ""
    for addr, orig, _new in sites:
        _expect(exe, addr, (orig,), "square 창 생성 상수")
    for addr, _orig, new in sites:
        struct.pack_into("<I", exe, _off(addr), new)
    return " · square 창 열 6"


def apply_result_windows(exe, disc):
    sites = RESULT_WINDOWS.get(disc)
    if not sites:
        return ""
    orig = 0x24060000 | 8  # addiu a2, zero, 8
    for addr, label in sites:
        _expect(exe, addr, (orig,), f"{label} 창 열 수")
    for addr, _label in sites:
        struct.pack_into("<I", exe, _off(addr), 0x24060000 | RESULT_COLS)
    return f" · 결과 창 열 {RESULT_COLS}"


def apply(exe, disc, table, josa=None):
    """실행파일(bytearray)에 타일 합성 훅을 넣는다. 코드는 죽은 함수에, 자료(상태·표)는 SDK 오류 함수 자리에 둔다.

    그 디스크에 패치가 없으면 None. 사전조건(두 구간 sha1 · 훅 자리 원본 워드)이 안 맞으면 **쓰기 전에** 선다.
    """
    import tile_hook

    p = PATCH.get(disc)
    if p is None or " " not in table:
        return None
    d0, x0 = _off(p["dead"]), _off(p["data"])
    for what, off, ln, sha in (
        ("죽은 함수", d0, p["dead_len"], p["dead_sha1"]),
        ("자료 자리", x0, p["data_len"], p["data_sha1"]),
    ):
        got = hashlib.sha1(bytes(exe[off : off + ln])).hexdigest()
        if got != sha:
            raise SystemExit(f"🔴 엔진 패치 사전조건 — {what} sha1 이 다르다 ({got[:12]})")
    _expect(exe, p["site_a"], p["site_a_orig"], "훅 자리")
    half = half_codes(table)
    markers = josa["markers"] if josa else [(0x7FFF, 0, 0, 0)] * tile_hook.N_MARK
    blist = josa["blist"] if josa else []
    words, labels = tile_hook.hooks_b(disc, len(blist), with_josa=josa is not None)
    mwords, mbase = tile_hook.msg_stub(disc, labels)
    assert 4 * len(words) <= p["dead_len"], f"훅 코드가 죽은 함수 자리를 넘는다 ({4 * len(words)}B > {p['dead_len']}B)"
    blob = tile_hook.data_blob(p, half, markers, blist)
    assert len(blob) <= p["data_len"], f"자료가 자리를 넘는다 ({len(blob)}B > {p['data_len']}B)"
    assert (mbase - p["data"]) + 4 * len(mwords) <= p["data_len"], "메시지 창 갈래가 자료 자리를 넘는다"
    assert len(blob) <= tile_hook.PANEL_CODE_OFF, "상태·표가 패널 스텁 자리를 넘는다"
    struct.pack_into(f"<{len(words)}I", exe, d0, *words)
    exe[x0 : x0 + len(blob)] = blob
    struct.pack_into(f"<{len(mwords)}I", exe, _off(mbase), *mwords)
    struct.pack_into("<II", exe, _off(p["site_a"]), (3 << 26) | ((p["dead"] >> 2) & 0x3FFFFFF), 0)
    import cursor_hook

    cursor = cursor_hook.apply(exe, disc)
    panel = apply_panel(exe, disc) + apply_result_windows(exe, disc) + apply_square_window(exe, disc) + apply_lineup_window(exe, disc) + cursor
    return f"타일 합성(반 칸 {len(half)}종) · 훅 {len(words)}워드 @ {p['dead']:#x} · 자료 {len(blob)}B @ {p['data']:#x}{panel}"
