"""폰트 후킹 — 한글 글리프를 **디스크에서 RAM 으로 올려** 화면에 그린다.

## 사슬 셋

    ⑴ 로더   IPL 이 로드된 코드로 뛰기 직전에 끼어들어, 디스크의 글리프 표를 RAM 으로 읽는다
    ⑵ 후킹   글자 그리기 루틴 A 를 가로채 **우리 대역이면** RAM 표에서 32B 를 버퍼에 복사
    ⑶ 표시   원본 블릿 B 가 그 버퍼를 VRAM 세 면에 뿌린다 (손 안 댄다)

## 무엇을 가로채나

루틴 A(`0x8fac`)가 CGROM 에서 16행 × 좌·우 바이트를 읽어 **버퍼 `0x4070`** 에 담고,
블릿이 그걸 VRAM 에 뿌린다. ⇒ **A 의 출력만 바꾸면 화면이 바뀐다.**

🔴 사본이 셋인데 오프닝을 그리는 건 `0x8fac` 하나다(사본마다 `out 0xa1,al` 을 nop 으로 막는
프로브로 갈랐다). 부트 섹터 사본(0x25f)은 화면에 아무 영향이 없다.

## 자리를 어떻게 냈나 — **루틴 안에서 만든다**

트랙(8KB)은 꽉 찼고 이미지의 0 런은 **런타임 변수 영역**이라 코드를 두면 덮인다(실측:
되돌려 보내기만 하는 스텁조차 화면을 죽였다). 부트 섹터로 far 점프도 안 됐다.

이 루틴은 한자/비한자 경로가 「굵게」 블록 말고는 같다. **비한자 경로(48B)를 없애고 한자
경로로 합치면** 그 48바이트가 통째로 빈다 — 지금은 글리프를 안 박으므로 **48B 전부가 코드**다.
⚠ 대가: 가나가 한자 쪽 「굵게」 공식으로 그려진다(화면은 멀쩡하다).

## 규율

🔴 **손인코딩도, 손계산도 하지 않는다.** nasm 으로 어셈블하고 capstone 으로 되읽어 검산한다.
   ⚠ 예전에 `sub si, N` 을 손으로 세다 **한 바이트 틀려** 화면이 어긋났는데, **디스어셈블은
   통과했다**(명령은 맞고 상수가 틀렸다). 상수는 라벨 뺄셈으로 nasm 이 낸다.
⚠ 조건 점프는 **short** 여야 한다 — near Jcc(`0F 8x`)는 386 전용, 이 게임은 286 도 대상이다.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── 사이트 — 디스크마다 **구조가 같은** 글자 그리기 루틴이 있다 ──────────────
# 🔴 event 와 program 의 루틴은 **바이트까지 같은 꼴**이다 — 갈림길 다섯 바이트도, 없앨
#    비한자 경로 48바이트도, `je` 거리(0x3f)도 같다. **버퍼 주소만 다르다**(0x4070 / 0x4076).
#    그래서 같은 패치를 두 디스크에 그대로 건다.
# ⚠ event 는 **오프닝**을, program 은 **인게임 본문**을 그린다 — 둘 다 있어야 게임이 한글이다.
SITES = {
    "event": {
        "hook": 0x8FB6,  # `cmp ax,0x3021` / `jb`
        "kanji": 0x8FBB,
        "kana": 0x8FFA,  # 없애는 비한자 경로(48B) = 우리 코드 자리
        "epilogue": 0x902A,
        "buffer": 0x4070,
        "ipl": 0x13B,  # IPL 이 로드된 코드로 뛰기 직전 — **딱 한 번** 돈다
        "ipl_expect": bytes.fromhex("a07600"),  # `mov al,[0x76]`
        "loader": 0x302,  # 부트 섹터 꼬리의 빈 자리
        # 🔴 표를 **자기 디스크**에서 읽는다 — 부팅한 그 디스크는 드라이브 1에 반드시 있다.
        "font_disk": "event",
        "font_sector": 856,  # 트랙 107 첫 섹터
        "font_base": 0x30,  # event 의 섹터 ID 기저
        "drive": 0x90,  # 드라이브 1
    },
    "program": {
        "hook": 0x7DCE,
        "kanji": 0x7DD3,
        "kana": 0x7E12,
        "epilogue": 0x7E42,
        "buffer": 0x4076,
        "ipl": 0x116,
        "ipl_expect": bytes.fromhex("a07000"),  # `mov al,[0x70]`
        "loader": 0x1C0,
        # ⚠ program 디스크엔 자리가 21.5KB 뿐이라 표를 못 싣는다 → **시나리오(드라이브 2)**
        #   에서 읽는다. 게임이 그 경로에서 「시나리오를 드라이브 2에」를 **요구**하므로
        #   반드시 꽂혀 있다.
        "font_disk": "scenario",
        "font_sector": 1008,  # 트랙 126 첫 섹터
        "font_base": 0x20,  # scenario 의 섹터 ID 기저
        "drive": 0x91,  # 드라이브 2
    },
}
HOOK_EXPECT = bytes.fromhex("3d2130723f")  # 갈림길 — 두 디스크가 같다
KANA_EXPECT = bytes.fromhex("80ec20e6a1")  # 비한자 경로 머리 — 두 디스크가 같다
FETCH_ROOM = 48  # 비한자 경로 길이(두 디스크 다 0x30)

# ── ⑴ 로더 (부트 섹터) ────────────────────────────────────────────────────────
IPL_AT = 0x13B  # IPL 이 `ljmp 0:0x8000` 하기 직전 — **딱 한 번** 돈다
IPL_EXPECT = bytes.fromhex("a07600")  # `mov al,[0x76]` — 로더가 대신 해 준다
LOADER_AT = 0x302  # 부트 섹터 꼬리의 빈 자리(254B). 로더는 **부팅 때만** 돈다
LOADER_ROOM = 0x400 - LOADER_AT

# ── ⑷ 캐시 뱅크 끄기 (program 디스크) ────────────────────────────────────────
# 🔴 게임은 **선형 256KB 위**를 8KB 페이지 풀로 등록해 캐시로 쓴다(status 12절). 우리 표가
#    거기 있으므로 **뱅크 수를 0 으로 만든다** — `and cx,3` 을 `xor cx,cx` 로 바꾸면 바로
#    뒤 `je` 가 항상 걸려 등록을 통째로 건너뛴다.
# ⚠ 대가: 게임의 디스크 캐시가 없어져 로딩이 느려진다. 되돌리기는 이 세 바이트뿐이다.
BANK_AT = 0x5A56  # program 디스크 — `and cx,3`
BANK_EXPECT = bytes.fromhex("83e103")
BANK_NEW = bytes.fromhex("31c990")  # xor cx,cx / nop

# ── 글리프 표가 디스크 어디에 있나 ─────────────────────────────────────────
# 🔴 **시나리오 디스크**(드라이브 2)에 둔다. event 에 두면 **이어하기**(program 으로 부팅)
#    때 표를 못 읽는다 — 그때 드라이브 1 은 program 이다. 시나리오는 **두 경로 모두**
#    드라이브 2 에 꽂혀 있다(게임 안내가 그렇다).
# 🔴 **트랙 경계에 맞춘다**(1008 = 트랙 126 의 첫 섹터) — 로더가 트랙 통째로 읽는다.
# 🔴 **표를 두 디스크에 다 싣는다** — 각 부팅 경로가 **자기가 확실히 읽을 수 있는 드라이브**
#    에서 읽게 하려고다(위 SITES 의 `font_disk`/`drive`). 한쪽에만 두면 그 디스크가 안 꽂힌
#    경로에서 조용히 한글이 안 나온다.
FONT_SEG = 0x4000  # RAM 어디로 올리나 — 캐시 뱅크를 껐으니 여기부터 비어 있다

# ── 대역 배치 — **ku 당 128칸**으로 깐다 ─────────────────────────────────────
# 🔴 94칸(빈틈없이)이 아니라 **128칸**인 이유는 산술을 없애기 위해서다:
#      seg = FONT_SEG + ku_index × 0x100   ·   off = ten_index × 32
#    128×32 = 4,096B = 0x100 파라그래프라 **곱셈도 자릿수 넘김도 없다.**
#    94칸으로 깔면 `mul` 과 17비트 오프셋(64KB 넘김)이 들어가 48바이트에 안 들어간다.
# ⚠ 대가: 25 × 34칸 = 850칸(27,200B)이 빈다. RAM 도 디스크도 그만큼 여유가 있다.
KU_COUNT = 25  # 94 × 25 = 2,350 — 완성형 전부
SLOTS_PER_KU = 128
KU_LO = 0x40  # JIS 상위 바이트의 시작. `昔`(0x404e)이 여기 든다 — 화면에서 바로 보인다
KU_HI = KU_LO + KU_COUNT - 1
TRACKS = -(-(KU_COUNT * SLOTS_PER_KU * 32) // (8 * 1024))  # 통째로 읽을 트랙 수
# 🔴 **+1 트랙은 표 꼬리 자리다** — `patch_josa_hook`·`patch_hud_narrow` 가 여기 얹혀
#    산다(둘 다 FONT_SEG+TABLE_BYTES//16 뒤를 far 세그먼트로 쓴다). 실측(2026-09-27):
#    표 바로 뒤 빈 섹터가 224개 연속인데 위 계산은 208개만 읽어 16개(=1트랙)를 놀렸다 —
#    필드 HUD 8px 표(이름 스파스 인덱스 2,350B + 글리프)가 그 안에 다 안 들어가서 늘렸다.
TRACKS += 1
SOLID = False  # 진단용 — 글리프 대신 통짜로 채운다


def sector_chs(logical: int, base: int) -> tuple[int, int, int]:
    """논리 섹터 → (실린더, 헤드, 섹터 ID). 트랙 = 8섹터.

    ⚠ **섹터 ID 기저가 디스크마다 다르다**(event 0x30 · program 0x10 · scenario 0x20).
    """
    track, rank = divmod(logical, 8)
    return track // 2, track % 2, base + rank


def loader_asm(site: dict) -> str:
    """표를 **트랙 통째로** 읽어 올린다 — 한 트랙(8KB)마다 ES 를 0x200 씩 민다.

    ⚠ 밀어낸 원래 명령(`mov al,[…]`)을 **여기서 대신한다** — 디스크마다 주소가 다르다.
    ⚠ 읽기가 실패해도(시나리오 디스크가 없을 때) **그냥 진행한다** — 한글이 안 나올 뿐
      게임은 돈다. 여기서 멈추면 원본보다 나쁜 패치가 된다.
    """
    c, h, r = sector_chs(site["font_sector"], base=site["font_base"])
    assert r == site["font_base"], "표는 트랙 첫 섹터에서 시작해야 한다"
    drive = site["drive"]
    restore = site["ipl_expect"]
    addr = restore[1] | (restore[2] << 8)
    return f"""
