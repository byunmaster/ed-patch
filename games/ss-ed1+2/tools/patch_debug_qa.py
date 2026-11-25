"""QA 전용 디버그 빌드 — 진입키 X+Y+Z (마스터 11-18).

    ED_DEBUG_QA=1 ED_BUILD_TAG=qa-debug python3 tools/patch_debug_qa.py --apply

🔴 **제품 롬은 한 바이트도 안 바뀐다.** 이 단계는 환경변수 `ED_DEBUG_QA=1` 이 없으면 아무것도 안 하고
   끝난다(`check.sh` 가 체인 맨 끝에서 부른다). 쓰는 곳은 **꼬리표 `qa-debug` 의 빌드 칸**뿐이다.

## 어떻게 붙나
- 진입: 게임의 패드 읽기 함수(`ED.BIN 0x060806EC`)를 가리키는 리터럴 풀 참조를 우리 래퍼로 돌린다(조사 훅과 같은 방식 —
  원 명령을 안 건드린다). 래퍼는 원 함수를 먼저 부르고, **원시 패드 워드**(`*0x0609CA1C + 2`, 눌림 = 0)에서
  X·Y·Z 가 **동시에 눌린 순간**(엣지)을 본다. 게임 코드는 X·Y·Z 를 안 읽으므로 평소 입력과 안 겹친다.
- 자리: 원판 **개발용 루틴 구역**(`0x06074E9C~0x06075280`, 996B — 아무도 안 부른다. 셀 뷰어·폰트 테스트는 앞쪽에 그대로 둔다).
- 기능: 아래 `ACTIONS`. 값 자리는 헤드리스 하네스의 전투 전후 RAM diff 로 짚었다(NOTES · devlog 11-18).

ED2 는 X+Y+Z(소지금·경험치)만 — 소지품·워프·속도·벽 주소는 아직 미실측(`CONF` 의 `combos` 로 갈린다).
"""

import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import sh2
from build_tag import build_tag

LOAD_BASE = 0x06028000

