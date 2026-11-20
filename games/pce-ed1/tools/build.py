"""pce-ed1 빌드 — 원본을 그대로 복사한 뒤 **선언한 자리만** 고쳐 쓴다.

    python3 games/pce-ed1/tools/build.py            # work/build/<꼬리표>/ed1.iso + .cue
    python3 games/pce-ed1/tools/build.py --edits work/edits_poc.json   # 개발/PoC 입력(커밋 안 함)

규율(루트 CLAUDE.md 「빌드 규율」· docs/patcher-checklist.md):
  · 원본은 읽기만(지문 확인) · 출력은 새 파일 · 실패하면 산출물을 `*.failed` 로 무효화
  · 쓰기는 `shared.disc.mode1.write_user_data`(EDC/ECC 재계산 + `expect` 사전조건)로만
  · **무변경 구간**: 고치겠다고 선언한 섹터 밖은 원본과 byte 대조
  · **되읽기**: 구운 이미지의 컨테이너를 다시 풀어 의도한 블록과 대조하고, 참조표·개수가 그대로인지 본다

⚠ 지금은 씬 컨테이너만 고친다. 폰트 후킹·글리프 뱅크·할당기 패치는 status.md 9절 설계대로 뒤에 붙인다.
"""

import argparse
from collections import Counter
import contextlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import battle
import band_fallback
import boxpack
import chapter_band
import common
import containers
import ending_sub
import font
import gfx_text
import glyphdyn
import hook
import hud_plate
import lz
import narration_gates
import gwin_rt
import voice_sched
import omake_art
import omake_font
import structure
import syscard_screen
import opening_sub
import credits_kr
import debug_item
import debug_item_list
import debug_warp
import hud_half
import list_strip
import musicresume
import winmask
import defeat_strip
import debugkey
import staffroll
import splitload
import zone_image
import sysbuild
import translate
import viewer

from shared.disc import mode1

SLOT_SECTORS = 16  # 컨테이너 한 칸(실측: 참조표 간격 16섹터 = 32KB)
ENTRY_BYTES = containers.ENTRY
BANK = 0x2000  # 풀린 블록은 뱅크 0x76 하나에 들어가야 한다


# 제품에 비모달 자막(안 B)을 넣는 씬 — `씬@rel` 은 그 컨테이너 사본만(씬 18 = 1장 지역 1 사본). 늘릴 땐 5뱅크 한계·split 가름(풀 자리)을 본다
GWIN_PRODUCT = "6,98,18@1268,224,17,32,40,41,151,46,50,62,63,88,168,196,201,204,73,74,100,203,177,34,57,20,155"  # 12씬 확장(+73·74·100·203 11-08 — 음성 자막이 아예 없던 draft 4씬)(마스터 11-05) — 32·41·151·46·50·62·63·88·168·196·201·204 는 초안 시각표(마스터 동기 검수 전)


class BuildError(Exception):
    pass


class WriteLedger:
    """🔴 **뒤 단계가 앞 단계의 바이트를 지웠나**를 잡는다.

    ss-ed1+2 가 실제로 물렸다(중계 2026-09-07): 뒤 단계가 이주 자리를 **원본 덤프의 칸 경계**로
    골랐는데 앞 단계가 그 표를 다시 깔아 놔서 **살아 있는 한글 위에 대사를 얹었다.**
    ⚠ **게이트 셋이 다 초록이었다** — 되읽기는 *자기가 쓴 직후*를, 라운드트립은 *덤프↔원본*을,
    무변경 구간은 *안 여는 파일*을 본다. **덮어쓰기는 아무도 안 본다.**

    ⚠ **「구간이 겹치나」로 물으면 안 된다** — 우리 쓰기는 대개 섹터 통째 read-modify-write 라
    겹침이 정상이다(실측: 그렇게 물었더니 오탐 여덟). 물어야 하는 것은
    **「다 쓴 뒤에도 각 쓰기의 바이트가 그대로인가」**다. 덮였으면 그때만 운다.
    """

    def __init__(self):
        self.spans: list[tuple[int, bytes, str]] = []

    def add(self, start: int, data: bytes, label: str):
        if data:
            self.spans.append((start, bytes(data), label))

    def verify(self, iso: Path) -> int:
        """구운 이미지를 열어 장부의 모든 구간이 아직 그 바이트인지 본다."""
        errs = []
        with open(iso, "rb") as f:
            for start, data, label in self.spans:
                got = bytearray()
                lba, off = divmod(start, common.USER)
                while len(got) < len(data):
                    f.seek(lba * common.RAW + common.USER_OFF)
                    got += f.read(common.USER)[off:]
                    lba, off = lba + 1, 0
                if bytes(got[: len(data)]) != data:
                    bad = next(i for i in range(len(data)) if got[i] != data[i])
                    errs.append(f"「{label}」 +{bad} 가 덮였다 (선형 {start + bad})")
        if errs:
            raise BuildError(
                f"쓴 바이트가 나중에 덮였다 {len(errs)}건:\n  " + "\n  ".join(errs[:10])
            )
        return len(self.spans)


@contextlib.contextmanager
def _record_writes(ledger: WriteLedger):
    """`mode1` 의 두 쓰기 함수를 감싸 장부에 적는다.

    ⚠ `shared/` 는 게임 브랜치에서 못 고친다(루트 CLAUDE.md) — 그래서 **여기서 감싼다.**
    좌표는 **유저 데이터 선형 바이트**(`lba × USER + offset`)라 두 함수를 같은 자로 잰다.
    ⚠ **`write_at` 은 속에서 `write_user_data` 를 부른다** — 중첩을 둘 다 적으면 안쪽 것이
    **섹터 통째**로 잡혀 그 섹터의 남은 자리가 「덮였다」로 뜬다(실측 오탐). **바깥만 적는다.**
    """
    from shared.disc import mode1

    at, ud = mode1.write_at, mode1.write_user_data
    depth = [0]

    def w_at(f, lba, size, offset, data, *, label, expect=None):
        outer = depth[0] == 0  # ⚠ **부르기 전에** 판정한다 — 끝난 뒤엔 깊이가 이미 돌아와 있다
        depth[0] += 1
        try:
            r = at(f, lba, size, offset, data, label=label, expect=expect)
        finally:
            depth[0] -= 1
        if outer:
            ledger.add(lba * common.USER + offset, data, label)
        return r

    def w_ud(f, lba, data, *, label, expect=None):
        outer = depth[0] == 0
        depth[0] += 1
        try:
            r = ud(f, lba, data, label=label, expect=expect)
        finally:
            depth[0] -= 1
        if outer:
            ledger.add(lba * common.USER, data, label)
        return r

    mode1.write_at, mode1.write_user_data = w_at, w_ud
    try:
        yield
    finally:
        mode1.write_at, mode1.write_user_data = at, ud


class FreePool:
    """트랙 끝 0 구간(rel 9786~, 286섹터)에서 이사 자리를 내준다. 이미 0 이 아니면 멈춘다(`write_user_data` expect)."""

    START = 9786  # 원본에서 끝까지 0 (containers 지문 · status 2절)

    def __init__(self):
        self.next = self.START

    def alloc(self, n_sec: int) -> int:
        at = self.next
        if at + n_sec > common.T2_LEN - debug_warp.POOL_SECTORS:  # 트랙 맨 끝 4섹터는 디버그 워프 풀 자리(`debug_warp.pool_rel`)
            raise BuildError(f"이사 자리가 모자란다: rel {at} + {n_sec} > 트랙 끝 {common.T2_LEN} − 워프 풀 {debug_warp.POOL_SECTORS}")
        self.next += n_sec
        return at


