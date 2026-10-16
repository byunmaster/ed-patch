"""씬 블록별 **동적 글리프** — 글리프 뱅크 상한(`font.RESIDENT_MAX`)을 넘는 드문 글자를 블록이 직접 싣는다.

🔴 왜: 번역이 쓰는 글자가 1,000자를 넘는데(1,066) 상주 뱅크는 840칸(코드 자리 40 제외)이다. 리소스 캐시에서 뱅크를 더
떼면 종장 장 제목 띠가 조용히 안 뜨고(09-25, 원본이 캐시 14칸을 쓴다), 글리프를 줄이면 정본 순서(세이브 이름)가 깨진다.
⇒ **상주 816칸 + 동적 24칸**(`font.DYN0`~): 정본 글자(고유명사·시스템·전투·조사·숫자)와 문서 빈도가 높은 글자는 상주하고,
나머지(블록 하나가 쓰는 드문 글자 ≤ 24)는 **그 블록이 열릴 때** 자기 비트맵을 동적 칸에 복사한다.

동작(블록 열림 훅 — 게임 코드를 안 건드린다):
  · 블록 머리(`$A000`)는 늘 점프 한 개(`4C`/`20`)고 씬이 열릴 때 게임이 거기서 시작한다(10-11 BP: MPR5=0x76 에서 PC=$A000 적중).
    그 점프의 목적지를 블록 꼬리의 스텁으로 돌리고, 스텁은 복사를 마친 뒤 **원래 목적지로 `JMP`** 한다(`JSR` 머리여도 같다 —
    돌아갈 주소는 이미 스택에 있다).
  · 스텁: `PHP · PHA · SEI`, MPR3 에 글리프 뱅크를 걸고(`TMA/TAM` — 기존 렌더러 훅과 같은 패턴) `TII` 로 비트맵(n×18B)을
    동적 칸에, 받침·ㄹ받침 비트(각 3B)를 워크 RAM 비트맵의 같은 자리에 덮는다. 레지스터·플래그·MPR3 는 그대로 돌려 놓는다.
  · 블록마다 동적 칸 배정이 다르다(같은 글자가 블록마다 다른 코드) — `block_table` 이 블록 전용 글자표를 낸다.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import font
import hook
import messages as M
import sysbuild
import translate

BASE = M.BASE
BANK = 0x2000
GLYPH_WINDOW = hook.GLYPH_WINDOW_HI << 8  # 글리프 뱅크를 거는 창($6000, MPR3)
HEAD_OPS = (0x4C, 0x20)  # 블록 머리 점프(JMP · JSR)
BIT_BYTES = font.DYN_SLOTS // 8


class DynError(Exception):
    pass


def forced_chars() -> set[str]:
    """늘 상주해야 하는 글자 — 대사 본문 밖에서도 쓰이는 것(이름·UI·시스템·전투·조사·숫자·합자) + 씬 0(입장 배너 지명표)."""
    return (
        translate.name_chars()
        | translate.body_chars(0)
        | sysbuild.all_glyph_chars()
        | battle.glyph_chars()
        | set(font.JOSA_CHARS)
        | set(font.LIGATURES.values())
        | set(font.DIGIT_CHARS)
    )


def body_scene_ids() -> list[int]:
    return sorted(int(p.stem[3:]) for p in M.SCRIPT_DIR.glob("scn*.json") if int(p.stem[3:]) != 0)


def fill_candidates(have: set[str]) -> list[str]:
    """정본에 없는 본문 글자를 **씬(블록) 수 많은 순 → 코드 순**으로 — 상주 칸이 남으면 이 순서로 채운다."""
    df: Counter = Counter()
    for i in body_scene_ids():
        for ch in translate.body_chars(i) - have:
            df[ch] += 1
    return sorted(df, key=lambda ch: (-df[ch], ch))


def block_table(table: dict[str, bytes], scene_id: int) -> tuple[dict[str, bytes], list[str]]:
    """블록 전용 글자표 = 상주 표 + 동적 칸 배정(정상주에 없는 본문 글자, 코드 순)."""
    if scene_id == 0:
        return table, []
    dyn = sorted(ch for ch in translate.body_chars(scene_id) if ch not in table)
    if len(dyn) > font.DYN_SLOTS:
        raise DynError(f"씬 {scene_id}: 동적 글자 {len(dyn)}자 > {font.DYN_SLOTS}칸 — {''.join(dyn)}")
    t = dict(table)
    for k, ch in enumerate(dyn):
        t[ch] = font.code_of(font.DYN0 + k)
    return t, dyn


def _bits(dyn: list[str]) -> tuple[bytes, bytes]:
    """동적 칸 받침·ㄹ받침 비트(칸 번호 DYN0+k 가 8 의 배수에서 시작) 각 3B."""
    order = [""] * font.DYN0 + dyn
    has, rieul = font.batchim_tables(order)
    a = font.DYN0 >> 3
    return has[a : a + BIT_BYTES], rieul[a : a + BIT_BYTES]


def stub_bytes(org: int, data_addr: int, n: int, orig_target: int) -> bytes:
    """복사 스텁(HuC6280). `data_addr` = 글리프 n×18B · 받침 3B · ㄹ 3B 가 이어진 자료의 논리 주소."""
    bank_off = font.glyph_at(font.DYN0)
    bank = font.GLYPH_BANK0 + bank_off // BANK
    dst = GLYPH_WINDOW + bank_off % BANK
    a = hook.Asm(org)
    a.op("PHP")
    a.op("PHA")
    a.op("SEI")
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", bank)
    a.op("TAM", "tam", 3)
    a.tii(data_addr, dst, n * font.PACKED_BYTES)
    a.tii(data_addr + n * font.PACKED_BYTES, hook.BATCHIM_ADDR + (font.DYN0 >> 3), BIT_BYTES)
    a.tii(data_addr + n * font.PACKED_BYTES + BIT_BYTES, hook.RIEUL_ADDR + (font.DYN0 >> 3), BIT_BYTES)
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("PLA")
    a.op("PLP")
    a.op("JMP", "abs", orig_target)
    return a.bytes()


STUB_LEN = len(stub_bytes(0, 0, 1, 0))


def attach(block: bytes, dyn: list[str]) -> bytes:
    """블록 머리 점프를 스텁으로 돌리고 꼬리에 스텁 + 동적 글자 자료를 붙인다. 동적 글자가 없으면 그대로."""
    if not dyn:
        return block
    if block[0] not in HEAD_OPS:
        raise DynError(f"블록 머리가 점프가 아니다: {block[:3].hex()}")
    orig = block[1] | block[2] << 8
    stub_at = BASE + len(block)
    data_at = stub_at + STUB_LEN
    data = bytearray()
    for ch in dyn:
        data += font.pack(font.glyph(ch))
    has, rieul = _bits(dyn)
    data += has + rieul
    out = bytearray(block)
    out[1:3] = stub_at.to_bytes(2, "little")
    out += stub_bytes(stub_at, data_at, len(dyn), orig) + data
    if len(out) > BANK:
        raise DynError(f"블록이 {len(out)}B — 뱅크(8KB)를 넘는다(동적 글리프 {len(dyn)}자 · {STUB_LEN + len(data)}B 포함)")
    return bytes(out)


def simulate(block: bytes) -> tuple[bytearray, bytearray, bytearray, int, int]:
    """꼬리 스텁을 **엄밀히 흉내**내 효과를 돌려준다 — (글리프 뱅크 창 바이트, 받침 비트, ㄹ 비트, 끝 PC, 스택 균형).

    HuC6280 중 스텁이 쓰는 열한 옵코드만 안다 — 다른 옵코드를 만나면 죽는다(손인코딩 검산 · patcher-checklist).
    """
    win = bytearray(BANK)  # 글리프 뱅크(MPR3 에 걸렸을 때)
    has = bytearray(font.MAX_GLYPHS // 8 + 1)
    rieul = bytearray(font.MAX_GLYPHS // 8 + 1)
    mpr3 = 0x6A  # 아무 값 — 돌려놓는지 본다
    pc = (block[1] | block[2] << 8) - BASE
    stack: list[int] = []
    a = 0x55
    mpr = mpr3
    bank = None

    def rd(addr: int) -> int:
        return block[addr - BASE]

    def wr(addr: int, v: int) -> None:
        if hook.BATCHIM_ADDR <= addr < hook.BATCHIM_ADDR + len(has):
            has[addr - hook.BATCHIM_ADDR] = v
        elif hook.RIEUL_ADDR <= addr < hook.RIEUL_ADDR + len(rieul):
            rieul[addr - hook.RIEUL_ADDR] = v
        elif GLYPH_WINDOW <= addr < GLYPH_WINDOW + BANK:
            assert mpr == font.GLYPH_BANK0 + font.glyph_at(font.DYN0) // BANK, "글리프 뱅크가 안 걸린 채 썼다"
            win[addr - GLYPH_WINDOW] = v
        else:
            raise AssertionError(f"스텁이 엉뚱한 주소에 썼다: {addr:#06x}")

    while True:
        op = rd(BASE + pc)
        if op == 0x08:  # PHP
            stack.append(0x100)
            pc += 1
        elif op == 0x48:  # PHA
            stack.append(a)
            pc += 1
        elif op == 0x78:  # SEI
            pc += 1
        elif op == 0x43:  # TMA #8
            assert rd(BASE + pc + 1) == 0x08
            a = mpr
            pc += 2
        elif op == 0xA9:  # LDA #
            a = rd(BASE + pc + 1)
            pc += 2
        elif op == 0x53:  # TAM #8
            assert rd(BASE + pc + 1) == 0x08
            mpr = a
            pc += 2
        elif op == 0x73:  # TII src,dst,len
            src = rd(BASE + pc + 1) | rd(BASE + pc + 2) << 8
            dst = rd(BASE + pc + 3) | rd(BASE + pc + 4) << 8
            ln = rd(BASE + pc + 5) | rd(BASE + pc + 6) << 8
            for i in range(ln):
                wr(dst + i, rd(src + i))
            pc += 7
        elif op == 0x68:  # PLA
            a = stack.pop()
            pc += 1
        elif op == 0x28:  # PLP
            assert stack.pop() == 0x100
            pc += 1
        elif op == 0x4C:  # JMP — 끝
            end = rd(BASE + pc + 1) | rd(BASE + pc + 2) << 8
            assert a == 0x55, "A 를 못 돌려놨다"
            assert mpr == mpr3 and bank is None, "MPR3 를 못 돌려놨다"
            return win, has, rieul, end, len(stack)
        else:
            raise AssertionError(f"스텁 시뮬레이터가 모르는 옵코드 {op:#04x} @ {BASE + pc:#06x}")