CONF = {
    "/ED.BIN": dict(
        combos=("gold", "item", "warp", "speed", "enc"),
        # 조우 끄기 = 맵 이벤트 디스패처(0x06038D14)의 접촉 조우 호출 `jsr @r8`(→ 0x06083724) 하나를 nop 으로 — 480B ↔ 0009 (바이트별 k=72 · 20).
        #   전투 시작 함수를 막는 것과 달리 전투 뒤 처리가 안 깨진다(11-21 emucap 쓰기 BP 로 호출 스택 확인 · 헤드리스 39걸음 무조우)
        enc_sites=((0x06038D36, 72), (0x06038D37, 20)),
        pad_fn=0x060806EC,  # 패드 읽기 — 이 주소를 담은 풀 참조를 래퍼로 돌린다
        pad_sig="2fe6e7002472d33062326120601c88028d026ef3a04fe000",
        region=(
            0x06074E9C,
            0x06075280,
        ),  # 미호출 개발용 루틴 구역(996B) — 사전조건: 원본 바이트 그대로
        padptr=0x0609CA1C,  # *ptr = 패드 구조 (+0 종류 2 = 디지털, +2 워드 = 원시 버튼 · 눌림 0)
        gold=0x060AC364,  # 소지금 (BE dword) — 실측 11-18
        party=(
            0x060B8820,
            0x060B8CA0,
        ),  # 세리오스 레코드 사본 (108B 칸 × 4 · +0x1C = 누적 EP · u16@+2 = 레벨)
        add_exp=1000,
        add_gold=1000,
        bag=0x060BC490,  # 소지품 = 아이템 번호 바이트 배열(0 = 빈 칸) — 파티원 사본 둘은 따로. 번호 = 이름표 0x060BE470+32×번호
        warp_flags=0x060BF31F,  # 방문 깃발 바이트 50개(+1.. = 장소 번호 0~47, 1 = 가 봄). 워프 목록 짓는 함수 0x0603EFCC 가 읽는다
        # 걷기 한 걸음 = 방향 키에서 ±8 을 정하는 `mov #±8,r1`(0xE1xx) 명령의 즉치 바이트(함수 0x0602B430 · 8 = 한 칸의 1/?)
        #   — 8 ↔ 16 을 서로 뒤집는다(새 값 = ±24 − 옛 값). 0x0602B4AC 의 `mov #8` 은 마스크라 건드리지 않는다.
        speed_sites=tuple(
            (0x0602B000 + a + 1, k)
            for a, k in (
                (0x456, -24),
                (0x464, 24),
                (0x46A, -24),
                (0x474, -24),
                (0x482, 24),
                (0x4AE, -24),
                (0x4BC, 24),
                (0x4CC, -24),
                (0x4DA, 24),
            )
        ),
        bag_items=(
            78,
            76,
            64,
            65,
            72,
            85,
            82,
            69,
            99,
            102,
            67,
            66,
            98,
            106,
            107,
            113,
            48,
            62,
            114,
            115,
        ),
    ),
    "/ED2.BIN": dict(
        combos=("gold", "item", "speed"),
        pad_fn=0x06064008,  # 바이트가 ED1 과 똑같다(같은 시그니처)
        pad_sig="2fe6e7002472d33062326120601c88028d026ef3a04fe000",
        region=(0x06063C18, 0x06063FFC),  # 미호출 개발용 루틴 구역(996B) — 구역 안을 가리키는 풀은 구역 자신뿐
        padptr=0x06082718,  # *ptr = 패드 구조 0x06082954 (`0200ffbf…` — X 누름 실측 11-19, ED1 과 같은 거리 0x23C)
        gold=0x06091938,  # 소지금 (BE dword) — 전투 승리 0 → 10000 · HUD 10000 실측 11-19
        party=(0x0609E210, 0x0609E690),  # 파티 레코드(+0x1C = 누적 EP · 살아 있는 쪽은 0x0609E690 — 전투 뒤 +10000 실측)
        add_exp=1000,
        add_gold=1000,
        bag=0x0609ECF0,  # 소지품 = 번호 바이트 20칸(전투 드롭 +0x45 이 `32 32` 뒤에 붙는 것으로 짚음 11-19, 정적 대조 0x060322D8↔ED1 0x06049348)
        bag_items=tuple(range(1, 21)),  # ED2 번호표는 미확인 — 1~20 을 채워 목록 화면에서 본다
        # 걷기 함수 = ED1 0x0602B430 과 같은 코드가 ED2 0x0604F340(+0x23F10) — 즉치 명령 9곳이 바이트까지 같다(정적 대조 11-19)
        speed_sites=tuple(
            (0x0604EF10 + a + 1, k)
            for a, k in (
                (0x456, -24),
                (0x464, 24),
                (0x46A, -24),
                (0x474, -24),
                (0x482, 24),
                (0x4AE, -24),
                (0x4BC, 24),
                (0x4CC, -24),
                (0x4DA, 24),
            )
        ),
        # 워프 깃발·벽: ED2 주소 미실측 — 해당 조합은 ED2 에선 안 쓴다
    ),
}