BITS 16
loader:
    pushf                   ; 🔴 **플래그도 되돌린다** — 우리가 밀어낸 `mov al,[…]` 는
                            ;    플래그를 안 건드리는데 우리는 `int`·`dec`·`xor` 로 바꾼다
    push ax                 ; 🔴 **AX 를 살린다** — 밀어낸 명령은 **AL 만** 바꾸고 AH 는
                            ;    그대로 둔다. IPL 은 그 AX 를 들고 로드된 코드로 뛴다
                            ;    (부트 로그에 `AX=4100`). 안 살리면 그쪽이 조용히 어긋난다.
    push es
    push bp
    push bx
    push cx
    push dx
    push si
    mov ax, 0x{FONT_SEG:x}
    mov es, ax
    xor bp, bp              ; ES:BP = 표를 올릴 자리
    mov cx, 0x03{c:02x}          ; CH=3(N=1024) · CL=실린더
    mov dx, 0x{h:02x}{r:02x}          ; DH=헤드 · DL=섹터 ID(트랙 첫 섹터)
    mov si, {TRACKS}              ; 읽을 트랙 수
.track:
    push cx
    push dx
    mov ax, 0x56{drive:02x}       ; AH=0x56 읽기 · AL=DA/UA
    mov bx, 0x2000          ; 8,192B = 한 트랙
    int 0x1b
    pop dx
    pop cx
    mov ax, es
    add ax, 0x200           ; 8KB 만큼 세그먼트를 민다
    mov es, ax
    xor dh, 1               ; 다음 트랙 — 면을 뒤집고
    jnz .same
    inc cl                  ; 면이 0 으로 돌아오면 실린더 하나
