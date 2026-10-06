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
import contextlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import battle
import boxpack
import chapter_band
import common
import containers
import ending_sub
import font
import gfx_text
import hook
import hud_plate
import lz
import narration_gates
import opening_sub
import staffroll
import sysbuild
import translate

from shared.disc import mode1

SLOT_SECTORS = 16  # 컨테이너 한 칸(실측: 참조표 간격 16섹터 = 32KB)
BANK = 0x2000  # 풀린 블록은 뱅크 0x76 하나에 들어가야 한다


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


def assemble(entries: list[tuple[int, bytes]], orig: bytes, where: str = "") -> bytes:
    """(id, 풀린 블록) 목록 → 컨테이너 바이트. 🔴 **블록을 원본 자리(`src`)에 그대로 둔다.**

    옛 판은 앞에서부터 다시 깔았는데, 우리 인코더가 원본보다 조금씩 촘촘해서 **안 고친 블록까지
    앞으로 당겨졌다**(rel 1252 실측 −254B, blk6 은 10,542 → 10,406). 디렉터리는 따라가지만
    **디렉터리를 안 보는 참조**가 있으면 그게 곧 소프트락이다 — 이 레포가 PS1 에서 이미 물린
    「위치가 계약인 구간」이다(`docs/reference/our-findings.md` 재삽입 「구조 계약」).
    ⇒ 원본 컨테이너 바이트에서 출발해 **각 블록의 원래 슬롯만 덮어쓴다.** 슬롯을 넘치면 죽는다.
    """
    for id_, blk in entries:
        if len(blk) > BANK:
            raise BuildError(f"블록 id {id_} 가 {len(blk)}B — 뱅크(8KB)를 넘는다")

    o_ents, _ = containers.parse_dir(orig[: common.USER])
    if [i for i, _, _ in o_ents] != [i for i, _ in entries]:
        raise BuildError(f"컨테이너 {where}: 블록 id 목록이 원본과 다르다")

    # 슬롯 = 이 src 부터 **다음 src** 까지(같은 src 를 나눠 쓰는 중복 블록은 한 칸이다)
    srcs = sorted({src for _, src, _ in o_ents})
    end_of = {s: (srcs[k + 1] if k + 1 < len(srcs) else len(orig)) for k, s in enumerate(srcs)}
    ln_of = {src: ln for _, src, ln in o_ents}  # 원본이 말하는 풀린 길이(되풀어 대조용)

    out = bytearray(orig)
    done: dict[int, bytes] = {}
    d = bytearray()
    for (id_, blk), (_, src, _) in zip(entries, o_ents, strict=True):
        if src in done:
            if done[src] != blk:
                raise BuildError(f"컨테이너 {where}: 같은 src {src} 를 다른 내용이 나눠 쓴다")
        else:
            room = end_of[src] - src
            was, _ = lz.decode(orig[src:], ln_of[src])
            if blk != was:  # ⚠ 안 고친 블록은 **원본 바이트를 손대지 않는다** — 우리 인코더가
                pk = lz.encode(blk)  #    조금 촘촘해 다시 누르면 바꿀 이유 없는 바이트가 다 바뀐다
                if len(pk) > room:  # 탐욕이 넘치면 최적 파싱으로 다시(느리다 — 넘칠 때만)
                    pk = lz.encode_optimal(blk)
                if len(pk) > room:
                    raise BuildError(
                        f"컨테이너 {where} 블록 id {id_}: 압축 {len(pk)}B > 원래 슬롯 {room}B — "
                        "자리를 옮기지 않는 게 계약이다. 문안을 줄이거나 배치를 다시 설계해라"
                    )
                out[src : src + len(pk)] = pk
                out[src + len(pk) : end_of[src]] = b"\0" * (room - len(pk))
            done[src] = blk
        d += bytes([id_, src & 0xFF, src >> 8, len(blk) & 0xFF, len(blk) >> 8])
    d.append(containers.DIR_END)
    if len(d) > srcs[0]:
        raise BuildError(f"컨테이너 {where}: 디렉터리 {len(d)}B > 첫 블록 자리 {srcs[0]}B")
    out[: len(d)] = d
    out[len(d) : srcs[0]] = b"\0" * (srcs[0] - len(d))

    # 자기 검산 — 우리 디코더로 되풀어 같은가(코덱 A 조건)
    ents, _ = containers.parse_dir(bytes(out[:2048]))
    for (id_, blk), (id2, src, ln) in zip(entries, ents, strict=True):
        assert id_ == id2 and ln == len(blk)
        got, _ = lz.decode(bytes(out[src:]), ln)
        assert got == blk, f"재조립 검산 실패 id {id_}"
    return bytes(out)


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
`glyph`(글리프 뱅크 적재) · `payload`(후킹 루틴 + 표를 $3B00 에 싣기) ·
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