class QAsm(sh2.Asm):
    """`sh2.Asm` 에 래퍼가 더 쓰는 명령만 얹는다(없는 걸 쓰면 이름 그대로 실패)."""

    def _jsr(self, s):
        self.emit(0x400B | (sh2._n(s[1:]) << 8))

    def _sts_l(self, s, d):  # sts.l pr,@-Rn
        assert s == "pr" and d.startswith("@-")
        self.emit(0x4022 | (sh2._n(d[2:]) << 8))

    def _lds_l(self, s, d):  # lds.l @Rn+,pr
        assert d == "pr" and s.startswith("@") and s.endswith("+")
        self.emit(0x4026 | (sh2._n(s[1:-1]) << 8))

    def _mov_l(self, s, d):
        if not s.startswith("@(") and not d.startswith("@-") and not s.endswith("+"):
            if s.startswith("@"):  # mov.l @Rm,Rn
                return self.emit(0x6002 | (sh2._n(d) << 8) | (sh2._n(s[1:]) << 4))
            if d.startswith("@"):  # mov.l Rm,@Rn
                return self.emit(0x2002 | (sh2._n(d[1:]) << 8) | (sh2._n(s) << 4))
        return super()._mov_l(s, d)

    def _mov_w(self, s, d):
        if s.startswith("@(") and d == "r0":  # mov.w @(disp,Rm),r0  (disp 는 바이트 단위·짝수)
            disp, rm = s[2:-1].split(",")
            v = int(disp, 0)
            assert v % 2 == 0 and 0 <= v <= 30
            return self.emit(0x8500 | (sh2._n(rm) << 4) | (v // 2))
        if s.startswith("@"):  # mov.w @Rm,Rn
            return self.emit(0x6001 | (sh2._n(d) << 8) | (sh2._n(s[1:]) << 4))
        raise AssertionError(f"mov.w 꼴 모름: {s},{d}")

    def _extu_w(self, s, d):
        self.emit(0x600D | (sh2._n(d) << 8) | (sh2._n(s) << 4))


def assemble(lines):
    a = QAsm()
    pend = []
    for ln in lines:
        ln = re.sub(r";.*$", "", ln).strip()
        if not ln:
            continue
        if ln.endswith(":"):
            a.label(ln[:-1])
        elif ln.startswith(".long"):
            _, name, val = ln.split(None, 2)
            pend.append((name, int(val, 0)))
        else:
            a.op(ln)
    for name, val in pend:
        a.long(name, val)
    return a.link(0)


# 진입 조합 — 원시 패드 워드 하위 바이트 & 0xF8(눌림 = 0). 게임이 안 읽는 다섯 버튼(Rt X Y Z Lt)만 쓴다.
#   바이트 비트: Rt 0x80 · X 0x40 · Y 0x20 · Z 0x10 · Lt 0x08. 값 = 0xF8 에서 누른 버튼 비트를 뺀 것(부호 있는 즉치로 적는다).
COMBOS = {
    "gold": 0x88,  # X+Y+Z
    "item": 0x90,  # X+Y+Lt
    "warp": 0xC0,  # Y+Z+Lt
    "speed": 0xA0,  # X+Z+Lt — 이동 속도 2배 토글
    "enc": 0x28,  # X+Z+Rt — 몬스터 접촉 조우 끄기 토글
}


def _s8(v):
    return v - 256 if v >= 128 else v


def wrapper_src(c, state):
    """래퍼 — 원 함수를 부른 뒤 조합 엣지에서 액션을 돌린다. r0~r7 만 쓴다(r8~r14 는 호출자 몫)."""
    lines = [
        "dbg_pad:",
        "sts.l pr,@-r15",
        "mov.l r4,@-r15",
        "mov.l @(L_ORIG,pc),r0",
        "jsr @r0",
        "nop",
        "mov.l r0,@-r15  ; 원 함수 반환값",
        "mov.l @(L_PAD,pc),r1",
        "mov.l @r1,r1  ; 패드 구조",
        "mov.b @r1,r2",
        "extu.b r2,r2",
        "mov #2,r3",
        "cmp/eq r3,r2",
        "bt isdig",
        "bra done  ; 디지털 패드가 아니면 무동작",
        "nop",
        "isdig:",
        "mov.w @(2,r1),r0  ; 원시 버튼(눌림 = 0)",
        "and #0xF8,r0",
        "mov r0,r5  ; 지금",
        "mov.l @(L_STATE,pc),r6",
        "mov.b @r6,r7",
        "extu.b r7,r7  ; 지난 프레임",
        "mov.b r5,@r6",
        "cmp/eq r5,r7",
        "bf changed",
        "bra done  ; 바뀐 순간(엣지)만",
        "nop",
        "changed:",
    ]
    for name, v in COMBOS.items():
        if name not in c["combos"]:
            continue
        lines += [
            f"mov #{_s8(v)},r3",
            "extu.b r3,r3",
            "cmp/eq r3,r5",
            f"bf not_{name}",
            f"bra act_{name}",
            "nop",
            f"not_{name}:",
        ]
    lines += ["bra done", "nop"]
    # ── 액션: 소지금·경험치 ──
    lines += [
        "act_gold:",
        "mov.l @(L_GOLD,pc),r1",
        "mov.l @r1,r2",
        "mov.l @(L_AGOLD,pc),r3",
        "add r3,r2",
        "mov.l r2,@r1",
    ]
    for i, _ in enumerate(c["party"]):
        lines += [
            f"mov.l @(L_P{i},pc),r1  ; 레코드 사본 {i}",
            "mov #4,r5  ; 4칸",
            f"p{i}loop:",
            "mov r1,r0",
            "mov.w @(2,r1),r0  ; 레벨 (0 이면 빈 칸)",
            "tst r0,r0",
            f"bt p{i}skip",
            "mov.l @(L_AEXP,pc),r3",
            "mov #0x1C,r0",
            "mov r1,r2",
            "add r0,r2",
            "mov.l @r2,r4",
            "add r3,r4",
            "mov.l r4,@r2",
            f"p{i}skip:",
            "mov #108,r0",
            "add r0,r1",
            "mov #1,r0",
            "sub r0,r5",
            "tst r5,r5",
            f"bf p{i}loop",
        ]
    lines += ["bra done", "nop"]
    # ── 액션: 소지품 채우기(스무 칸을 덮어쓴다) ──
    nb = (len(c.get("bag_items", ())) + 3) // 4
    if "item" in c["combos"]:
        lines += ["act_item:", "mov.l @(L_BAG,pc),r1"]
        for k in range(nb):
            lines += [f"mov.l @(L_B{k},pc),r2", "mov.l r2,@r1", "add #4,r1"]
        lines += ["bra done", "nop"]
    # ── 액션: 워프 — 방문 깃발 전부 세움(워프의 날개 목록은 이 깃발로 짓는다) ──
    if "warp" in c["combos"]:
        lines += [
            "act_warp:",
            "mov.l @(L_FLAGS,pc),r1",
            "mov #50,r5",
            "mov #1,r2",
            "wloop:",
            "mov.b r2,@r1",
            "add #1,r1",
            "add #-1,r5",
            "tst r5,r5",
            "bf wloop",
            "bra done",
            "nop",
        ]
    if "speed" in c["combos"]:
        lines.append("act_speed:")
    for i, (_a, k) in enumerate(c.get("speed_sites", ())):
        lines += [
            f"mov.l @(L_S{i},pc),r1",
            "mov.b @r1,r2",
            f"mov #{k},r3",
            "sub r2,r3",
            "mov.b r3,@r1",
        ]
    if "enc" in c["combos"]:
        lines += ["bra done", "nop", "act_enc:"]
        for i, (_a, k) in enumerate(c["enc_sites"]):
            lines += [
                f"mov.l @(L_E{i},pc),r1",
                "mov.b @r1,r2",
                f"mov #{k},r3",
                "sub r2,r3",
                "mov.b r3,@r1",
            ]
    lines += [
        "done:",
        "mov.l @r15+,r0",
        "mov.l @r15+,r4",
        "lds.l @r15+,pr",
        "rts",
        "nop",
        f".long L_ORIG 0x{c['pad_fn']:08X}",
        f".long L_PAD 0x{c['padptr']:08X}",
        f".long L_STATE 0x{state:08X}",
        f".long L_GOLD 0x{c['gold']:08X}",
        f".long L_AGOLD {c['add_gold']}",
        f".long L_AEXP {c['add_exp']}",
    ]
    if "item" in c["combos"]:
        lines.append(f".long L_BAG 0x{c['bag']:08X}")
    if "warp" in c["combos"]:
        lines.append(f".long L_FLAGS 0x{c['warp_flags']:08X}")
    lines += [f".long L_S{i} 0x{a:08X}" for i, (a, _k) in enumerate(c.get("speed_sites", ()))]
    lines += [f".long L_E{i} 0x{a:08X}" for i, (a, _k) in enumerate(c.get("enc_sites", ()))]
    lines += [f".long L_P{i} 0x{p:08X}" for i, p in enumerate(c["party"])]
    bi = list(c.get("bag_items", ())) + [0] * (nb * 4 - len(c.get("bag_items", ())))
    lines += [
        f".long L_B{k} 0x{bi[4 * k] << 24 | bi[4 * k + 1] << 16 | bi[4 * k + 2] << 8 | bi[4 * k + 3]:08X}"
        for k in range(nb)
    ]
    return lines


def build(fname, d):
    c = CONF[fname]
    for a, _k in c.get("speed_sites", ()):  # 사전조건: 원본 그대로(±8 즉치)
        assert d[a - LOAD_BASE - 1] == 0xE1 and d[a - LOAD_BASE] in (0x08, 0xF8), hex(a)
    for a, _k in c.get("enc_sites", ())[::2]:  # 사전조건: `jsr @r8`(48 0B) — 접촉 조우 디스패치
        assert d[a - LOAD_BASE : a - LOAD_BASE + 2] == b"\x48\x0b", hex(a)
    lo, hi = c["region"]
    state = hi - 4  # 상태 바이트(지난 프레임에 X+Y+Z 였나) — 구역 맨 끝 dword
    blob, body = assemble(wrapper_src(c, state))
    assert len(blob) <= (hi - lo) - 8, f"래퍼 {len(blob)}B 가 구역({hi - lo}B)에 안 든다"
    sig = bytes.fromhex(c["pad_sig"])
    i = d.find(sig)
    assert i >= 0 and d.find(sig, i + 1) < 0 and LOAD_BASE + i == c["pad_fn"], (
        "패드 읽기 함수를 못 찾았다"
    )
    pat = c["pad_fn"].to_bytes(4, "big")
    refs, j = [], 0
    while (k := d.find(pat, j)) >= 0:
        refs.append(k)
        j = k + 1
    refs = [
        k for k in refs if not (lo <= LOAD_BASE + k < hi)
    ]  # 구역 안(개발용 루틴 풀)은 덮일 자리
    return blob, body, refs


BASE_RECORD = "qa_base.json"  # QA 칸에 남기는 「어느 제품 빌드 위에 구웠나」 기록


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def sync_with_product(dst, apply):
    """🔴 QA 이미지는 **늘 지금 제품 빌드의 새 복사본** 위에 굽는다(마스터 11-18 — 낡은 복사본 재사용 사고).

    --apply: 제품 칸(`ED_BUILD_TAG` 를 무시한 현재 브랜치 꼬리표)의 이미지를 통째로 다시 복사한다 → 제품 sha1 을
    `qa_base.json` 에 남긴다. 제품 이미지가 없으면 실패. (검사만) : 기록의 sha1 이 지금 제품과 다르면 실패.
    """
    prod_dir = os.path.join(common.WORK_DIR, "build", build_tag(env="ED_PRODUCT_TAG__UNSET"))
    name = os.path.basename(common.ORIG_BIN)
    prod = os.path.join(prod_dir, name)
    assert os.path.abspath(prod_dir) != os.path.abspath(common.BUILD_DIR), "제품 칸 = QA 칸 — 말이 안 된다"
    if not os.path.exists(prod):
        raise SystemExit(f"제품 빌드가 없다 — 먼저 제품을 굽는다: {prod}")
    sha = _sha1(prod)
    rec = os.path.join(common.BUILD_DIR, BASE_RECORD)
    if apply:
        os.makedirs(common.BUILD_DIR, exist_ok=True)
        shutil.copyfile(prod, dst)
        cue = os.path.splitext(prod)[0] + ".cue"
        if os.path.exists(cue):
            shutil.copyfile(cue, os.path.splitext(dst)[0] + ".cue")
        with open(rec, "w", encoding="utf-8") as f:
            json.dump({"product": os.path.relpath(prod, common.WORK_DIR), "product_sha1": sha}, f)
        print(f"  ↻ 제품 빌드를 새로 복사 — 제품 sha1 {sha}")
    else:
        if not os.path.exists(rec):
            raise SystemExit(f"QA 칸에 {BASE_RECORD} 가 없다 — --apply 로 다시 굽는다")
        old = json.load(open(rec, encoding="utf-8"))["product_sha1"]
        if old != sha:
            raise SystemExit(f"QA 빌드가 낡았다: 기록 {old} ≠ 지금 제품 {sha} — --apply 로 다시 굽는다")
        print(f"  ✓ QA 빌드가 지금 제품 위에 구워졌다 — 제품 sha1 {sha}")
    return sha


def main():
    apply = "--apply" in sys.argv
    if os.environ.get("ED_DEBUG_QA") != "1":
        print("  ℹ ED_DEBUG_QA=1 이 아니라 건너뜀 — 제품 빌드는 이 단계를 안 돈다")
        return
    assert common.BUILD_TAG.startswith("qa-debug"), (
        f"꼬리표가 qa-debug 가 아니다({common.BUILD_TAG}) — 제품 칸을 건드리면 안 된다 (ED_BUILD_TAG=qa-debug)"
    )
    common.verify_source()
    _f, mm = common.open_image()
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    base_sha = sync_with_product(dst, apply)
    files = common.dst_files(dst, mm)
    for fname, c in CONF.items():
        d = common.read_extent(mm, *files[fname])
        d0 = common.extract(fname)
        lo, hi = c["region"]
        blob, body, refs = build(fname, d0)
        print(
            f"{fname}: 래퍼 {len(blob)}B (명령 {body}B) · 구역 0x{lo:08X}~0x{hi:08X} · 참조 {len(refs)}곳"
        )
        for ln in sh2.verify(blob, lo, body):
            print("    ", ln)
        if not apply:
            continue
        lba, fsize = files[fname]
        orig = d0[lo - LOAD_BASE : hi - LOAD_BASE]
        _fd, mmd = common.open_image(dst)
        cur_all = bytes(common.read_extent(mmd, lba, fsize))
        mmd.close()
        _fd.close()
        cur = cur_all[lo - LOAD_BASE : hi - LOAD_BASE]
        assert cur == orig or cur[: len(blob)] == blob, f"{fname}: 구역이 원본도 우리 것도 아니다"
        pad = blob + bytes(hi - lo - 4 - len(blob)) + bytes(4)
        with open(dst, "r+b") as f:
            common.write_at(
                f, lba, fsize, lo - LOAD_BASE, pad, label=f"{fname} QA 디버그 래퍼", expect=cur
            )
            wrapper = lo.to_bytes(4, "big")  # 래퍼 진입 = 구역 맨 앞
            was = c["pad_fn"].to_bytes(4, "big")
            for k in refs:
                got = cur_all[k : k + 4]
                assert got in (was, wrapper), (
                    f"{fname} 참조 0x{LOAD_BASE + k:X}: 원본도 래퍼도 아니다"
                )
                common.write_at(
                    f,
                    lba,
                    fsize,
                    k,
                    wrapper,
                    label=f"{fname} 패드 참조 0x{LOAD_BASE + k:X}",
                    expect=got,
                )
        print(f"   → 넣음 · 참조 {len(refs)}곳")
    if apply:
        print(
            "  ✅ QA 디버그 래퍼 넣음 (X+Y+Z = 소지금·경험치 · X+Y+L = 소지품 · Y+Z+L = 워프 해금 · X+Z+L = 이동 2배 토글)"
        )


if __name__ == "__main__":
    main()