.same:
    dec si
    jnz .track
    pop si
    pop dx
    pop cx
    pop bx
    pop bp
    pop es
    pop ax
    popf
    mov al, [0x{addr:x}]          ; ⚠ 우리가 밀어낸 원래 명령 — 여기서 대신한다
    ret
"""


def fetch_asm(site: dict) -> str:
    body = (
        "    mov ax, 0xffff\n    rep stosw"
        if SOLID
        else "    rep movsw               ; DS:SI(표) → ES:DI(버퍼)"
    )
    # ⚠ `org` 는 **플랫 오프셋**을 준다 — 점프가 전부 상대라 실제 적재 위치와 무관하게 맞는다.
    #   (절대값을 쓰는 자리는 `mov si` 뿐인데 그건 우리 표 세그먼트 안이라 상관없다.)
    return f"""
BITS 16
org 0x{site["kana"]:x}
ours:
    cmp ah, 0x{KU_LO:x}
    jb  short back
    cmp ah, 0x{KU_HI:x}
    ja  short back
    push ds
    push ax
    xchg al, ah             ; al = ku · ah = ten
    sub al, 0x{KU_LO:x}
    mov ah, 0               ; ax = ku 색인
    xchg al, ah             ; ax = ku 색인 × 0x100 (= 4KB 파라그래프)
    add ax, 0x{FONT_SEG:x}
    mov ds, ax              ; DS = 그 ku 의 칸
    pop ax
    sub al, 0x21            ; ten → 0부터
    mov ah, 0
    mov cl, 5
    shl ax, cl              ; ×32 = 글리프 한 자
    xchg si, ax             ; ⚠ `mov si,ax`(2B) 대신 1바이트 — 48칸이 딱 맞는다
    mov di, 0x{site["buffer"]:x}
    mov cx, 16
{body}
    pop ds
    jmp short 0x{site["epilogue"]:x}