def patch_ref_table(f, refs, moves, touched) -> str:
    """참조표(44항목 · 3B = rel−34 16비트 + 섹터수)에서 이사한 컨테이너를 가리키는 항목을 새 자리로 고친다."""
    n = 0
    for i, (r, nsec) in enumerate(refs):
        if r not in moves:
            continue
        new_rel, new_nsec = moves[r]
        off = containers.REF_TABLE_OFF + 3 * i
        old = bytes([(r - containers.REC_BASE) & 0xFF, (r - containers.REC_BASE) >> 8, nsec])
        v = new_rel - containers.REC_BASE
        new = bytes([v & 0xFF, v >> 8, new_nsec])
        lba = common.T2_SECTOR + containers.REF_BANK_REL
        mode1.write_at(
            f, lba, 4 * common.USER, off, new, label=f"ref table #{i} rel {r}→{new_rel}", expect=old
        )
        touched.append((lba + off // common.USER, 1))
        n += 1
    return f"참조표 {n}항목을 이사 자리로 고침 (이사 {len(moves)}개)"


def set_partner(data: bytes, rec: int, secs: int) -> bytes:
    """나눈 컨테이너 `data` 의 짝 정보 항목에 짝의 rec(= rel − 34)·섹터수를 쓴다. 🔴 씬 열기 루틴(`splitload`)이 이 4B 를 읽어 짝을 올린다."""
    ents, _ = containers.parse_dir(data[: common.USER])
    at = next((5 * k for k, e in enumerate(ents) if e[0] == containers.PARTNER_ID), None)
    if at is None or not (0 < secs <= splitload.LIMIT_SECTORS) or not (0 < rec < 0x10000):
        raise BuildError(f"짝 정보 항목을 쓸 수 없다: 항목 {at} · rec {rec} · 섹터 {secs}")
    return data[: at + 1] + bytes([rec & 0xFF, rec >> 8, secs, 0]) + data[at + 5 :]


_ENC: dict[bytes, bytes] = {}  # 블록 → 최적 압축(같은 블록을 여러 번 깔아 보는 나누기 계산이 느려지지 않게)


def assemble(entries: list[tuple[int, bytes]], orig: bytes, where: str = "", ids: set[int] | None = None, partner: bool = False) -> bytes:
    """(id, 풀린 블록) 목록 → 컨테이너 바이트(칸 채움 없이 쓴 만큼). 🔴 **블록을 다시 깐다**(마스터 10-11).

    한글은 일본어보다 안 눌려서 블록마다 원래 슬롯을 수십~수백B 넘긴다(24컨테이너 거의 전부). 슬롯을 지키는
    옛 규칙(「자리를 안 옮긴다」)을 풀고, **원래 src 순서대로** 앞에서부터 다시 깐다 — 게임은 씬 id 로
    디렉터리를 찾아 블록을 푼다(`containers` 머리말). 안 고친 블록은 **원본 압축 바이트 그대로**
    옮긴다(우리 인코더가 원본보다 촘촘해 다시 누르면 바꿀 이유 없는 바이트가 바뀐다). 같은 src 를 나눠 쓰는
    중복 블록은 한 칸이다. 총량이 칸을 넘으면 호출자(`_build`)가 컨테이너를 이사시킨다.
    `ids` 를 주면 그 id 만 든 컨테이너(나누기 — `splitload`)를 낸다: 디렉터리는 줄고 그림 자원 목록(디렉터리 뒤 틈)은 원본 그대로 이어 붙는다.
    `partner` 면 디렉터리 끝(FF 앞)에 짝 정보 항목(`containers.PARTNER_ID`)을 하나 더한다 — 값은 자리표시고 `set_partner` 가 짝이 정해진 뒤 채운다(길이는 같다).
    """
    for id_, blk in entries:
        if len(blk) > BANK:
            raise BuildError(f"블록 id {id_} 가 {len(blk)}B — 뱅크(8KB)를 넘는다")
        # 🔴 풀린 블록은 0x1A00(6,656B)까지다 — 씬 열기가 블록을 고정 뱅크 0x76 에 풀고 엔진이 그 뱅크 꼬리 $BA00~$BBEF 를 구역 작업표로 쓴다(구역 진입 때
        #    짓고 다음 구역 진입이 읽는다). 넘기면 다음 구역 진입이 쓰레기 주소로 AD_READ 를 불러 메모리를 쓸어 폭주한다(10-31 비모달 자막 실측 — devlog).
        #    원판 최대 6,595B(공통 블록 0) · 번역 블록 0 은 6,624B(여유 32B).
        if len(blk) > gwin_rt.BLOCK_MAX:
            raise BuildError(f"블록 id {id_} 가 {len(blk)}B — 풀린 블록 한계 {gwin_rt.BLOCK_MAX}B(엔진 구역 작업표 자리)를 넘는다")

    o_ents, _ = containers.parse_dir(orig[: common.USER])
    if [i for i, _, _ in o_ents] != [i for i, _ in entries]:
        raise BuildError(f"컨테이너 {where}: 블록 id 목록이 원본과 다르다")
    n_dir_orig = ENTRY_BYTES * len(o_ents) + 1
    list_start = n_dir_orig
    first_src = min(src for _, src, _ in o_ents)
    gap = orig[list_start:first_src]  # 그림 자원 번호 목록(원본 그대로 — 아래 주석)
    if ids is not None:
        keep_i = [k for k, (i, _, _) in enumerate(o_ents) if i in ids]
        o_ents = [o_ents[k] for k in keep_i]
        entries = [entries[k] for k in keep_i]

    srcs = sorted({src for _, src, _ in o_ents})
    ln_of = {src: ln for _, src, ln in o_ents}  # 원본이 말하는 풀린 길이(되풀어 대조용)
    blk_of: dict[int, bytes] = {}
    for (id_, blk), (_, src, _) in zip(entries, o_ents, strict=True):
        if blk_of.setdefault(src, blk) != blk:
            raise BuildError(f"컨테이너 {where}: 같은 src {src} 를 다른 내용이 나눠 쓴다")

    packed: dict[int, bytes] = {}
    for src in srcs:
        was, used = lz.decode(orig[src:], ln_of[src])
        # 🔴 안 고친 블록도 우리 인코더가 원본보다 촘촘하면 그쪽을 쓴다(컨테이너마다 ~500B — 5뱅크 컨테이너를 4뱅크로 돌려놓는다,
        #    10-24 ch2 전투 뒤 화면 깨짐). 풀어 보면 같은 바이트이고 위 자기 검산이 되풀어 대조한다.
        enc = _ENC.get(blk_of[src])
        if enc is None:
            enc = _ENC[blk_of[src]] = lz.encode_optimal(blk_of[src])
        keep = orig[src : src + used]
        packed[src] = keep if blk_of[src] == was and len(keep) <= len(enc) else enc
    if any(i == containers.PARTNER_ID for i, _, _ in o_ents):
        raise BuildError(f"컨테이너 {where}: 실제 블록 id 가 짝 정보 항목 id({containers.PARTNER_ID:#x})와 겹친다")
    n_dir = ENTRY_BYTES * (len(o_ents) + (1 if partner else 0)) + 1
    if n_dir > n_dir_orig:
        raise BuildError(f"컨테이너 {where}: 디렉터리 {n_dir}B > 원본 {n_dir_orig}B")

    new_src: dict[int, int] = {}
    # 🔴 디렉터리 끝(FF)과 첫 블록 사이의 「빈틈」은 빈 게 아니다 — 이 구역이 미리 올릴 그림 자원 번호 목록이고, 구역 적재가 첫 블록 바로
    #    앞 바이트부터 거꾸로 FF 까지 읽는다(`$6D7A`). 지우면 구역의 스프라이트·타일이 안 올라온다(10-24 실수 — 되돌림). 원본 그대로 둔다.
    body = bytearray(n_dir) + bytearray(gap)
    for src in srcs:
        new_src[src] = len(body)
        body += packed[src]
    d = bytearray()
    for (id_, blk), (_, src, _) in zip(entries, o_ents, strict=True):
        ns = new_src[src]
        d += bytes([id_, ns & 0xFF, ns >> 8, len(blk) & 0xFF, len(blk) >> 8])
    if partner:
        d += bytes([containers.PARTNER_ID, 0x00, 0x02, 1, 0])  # 자리표시(src ≥ 디렉터리 끝, 길이 ≥ 1 — `parse_dir` 가 받는 꼴)
    d.append(containers.DIR_END)
    body[: len(d)] = d

    # 🔴 디렉터리 끝 ~ 첫 블록 앞(미리 올릴 그림 자원 번호 목록)은 원본 바이트 그대로여야 한다 — 「빈 칸처럼 보이는 데이터」(10-24:
    #    ebf7e7197 이후 0 으로 지워져 있었다)를 다시 지우지 못하게 빌드가 막는다.
    if bytes(body[n_dir : n_dir + len(gap)]) != gap:
        raise BuildError(f"컨테이너 {where}: 디렉터리 뒤 그림 자원 목록({len(gap)}B)이 원본과 다르다")

    # 자기 검산 — 우리 디코더로 되풀어 같은가(코덱 A 조건)
    ents, _ = containers.parse_dir(bytes(body[:2048]))
    ents = [e for e in ents if e[0] != containers.PARTNER_ID]
    for (id_, blk), (id2, src, ln) in zip(entries, ents, strict=True):
        assert id_ == id2 and ln == len(blk)
        got, _ = lz.decode(bytes(body[src:]), ln)
        assert got == blk, f"재조립 검산 실패 id {id_}"
    return bytes(body)


def load_edits(path: Path, table: dict[str, bytes]):
    """PoC 편집 입력: [{rel, id, find_hex, replace_hex | replace_text}] → {(rel,id): [(find, replace)]}.

    `replace_text` 는 우리 문안(한글 + 전각) — 글리프 표는 빌드가 정본 전체에서 뽑아 넘긴다.
    """
    raw = json.loads(path.read_text())
    out: dict[tuple[int, int], list[tuple[bytes, bytes]]] = {}
    for e in raw:
        rep = (
            bytes.fromhex(e["replace_hex"])
            if "replace_hex" in e
            else font.encode(e["replace_text"], table)
        )
        out.setdefault((e["rel"], e["id"]), []).append((bytes.fromhex(e["find_hex"]), rep))
    return out


# ─── 코드 패치(rel:offset, 기대 바이트 → 새 바이트) ─────────────────────────────────────
# 좌표는 전부 rel:offset(유저 데이터 2048B 안). 뱅크 → rel 은 본 프로그램(rel 34, 뱅크 0x68 부터 4섹터씩).
def _main(bank: int, off: int) -> tuple[int, int]:
    return 34 + (bank - 0x68) * 4 + off // common.USER, off % common.USER


ONLY: set[str] | None = None
"""진단용 — 개입 그룹의 부분집합만 건다(`--only font,hook`). 그룹은 여섯:
`font`(글리프 뱅크 + 진입 스텁) · `cache`(16 → 16−글리프 뱅크 칸) · `hook`(EX_GETFNT 우회) ·
`sys`(시스템 문구) · `battle`(전투 컨테이너) · `scn`(씬 컨테이너) ·
`band`(장 제목 띠, rel 210) · `hud`(HUD 이름판·あと·상태 글자, rel 54·55) · `box`(빈 슬롯 상자 msg1, 뱅크 0x7B 재배치) ·
`glyph`(글리프 뱅크 적재) · `payload`(후킹 루틴 + 표를 `hook.HOOK_ADDR`=$2300 에 싣기) ·
`narr`(나레이션 게이트 자막 — 게이트 + 블록 꼬리 스텁, `narration_gates.patch_block`)
— 뒤 둘은 `font` 안에서 다시 뺄 수 있다.
🔴 **이게 소프트락을 가르는 유일한 도구다** — 증상이 나면 하나씩 끄며 A/B 한다.
⚠ `font` 를 끄면 글리프가 없어 한글 자리가 통째로 안 그려진다(파일 선택에서 멈춘다) —
`font,hook` 은 늘 켜 두고 나머지를 끈다."""


def want(g: str) -> bool:
    return ONLY is None or g in ONLY


def _order_index(ch: str) -> int:
    """글리프 정본 순서에서의 번호 — 코드는 세이브에 남으므로 정본만 본다."""
    return font._order_canon().index(ch)


def code_patches(table: dict[str, bytes] | None = None) -> list[tuple[str, int, int, bytes, bytes]]:
    """(라벨, rel, offset, 기대, 새값). 기대가 어긋나면 그 자리에서 죽는다(쓰기 사전조건)."""
    p = []
    # 1. 본 프로그램 진입: JSR $5798 → JSR 스텁
    if want("font"):
        p.append(
            (
                "entry JSR→stub",
                *_main(0x68, 0x000F),
                b"\x20\x98\x57",
                b"\x20" + hook.STUB_ADDR.to_bytes(2, "little"),
            )
        )
        # 2. 스텁(뱅크 0x69 패딩)
        stub = hook.init_stub()
        p.append(("init stub", *_main(0x69, 0x1852), b"\0" * len(stub), stub))
    if want("cache"):
        # 3. 할당기: 캐시 16 → 16−글리프 뱅크 칸(끝 칸들을 글리프에 내준다) — status 9절
        #    🔴 13칸(글리프 3뱅크)으로는 종장 맵에서 넘쳤다 — 원본이 그 자리에서 14칸을 쓴다(devlog 09-25).
        n = 16 - font.GLYPH_NBANKS
        p.append(
            (f"cache init free={n}", *_main(0x68, 0x14FB), b"\xa9\x90", bytes([0xA9, 0x80 | n]))
        )
        for off in (0x151F, 0x15D1, 0x15F2, 0x163A, 0x1783):
            p.append(
                (f"cache CPX {n} @{off:04X}", *_main(0x68, off), b"\xe0\x10", bytes([0xE0, n]))
            )
        p.append((f"cache LDA {n} @15FC", *_main(0x68, 0x15FC), b"\xa9\x10", bytes([0xA9, n])))
        # 3-b. 🔴 장 제목 띠(세이브 LOAD 뒤 빈 띠, 11-06 마스터 「(가)안」) — 띠 로더 호출이 실패(C=1)하면 글리프 뱅크 1(0x87) 앞 섹터를 빌려 읽고 되돌린다(`band_fallback`)
        bf_code, bf_free = band_fallback.code()
        p.append(("band fallback code", *_main(0x70, band_fallback.LOAD_ORG - 0x6000), b"\xff" * len(bf_code), bf_code))
        p.append(("band load call", *_main(0x70, band_fallback.CALL_SITE - 0x6000), b"\x20\xd8\x56", b"\x20" + band_fallback.LOAD_ORG.to_bytes(2, "little")))
        p.append(("band free call", *_main(0x70, band_fallback.FREE_SITE - 0x6000), b"\x20\x97\x55", b"\x20" + bf_free.to_bytes(2, "little")))
    if want("debug") and os.environ.get("ED_DEBUG_MENU"):  # 🔴 시험 빌드 전용(배포 기준 「디버그는 기본 꺼짐, 키 입력으로만」 — 마스터 10-28): 제품은 항목이 숨고 SELECT+RUN 1초 키(`dbgkey`)로만 열린다
        assert common.BUILD_TAG.startswith("test-"), "ED_DEBUG_MENU 는 시험 빌드(ED_BUILD_TAG=test-*)에서만"
        # 4-b. 🔴 원판 「기타」 메뉴의 5번째 항목(디버그)은 시스템 카드 ROM 바이트(`LDA $FFF5; CMP #$38`)가 `$38` 이 아니면 숨는다 —
        #      시중 카드(v1.0~3.0)는 `$80` 이라 늘 숨었다. `BNE +3`(`D0 03`) 을 NOP 둘로 바꿔 늘 보이게 한다(10-24 — devlog). 뱅크 0x6E +0x209.
        #      새 기능을 만들지 않는다 — 원판에 남은 메뉴를 여는 것뿐이다(진입은 공식 경로 「기타 → 디버그」).
        p.append(("debug menu always on (BNE→NOP)", *_main(0x6E, 0x0209), b"\xd0\x03", b"\xea\xea"))
    if want("dbgkey"):
        # 4-e. 디버그 「I」 지급 효과음 — 원판 상점이 아이템을 더한 직후 부르는 `LDA #$23 / JSR $57B1`(소리 드라이버 입구)을 지급 뒤에 끼운다(마스터 10-28 「얻어질때 효과음이라도」).
        #      자리: 이름 변환 호출 뒤의 중복 `LDA $37AC / STA $F8`(5B — `$864B` 가 `$F8` 을 되돌려 놓으므로 불필요)를 빼고 그 5B 를 지급 호출 **뒤**로 옮겨 쓴다(14B 그대로).
        #      `20 D8 4F 06 5F 9B`(지급 far call) · `A9 23 20 B1 57`(효과음) · `4C A2 62`(루프로 복귀). 뱅크 0x70 +0x2E4.
        p.append(
            (
                "debug item grant sound",
                *_main(0x70, 0x02E4),
                bytes.fromhex("adac3785f8" "20d84f065f9b" "4ca262"),
                bytes.fromhex("20d84f065f9b" "a92320b157" "4ca262"),
            )
        )
    if want("dbgkey"):
        # 4-d. 디버그 「I」(아이템 고르기) 창의 아이템 이름 줄 — 왼쪽 정렬 + 줄 전체 다시 쓰기(마스터 11-08 「오른쪽 정렬이라 창 밖으로 나가고 끝에 깨진 조각」).
        #      원판은 이름 칸(14B)을 오른쪽 끝에 맞춰 앞만 공백으로 덮고 그려서, 긴 한글 이름이 왼쪽 테두리 밖으로 나가고(10-28 에 열 7→6 으로 밀었던 임시 처방은 이걸로 대체)
        #      칸을 못 채운 쪽 끝에 이전 이름의 잔재가 남았다. 줄 그리기 꼬리(뱅크 0x70 `$6308`~, 39B)를 `JMP` 로 돌리고 새 꼬리(`debug_item.code`)가 이름을 왼쪽으로
        #      당겨 꼬리를 전각 공백으로 채운 뒤 같은 열 7(제목 「디버그」 글자 선)에 그린다. 새 꼬리 자리 = 뱅크 0x70 FF 패딩 `$73A8~`(띠 폴백 뒤).
        di_code = debug_item.code()
        p.append(("debug item name tail code", *_main(0x70, debug_item.ORG - 0x6000), b"\xff" * len(di_code), di_code))
        p.append(("debug item name tail site", *_main(0x70, debug_item.SITE_OFF), debug_item.SITE_OLD, debug_item.site_new()))
        # 4-e. 디버그 「W」 워프(마스터 11-09 「ed1만 워프 추가하자. 모든 워프목록 가능하게」) — 원판 W 는 빈 핸들러. 목적지 목록(장·씬·지명) + 맵 전환 루틴 직접 호출. 코드·표는
        #      뱅크 0x70 FF 패딩(`debug_item` 뒤), 디스크립터 풀은 트랙 끝 새 섹터 4개(워프할 때만 BIOS CD_READ). `debug_warp` 머리말.
        p.extend(debug_warp.patches(debug_warp.pool_rel()))
        # 4-f. 디버그 「I」(아이템 고르기) 를 워프와 같은 목록창으로(마스터 11-11 「디버그 아이템도 워프처럼 바꾸자」) — 뱅크 0x70 워프 코드 뒤. `debug_item_list` 머리말.
        p.extend(debug_item_list.patches(table))
    if want("sys"):
        # HUD 지명 칸 4px 단위 가운데(마스터 11-08 「hud는 1번으로」) — 이름 렌더러(뱅크 0x6D `$92BE`)의 시작 열을 표시(`F8 24`)가 있으면 +1(8px)로 둔다(`hud_half.py`)
        hh = hud_half.code()
        assert len(hh) <= hud_half.CODE_LEN, len(hh)
        p.append(("hud half code", *_main(hud_half.BANK, hud_half.OFF_ORG), b"\xff" * len(hh), hh))
        p.append(("hud half site", *_main(hud_half.BANK, hud_half.SITE_OFF), hud_half.SITE_OLD, hud_half.site_new()))
        # 날개 목록 앞 공백 걷기(마스터 11-16 — 원판은 왼쪽 정렬, 우리는 HUD 가운데 공백이 목록에도 그려졌다) — 목록 호출 뒤 버퍼 포인터를 공백만큼 올린다(`list_strip.py`, HUD 불변)
        ls = list_strip.code()
        assert len(ls) <= list_strip.CODE_LEN, len(ls)
        p.append(("list strip code", *_main(list_strip.BANK, list_strip.OFF_ORG), b"\xff" * len(ls), ls))
        p.append(("list strip site", *_main(list_strip.SITE_BANK, list_strip.SITE_OFF), list_strip.SITE_OLD, list_strip.site_new()))
        # 창 맨 위 장치(마스터 11-19 「창이 떠 있으면 창 영역은 늘 맨 위」, 씬 57 횃불 어둠 원이 자막을 덮던 것의 일반화) — 상주 창 사각형 표 + 등록 루틴 + SAT 스텁을 뱅크 0x73 꼬리에,
        #   게임 SAT 루프의 속성 쓰기 8B 를 스텁 먼 호출로(`winmask.py`). 표 초기값 0(전 슬롯 꺼짐)
        wm = winmask.table_init() + winmask.reg_code().ljust(winmask.REG_LEN, b"\0") + winmask.stub_code().ljust(winmask.STUB_LEN, b"\0")
        assert len(wm) == winmask.TOTAL_LEN, len(wm)
        assert len(winmask.stub_code()) <= winmask.STUB_LEN and len(winmask.reg_code()) <= winmask.REG_LEN
        p.append(("window mask table+regs+stub", *_main(winmask.BANK, winmask.TAIL_OFF), b"\xff" * len(wm), wm))
        # 음악 이어 재생(마스터 11-20 「음악 겹침·중단」, 관리자 승인 (b)·②) — 짝 컨테이너 교체(CD_READ 가 CD-DA 를 멈춤) 직전 CD 위치를 저장하고 교체 뒤 그 위치부터 잇는다(`musicresume.py`). 같은 뱅크 0x73 꼬리, winmask 바로 뒤
        mr = musicresume.code().ljust(musicresume.CODE_LEN, b"\0")
        p.append(("music resume", *_main(musicresume.BANK, musicresume.OFF), b"\xff" * len(mr), mr))
        p.append(
            (
                "load stops cd",
                *_main(musicresume.ENG_BANK, musicresume.LOAD_SITE),
                musicresume.LOAD_SITE_ORIG,
                musicresume.far_call("loadhook"),
            )
        )
        fh_bank, fh_off, fh_old, fh_new = winmask.frame_hook_patch()  # 사이트는 원판 그대로 두고 프레임 후크가 창 있을 때만 스텁 먼 호출로 갈아 끼운다
        p.append(("window mask frame hook", *_main(fh_bank, fh_off), fh_old, fh_new))
        for nm, bk, off, was, now in winmask.engine_patches():
            p.append((f"window mask hook {nm}", *_main(bk, off), was, now))
        # 패배 귀환 확인창 앞 공백 걷기(마스터 11-18) — 메시지 머리 `10 7D C0` 앞에 지명 버퍼를 제자리에서 걷는 기계어 호출을 낀다(`defeat_strip.py`) — 글 시작은 3B 뒤(`sysstrings.read_inline`)
        ds = defeat_strip.code()
        assert len(ds) <= defeat_strip.CODE_LEN, len(ds)
        p.append(("defeat strip code", *_main(defeat_strip.BANK, defeat_strip.OFF), b"\xff" * len(ds), ds))
        p.append(("defeat strip head", *_main(defeat_strip.BANK, defeat_strip.MSG_OFF), defeat_strip.HEAD_OLD, defeat_strip.HEAD_NEW))
    if want("dbgkey"):
        # 4-c. 필드에서 SELECT+RUN 1초 → 「기타 → 디버그」(마스터 10-24 「다른 기종 스타일도」) — `debugkey.py`(틱 훅은 후킹 틱 트램펄린 끝, 글리프 뱅크 1 꼬리 코드)
        old_k, new_k = debugkey.menu_site()
        p.append(("debug key menu site", *_main(0x6E, debugkey.MENU_SITE_OFF), old_k, new_k))
    if want("slot"):
        # 5. 🔴 파일 선택 화면의 슬롯 줄 — 「第」가 **코드에 즉치값으로** 박혀 있다.
        #    $8616 LDA #$91 / STA $8533 / LDA #$E6 / STA $8534 로 슬롯 줄 틀의 「제」 자리를
        #    매번 원문 한자로 **덮어쓴다**(뱅크 0x78 = 논리 $8000 창). 그래서 틀을 번역해도
        #    첫 줄만 한글이고 둘째 줄부터 한자로 나왔다(마스터 실측: 1번 한글 · 2번 한자).
        #    ⚠ 이 자리는 **문자열 검색으로는 안 잡힌다** — 「91 e6」이 연속이 아니라
        #    `a9 91` … `a9 e6` 로 **두 즉치값에 쪼개져** 있기 때문이다. 화면 실측 → 쓰기
        #    브레이크포인트($8533)로 PC $8618 을 잡아서야 나왔다(devlog 09-16 (6)).
        kr = font.code_of(_order_index("제"))
        p.append(
            (
                "slot chapter 第→제",
                *_main(0x78, 0x0616),
                b"\xa9\x91\x8d\x33\x85\xa9\xe6",
                b"\xa9" + kr[:1] + b"\x8d\x33\x85\xa9" + kr[1:],
            ),
        )
        # 5-2. 종장(장 번호 6)은 같은 루틴이 **다른 즉치값**을 쓴다 — $85E3 에서 「終」(8F49)를
        #      $8533 에, 전각 공백을 $8535 에. 옛 3번 슬롯이 「終 장」으로 나온 자리(마스터 09-24).
        #      원문 자리 그대로 「종」+ 전각 공백 → 「종 장」 — 「종」은 「제」, 「장」은 「장」과 같은 칸
        #      (마스터 2026-09-25: 「종장」으로 붙여 오른쪽에 두었더니 「제1장」들과 칸이 안 맞았다).
        jong = font.code_of(_order_index("종"))
        p.append(
            (
                "slot final chapter 終→종",
                *_main(0x78, 0x05E3),
                b"\xa9\x8f\x8d\x33\x85\xa9\x49\x8d\x34\x85\xa9\x81\x8d\x35\x85\xa9\x40\x8d\x36\x85",
                b"\xa9"
                + jong[:1]
                + b"\x8d\x33\x85\xa9"
                + jong[1:]
                + b"\x8d\x34\x85\xa9\x81\x8d\x35\x85\xa9\x40\x8d\x36\x85",
            ),
        )
    if want("fsel"):
        # 5-3. 🔴 부팅 파일 선택 화면의 **반 칸(4px) 공백**(마스터 10-10 「pce 불러오기 반각 적용」, 규칙 1-6).
        #      이 화면은 글자를 칸 단위로 찍는다 — `$88F8 JSR $8974` 가 글자마다 불러, 홀짝(`Y>>1&1`)으로 정렬을 가른다:
        #      짝 = 타일 경계에 찍고 +1 타일 · 홀 = 4px 밀어 겹쳐 찍고 +2 타일(12px 글자 둘 = 3타일).
        #      그래서 변형 코드(+4px)는 안 먹고 공백 바이트만 빠져 글자가 붙었다(기각 실험 `rejected-boot-halfspace`).
        #      고침: 홀짝을 **줄마다 0 으로 시작하는 변수**(`$86FA`)로 바꾸고, 반각 공백 코드(`F8 24`)는 글자를 안 찍고 위상만
        #      넘긴다(짝 → 홀: 타일 그대로 · 홀 → 짝: +1 타일) — 4px 전진. 코드는 뱅크 0x78 의 0 런($86FA~$87F9, 256B)에 둔다
        #      (정적 참조 0 · 파일 선택 화면 동안 읽기/쓰기 BP 0 · 게임 로드 뒤엔 다른 자료가 올라오지만 이 화면이 끝난 뒤다).
        base = 0x86FA
        code = bytes.fromhex(
            "00"  # 86FA 위상 변수
            "9cfa86" "4c808c"  # 86FB init: STZ $86FA / JMP $8C80
            "a5f9" "c9f8" "d021"  # 8701 nb: LDA $F9 / CMP #$F8 / BNE norm
            "a5f8" "c924" "d01b"  # 8707 LDA $F8 / CMP #$24 / BNE norm
            "adfa86" "f010"  # 870D LDA $86FA / BEQ sp0
            "9cfa86" "a910" "18" "65fc" "85fc" "62" "65fd" "85fd" "60"  # 8712 홀→짝: STZ, +1 타일, RTS
            "a901" "8dfa86" "60"  # 8722 sp0: 짝→홀
            "207489" "adfa86" "4901" "8dfa86" "60"  # 8728 norm: JSR $8974 / 위상 반전 / RTS
        )
        assert base + len(code) == 0x8734, hex(base + len(code))
        p.append(("fsel code @86FA", *_main(0x78, 0x06FA), b"\0" * len(code), code))
        p.append(("fsel line init", *_main(0x78, 0x08E6), b"\x20\x80\x8c", b"\x20\xfb\x86"))
        p.append(("fsel blit call", *_main(0x78, 0x08F8), b"\x20\x74\x89", b"\x20\x01\x87"))
        p.append(("fsel parity", *_main(0x78, 0x0975), b"\x98\x4a\x29\x01", b"\xad\xfa\x86\xea"))
    if want("cast"):
        # 6. 「게임 시작」 뒤 성우 크레딧의 표제 `声優出演`. 마스터 확정 2026-09-23 은 `ＣＡＳＴ`(한글이 안 되는 줄 알았다)였으나 되는 길을 찾았다(마스터 10-16) —
        #    크레딧 모듈 안 자체 글리프 루틴(`credits_kr`). ED_CAST_EN=1 이면 옛 전각 영문.
        if os.environ.get("ED_CAST_EN"):
            p.append(("cast title 声優出演→ＣＡＳＴ", 517, 0x0420, "声優出演".encode("sjis"), "ＣＡＳＴ".encode("sjis")))
        else:
            p.extend(credits_kr.patches())
    if want("hook"):
        # 4. EX_GETFNT 호출부(본 프로그램 4곳) → `hook.HOOK_ADDR`($2300)
        tgt = hook.HOOK_ADDR.to_bytes(2, "little")
        p.append(("dialog JMP $7044", *_main(0x6C, 0x1044), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("name JMP $93A3", *_main(0x6D, 0x13A3), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("JSR 6C+0F5A", *_main(0x6C, 0x0F5A), b"\x20\x60\xe0", b"\x20" + tgt))
        p.append(("JSR 78+0932", *_main(0x78, 0x0932), b"\x20\x60\xe0", b"\x20" + tgt))
        # 4-2. 🔴 반 칸(4px) 전진 — 변형 코드 · 반각 공백. 렌더러 입구 `$7047` 의 `INC $38BB`(3B)를 `JSR 새 머리`로(마스터 10-07).
        #      새 머리는 `hook.hook_narrow()`(페이로드 안). 변형이 아닌 글자는 `INC` 만 하고 RTS → `$704A` 로 원래대로 이어진다.
        p.append(
            (
                "renderer entry INC→JSR narrow",
                *_main(0x6C, 0x1047),
                b"\xee\xbb\x38",
                b"\x20" + hook.NARROW_ENTRY.to_bytes(2, "little"),
            )
        )
        # 4-2b. 🔴 시스템 문구 조각 보관소 스텁(4-17 확대) — `0F` 처리부 `$6A41`(`JMP $66FB`)을 `JSR FRAGSH` 로, 복사 루틴은 뱅크 0x70 FF 패딩에.
        #       읽는 쪽은 이 스텁뿐이다(`hook._frag_asm`). 보관소 조각 쓰기는 `sysbuild` 몫.
        fr = hook.frag_routine()
        p.append(("frag copy routine @70", *_main(hook.FRAG_BANK, hook.FRAG_OFF), b"\xff" * len(fr), fr))
        # 4-2c. 🔴 엔진이 주문 이름 뒤에 붙이는 SJIS 전각 단계 숫자(「오비스３」)를 반각 글리프로(마스터 11-16) — 본체는 뱅크 0x70 FF 패딩, 글리프 뱅크 꼬리엔 스텁만.
        dg = hook.digit_routine([bytes(font.code_of(_order_index(ch))) for ch in sysbuild.spell_gate_chars()])
        p.append(("spell stage digit narrow @70", *_main(hook.FRAG_BANK, hook.DIGIT_OFF), b"\xff" * len(dg), dg))
        p.append(
            (
                f"0F handler JMP $66FB -> JSR fragsh @{hook.FRAG_SITE:04X}",
                *_main(0x6C, hook.FRAG_SITE - 0x6000),
                b"\x4c\xfb\x66",
                b"\x20" + hook.FRAGSH_ADDR.to_bytes(2, "little"),
            )
        )
        # 4-3. 칸 수를 0 으로 만드는 두 자리(`STZ $38BB` 3B — 줄 넘김 `$6AEA` · 창 비움 `$6B73`)를 `JSR rstz` 로 — 반각 공백의 나머지도 같이 0.
        for at, why in ((0x0AEA, "line wrap"), (0x0B73, "window clear")):
            p.append(
                (
                    f"col reset STZ→JSR rstz ({why})",
                    *_main(0x6C, at),
                    b"\x9c\xbb\x38",
                    b"\x20" + hook.RSTZ_ADDR.to_bytes(2, "little"),
                )
            )
        # 5. 로그 자동 개행 품질(①③) — 세 JSR 호출 대상을 우리 스텁으로 돌린다(원본 바이트 수 그대로,
        #    `hook.hook_wrap_fix()` 참조). $6D9C·$6723·$6730 은 전부 뱅크 0x6C(오프셋 = 논리주소−$6000).
        p.append(
            (
                "wrap orphan JSR $6D9C",
                *_main(0x6C, 0x0D9C),
                b"\x20\xb5\x6a",
                b"\x20" + hook.ORPHAN_ADDR.to_bytes(2, "little"),
            )
        )
        p.append(
            (
                "wrap mark JSR $6723",
                *_main(0x6C, 0x0723),
                b"\x20\xb9\x6a",
                b"\x20" + hook.MARK_ADDR.to_bytes(2, "little"),
            )
        )
        p.append(
            (
                "wrap eat JSR $6730",
                *_main(0x6C, 0x0730),
                b"\x20\x8a\x6d",
                b"\x20" + hook.EAT_ADDR.to_bytes(2, "little"),
            )
        )
    if want("battle"):
        # 9. 🔴 파티 행위자 이름 뒤 접미 — 엔진이 이름 뒤에 **언제나** 붙이던 「たち」(코드 뱅크 0x6C `$68C9` 의 6B 자료)가 혼자여도 화면에
        #    「세리오스たち는 도망쳤다」로 떴다(정본 문안·검사기·화면 일본어 게이트는 다 초록). 마스터 10-09: 혼자 = 「세리오스는」 ·
        #    파티 = 「세리오스들은」. 자료를 「들」+종결로 바꾸고, 복사 시작·길이를 파티 판정으로 정하는 루틴(`hook.party_suffix`, 페이로드 안)을
        #    `$68A5` 의 `LDA #6/STA $21/CLX` 자리에 건다 — 혼자면 종결 `06` 하나만 복사한다.
        deul = font.code_of(_order_index("들"))
        p.append(
            (
                "party suffix data たち→들",
                *_main(0x6C, 0x08C9),
                b"\x20\x82\xbd\x82\xbf\x06",
                b"\x04" + deul + b"\x06\x06\x06",  # 색 끝 `04` 를 앞에 — 이름만 노랗고 「들」은 기본색(마스터 11-17 상자 「세리오스들」)
            )
        )
        p.append(
            (
                "party suffix JSR (solo skips)",
                *_main(0x6C, hook.PARTY_SUFFIX_SITE - 0x6000),
                b"\xa9\x06\x85\x21\x82",
                b"\x20" + hook.PARTY_ADDR.to_bytes(2, "little") + b"\xea\xea",
            )
        )
    if want("battle") and os.environ.get("ED_LATIN") != "orig":  # 🧪 ED_LATIN=orig = 원판 BIOS 숫자표 유지(비교 시험)
        # 10. 🔴 엔진이 수치(`{22}`)를 찍을 때 쓰는 숫자 표 `$69D3`(전각 SJIS 「０~９」 열 쌍) → 우리 ASCII 숫자 글리프 코드 —
        #     BIOS 전각 숫자(「2 8」 벌어짐)가 우리 반각 영숫자 갈래(8px)로 그려진다(마스터 10-09).
        p.append(
            (
                "number digit table 전각→글리프",
                *_main(0x6C, 0x09D3),
                b"".join(bytes([0x82, 0x4F + d]) for d in range(10)),
                b"".join(font.code_of(_order_index(str(d))) for d in range(10)),
            )
        )
    if want("narr"):
        # 7. 나레이션 자막 상주부 — 본 프로그램 뱅크 0x6B 꼬리 FF 패딩(`$9E56~$9FFF`, 426B). 장면 코드가 돌 때
        #    늘 `$8000` 창(MPR4)에 있다(메인 루프가 이 뱅크에서 돈다). 쓰기·실행 BP 로 라이아스 장면 · 필드 ·
        #    전투 두 판 동안 0회 실측(2026-10-05). 씬 블록은 JSR 목적지 2B 만 바꾼다(`narration_gates`).
        code = narration_gates.resident()
        p.append(
            (
                "narration resident",
                *_main(0x6B, narration_gates.RES_ORG - 0x8000),
                b"\xff" * len(code),
                code,
            )
        )
        # 8. ON 자동 넘김 — 대사 엔진(뱅크 0x6C) 쪽 대기의 `LDA $CF1A` 넷을 `JSR` 훅으로(같은 3B).
        #    훅 본체는 뱅크 0x68 꼬리 FF 패딩(`$5FBC~`, 대사 엔진이 돌 때도 `$4000` 창에 있다).
        hook_code = narration_gates.auto_hook()
        p.append(
            (
                "narration auto hook",
                *_main(0x68, narration_gates.AUTO_ORG - 0x4000),
                b"\xff" * len(hook_code),
                hook_code,
            )
        )
        for at in narration_gates.AUTO_SITES:
            p.append(
                (
                    f"auto advance LDA $CF1A @{at:04X}",
                    *_main(0x6C, at - 0x6000),
                    b"\xad\x1a\xcf",
                    b"\x20" + narration_gates.AUTO_ORG.to_bytes(2, "little"),
                )
            )
        # 8-3. 자막 모드 화자 이름 글자 대기(흔들림 — `hook.namewait_routine`) — 엔진 글자 찍기 `LDA $8A · CMP #$06`(4B)을 `JSR 훅 · NOP` 으로
        p.append(
            (
                f"name-char wait LDA $8A/CMP #6 @{hook.NAMEWAIT_SITE:04X}",
                *_main(0x6C, hook.NAMEWAIT_SITE - 0x6000),
                b"\xa5\x8a\xc9\x06",
                b"\x20" + hook.NAMEWAIT_ADDR.to_bytes(2, "little") + b"\xea",
            )
        )
        # 8-2. 자막 모드 자동 넘김의 넘김 효과음 끄기 — `JSR $67EC` 셋을 후킹 페이로드 안 거름 루틴으로(같은 3B)
        for at in narration_gates.QUIET_SITES:
            p.append(
                (
                    f"quiet page-turn SFX JSR $67EC @{at:04X}",
                    *_main(0x6C, at - 0x6000),
                    b"\x20" + hook.QUIET_ORIG.to_bytes(2, "little"),
                    b"\x20" + hook.QUIET_ADDR.to_bytes(2, "little"),
                )
            )
        # 9. 자막 모드에선 넘김 커서(▽)를 숨긴다 — 깜빡임 `JSR $6CC3` 넷을 후킹 페이로드 안 루틴으로(같은 3B)
        for at in narration_gates.BLINK_SITES:
            p.append(
                (
                    f"hide cursor blink JSR $6CC3 @{at:04X}",
                    *_main(0x6C, at - 0x6000),
                    b"\x20" + hook.BLINK_ORIG.to_bytes(2, "little"),
                    b"\x20" + hook.BLINK_ADDR.to_bytes(2, "little"),
                )
            )
    if want("scn"):
        # 🔴 판매 감사 유지(마스터 11-18) — 감사 뒤 `JMP $9E4B`(목록 위젯 진입: 질문 메시지를 다시 보임 → 첫 바이트 `08` 창 다시 그리기가 감사를 지운다)를
        #    질문을 보인 **뒤** 지점 `$9E58` 로 돌린다. 질문은 `translate.merge_sell_thanks` 가 감사 메시지 끝에 이어 써 두었다. 판매 구조체 호출이 있는 모든 씬이 합쳐졌는지는 같은 함수가 죽어서 지킨다.
        p.append(("sell thanks keep JMP $9E4B→$9E58", *_main(0x6F, 0x1F32), b"\x4b\x9e", b"\x58\x9e"))
    if os.environ.get("ED_BATTLE_DBG"):  # 🔴 디버그 전용 — 전투 일괄 촬영(10-20): 조우 번호를 카드 RAM `$C05F` 가 아니라 워크 RAM `$3FFA` 에서 읽는다(하네스가 poke 한다)
        assert common.BUILD_TAG.startswith("test-"), "ED_BATTLE_DBG 는 시험 빌드(ED_BUILD_TAG=test-*)에서만"
        p.append(("battle debug LDA $C05F→$3FFA", 94, 1564, b"\x5f\xc0", b"\xfa\x3f"))
    return p


ZONE54: list[bytes] = []  # 씬 54 번역 이미지(지도 구역 묶음 스트림 — tools/zone_image.py). 컨테이너 단계에서 채우고 apply_zone 이 쓴다


def _scene54_image(bdata: bytes, rel: int, table: dict[str, bytes], edits, blocked: set[int]) -> bytes:
    """씬 54 이미지 = 컨테이너 블록과 같은 단계(번역 → 편집 → 동적 글리프)를 오버레이 뒤에 꼬리를 놓게 돌린 것. 다른 단계(나레이션·시각표·대사창)가 걸린 씬이면 죽는다."""
    if zone_image.SCENE in blocked:
        raise BuildError("씬 54 에 나레이션·시각표·대사창 단계가 걸렸다 — 지도 구역 이미지(zone_image)가 그 단계를 안 돈다")
    btab, dyn = glyphdyn.block_table(table, zone_image.SCENE)
    with zone_image.pad():
        blk, _n = translate.translate_block(zone_image.SCENE, bdata, btab)
    if len(blk) <= zone_image.ORIG_LEN:
        raise BuildError("씬 54 이미지가 원판 길이 이하 — 번역이 안 닿았다")
    if (rel, zone_image.SCENE) in edits:
        blk = apply_edits(blk, edits[(rel, zone_image.SCENE)], f"rel {rel} id {zone_image.SCENE} (이미지)")
    if dyn:
        blk = glyphdyn.attach(blk, dyn)
    return blk


def apply_zone(f, image: bytes, touched: list[tuple[int, int]]) -> str:
    """씬 54 이미지를 지도 구역 묶음 스트림 자리(1141:1772~)에 쓰고 구역 섹터 수 표를 9 → 10 으로."""
    from shared.disc import mode1

    packed, writes = zone_image.compose(image)
    for rel, off, old, new in writes:
        lba = common.T2_SECTOR + rel
        mode1.write_at(f, lba, common.USER, off, new, label=f"scene54 zone stream rel {rel}:{off}", expect=old)
        touched.append((lba, 1))
    rel, off = zone_image.COUNT_TABLE
    lba = common.T2_SECTOR + rel
    mode1.write_at(
        f, lba, common.USER, off, bytes([zone_image.ZONE_SECTORS_NEW]), label="scene54 zone sectors 9→10",
        expect=bytes([zone_image.ZONE_SECTORS_OLD]),
    )
    touched.append((lba, 1))
    return f"씬 54 지도 구역 이미지 {len(image)}B → 압축 {len(packed)}B(원판 4359B) · 묶음 {zone_image.ZONE_SECTORS_NEW}섹터"


def apply_code_patches(
    f, glyph_bank: bytes, table: dict[str, bytes], touched: list[tuple[int, int]]
):
    for label, rel, off, old, new in code_patches(table):
        assert len(old) == len(new), label
        lba = common.T2_SECTOR + rel
        mode1.write_at(f, lba, common.USER, off, new, label=label, expect=old)
        touched.append((lba, 1))


def apply_glyph_payload(
    f, glyph_bank: bytes, table: dict[str, bytes], touched: list[tuple[int, int]], pairs: list[tuple[int, int, int, int]]
):
    """글리프 뱅크 + 후킹 루틴 쓰기 — 컨테이너를 다 깐 **뒤에** 쓴다(나눈 컨테이너의 짝 표가 글리프 뱅크 꼬리에 들어가
    할당된 rel 을 알아야 하고, 한 구간을 두 번 쓰면 쓰기 장부가 막는다)."""
    # 5. 글리프 뱅크 → rel 114~(뱅크 0x7C~0x7D 적재분, 원본 0 — font.GLYPH_NBANKS 뱅크), 후킹 루틴 → rel 126 앞 0x340B
    if not want("font"):
        return
    if want("glyph"):  # 진단용으로 뺄 수 있다 — 뱅크 0x7C~0x7D 를 0 인 채로 두는 A/B
        lba = common.T2_SECTOR + 114
        # 뱅크 꼬리 = 코드: 뱅크마다 풀기 루틴(`hook.unpack_asm`, 18B → 24B) · 마지막 뱅크 맨 끝은 어절
        #   줄바꿈 루틴(`hook.wordck`, `$6723` 경로가 MPR2 에 걸어 부른다). 글리프는 `BANK_GLYPH_END` 앞까지만.
        glyph_bank = hook.finish_banks(glyph_bank)
        mode1.write_user_data(
            f, lba, glyph_bank, label="glyph banks", expect=b"\0" * len(glyph_bank)
        )
        touched.append((lba, len(glyph_bank) // common.USER))
    # 루틴 + 조사 코드표 + 받침 비트맵 둘 + 줄바꿈 품질 블록 — 스텁이 통째로 `HOOK_ADDR`($2300)로 옮긴다(0x340B)
    payload = hook.payload(table)
    if want("payload"):  # 진단용 — `HOOK_ADDR` 자리를 0 인 채로 두는 A/B(스텁은 그대로 돈다)
        lba = common.T2_SECTOR + 126
        mode1.write_user_data(
            f, lba, bytes(payload), label="hook routine + josa tables", expect=b"\0" * len(payload)
        )
        touched.append((lba, 1))
    routine = payload
    print(
        f"  코드 패치 {len(code_patches(table))}곳 + 글리프 {len(glyph_bank.rstrip(b'\0'))}B + 루틴 {len(routine.rstrip(b'\0'))}B"
    )


GWIN_DONE: set[tuple[int, int]] = set()  # (rel, 씬) 중 이 빌드에서 안 B 를 넣은 사본 — 코드 영역은 그 컨테이너에만 붙는다(같은 씬의 다른 컨테이너 사본은 제품 그대로)


def _gwin_tail(ids, rel: int) -> bytes:
    """이 컨테이너(`rel`)의 안 B 씬들이 나눠 쓰는 코드 영역(`gwin_rt.container_tail` — 공용 렌더러 한 벌 + 씬별 표) — 컨테이너 4번째 뱅크(섹터 12~)에 붙는다."""
    sids = sorted(i for i in ids if (rel, i) in GWIN_DONE and i in gwin_rt.SCENE_PARTS)
    return gwin_rt.container_tail(sids)[0] if sids else b""


def _with_tail(data: bytes, tail: bytes, where: str, strict: bool = True, code_sector: int = gwin_rt.CODE_SECTOR) -> bytes | None:
    """컨테이너 데이터 뒤 섹터 `code_sector`(컨테이너 마지막 뱅크의 첫 섹터, `gwin_rt.code_sector`)에 코드 영역을 붙인다. 데이터가 그 앞에 안 들면 strict 면 실패, 아니면 None(나누기 후보 탐색용)."""
    if not tail:
        return data
    lim = code_sector * common.USER
    if len(data) > lim:
        if strict:
            raise BuildError(f"컨테이너 {where}: 데이터 {len(data)}B 가 코드 영역 앞 {lim}B 를 넘는다 — 나눌 목록(splitload.SPLIT_RELS)에 넣어라")
        return None
    return data + b"\0" * (lim - len(data)) + tail


def _readback_user(f, lba: int, n: int) -> bytes:
    """방금 쓴 섹터들의 유저 데이터를 되읽는다(코드 영역 대조용)."""
    out = b""
    for k in range(n):
        f.seek((lba + k) * common.RAW + common.USER_OFF)
        out += f.read(common.USER)
    return out


def _tail_cap_split(entries, orig, rel, com, rest, slot, o_banks, cap_banks):
    """자막 코드 영역이 든 쪽 Y 를 `cap_banks` 뱅크(코드 영역 앞 데이터 + 코드)로 줄이는 가름을 찾는다 — 블록 부분집합 탐색(크기는 블록별 가산 추정 → 실제 조립으로 확인).
    제자리 쪽 X 는 원판 칸(`slot`) 안. 풀 섹터가 가장 적은 가름을 고른다. 반환 `best` 꼴(`_write_split`) 또는 None."""
    import itertools

    g_ids = {i for i in rest if (rel, i) in GWIN_DONE and i in gwin_rt.SCENE_PARTS} | {i for i in splitload.FORCE_Y.get(rel, ()) if i in rest}
    others = [i for i in rest if i not in g_ids]
    has_gwin = any((rel, i) in GWIN_DONE and i in gwin_rt.SCENE_PARTS for i in g_ids)
    cs_y = gwin_rt.code_sector(cap_banks * 4) if has_gwin else cap_banks * 4  # 자막 코드가 없으면 코드 영역을 비우지 않는다(FORCE_Y 만, 11-06)
    cs_x = gwin_rt.code_sector(slot)
    base = len(assemble(entries, orig, f"rel {rel} base", ids=set(com), partner=True))
    pk = {i: len(assemble(entries, orig, f"rel {rel} pk", ids=set(com) | {i}, partner=True)) - base for i in rest}
    tail_y = _gwin_tail(set(com) | g_ids, rel)
    cands = []
    for r in range(len(others) + 1):
        for sub in itertools.combinations(others, r):
            ys = g_ids | set(sub)
            est_y = base + sum(pk[i] for i in ys)
            est_x = base + sum(pk[i] for i in rest if i not in ys)
            if est_y > cs_y * common.USER or est_x > slot * common.USER:
                continue
            cands.append((est_y, sorted(ys)))
    cands.sort()
    for _, ys in cands[:40]:
        y_ids = set(com) | set(ys)
        x_ids = set(com) | {i for i in rest if i not in ys}
        dy = _with_tail(assemble(entries, orig, f"rel {rel} Y", ids=y_ids, partner=True), tail_y, f"rel {rel} Y", strict=False, code_sector=cs_y)
        dx = _with_tail(assemble(entries, orig, f"rel {rel} X", ids=x_ids, partner=True), _gwin_tail(x_ids, rel), f"rel {rel} X", strict=False, code_sector=cs_x)
        if dy is None or dx is None:
            continue
        nx, ny = -(-len(dx) // common.USER), -(-len(dy) // common.USER)
        if nx <= slot and ny <= cap_banks * 4:
            return (ny, 0, True, True, dx, dy, x_ids, y_ids, nx, ny)
    raise BuildError(f"컨테이너 rel {rel}: 자막 코드 쪽을 {cap_banks}뱅크 안에 넣는 가름이 없다")


def _write_split(f, rel, entries, orig, free_pool, moves, intended, split_intended, touched, split_gone):
    """씬 컨테이너를 둘로 나눠 쓴다 — 공통 블록(0·1·4·5)은 양쪽에 복사, 나머지는 id 순으로 갈라 두 쪽이 4뱅크 안에 들게 한다.
    🔴 **원래 칸(`slot`)에 들어가는 쪽은 제자리에 둔다**(참조표·재배치 장부가 안 바뀐다, 11-05) — 나머지만 풀로 보내 풀을 아낀다. 풀에 보내는 몫이 가장 작은 가름을
    고른다(양쪽 다 칸에 안 들면 예전처럼 둘 다 풀로: 앞쪽을 참조표 자리로 이사). 두 쪽은 디렉터리 끝 가짜 항목으로 서로를 가리킨다(`splitload`).
    반환 (참조표가 가리키는 쪽 rel, 섹터, 풀 쪽 rel, 섹터)."""
    ids = [i for i, _ in entries]
    slot = splitload.slot_sectors(rel)
    cs = gwin_rt.code_sector(slot)
    o_banks = -(-slot // 4)
    com = [i for i in ids if i in splitload.COMMON_IDS]
    rest = sorted(i for i in ids if i not in com)
    best = None
    cap_banks = splitload.TAIL_BANKS.get(rel, 0)
    if cap_banks:  # 🔴 자막 코드 영역이 든 쪽(풀 쪽)을 `cap_banks` 뱅크 안으로 — 보스 그림 등 캐시 자원이 한 칸 더 필요한 장면(씬 168, 11-05)이라 코드 영역 앞 데이터를 줄인다
        best = _tail_cap_split(entries, orig, rel, com, rest, slot, o_banks, cap_banks)
    if rel in splitload.FORCE_SEP and not best:  # 🔴 위치가 다른 두 씬을 가르는 컨테이너 — 번호 순 앞/뒤 가름이 안 맞을 수 있어 부분집합(크기 추정으로 균형 좋은 순)을 훑는다
        import itertools
        sa, sb, *wa = splitload.FORCE_SEP[rel]  # 셋째 이후 = 아래 쪽(sa)과 같은 쪽에 두는 씬(위치가 같은 씬 — 씬 20 은 17 과 아래)
        base_len = len(assemble(entries, orig, f"rel {rel} base", ids=set(com), partner=True))
        pk = {i: len(assemble(entries, orig, f"rel {rel} pk", ids=set(com) | {i}, partner=True)) - base_len for i in rest}
        others = [i for i in rest if i not in (sa, sb, *wa)]
        cands = []
        for r in range(len(others) + 1):
            for sub in itertools.combinations(others, r):
                xs = {sa, *wa, *sub}
                ys = set(rest) - xs
                ex, ey = base_len + sum(pk[i] for i in xs), base_len + sum(pk[i] for i in ys)
                cands.append((max(ex, ey), sorted(xs), sorted(ys)))
        cands.sort(key=lambda c: c[0])
        splits = [(n + 1, set(com) | set(c[1]), set(com) | set(c[2])) for n, c in enumerate(cands[:60])]
    else:
        splits = [(k, set(com) | set(rest[:k]), set(com) | set(rest[k:])) for k in range(1, 0 if best else len(rest))]
    for k, x_ids, y_ids in splits:
        dx = _with_tail(assemble(entries, orig, f"rel {rel} X", ids=x_ids, partner=True), _gwin_tail(x_ids, rel), f"rel {rel} X", strict=False, code_sector=cs)
        dy = _with_tail(assemble(entries, orig, f"rel {rel} Y", ids=y_ids, partner=True), _gwin_tail(y_ids, rel), f"rel {rel} Y", strict=False, code_sector=cs)
        if dx is None or dy is None:  # 안 B 코드 영역 앞에 데이터가 안 드는 가름은 버린다
            continue
        nx, ny = -(-len(dx) // common.USER), -(-len(dy) // common.USER)
        for stay_is_x in (True, False):  # 제자리에 둘 쪽 — 칸에 들고, 풀 쪽은 4뱅크·원판 뱅크 수 안
            ns, np_ = (nx, ny) if stay_is_x else (ny, nx)
            if ns <= slot and np_ <= splitload.LIMIT_SECTORS and -(-np_ // 4) <= o_banks:
                cand = (np_, k, stay_is_x, True)
                if best is None or cand[:2] < best[:2]:
                    best = (*cand, dx, dy, x_ids, y_ids, nx, ny)
        if best is None or best[3] is False:  # 제자리에 둘 수 있는 가름이 아직 없을 때만 둘 다 풀로 보내는 안을 후보로
            if max(nx, ny) <= splitload.LIMIT_SECTORS and max(-(-nx // 4), -(-ny // 4)) <= o_banks:
                cand = (nx + ny, k, True, False)
                if best is None or cand[:2] < best[:2]:
                    best = (*cand, dx, dy, x_ids, y_ids, nx, ny)
    if best is None:
        raise BuildError(f"컨테이너 rel {rel}: 어떻게 나눠도 안 B 코드 영역 앞 {cs}섹터·4뱅크·원판 {o_banks}뱅크 안에 두 쪽이 안 든다 — 셋으로 나눠야 한다")
    cost, k, stay_is_x, in_place, dx, dy, x_ids, y_ids, nx, ny = best
    if in_place:
        (d_s, n_s, s_ids), (d_p, n_p, p_ids) = ((dx, nx, x_ids), (dy, ny, y_ids)) if stay_is_x else ((dy, ny, y_ids), (dx, nx, x_ids))
        rel_s, rel_p = rel, free_pool.alloc(n_p)
        n_s = slot  # 제자리 쪽은 칸 끝까지 0 으로 채워 쓴다(참조표가 말하는 섹터 수)
    else:
        (d_s, n_s, s_ids), (d_p, n_p, p_ids) = (dx, nx, x_ids), (dy, ny, y_ids)
        rel_s, rel_p = free_pool.alloc(n_s), free_pool.alloc(n_p)
    d_s = set_partner(d_s, rel_p - containers.REC_BASE, n_p)
    d_p = set_partner(d_p, rel_s - containers.REC_BASE, n_s)
    for at, data, n, ids_, expect in ((rel_s, d_s, n_s, s_ids, orig if in_place else None), (rel_p, d_p, n_p, p_ids, None)):
        buf = data + b"\0" * (n * common.USER - len(data))
        lba = common.T2_SECTOR + at
        mode1.write_user_data(f, lba, buf, label=f"split container rel {at}", expect=expect if expect is not None else b"\0" * len(buf))
        touched.append((lba, n))
        if _gwin_tail(ids_, rel):  # 안 B 코드 영역이 붙은 쪽 — 디렉터리 밖이라 블록 되읽기가 못 본다, 바로 되읽어 대조
            got = _readback_user(f, lba, n)
            if got != buf:
                raise BuildError(f"컨테이너 rel {at}: 코드 영역 되읽기가 쓴 것과 다르다")
            print(f"  안 B 코드 영역: rel {at} 섹터 {cs}~ {len(data) - cs * common.USER}B 되읽기 OK")
    print(f"    가름: 참조표 쪽 {'(제자리) ' if in_place else ''}{sorted(set(s_ids) - set(splitload.COMMON_IDS))} · 풀 쪽 {sorted(set(p_ids) - set(splitload.COMMON_IDS))}")
    swapped = False
    if not in_place:
        moves[rel] = (rel_s, n_s)
    elif os.environ.get("ED_SPLIT_SWAP") or rel in splitload.TAIL_BANKS:  # 🔴 디버그: 구역 적재가 풀 쪽을 먼저 올리게(참조표를 풀 쪽으로) 해 풀→제자리 교체 방향을 시험한다. 제품에선 `TAIL_BANKS` 컨테이너만 — 자막 쪽(3뱅크)이 먼저 올라야 캐시 구멍이 안 생긴다(씬 168, 11-05)
        assert rel in splitload.TAIL_BANKS or common.BUILD_TAG.startswith("test-"), "ED_SPLIT_SWAP 은 시험 빌드(ED_BUILD_TAG=test-*)에서만"
        moves[rel] = (rel_p, n_p)
        swapped = True
    blk = dict(entries)
    for key in [kk for kk in intended if kk[0] == rel]:
        b = intended.pop(key)
        if key[1] in s_ids:
            intended[(rel_s, key[1])] = b
        if key[1] in p_ids:
            split_intended[(rel_p, key[1])] = b
    # 풀 쪽은 참조표 밖이라 스캔이 못 본다 — 안 고친 블록까지 전부 되읽기 대상으로 넣는다
    for i in p_ids:
        split_intended.setdefault((rel_p, i), blk[i])
    split_gone.update((rel, i) for i in p_ids if i not in s_ids and in_place)  # 제자리 컨테이너에서 풀 쪽으로 간 블록 — 원 자리에서 사라진다(되읽기 「안 고친 블록」 대조에서 뺀다)
    return (rel_p, n_p, rel_s, n_s) if swapped else (rel_s, n_s, rel_p, n_p)


RING_PAIRS: set[tuple[int, int]] = set()  # 조각 고리의 방향 간선(앞 rel → 뒤 rel) — `verify_split` 이 한 방향만 본다
NSEC_NEW: dict[int, int] = {}  # 제자리에 둔 채 참조표 섹터 수만 낮출 컨테이너(rel → 섹터) — 이사(`moves`)가 아니다


def _write_parts(f, rel, entries, orig, free_pool, moves, intended, split_intended, touched, split_gone, limit):
    """🔴 ⓣ(마스터 11-17) — 컨테이너를 **`limit` 섹터(3뱅크) 이하 조각 k 개**로 나눠 쓴다. 한글판 캐시가 14칸이라 원판이 14칸을 정상 상태로 쓰는 2장 구역은 여유가 0 이어서,
    구역 적재 4뱅크 → 3뱅크로 한 뱅크를 돌려받는다. 공통 블록(0·1·4·5)은 조각마다 사본, 나머지 블록은 id 순으로 채운다. 첫 조각은 제자리(참조표 섹터 수만 낮춘다 — `NSEC_NEW`),
    나머지는 풀로. 조각은 디렉터리 끝 가짜 항목으로 **고리**(0→1→…→k−1→0)를 이룬다(`splitload` 교체 횟수 상한 `MAX_HOPS`). 반환: 고리 간선 목록(`split_pairs` 에 더한다)."""
    ids = [i for i, _ in entries]
    com = [i for i in ids if i in splitload.COMMON_IDS]
    rest = sorted(i for i in ids if i not in com)
    cap = limit * common.USER
    base = len(assemble(entries, orig, f"rel {rel} base", ids=set(com), partner=True))
    pk = {i: len(assemble(entries, orig, f"rel {rel} pk", ids=set(com) | {i}, partner=True)) - base for i in rest}
    def pack(group):
        """`group`(id 순)을 조각당 cap 이하가 되게 — 조각 수가 가장 적은 균형 채움(id 순 인접)."""
        if not group:
            return []
        for k in range(1, len(group) + 1):
            target = -(-sum(pk[i] for i in group) // k)
            cand, cur, cur_len = [], [], base
            for i in group:
                if cur and (cur_len + pk[i] > cap or (cur_len + pk[i] > target + base and len(cand) < k - 1)):
                    cand.append(cur)
                    cur, cur_len = [], base
                cur.append(i)
                cur_len += pk[i]
            cand.append(cur)
            if len(cand) == k and all(base + sum(pk[i] for i in c) <= cap for c in cand):
                return cand
        raise BuildError(f"컨테이너 rel {rel}: {limit}섹터 이하 조각으로 못 나눈다")

    # 🔴 안 B 자막 씬(코드 영역이 든 조각은 4뱅크)은 한 곳에 모은다 — 코드 영역이 없는 조각은 3뱅크라 구역 적재가 한 뱅크 가볍다. 자막 없는 조각이 앞(제자리 · 참조표 쪽)
    g_set = {i for i in rest if (rel, i) in GWIN_DONE and i in gwin_rt.SCENE_PARTS}
    parts = pack([i for i in rest if i not in g_set]) + pack([i for i in rest if i in g_set])
    if len(parts) < 2:
        raise BuildError(f"컨테이너 rel {rel}: 조각 둘이 안 된다")
    datas = []
    cs = gwin_rt.code_sector(splitload.slot_sectors(rel))
    for pi, pids in enumerate(parts):
        d = assemble(entries, orig, f"rel {rel} part{pi}", ids=set(com) | set(pids), partner=True)
        if len(d) > cap:
            raise BuildError(f"컨테이너 rel {rel}: 조각 {pi} 가 {len(d)}B > {cap}B")
        tail = _gwin_tail(set(com) | set(pids), rel)
        if tail:  # 안 B 자막 씬이 든 조각 — 코드 영역은 그 조각의 마지막(4번째) 뱅크라 이 조각만 4뱅크다(데이터는 3뱅크 안, 코드 영역이 뒤에 붙는다)
            d = _with_tail(d, tail, f"rel {rel} part{pi}", strict=False, code_sector=cs)
            if d is None:
                raise BuildError(f"컨테이너 rel {rel}: 조각 {pi} 의 데이터가 안 B 코드 영역 앞 {cs}섹터에 안 든다")
        datas.append(d)
    ns = [-(-len(d) // common.USER) for d in datas]
    slot = splitload.slot_sectors(rel)
    rels = [rel] + [free_pool.alloc(n) for n in ns[1:]]
    k = len(parts)
    ids_of = [set(com) | set(p) for p in parts]
    for pi in range(k):
        j = (pi + 1) % k
        datas[pi] = set_partner(datas[pi], rels[j] - containers.REC_BASE, ns[j])
    for pi in range(k):
        n_w = slot if pi == 0 else ns[pi]  # 제자리 조각은 칸 끝까지 0 으로 채워 쓴다(옛 일본어 꼬리가 남지 않게)
        buf = datas[pi] + b"\0" * (n_w * common.USER - len(datas[pi]))
        lba = common.T2_SECTOR + rels[pi]
        mode1.write_user_data(f, lba, buf, label=f"split part rel {rels[pi]}", expect=orig if pi == 0 else b"\0" * len(buf))
        touched.append((lba, n_w))
    NSEC_NEW[rel] = ns[0]
    blk = dict(entries)
    for key in [kk for kk in intended if kk[0] == rel]:
        b = intended.pop(key)
        for pi in range(k):
            if key[1] in ids_of[pi]:
                (intended if pi == 0 else split_intended)[(rels[pi], key[1])] = b
    for pi in range(1, k):
        for i in ids_of[pi]:
            split_intended.setdefault((rels[pi], i), blk[i])
    moved_out = set().union(*ids_of[1:]) - ids_of[0]
    split_gone.update((rel, i) for i in moved_out)
    print(f"    조각 {k}개: " + " · ".join(f"rel {rels[pi]}({ns[pi]}섹터) {sorted(set(parts[pi]))}" for pi in range(k)))
    edges = []
    for pi in range(k):
        j = (pi + 1) % k
        edges.append((rels[pi], ns[pi], rels[j], ns[j]))
        RING_PAIRS.add((rels[pi], rels[j]))
    return edges


def apply_edits(block: bytes, edits: list[tuple[bytes, bytes]], where: str) -> bytes:
    b = block
    for find, rep in edits:
        n = b.count(find)
        if n != 1:
            raise BuildError(
                f"{where}: 찾는 바이트가 {n}번 나온다(정확히 1번이어야) — {find.hex()}"
            )
        b = b.replace(find, rep)
    return b


def build(edits_path: Path | None) -> Path:
    common.verify_originals()
    out_dir = common.BUILD_DIR / common.BUILD_TAG
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = out_dir / "ed1.iso"
    cue = out_dir / "ed1.cue"
    for p in (iso, cue, out_dir / "ed1.iso.failed"):
        if p.exists():
            p.unlink()
    try:
        _build(edits_path, iso, cue)
    except Exception:
        if iso.exists():
            iso.rename(out_dir / "ed1.iso.failed")
        raise
    return iso


def _build(edits_path, iso: Path, cue: Path):
    shutil.copyfile(common.ORIG_ISO, iso)
    cue.write_text(common.ORIG_CUE.read_text().replace(common.ORIG_ISO.name.upper(), "ed1.iso"))
    # 원본 cue 의 FILE 줄은 대문자 파일명 — 위 치환이 안 먹으면 여기서 죽는다
    if "ed1.iso" not in cue.read_text():
        raise BuildError("cue 의 FILE 이름을 못 바꿨다")
    # 글리프 표 = 번역 정본 전체 + PoC 편집의 음절(결정적). 표를 따로 두지 않는다(폰트 전략 §3.2)
    # 🔴 상주 표 = 늘 상주해야 하는 글자(`glyphdyn.forced_chars`) + 정본에 든 본문 글자. 정본에 없는 본문 글자는 블록이 싣는다(동적 칸).
    chars = glyphdyn.forced_chars() | (translate.all_glyph_chars() & set(font._order_canon()))
    chars |= credits_kr.chars()  # 오프닝 성우 크레딧 글자(글리프 표는 모듈 안 0 구역에 따로 싣는다 — credits_kr)
    raw = json.loads(edits_path.read_text()) if edits_path else []
    chars |= {ch for e in raw for ch in e.get("replace_text", "") if font.needs_glyph(ch)}
    table, glyph_bank = font.build_table(chars)
    edits = load_edits(edits_path, table) if edits_path else {}
    found = containers.scan()
    by_rel = {c["rel"]: c for c in found}
    touched: list[tuple[int, int]] = []  # (첫 파일 섹터, 섹터 수)
    intended: dict[tuple[int, int], bytes] = {}
    recs: dict[tuple[int, int], structure.BlockRec] = {}  # 재배치 장부·구조 대조(structure.py)
    refs = containers.referenced()
    slot_of = {r: n for r, n in refs}  # 참조표가 말하는 섹터 수
    ledger = WriteLedger()
    free_pool = FreePool()
    moves: dict[int, tuple[int, int]] = {}  # 옛 rel → (새 rel, 섹터 수)
    split_pairs: list[tuple[int, int, int, int]] = []  # (참조표 쪽 rel, 섹터, 풀 쪽 rel, 섹터) — 짝 정보는 두 컨테이너 디렉터리에 들어 있다(splitload)
    split_gone: set[tuple[int, int]] = set()  # (원 rel, id) — 제자리 컨테이너에서 풀 쪽으로 옮겨 간 블록
    split_intended: dict[tuple[int, int], bytes] = {}  # 나눈 컨테이너 B 쪽 블록(참조표 밖이라 스캔이 못 본다 — 따로 되읽는다)
    with open(iso, "r+b") as f, _record_writes(ledger):
        apply_code_patches(f, glyph_bank, table, touched)
        if want("opsub"):  # 오프닝 나레이션 자막(스프라이트) — tools/opening_sub.py
            print("  " + opening_sub.apply(f, touched))
        if want("staff"):  # 엔딩 스태프롤 전각 영문(사람 이름만 원문) — tools/staffroll.py
            print("  " + staffroll.apply(f, touched))
        # 엔딩 끝 카드 「영웅들의 전설 / 제작·저작」(네오둥근모) · 오마케 간판 — tools/gfx_text.py
        if want("card"):
            print("  " + gfx_text.apply_card(f, touched))
        if want("banner"):
            print("  " + gfx_text.apply_banner(f, touched))
        if want("kkeut"):
            print("  " + gfx_text.apply_kkeut(f, touched))
        # 엔딩 음성 자막(스프라이트, 오프닝 런타임 한 벌 더) — tools/ending_sub.py
        if want("edsub"):
            print("  " + ending_sub.apply(f, touched))
        # ⚠ HUD 가 먼저 — 시스템 문구가 HUD 묶음 꼬리(빈 공간 ⓑ)에 조각을 옮겨 싣는다(freespace.spans)
        if want("hud"):
            print("  " + hud_plate.apply(f, touched))
        if want("sys"):
            print("  시스템 문구:", sysbuild.apply(f, table, touched))
        if want("sys"):  # 오마케(사운드 테스트·도감) 한글 — 전용 미니 훅 + 글리프 블록(rel 450 모듈 안 · rel 447~449) + 첫 메뉴 라벨 그림(rel 642~)
            _extras = json.loads((common.GAME_DIR / "script" / "sys" / "extras.json").read_text(encoding="utf-8"))
            print("  " + omake_font.apply(f, table, _extras, touched))
            print("  " + syscard_screen.apply(f, touched))  # 구형 카드 안내 화면 한글 띠(코드 훅 + rel 25~27 자료)
        if want("battle"):
            print("  전투 데이터:", battle.apply(f, table, touched))
        if want("band"):
            print("  " + chapter_band.apply(f, touched))
        if want("box"):
            print("  " + boxpack.apply_msg1_relocation(f, touched))
        translated_ids = {int(p.stem[3:]) for p in translate.M.SCRIPT_DIR.glob("scn*.json")}
        if os.environ.get("ED_SKIP_TRANSLATE"):  # 🔴 시험 전용 — 컨테이너 자리를 비우려고 그 씬들은 번역을 안 건다(비모달 자막 시제품이 씬 블록을 키운다)
            assert common.BUILD_TAG.startswith("test-"), "ED_SKIP_TRANSLATE 는 시험 빌드(ED_BUILD_TAG=test-*)에서만"
            translated_ids -= {int(x) for x in os.environ["ED_SKIP_TRANSLATE"].split(",") if x}
        # 나레이션 게이트는 번역 여부와 무관하게 건다(아직 번역 전인 씬도 자막은 원문으로 나온다)
        narr_ids = set(narration_gates.SITES) | set(narration_gates.ALWAYS) if want("narr") else set()
        n_gates = 0
        n_gwin = 0
        n_sched = 0
        sched_ids = voice_sched.scene_ids() if want("narr") else set()
        # 🔴 시험 전용 — 원판 ON 흐름 + 비모달 자막(`gwin_rt.on_flow_spec`, 마스터 10-30 「캐릭터 움직임과 대사창을 동시에」). `ED_GWIN_ON=6` 이면 그 씬은 나레이션 게이트·전역 시각표를 걸지 않는다
        # `ED_GWIN_ON=6,98,18@1268` — `씬@rel` 은 **그 컨테이너의 사본만**(10-31 ⓒ: 씬 18 은 1장 지역 1 = 1268 과 2장 지역 0·1 = 1284 에 같은 블록이 들어 있고,
        #   둘 다 넣으면 둘 다 17섹터라 나눠야 해 split 짝 표(6항목)를 넘는다. 1장 이벤트는 1268 에서만 열리므로 그 사본만 안 B, 1284 사본은 제품 그대로(OFF 흐름 + 시각표)).
        gwin_sel: dict[int, set[int] | None] = {}
        # 🔴 제품 기본(마스터 11-05 「비모달 자막은 0.1.0 대상」): 이 씬들은 비모달 자막이 제품 롬에 든다. `ED_GWIN_ON` 을 주면(빈 값 포함) 그걸로 덮는다 — 시험 빌드 전용
        gwin_env = os.environ.get("ED_GWIN_ON", GWIN_PRODUCT)
        for x in gwin_env.split(","):
            if x:
                sid, _, at = x.partition("@")
                gwin_sel.setdefault(int(sid), set() if at else None)
                if at and gwin_sel[int(sid)] is not None:
                    gwin_sel[int(sid)].add(int(at))
        gwin_on = set(gwin_sel)
        if gwin_env != GWIN_PRODUCT:
            assert common.BUILD_TAG.startswith("test-"), "ED_GWIN_ON 은 시험 빌드(ED_BUILD_TAG=test-*)에서만"
        GWIN_DONE.clear()
        ZONE54.clear()
        n_msgs = 0
        n_dyn = 0
        n_dyn_blocks = 0
        viewer_idx: list[dict] = []
        # 🔴 디버그 전용 — 대사 보기 **블록 바꿔 넣기**(관리자 11-02 「씬 입구나 점프 세이브에 기대지 않는」 대사 보기): `ED_VIEWER_SWAP={"호스트씬": 대상씬}` — 점프로 닿는
        #   호스트 씬의 블록 자리에 대상 씬의 블록(번역·동적 글리프·대사 보기 스텁 포함)을 넣는다. 호스트 입구로 들어가면 대상 씬의 메시지 전부가 렌더러로 그려진다(이벤트 코드는 안 돈다).
        viewer_swap = {int(k): int(v) for k, v in json.loads(os.environ.get("ED_VIEWER_SWAP", "{}")).items()}
        viewer_swap_hosts = set(viewer_swap)
        if viewer_swap:
            assert common.BUILD_TAG.startswith("test-"), "ED_VIEWER_SWAP 은 시험 빌드(ED_BUILD_TAG=test-*)에서만"
        _swap_src: dict[int, bytes] = {}
        if viewer_swap:
            for _c in containers.scan():
                for _b in _c["blocks"]:
                    _swap_src.setdefault(_b["id"], _b["data"])
        for rel, c in sorted(by_rel.items()) if want("scn") else []:
            hit = {k for k in edits if k[0] == rel} or {b["id"] for b in c["blocks"]} & (
                translated_ids | narr_ids | {int(x) for x in gwin_rt.build_specs()} | sched_ids | gwin_on | viewer_swap_hosts
            )
            if not hit:
                continue
            entries = []
            for b in c["blocks"]:
                dir_id = b["id"]
                if dir_id in viewer_swap:  # 호스트 자리에 대상 블록 — 아래 단계는 전부 대상 씬 번호로 돈다, 디렉터리 id 만 호스트
                    b = {"id": viewer_swap[dir_id], "data": _swap_src[viewer_swap[dir_id]]}
                blk = b["data"]
                dyn: list[str] = []
                rec = structure.BlockRec(rel, dir_id, b["data"])  # 재배치 장부·구조 대조용 단계 기록(structure.py)
                _s = blk
                if b["id"] in translated_ids:
                    btab, dyn = glyphdyn.block_table(table, b["id"])
                    blk, n = translate.translate_block(b["id"], blk, btab)
                    n_msgs += n
                    rec.add("translate", _s, blk)
                    _s = blk
                if (rel, b["id"]) in edits:
                    blk = apply_edits(blk, edits[(rel, b["id"])], f"rel {rel} id {b['id']}")
                    rec.add("edits", _s, blk)
                    _s = blk
                gwin_here = b["id"] in gwin_sel and (gwin_sel[b["id"]] is None or rel in gwin_sel[b["id"]])  # 이 사본에 안 B 를 넣는가 — 넣으면 게이트·시각표는 안 건다
                if b["id"] in narr_ids and not gwin_here:
                    blk, n = narration_gates.patch_block(b["id"], blk, btab if b["id"] in translated_ids else None)
                    n_gates += n
                    rec.add("narr", _s, blk)
                    _s = blk
                if b["id"] in sched_ids and not gwin_here:  # 음성 장면 — ON 이어도 OFF 흐름 + 음성 + 전역 시각표(voice_sched)
                    blk, n = voice_sched.patch_block(b["id"], b["data"], blk)
                    n_sched += n
                    rec.add("sched", _s, blk)
                    _s = blk
                if gwin_here:  # 시험: 원판 ON 흐름 + 비모달 자막
                    blk, n = gwin_rt.patch_block(b["id"], blk, gwin_rt.on_flow_spec(b["id"]), btab if b["id"] in translated_ids else None, code_bank=(splitload.TAIL_BANKS[rel] - 1 if rel in splitload.TAIL_BANKS else gwin_rt.code_sector(slot_of[rel]) // 4))
                    n_gwin += n
                    GWIN_DONE.add((rel, b["id"]))
                    rec.add("gwin", _s, blk)
                    _s = blk
                if want("narr") and str(b["id"]) in gwin_rt.build_specs():  # 월드를 안 멈추는 대사창 모양 자막(장면 2 인사)
                    blk, n = gwin_rt.patch_block(b["id"], blk)
                    n_gwin += n
                    rec.add("gwin", _s, blk)
                    _s = blk
                if os.environ.get("ED_VIEWER"):  # 🔴 디버그 전용 — 대사 보기(tools/viewer.py). 꼬리표는 test- 로 시작해야 한다
                    assert common.BUILD_TAG.startswith("test-"), "ED_VIEWER 는 시험 빌드(ED_BUILD_TAG=test-*)에서만"
                    lo_hi = os.environ["ED_VIEWER"]  # "1" = 전부 · "3-110" = 그 씬 번호만(스텁이 이사 자리를 넘겨서 반씩 굽는다)
                    lo, _, hi = (lo_hi if "-" in lo_hi else "0-999").partition("-")
                    only = json.loads(os.environ.get("ED_VIEWER_ADDRS", "{}"))  # 주소 목록이 있으면 그 씬만 스텁을 단다(시험용 — 이사 자리를 아낀다)
                    if int(lo) <= b["id"] <= int(hi) and (not only or str(b["id"]) in only) and (not viewer_swap or dir_id in viewer_swap):  # 바꿔 넣기 빌드는 바꿔 넣은 블록에만 스텁(전 씬에 달면 컨테이너가 터진다)
                        viewer_idx.append(viewer.index(b["id"], b["data"]))
                        _s = blk
                        _item = font.encode(os.environ["ED_VIEWER_ITEM"], btab, half_space=True) if os.environ.get("ED_VIEWER_ITEM") else b""
                        blk = viewer.patch_block(blk, b["data"], b["id"], item=_item)
                        rec.add("viewer", _s, blk)
                if dyn:  # 동적 글리프 — 머리 점프를 꼬리 스텁으로(블록 열림 훅)
                    _s = blk
                    blk = glyphdyn.attach(blk, dyn)
                    n_dyn += len(dyn)
                    n_dyn_blocks += 1
                    rec.add("dyn", _s, blk)
                if b["id"] == zone_image.SCENE and dir_id == b["id"] and b["id"] in translated_ids and rel == zone_image.CONTAINER_REL:
                    _img = _scene54_image(
                        b["data"], rel, table, edits,
                        ({b["id"]} if (b["id"] in narr_ids or b["id"] in sched_ids or gwin_here or str(b["id"]) in gwin_rt.build_specs()) else set()),
                    )
                    _s = blk
                    blk = zone_image.patch_count(blk, len(_img))  # 초기화 루프 복사 길이 — 컨테이너 블록과 이미지가 같아야 한다(루프가 자기 코드를 덮어쓴다)
                    rec.add("edits", _s, blk)
                    ZONE54[:] = [zone_image.patch_count(_img, len(_img))]
                if blk != b["data"] or dir_id != b["id"]:
                    if rec.final != blk and dir_id == b["id"]:
                        raise BuildError(f"rel {rel} id {b['id']}: 단계 기록(structure)이 최종 블록과 다르다 — 기록 안 하는 단계가 블록을 바꿨다")
                    intended[(rel, dir_id)] = blk
                    if dir_id == b["id"]:
                        recs[(rel, dir_id)] = rec
                entries.append((dir_id, blk))
            orig = common.track_data(rel, slot_of[rel])
            data = assemble(entries, orig, f"rel {rel}")
            gwin_ids = [i for i, _ in entries]
            tail = b"\1" if rel in splitload.FORCE_SEP else _gwin_tail(gwin_ids, rel)  # 🔴 FORCE_SEP 컨테이너는 자막 코드 영역이 쪽마다 따로라 통짜로 못 만든다 — 자리표시만, 나누기가 쪽별로 붙인다
            cs = gwin_rt.code_sector(slot_of[rel])  # 코드 영역 = 그 컨테이너의 마지막 뱅크(뱅크 수를 원판보다 늘리지 않는다)
            tail_fits = bool(tail) and len(data) <= cs * common.USER and rel not in splitload.TAIL_BANKS and rel not in splitload.FORCE_SEP
            if tail_fits:  # 안 나누고 붙인다(11-01) — 데이터가 마지막 뱅크 앞에 들면 제자리(11-05: 나눔 목록에 있어도 들면 안 나눈다 — 이사·짝 교체를 아낀다)
                data = _with_tail(data, tail, f"rel {rel}", code_sector=cs)
            elif tail and rel not in splitload.SPLIT_RELS:
                raise BuildError(f"컨테이너 rel {rel}: 안 B 자막 씬이 있는데 데이터 {len(data)}B 가 코드 영역 앞 {cs}섹터를 넘는다 — 나눌 목록(splitload.SPLIT_RELS)에 넣어라")
            elif tail:
                data = data + b"\0" * max(0, splitload.LIMIT_SECTORS * common.USER + 1 - len(data))  # 나누기로 보낸다(코드 영역은 _write_split 가 붙인다)
            slot = slot_of[rel] * common.USER
            n_total = -(-len(data) // common.USER)
            if rel in splitload.PART_RELS and want("split"):  # 🔴 ⓣ — 구역 적재를 3뱅크 이하로(2장 컨테이너, 한 뱅크를 캐시에 돌려준다)
                if n_total > splitload.PART_SECTORS:
                    edges = _write_parts(f, rel, entries, orig, free_pool, moves, intended, split_intended, touched, split_gone, splitload.PART_SECTORS)
                    split_pairs.extend(edges)
                    print(f"  컨테이너 rel {rel}: {len(entries)}블록 · 다시 깖 · 총량 {len(data)}B = {n_total}섹터 > {splitload.PART_SECTORS} → 조각 {len(edges)}개 고리")
                    continue
                if n_total < slot_of[rel]:  # 안 나뉘어도 참조표 섹터 수를 실제 크기로(제자리)
                    NSEC_NEW[rel] = n_total
            if n_total > splitload.LIMIT_SECTORS or rel in splitload.FORCE_Y or rel in splitload.FORCE_SEP:  # 🔴 5뱅크(17섹터↑) 컨테이너 — 캐시 칸이 모자라 자원이 조용히 안 올라온다(10-24)
                if rel in splitload.SPLIT_RELS and want("split"):
                    split_pairs.append(_write_split(f, rel, entries, orig, free_pool, moves, intended, split_intended, touched, split_gone))
                    print(f"  컨테이너 rel {rel}: {len(entries)}블록 · 다시 깖 · 총량 {len(data)}B = {n_total}섹터 > {splitload.LIMIT_SECTORS} → 둘로 나눔 {split_pairs[-1]}")
                    continue
                if want("split"):
                    raise BuildError(f"컨테이너 rel {rel}: {n_total}섹터 > {splitload.LIMIT_SECTORS}(4뱅크, {len(data) - splitload.LIMIT_SECTORS * common.USER}B 넘침) — 캐시 칸이 모자라 조용히 깨진다. 나눌 목록(splitload.SPLIT_RELS)에 넣거나 줄여라")
            data_raw = data
            if len(data) <= slot:  # 제자리 — 남는 칸은 0
                data += b"\0" * (slot - len(data))
                at_rel, n_sec, expect = rel, slot_of[rel], orig
            else:  # 🔴 총량이 칸을 넘는다 (넘침 {len(data)-slot}B) → 트랙 끝 빈 구간으로 이사(참조표 항목은 아래서 고친다)
                n_sec = -(-len(data) // common.USER)
                if want("split") and -(-n_sec // 4) > -(-slot_of[rel] // 4):  # 🔴 원판보다 뱅크를 더 먹으면 캐시 칸이 모자란다(원판은 어느 구역이든 14칸 점유)
                    raise BuildError(f"컨테이너 rel {rel}: {n_sec}섹터 = {-(-n_sec // 4)}뱅크 > 원판 {slot_of[rel]}섹터 = {-(-slot_of[rel] // 4)}뱅크 — 캐시 점유가 원판보다 는다")
                data += b"\0" * (n_sec * common.USER - len(data))
                at_rel = free_pool.alloc(n_sec)
                expect = b"\0" * len(data)
                moves[rel] = (at_rel, n_sec)
                for k in [k for k in intended if k[0] == rel]:
                    intended[(at_rel, k[1])] = intended.pop(k)
            need = len(data_raw)
            lba = common.T2_SECTOR + at_rel
            mode1.write_user_data(f, lba, data, label=f"container rel {at_rel}", expect=expect)
            touched.append((lba, n_sec))
            if tail_fits:  # 안 나눈 컨테이너의 코드 영역 — 디렉터리 밖이라 블록 되읽기가 못 본다, 바로 되읽어 대조
                o = cs * common.USER
                got = _readback_user(f, lba + cs, -(-len(tail) // common.USER))
                if got[: len(tail)] != tail or data[o : o + len(tail)] != tail:
                    raise BuildError(f"컨테이너 rel {at_rel}: 코드 영역 되읽기가 쓴 것과 다르다")
                print(f"  안 B 코드 영역: rel {at_rel} 섹터 {cs}~ {len(tail)}B 되읽기 OK(안 나눔)")
            moved = sum(1 for a, b in zip(data, orig, strict=False) if a != b)
            where = f"→ rel {at_rel}({n_sec}섹터, 총량 {need}B/{slot}B) 이사" if at_rel != rel else "제자리"
            print(f"  컨테이너 rel {rel}: {len(entries)}블록 · 다시 깖 · {where} · 바뀐 바이트 {moved}/{slot}")
        ref_moves = {**{r: (r, n) for r, n in NSEC_NEW.items() if r not in moves}, **moves}
        if ref_moves:
            print("  " + patch_ref_table(f, refs, ref_moves, touched))
        apply_glyph_payload(f, glyph_bank, table, touched, split_pairs)
        if ZONE54:
            print("  " + apply_zone(f, ZONE54[0], touched))
        if split_pairs:  # 씬 열기 탐색 루프를 짝 교체 루틴 호출로 바꾼다(사이트 21B)
            old, new = splitload.site_patch()
            lbl, srel, soff = "scene-open split site", *_main(*splitload.SITE_REL_OFF)
            lba = common.T2_SECTOR + srel
            mode1.write_at(f, lba, common.USER, soff, new, label=lbl, expect=old)
            touched.append((lba, 1))
            print(f"  컨테이너 나누기 {len(split_pairs)}곳 — 씬 열기 사이트 패치(뱅크 0x6A+{splitload.SITE_REL_OFF[1]:#x})")
    if os.environ.get("ED_VIEWER"):  # 대사 보기 색인(번호표 → 원본 열쇠) — 원문 열쇠만(문안 없음), 커밋 안 함
        import json as _json

        common.REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        (common.REVIEW_DIR / "viewer_index.json").write_text(_json.dumps(viewer_idx, ensure_ascii=False), "utf-8")
        print(f"  대사 보기 색인 {len(viewer_idx)}블록 · 개수 어긋남 {sum(not v['ok'] for v in viewer_idx)}")
    print(f"  번역 메시지 {n_msgs}건(컨테이너마다 다시 셈) · 상주 글리프 {len(chars)}자 · 동적 글리프 블록 {n_dyn_blocks}건(컨테이너마다 다시 셈, 글자 {n_dyn}자)")
    if want("narr") and want("scn"):
        print(f"  나레이션 게이트 자막 {n_gates}곳 · 음성 장면 시각표 게이트 {n_sched}곳 · 대사창 모양 자막 {n_gwin}곳(컨테이너마다 다시 셈)")
    print(f"  덮어쓰기 없음 (쓰기 구간 {ledger.verify(iso)})")
    verify_immutable(iso, touched)
    verify_readback(iso, intended, found, moves, [p[2] for p in split_pairs if p[2] >= FreePool.START], split_gone, NSEC_NEW)
    verify_split(iso, split_intended, split_pairs)
    if want("scn"):
        led, viol, summ = structure.verify_all(recs, sum(len(c["blocks"]) for c in found), moves)
        if want("battle"):  # 전투 컨테이너 문구 단위 — 같은 대조(structure.analyze_battle_block)
            bl, bv, bs = structure.verify_battle(battle.STRUCT_RECS)
            led += bl
            viol += bv
            summ["battle"] = bs
        if want("sys"):  # 시스템 메시지(뱅크 0x6D) 제어 열 + 라벨 구분자 — 구운 이미지를 읽어 대조(structure.verify_sys)
            sl, sv, sp, ss = structure.verify_sys(iso)
            led += sl
            viol += sv
            summ["sys"] = ss
            if sp:
                print(f"  ⚠ 구조 대조 보류 {len(sp)}건(의도 확인 대기 — structure.PENDING): " + " | ".join(sp))
        (iso.parent / "relocations.tsv").write_text(structure.ledger_tsv(led), encoding="utf-8")  # 장부 = 씬 + 전투 + 시스템(커밋 대상은 check_relocations.py --freeze)
        kinds_n = Counter(k for _b, k, _c in led)
        print(
            f"  구조 대조: 씬 블록 {summ['compared']}/{summ['total']}(나머지는 번역·패치가 안 닿은 블록 = 원본 그대로) · 전투 블록 {summ.get('battle', {}).get('compared', 0)}/{summ.get('battle', {}).get('total', 0)} · 시스템 메시지 {summ.get('sys', {}).get('compared', 0)}/{summ.get('sys', {}).get('total', 0)} · 위반 {len(viol)} · "
            f"재배치 장부 {len(led)}행(" + " ".join(f"{k} {v}" for k, v in sorted(kinds_n.items())) + ")"
        )
        if viol:
            raise BuildError("구조 대조 위반 %d건:\n  " % len(viol) + "\n  ".join(viol[:40]) + ("\n  …" if len(viol) > 40 else ""))
    if want("sys"):
        print("  오마케 그림 되읽기 OK — " + omake_art.verify_iso(iso))
        print("  " + syscard_screen.verify_iso(iso))
    if want("battle"):
        print(f"  전투 컨테이너 되읽기 OK (블록 {battle.verify(iso, table)})")
    bad = mode1.selftest(
        iso,
        lbas=(
            common.T2_SECTOR + 2,
            common.T2_SECTOR + 34,
            common.T2_SECTOR + 1252,
            common.T22_SECTOR + 1,
        ),
    )
    if bad:
        raise BuildError(f"EDC/ECC 자기검증 실패: {bad}")
    print(f"빌드 OK: {iso}  sha1 {common.sha1_of(iso)}")


def verify_immutable(iso: Path, touched: list[tuple[int, int]]):
    """선언한 섹터 밖은 원본과 byte 동일해야 한다."""
    allowed = set()
    for lba, n in touched:
        allowed.update(range(lba, lba + n))
    with open(common.ORIG_ISO, "rb") as a, open(iso, "rb") as b:
        chunk = 4096 * common.RAW
        lba = 0
        while True:
            x = a.read(chunk)
            y = b.read(chunk)
            if not x and not y:
                break
            if x != y:
                for i in range(0, len(x), common.RAW):
                    if (
                        x[i : i + common.RAW] != y[i : i + common.RAW]
                        and (lba + i // common.RAW) not in allowed
                    ):
                        raise BuildError(
                            f"무변경 구간이 바뀌었다: 파일 섹터 {lba + i // common.RAW}"
                        )
            lba += chunk // common.RAW
    print(f"  무변경 대조 OK (허용 {len(allowed)}섹터 밖 동일)")


def verify_split(iso: Path, split_intended, pairs):
    """나눈 컨테이너 둘(A 는 참조표가 가리키고 B 는 짝 표만 가리킨다)을 이미지에서 되읽어 대조 — 4뱅크 안 · 블록 일치 ·
    짝 표(글리프 뱅크 0 꼬리) 양방향 · 사이트 패치."""
    if not pairs:
        return
    data = iso.read_bytes()

    def sec(r):
        o = (common.T2_SECTOR + r) * common.RAW + common.USER_OFF
        return data[o : o + common.USER]

    for ra, na, rb, nb in pairs:
        for r, n in ((ra, na), (rb, nb)):
            if n > splitload.LIMIT_SECTORS:
                raise BuildError(f"나누기 되읽기: rel {r} {n}섹터 > {splitload.LIMIT_SECTORS}")
            buf = b"".join(sec(r + k) for k in range(n))
            ents, _ = containers.parse_dir(buf[: common.USER])
            for id_, src, ln in ents:
                if id_ == containers.PARTNER_ID:
                    continue
                got, _ = lz.decode(buf[src:], ln)
                want_b = split_intended.get((r, id_))
                if r == rb and want_b is not None and got != want_b:
                    raise BuildError(f"나누기 되읽기: rel {r} id {id_} 이 의도와 다르다")
    # 짝 정보 항목 — 서로를 가리키고(rec·섹터수), 짝 쪽도 컨테이너로 읽히며 4뱅크 안인가
    for ra, na, rb, nb in pairs:
        for r, other, n_o in (((ra, rb, nb),) if (ra, rb) in RING_PAIRS else ((ra, rb, nb), (rb, ra, na))):
            buf = b"".join(sec(r + k) for k in range(2))
            ents, dend = containers.parse_dir(buf[: common.USER])
            pe = [e for e in ents if e[0] == containers.PARTNER_ID]
            if len(pe) != 1 or ents[-1][0] != containers.PARTNER_ID or pe[0][1] != other - containers.REC_BASE or pe[0][2] != n_o:
                raise BuildError(f"나누기 되읽기: rel {r} 의 짝 정보 항목이 의도({other - containers.REC_BASE}, {n_o})와 다르다")
    gb = b"".join(sec(114 + k) for k in range(font.GLYPH_NBANKS * 0x2000 // common.USER))
    lay = splitload.layout()
    code = splitload.code()
    off = splitload.BANK_OFF
    if gb[off : off + len(code)] != code:
        raise BuildError("나누기 되읽기: 글리프 뱅크 0 꼬리의 짝 교체 루틴이 의도와 다르다")
    print(f"  나누기 되읽기 OK — 컨테이너 쌍 {len(pairs)} · " + " · ".join(f"{ra}({na}섹터)↔{rb}({nb}섹터)" for ra, na, rb, nb in pairs))


def verify_readback(iso: Path, intended, found_orig, moves=None, extra_rels=(), gone=frozenset(), nsec_new=None):
    data = iso.read_bytes()
    track = b"".join(
        data[
            (common.T2_SECTOR + r) * common.RAW + common.USER_OFF : (common.T2_SECTOR + r)
            * common.RAW
            + common.USER_OFF
            + common.USER
        ]
        for r in range(common.T2_LEN)
    )
    got = containers.scan(track)
    moves = moves or {}
    want = sorted([c["rel"] for c in found_orig] + [v[0] for v in moves.values()] + list(extra_rels))  # extra = 나눈 컨테이너 B 쪽(참조표 밖)
    if [c["rel"] for c in got] != want:
        raise BuildError("되읽기: 컨테이너 목록이 달라졌다")
    # 참조표가 가리키는 (rel, 섹터수) 가 전부 스캔된 컨테이너고, 이사한 건 새 자리를 가리키나
    b42 = track[containers.REF_BANK_REL * common.USER :][: 4 * common.USER]
    out_refs = []
    for i in range(containers.REF_ENTRIES):
        e = b42[containers.REF_TABLE_OFF + 3 * i :][:3]
        out_refs.append((containers.REC_BASE + (e[0] | e[1] << 8), e[2]))
    in_refs = containers.referenced()
    for (r0, n0), (r1, n1) in zip(in_refs, out_refs, strict=True):
        want_ref = moves.get(r0) or ((r0, (nsec_new or {})[r0]) if r0 in (nsec_new or {}) else (r0, n0))
        if (r1, n1) != want_ref:
            raise BuildError(f"되읽기: 참조표 {(r0, n0)} → {(r1, n1)} 가 의도와 다르다")
    scanned = {c["rel"] for c in got}
    if {r for r, _ in out_refs} - scanned:
        raise BuildError("되읽기: 참조표가 컨테이너가 아닌 곳을 가리킨다")
    blocks = {(c["rel"], b["id"]): b["data"] for c in got for b in c["blocks"]}
    for k, blk in intended.items():
        if blocks.get(k) != blk:
            raise BuildError(f"되읽기: rel {k[0]} id {k[1]} 이 의도와 다르다")
    # 안 고친 블록은 원본 그대로
    orig_blocks = {(c["rel"], b["id"]): b["data"] for c in found_orig for b in c["blocks"]}
    for k, blk in orig_blocks.items():
        if k not in intended and k not in gone and blocks.get(k) != blk:
            raise BuildError(f"되읽기: 안 고친 블록 rel {k[0]} id {k[1]} 이 바뀌었다")
    print(f"  되읽기 OK (고친 블록 {len(intended)} · 컨테이너 {len(got)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", type=Path, help="PoC 편집 입력 JSON (work/ 아래, 커밋 안 함)")
    ap.add_argument("--only", help="진단용: 패치 그룹만(cache,font,hook 쉼표 구분)")
    a = ap.parse_args()
    global ONLY
    if a.only:
        ONLY = set(a.only.split(","))
    build(a.edits)


if __name__ == "__main__":
    main()