def code_patches() -> list[tuple[str, int, int, bytes, bytes]]:
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
    if want("cast"):
        # 6. 「게임 시작」 뒤 성우 크레딧의 표제 `声優出演` → `ＣＡＳＴ`(마스터 확정 2026-09-23 —
        #    이름 13개는 실존 성우라 원문 유지, 표제만). 크레딧 모듈(rel 514)이 이 SJIS 평문
        #    (rel 517)을 BIOS 글꼴(EX_GETFNT)로 직접 그리므로 **같은 길이의 전각 영문**으로 바꾸면
        #    코드 수정 없이 같은 자리에 나온다. 뒤의 `81 40 00`(전각 공백·종단)은 그대로 둔다.
        p.append(
            (
                "cast title 声優出演→ＣＡＳＴ",
                517,
                0x0420,
                "声優出演".encode("sjis"),
                "ＣＡＳＴ".encode("sjis"),
            )
        )
    if want("hook"):
        # 4. EX_GETFNT 호출부(본 프로그램 4곳) → $3B00
        tgt = hook.HOOK_ADDR.to_bytes(2, "little")
        p.append(("dialog JMP $7044", *_main(0x6C, 0x1044), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("name JMP $93A3", *_main(0x6D, 0x13A3), b"\x4c\x60\xe0", b"\x4c" + tgt))
        p.append(("JSR 6C+0F5A", *_main(0x6C, 0x0F5A), b"\x20\x60\xe0", b"\x20" + tgt))
        p.append(("JSR 78+0932", *_main(0x78, 0x0932), b"\x20\x60\xe0", b"\x20" + tgt))
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
    return p


def apply_code_patches(
    f, glyph_bank: bytes, table: dict[str, bytes], touched: list[tuple[int, int]]
):
    for label, rel, off, old, new in code_patches():
        assert len(old) == len(new), label
        lba = common.T2_SECTOR + rel
        mode1.write_at(f, lba, common.USER, off, new, label=label, expect=old)
        touched.append((lba, 1))
    # 5. 글리프 뱅크 → rel 114~(뱅크 0x7C~ 적재분, 원본 0 — font.GLYPH_NBANKS 뱅크), 후킹 루틴 → rel 126 앞 256B
    if not want("font"):
        return
    if want("glyph"):  # 진단용으로 뺄 수 있다 — 뱅크 0x7C~0x7E 를 0 인 채로 두는 A/B
        lba = common.T2_SECTOR + 114
        # 뱅크 꼬리 = 코드: 뱅크마다 풀기 루틴(`hook.unpack_asm`, 18B → 24B) · 마지막 뱅크 맨 끝은 어절
        #   줄바꿈 루틴(`hook.wordck`, `$6723` 경로가 MPR4 에 걸어 부른다). 글리프는 `BANK_GLYPH_END` 앞까지만.
        glyph_bank = hook.finish_banks(glyph_bank)
        mode1.write_user_data(
            f, lba, glyph_bank, label="glyph banks", expect=b"\0" * len(glyph_bank)
        )
        touched.append((lba, len(glyph_bank) // common.USER))
    # 루틴 + 조사 오프셋표 + 받침 비트맵 둘 — 스텁이 통째로 $3B00 으로 옮긴다(0x300B)
    payload = hook.payload(table)
    if want("payload"):  # 진단용 — $3B00~$3DFF 를 0 인 채로 두는 A/B(스텁은 그대로 돈다)
        lba = common.T2_SECTOR + 126
        mode1.write_user_data(
            f, lba, bytes(payload), label="hook routine + josa tables", expect=b"\0" * len(payload)
        )
        touched.append((lba, 1))
    routine = payload
    print(
        f"  코드 패치 {len(code_patches())}곳 + 글리프 {len(glyph_bank.rstrip(b'\0'))}B + 루틴 {len(routine.rstrip(b'\0'))}B"
    )


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
    chars = translate.all_glyph_chars() | sysbuild.all_glyph_chars() | battle.glyph_chars()
    raw = json.loads(edits_path.read_text()) if edits_path else []
    chars |= {ch for e in raw for ch in e.get("replace_text", "") if font.needs_glyph(ch)}
    table, glyph_bank = font.build_table(chars)
    edits = load_edits(edits_path, table) if edits_path else {}
    found = containers.scan()
    by_rel = {c["rel"]: c for c in found}
    touched: list[tuple[int, int]] = []  # (첫 파일 섹터, 섹터 수)
    intended: dict[tuple[int, int], bytes] = {}
    refs = containers.referenced()
    slot_of = {r: n for r, n in refs}  # 참조표가 말하는 섹터 수
    ledger = WriteLedger()
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
        if want("battle"):
            print("  전투 데이터:", battle.apply(f, table, touched))
        if want("band"):
            print("  " + chapter_band.apply(f, touched))
        if want("box"):
            print("  " + boxpack.apply_msg1_relocation(f, touched))
        translated_ids = {int(p.stem[3:]) for p in translate.M.SCRIPT_DIR.glob("scn*.json")}
        # 나레이션 게이트는 번역 여부와 무관하게 건다(아직 번역 전인 씬도 자막은 원문으로 나온다)
        narr_ids = set(narration_gates.SITES) if want("narr") else set()
        n_gates = 0
        n_msgs = 0
        for rel, c in sorted(by_rel.items()) if want("scn") else []:
            hit = {k for k in edits if k[0] == rel} or {b["id"] for b in c["blocks"]} & (
                translated_ids | narr_ids
            )
            if not hit:
                continue
            entries = []
            for b in c["blocks"]:
                blk = b["data"]
                if b["id"] in translated_ids:
                    blk, n = translate.translate_block(b["id"], blk, table)
                    n_msgs += n
                if (rel, b["id"]) in edits:
                    blk = apply_edits(blk, edits[(rel, b["id"])], f"rel {rel} id {b['id']}")
                if b["id"] in narr_ids:
                    blk, n = narration_gates.patch_block(b["id"], blk)
                    n_gates += n
                if blk != b["data"]:
                    intended[(rel, b["id"])] = blk
                entries.append((b["id"], blk))
            orig = common.track_data(rel, slot_of[rel])
            data = assemble(entries, orig, f"rel {rel}")
            slot = slot_of[rel] * common.USER
            assert len(data) == slot, f"컨테이너 rel {rel}: {len(data)}B ≠ 칸 {slot}B"
            lba = common.T2_SECTOR + rel
            mode1.write_user_data(f, lba, data, label=f"container rel {rel}", expect=orig)
            touched.append((lba, slot_of[rel]))
            moved = sum(1 for a, b in zip(data, orig, strict=True) if a != b)
            print(
                f"  컨테이너 rel {rel}: {len(entries)}블록 · 자리 보존 · 바뀐 바이트 {moved}/{slot}"
            )
    print(f"  번역 메시지 {n_msgs}건(컨테이너마다 다시 셈) · 글리프 {len(chars)}자")
    if want("narr") and want("scn"):
        print(f"  나레이션 게이트 자막 {n_gates}곳(컨테이너마다 다시 셈)")
    print(f"  덮어쓰기 없음 (쓰기 구간 {ledger.verify(iso)})")
    verify_immutable(iso, touched)
    verify_readback(iso, intended, found)
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


def verify_readback(iso: Path, intended, found_orig):
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
    if [c["rel"] for c in got] != [c["rel"] for c in found_orig]:
        raise BuildError("되읽기: 컨테이너 목록이 달라졌다")
    blocks = {(c["rel"], b["id"]): b["data"] for c in got for b in c["blocks"]}
    for k, blk in intended.items():
        if blocks.get(k) != blk:
            raise BuildError(f"되읽기: rel {k[0]} id {k[1]} 이 의도와 다르다")
    # 안 고친 블록은 원본 그대로
    orig_blocks = {(c["rel"], b["id"]): b["data"] for c in found_orig for b in c["blocks"]}
    for k, blk in orig_blocks.items():
        if k not in intended and blocks.get(k) != blk:
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