back:
    jmp short 0x{site["kanji"]:x}
"""


def assemble(src: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        s, o = Path(d) / "p.asm", Path(d) / "p.bin"
        s.write_text(src, encoding="utf-8")
        r = subprocess.run(
            ["nasm", "-f", "bin", str(s), "-o", str(o)], capture_output=True, check=False
        )
        if r.returncode:
            raise SystemExit("🔴 nasm 실패:\n" + r.stderr.decode())
        return o.read_bytes()


def _no_near_jcc(blob: bytes, at: int) -> None:
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs

    for i in Cs(CS_ARCH_X86, CS_MODE_16).disasm(blob, at):
        if i.bytes[:1] == b"\x0f":
            raise SystemExit(f"🔴 {i.address:#07x} 386 전용 near Jcc — short 로 잡아라")


def build_patch(disk: str) -> list[tuple[int, bytes, bytes]]:
    """→ [(플랫 오프셋, 원본이어야 할 바이트, 새 바이트)]. `disk` 는 event/program."""
    site = SITES[disk]
    room = 0x400 - site["loader"]

    loader = assemble(loader_asm(site))
    _no_near_jcc(loader, site["loader"])
    if len(loader) > room:
        raise SystemExit(f"🔴 {disk} 로더가 자리를 넘는다: {len(loader)} > {room}")

    fetch = assemble(fetch_asm(site))
    _no_near_jcc(fetch, site["kana"])
    if len(fetch) > FETCH_ROOM:
        raise SystemExit(f"🔴 {disk} 후킹 코드가 자리를 넘는다: {len(fetch)} > {FETCH_ROOM}")

    # IPL → 로더 호출 (원래 `mov al,[…]` 를 밀어낸다 — 로더가 대신 한다)
    rel = site["loader"] - (site["ipl"] + 3)
    call = bytes([0xE8, rel & 0xFF, (rel >> 8) & 0xFF])

    # 갈림길 → 우리 코드로 (near jmp 3B + nop 둘)
    rel = site["kana"] - (site["hook"] + 3)
    hook = bytes([0xE9, rel & 0xFF, (rel >> 8) & 0xFF, 0x90, 0x90])

    out = [
        (site["ipl"], site["ipl_expect"], call),
        (site["loader"], bytes(len(loader)), loader),
        (site["hook"], HOOK_EXPECT, hook),
        (site["kana"], KANA_EXPECT, fetch + bytes([0x90]) * (FETCH_ROOM - len(fetch))),
    ]
    if disk == "program":
        out += [(BANK_AT, BANK_EXPECT, BANK_NEW)]  # ⑷ 캐시 뱅크 끄기
    return out


def ku128_table() -> bytes:
    """디스크에 깔 표 — **ku 당 128칸**, 앞 94칸만 글자. 나머지는 0."""
    import font as _font

    syl, table = _font.build()
    out = bytearray()
    for k in range(KU_COUNT):
        for t in range(SLOTS_PER_KU):
            i = k * 94 + t
            if t < 94 and i < len(syl):
                out += table[i * _font.STRIDE : (i + 1) * _font.STRIDE]
            else:
                out += b"\x00" * _font.STRIDE
    return bytes(out)


if __name__ == "__main__":
    print(f"표 {KU_COUNT * SLOTS_PER_KU * 32:,}B · {TRACKS}트랙 · RAM {FONT_SEG:#06x}")
    print(f"대역 ku {KU_LO:#04x}~{KU_HI:#04x} (완성형 2,350자)")
    for disk, site in SITES.items():
        c, h, r = sector_chs(site["font_sector"], base=site["font_base"])
        print(
            f"== {disk}  표는 {site['font_disk']} C{c} H{h} R{r:#04x} · 드라이브 "
            f"{'1' if site['drive'] == 0x90 else '2'}"
        )
        for off, exp, new in build_patch(disk):
            print(f"    {off:#07x}  {len(new):3d}B  ← {exp[:6].hex(' ')}…")
