"""BRAM 세이브(2KB) — 항목 파싱 · 비트 직렬화 풀기/묶기 · **씬 점프 세이브 굽기**.

게임 상태는 뱅크 0x74 `$C000~$C3FF` 에 살고, 세이브는 그걸 **비트 단위로** 직렬화한 601B 다
(디스크립터 표 = 본 프로그램 뱅크 0x69 `$7E44`, 항목 `op lo hi` — op 하위 3비트+1 = 비트 폭,
`18 stride cnt … 20` = 반복, `08` = 로드 때 0, `11`/`14` = −1 저장/+1 복원, `80~` = 끝).
게임이 BRAM 에 쓰는 자리는 `$2669`(BM_WRITE, 601B) 이고 여기서 그 묶음을 흉내 낸다.

**씬 점프** — 맵 전환 루틴(`$6558`)이 씬 블록 안 29B 디스크립터를 `$C201~3` + `$C000~$C019`
로 복사한다(장 `$C1B6`·지역 `$C010`·씬 `$C009`·좌표·스크롤 창·스프라이트 8). 그 디스크립터는
**어느 블록의 `JMP $65AD` 앞 `LDA #lo/STA $FA/LDA #hi/STA $FB`** 가 가리킨다. 그러니 목표 씬으로
들어가는 워프 디스크립터를 컨테이너에서 찾아 세이브에 박으면 **Continue 로 그 씬에 선다.**
⚠ `$C01A`(엔티티 표 초기화 플래그)는 0 이어야 블록의 엔티티 표를 새로 깐다 — 1 이면 옛 맵의
표가 남아 엔딩 블록은 `$C208` bit7 로 「이미 끝났다」고 보고 完 카드로 직행한다(2026-09-23 실측).

    python3 tools/savefile.py dump <sav>                      항목·핵심 상태 출력
    python3 tools/savefile.py warps 224                       씬 224 로 들어가는 디스크립터 목록
    python3 tools/savefile.py goto <sav> 224 --out <sav2> [--slot 3] [--boost] [--party] [--set C155=38 --set C319=1F] [--pick N]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

DESC_BANK = 0x69  # 디스크립터 표가 든 뱅크 (rel 38~41)
DESC_OFF = 0x1E44  # 뱅크 안 오프셋 ($7E44)
SAVE_LEN = 601
BRAM_HDR = 0x10
ENTRY_HDR = 16  # size(2) chk(2) name(12)
DESC_LEN = 29  # 워프 디스크립터: 3B($C201~3) + 26B($C000~$C019)

# 상태 변수 — status.md 3절·이 파일 머리
CHAPTER, REGION, SCENE, ENT_INIT = 0xC1B6, 0xC010, 0xC009, 0xC01A


def layout(track: bytes | None = None) -> list[tuple[int, int, str]]:
    """디스크립터 표 → [(주소, 비트, 종류)] 평탄화. 종류: v 값 · z 로드때0 · m1 −1저장."""
    if track is None:
        track = common.track_data()
    rel = 34 + (DESC_BANK - 0x68) * 4
    tb = track[rel * common.USER + DESC_OFF : (rel + 4) * common.USER]
    out = []

    def run(i: int, base: int) -> int:
        while True:
            b = tb[i]
            if b & 0x80:
                return i + 1
            x = (b >> 2) & 0xFE
            if x == 6:  # 반복: stride, count, 본문…, 0x20
                stride, cnt = tb[i + 1], tb[i + 2]
                j = i + 3
                for k in range(cnt):
                    j = run(i + 3, base + k * stride)
                i = j
                continue
            if x == 8:
                return i + 1
            addr = (tb[i + 1] | tb[i + 2] << 8) + base
            out.append((addr, (b & 7) + 1, {0: "v", 2: "z", 4: "m1"}.get(x, f"x{x}")))
            i += 3

    run(0, 0)
    return out


def decode(data: bytes, ents=None) -> dict[int, int]:
    ents = ents or layout()
    data = data + b"\0" * 8
    pos, vals = 0, {}
    for a, bits, kind in ents:
        if kind == "z":
            vals[a] = 0
            continue
        v = 0
        for _ in range(bits):
            v = (v << 1) | ((data[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        vals[a] = v + 1 if kind == "m1" else v
    return vals


def encode(vals: dict[int, int], ents=None) -> bytes:
    ents = ents or layout()
    bits = []
    for a, n, kind in ents:
        if kind == "z":
            continue
        v = vals[a] - 1 if kind == "m1" else vals[a]
        if not 0 <= v < (1 << n):
            raise ValueError(f"${a:04X}={v} 가 {n}비트를 넘는다")
        bits += [(v >> (n - 1 - i)) & 1 for i in range(n)]
    out = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        out[i >> 3] |= bit << (7 - (i & 7))
    return bytes(out[:SAVE_LEN]).ljust(SAVE_LEN, b"\0")


# ── BRAM ──────────────────────────────────────────────────────────────────────
def entries(bram: bytes) -> list[tuple[int, int]]:
    out, i = [], BRAM_HDR
    while i + ENTRY_HDR <= len(bram):
        sz = bram[i] | bram[i + 1] << 8
        if sz == 0 or i + sz > len(bram):
            break
        out.append((i, sz))
        i += sz
    return out


def checksum(entry: bytes) -> int:
    """BIOS 규약 — 이름+본문 바이트 합의 2의 보수(실측: 마스터 세이브 두 슬롯 일치)."""
    return (-sum(entry[4:])) & 0xFFFF


def set_entry(bram: bytes, slot: int, vals: dict[int, int], template: bytes) -> bytes:
    """슬롯(1~3)에 항목을 놓는다 — 없으면 template(다른 슬롯 항목) 모양으로 새로 만든다."""
    ents = entries(bram)
    e = bytearray(template)
    e[6:16] = b"DS-EIYU1-%d" % slot
    e[ENTRY_HDR : ENTRY_HDR + SAVE_LEN] = encode(vals)
    c = checksum(e)
    e[2], e[3] = c & 0xFF, c >> 8
    nb = bytearray(bram)
    if slot - 1 < len(ents):
        off, sz = ents[slot - 1]
        assert sz == len(e), (sz, len(e))
        nb[off : off + sz] = e
    else:
        off = ents[-1][0] + ents[-1][1] if ents else BRAM_HDR
        assert slot - 1 == len(ents), "슬롯은 이어서만 만든다"
        nb[off : off + len(e)] = e
        # 헤더 +6: 첫 빈 바이트($8000 기준) — 실측: 항목 둘이면 $84E2, 게임이 슬롯 3을 쓰면 $874B.
        # (+4 는 BRAM 끝 $8800 으로 고정.) 안 올리면 다음 세이브가 슬롯 3 위에 겹쳐 앉는다.
        end = 0x8000 + off + len(e)
        nb[6], nb[7] = end & 0xFF, end >> 8
    return bytes(nb)


# ── 워프 디스크립터 ───────────────────────────────────────────────────────────
PTR = re.compile(rb"\xa9(.)\x85\xfa\xa9(.)\x85\xfb", re.DOTALL)


def find_warps(scene: int, blocks=None) -> list[dict]:
    """씬 `scene` 으로 들어가는 워프 디스크립터 전부 — 컨테이너 전 블록의 `$FA` 포인터를 따라간다."""
    if blocks is None:
        import containers

        blocks = [(c["rel"], b["id"], b["data"]) for c in containers.scan() for b in c["blocks"]]
    out, seen = [], set()
    for rel, bid, data in blocks:
        for m in PTR.finditer(data):
            off = ((m.group(2)[0] << 8) | m.group(1)[0]) - 0xA000
            if not 0 <= off <= len(data) - DESC_LEN:
                continue
            d = data[off : off + DESC_LEN]
            if d[3 + 9] != scene or d in seen:
                continue
            seen.add(d)
            out.append({"from": (rel, bid), "off": off, "desc": d, "xy": (d[3], d[4])})
    return out


def apply_desc(vals: dict[int, int], desc: bytes) -> None:
    """맵 전환 루틴 `$6558` 과 같은 복사 — 3B → $C201~3, 26B → $C000~$C019. 7비트 칸은 0x7F 로."""
    for i in range(3):
        vals[0xC201 + i] = desc[i]
    for i in range(26):
        vals[0xC000 + i] = desc[3 + i]
    for a in range(0xC012, 0xC01A):  # 스프라이트 8칸은 7비트 — 빈 칸 0xFF 는 0x7F 로 저장된다
        vals[a] &= 0x7F
    vals[ENT_INIT] = 0


def boost(vals: dict[int, int], rec: int = 0xC300) -> None:
    """캐릭터 레코드(64B) 하나를 Lv99·HP/MP 9999·능력치 120 으로 — 확인용. 장비는 그대로.

    🔴 능력치는 **127 이하**로 둔다(2026-09-23 실측). 255 로 두면 부호 있는 계산에서 음수가 돼
    아그니자가 먼저 움직여 오비스4(즉사)로 둘이 쓰러졌고, 100 으로 두니 세리오스가 먼저
    쳐서(61908) 한 방에 끝났다."""
    vals[rec + 0x03] = 99
    for off in (0x04, 0x06, 0x08, 0x0A):
        vals[rec + off], vals[rec + off + 1] = 0x0F, 0x27
    for off in range(0x10, 0x19):
        vals[rec + off] = 120


def set_values(vals: dict[int, int], specs: list[str]) -> None:
    """`--set C155=38 --set C31F=1F` — 주소·값 16진. 마스터 지적(09-23 밤)으로 생긴 칸:
    `C155` bit3·4·5 = 종장 열쇠·문 둘(맵 로드 때 다시 연다) · `C319` = 세리오스 무기 칸(장비 넷 = `$C319~$C31C`, `$C31F~` 가 아니다 — 09-23 실측)
    (光のつるぎ = 31) · `C340/C380/C3C0` bit7 을 내리면 동료 셋이 파티에 든다."""
    for spec in specs:
        a, v = spec.split("=")
        vals[int(a, 16)] = int(v, 16)


# 최종 파티·장비 (마스터 확정 2026-09-23 밤: 「최종 파티는 로가 아니라 소니아」·「넷 다 좋은 갑옷·방패」)
SONIA_TEMPLATE = (
    1364,
    63,
    0x2F4,
)  # 컨테이너 rel · 블록 id · 블록 안 오프셋 — 소니아 합류 이벤트가 베끼는 64B 레코드
BEST_GEAR = {  # 레코드 → (무기, 갑옷, 방패, 장신구) — 아이템 id(work/derived/sys/items.json)
    0xC300: (
        31,
        49,
        63,
        73,
    ),  # 세리오스: 光のつるぎ · バトル・スーツ · いにしえのたて · テュトの指輪
    0xC340: (25, 49, 63, 73),  # 류난: 戦士のつるぎ
    0xC380: (28, 49, 63, 73),  # 소니아: ダイヤの杖
    0xC3C0: (25, 49, 63, 73),  # 게일
}


def put_sonia(vals: dict[int, int]) -> None:
    """레코드 2(로) 자리에 소니아 — 씬 블록 안 템플릿 64B 를 그대로 놓고 이름만 우리 글리프로."""
    import containers
    import font

    rel, bid, off = SONIA_TEMPLATE
    blk = next(
        b["data"]
        for c in containers.scan()
        if c["rel"] == rel
        for b in c["blocks"]
        if b["id"] == bid
    )
    for i, x in enumerate(blk[off : off + 64]):
        if 0xC380 + i in vals:
            vals[0xC380 + i] = x
    tbl, _ = font.build_table(font._order_canon())
    name = font.encode("소니아", tbl) + b"\x06"
    for i in range(9):
        vals[0xC3B0 + i] = name[i] if i < len(name) else 0


def put_gear(vals: dict[int, int]) -> None:
    """장비 칸 `$C319~$C31C`(무기·갑옷·방패·장신구)에 BEST_GEAR."""
    for rec, gear in BEST_GEAR.items():
        for i, item in enumerate(gear):
            vals[rec + 0x19 + i] = item


def chapter_of(rel: int, track: bytes | None = None) -> int:
    """컨테이너 rel → 장(0~5): 뱅크 0x6A `$6BE8` 장 포인터 + `$6BF4` 3B 표(rec = rel − 34).

    디스크립터엔 장이 없어 따로 정한다(status.md 3절의 장별 지역 표를 거꾸로 탄다)."""
    if track is None:
        track = common.track_data()
    b = track[42 * common.USER : 46 * common.USER]
    ptrs = [b[0xBE8 + 2 * i] | b[0xBE8 + 2 * i + 1] << 8 for i in range(6)] + [0x6C51 + 13 * 3]
    for ch in range(6):
        for p in range(ptrs[ch], ptrs[ch + 1], 3):
            o = p - 0x6000
            if (b[o] | b[o + 1] << 8) + 34 == rel:
                return ch
    raise KeyError(rel)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("sav")
    w = sub.add_parser("warps")
    w.add_argument("scene", type=int)
    g = sub.add_parser("goto")
    g.add_argument("sav")
    g.add_argument("scene", type=int)
    g.add_argument("--out", required=True)
    g.add_argument("--slot", type=int, default=3)
    g.add_argument("--src", type=int, default=1, help="상태를 베낄 슬롯(파티·플래그)")
    g.add_argument("--pick", type=int, default=0, help="warps 목록에서 고를 번호")
    g.add_argument("--boost", action="store_true", help="파티 넷을 Lv99·HP9999·능력치 120 으로")
    g.add_argument("--party", action="store_true", help="동료 셋(레코드 1~3)을 파티에 넣는다")
    g.add_argument(
        "--set", action="append", default=[], metavar="ADDR=VAL", help="상태 바이트 직접(16진)"
    )
    g.add_argument("--sonia", action="store_true", help="레코드 2(로) 를 소니아로")
    g.add_argument("--gear", action="store_true", help="넷 다 최상 장비(BEST_GEAR)")
    g.add_argument(
        "--keep-desc",
        action="store_true",
        help="워프 디스크립터를 안 바꾼다(자리 그대로, 파티·장비만)",
    )
    a = ap.parse_args()

    if a.cmd == "dump":
        bram = Path(a.sav).read_bytes()
        for n, (off, sz) in enumerate(entries(bram), 1):
            e = bram[off : off + sz]
            v = decode(e[ENTRY_HDR : ENTRY_HDR + SAVE_LEN])
            ok = "✓" if checksum(e) == (e[2] | e[3] << 8) else "✗"
            print(
                f"슬롯{n} @{off:04x} {e[6:16].decode()} chk{ok} 장{v[CHAPTER] + 1} 지역{v[REGION]} "
                f"씬{v[SCENE]} xy=({v[0xC000]},{v[0xC001]}) Lv{v[0xC303]} HP{v[0xC304] | v[0xC305] << 8}"
            )
        return
    if a.cmd == "warps":
        for i, wp in enumerate(find_warps(a.scene)):
            print(
                i,
                f"rel{wp['from'][0]} blk{wp['from'][1]} @{wp['off']:04x} xy={wp['xy']} {wp['desc'].hex(' ')}",
            )
        return
    bram = Path(a.sav).read_bytes()
    ents = entries(bram)
    src_off, src_sz = ents[a.src - 1]
    tmpl = bram[src_off : src_off + src_sz]
    vals = decode(tmpl[ENTRY_HDR : ENTRY_HDR + SAVE_LEN])
    warps = find_warps(a.scene)
    if not warps:
        raise SystemExit(f"씬 {a.scene} 로 들어가는 워프가 없다")
    wp = warps[a.pick]
    if not a.keep_desc:
        apply_desc(vals, wp["desc"])
        vals[CHAPTER] = chapter_of(wp["from"][0])
    if a.sonia:
        put_sonia(vals)
    if a.party:
        for rec in (0xC340, 0xC380, 0xC3C0):
            vals[rec] &= 0x7F
    if a.boost:
        for rec in (0xC300, 0xC340, 0xC380, 0xC3C0):
            boost(vals, rec)
    if a.gear:
        put_gear(vals)
    set_values(vals, a.set)
    out = set_entry(bram, a.slot, vals, tmpl)
    Path(a.out).write_bytes(out)
    print(
        f"슬롯{a.slot} ← 씬 {a.scene} (rel{wp['from'][0]} blk{wp['from'][1]} 의 워프, xy={wp['xy']}, "
        f"장{vals[CHAPTER] + 1} 지역{vals[REGION]}){' +party' if a.party else ''}{' +boost' if a.boost else ''}{' ' + ' '.join(a.set) if a.set else ''} → {a.out}"
    )


if __name__ == "__main__":
    main()
