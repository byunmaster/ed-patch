"""sfc-ed1 스크립트 모델 — 문안 구간을 **항목(item) 열 + 라벨**로 읽고 되쓴다.

재삽입의 첫 게이트는 「원문을 그대로 되쓰면 바이트가 같다」이고, 그 다음이 「옮겨 써도 참조가 산다」다.
그래서 분기 인자를 **라벨**로 풀어 두고 되쓸 때 **오프셋을 다시 계산**한다 — 원문 자리에 되쓴 결과가 원본과
같아야 라벨 모델(어느 코드가 무엇을 기준으로 어디를 가리키나)이 맞다는 뜻이다.

참조 종류(디스패치 표 $02:E248 · `text.py` ARGLEN 주석):
  포인터 표 4벌      addr24            → 항목 시작
  $F9 addr24         절대 호출         → 항목 시작(같은 뱅크가 아닐 수도 있다)
  $FA rel16 / $FC rel16   제어 바이트 기준, 같은 뱅크 안에서 16비트 랩
  $FB / $FD  o0..o4  제어 바이트 기준 8비트 오프셋 5개(파티 인덱스로 고른다)
  $EE addr24         네이티브 코드 — 문안이 아니므로 **절대값 그대로**(옮기지 않는다)
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# ⚠ `text` 를 `common` 보다 먼저 — common 이 `shared/` 를 sys.path 맨 앞에 끼우는데 거기 `shared/text/`
#   패키지가 있어 이름이 겹친다(실측: TEXT_START 가 없다며 죽었다).
import text  # noqa: I001
import common

# 문안 구간 — 포인터 표·코드가 아닌, 항목이 연속하는 자리. 뱅크 $05·$1E 는 코드와 섞여 있어 포인터
# 목표에서 END 까지만 읽는다(`from_pointers`). 본체는 표 끝부터 뱅크 $0B 의 마지막 END 까지 한 덩어리다.
MAIN_REGION = (text.TEXT_START, 0x0BFE76)


@dataclass
class Item:
    off: int  # 파일 오프셋(원문 자리)
    kind: str  # char | dict | subst | ctrl
    code: int
    args: bytes = b""
    targets: list = field(default_factory=list)  # 참조하는 항목의 파일 오프셋들(라벨)
    dead: set = field(
        default_factory=set
    )  # $FB/$FD 의 슬롯 번호 중 항목 시작을 안 가리키는 것 — 원값 유지

    @property
    def size(self) -> int:
        if self.kind == "raw":  # 인코더가 만든 글자 바이트열(코드 없음)
            return len(self.args)
        return 1 + (1 if self.kind == "dict" else len(self.args))


VARIABLE = (
    0xFB,
    0xFD,
)  # 슬롯 오프셋 열 — 저작 시 **필요한 만큼만** 둔다(최대 5). 다음 앵커에서 잘린다.


def parse_region(rom: bytes, start: int, end: int, anchors: set[int] | None = None) -> list[Item]:
    """앵커(포인터 목표·분기 목표)에서 가변 길이 항목을 자르며 파싱한다. 분기 목표는 파싱해야 나오므로
    앵커가 늘지 않을 때까지 되풀이한다(고정점). 실측: $0A:80D0 의 FD 바로 뒤가 포인터 목표라 슬롯이 0개다."""
    anchors = set(anchors or ())
    while True:
        items = _parse(rom, start, end, anchors)
        new = anchors | {t for it in items for t in it.targets if start <= t < end}
        if new == anchors:
            break
        anchors = new
    starts = {it.off for it in items}
    # 남은 슬롯 중 항목 시작을 안 가리키는 것은 「죽은 슬롯」 — 옮길 때 원값을 그대로 둔다
    for it in items:
        if it.code in VARIABLE:
            it.dead = {k for k, t in enumerate(it.targets) if t not in starts}
    return items


def _parse(rom: bytes, start: int, end: int, anchors: set[int]) -> list[Item]:
    items = []
    i = start
    while i < end:
        c = rom[i]
        if c < 0xD0:
            items.append(Item(i, "char", c))
            i += 1
        elif c in text.DICT_TABLES:
            items.append(Item(i, "dict", c, rom[i + 1 : i + 2]))
            i += 2
        elif c < 0xE0:
            items.append(Item(i, "subst", c))
            i += 1
        else:
            k = text.ARGLEN.get(c, 0)
            if c in VARIABLE:
                # 다음 앵커까지만 — 앵커가 인자 한복판에 있으면 거기서 끝난다
                for j in range(1, k + 1):
                    if (i + j) in anchors:
                        k = j - 1
                        break
            it = Item(i, "ctrl", c, rom[i + 1 : i + 1 + k])
            it.targets = resolve_targets(it)
            items.append(it)
            i += 1 + k
    return items


def _rel16(off: int, o16: int) -> int:
    a = common.off2snes(off)
    d = o16 if o16 < 0x8000 else o16 - 0x10000
    return common.snes2off((a & 0xFF0000) | ((a + d) & 0xFFFF))


def resolve_targets(it: Item) -> list[int]:
    c, a = it.code, it.args
    if c == 0xF9:
        addr = a[0] | (a[1] << 8) | (a[2] << 16)
        return (
            [common.snes2off(addr)] if (addr & 0x8000) else [-1]
        )  # -1: 롬 밖(표를 문안으로 읽은 자리)
    if c in (0xFA, 0xFC):
        return [_rel16(it.off, a[0] | (a[1] << 8))]
    if c in (0xFB, 0xFD):
        return [it.off + b for b in a]
    return []


def emit(items: list[Item], place: dict[int, int], strict: bool = True) -> bytes:
    """`place[원문 오프셋] = 새 오프셋` 으로 옮겨 쓴다. 참조 인자는 라벨에서 다시 계산한다."""
    out = bytearray()
    for it in items:
        if it.kind == "raw":
            out += it.args
            continue
        out.append(it.code)
        if it.kind == "dict":
            out += it.args
        elif it.kind == "ctrl" and it.targets:
            new_off = place[it.off]
            c = it.code
            if c == 0xF9:
                t = it.targets[0]
                if t < 0:
                    out += it.args
                else:
                    # 구간 밖(뱅크 $05·$1E 의 코드 쪽 문안)은 안 옮긴다 — 그대로 가리킨다
                    out += common.off2snes(place.get(t, t)).to_bytes(3, "little")
            elif c in (0xFA, 0xFC):
                t = place.get(it.targets[0], it.targets[0])
                a_new, a_t = common.off2snes(new_off), common.off2snes(t)
                if a_new >> 16 != a_t >> 16:
                    if strict:
                        raise AssertionError(
                            f"{c:02X} 가 뱅크를 넘는다: {common.fmt(a_new)}→{common.fmt(a_t)}"
                        )
                    a_t = a_new  # 투영 단계: 자리만 채운다(보고에 실패로 남는다)
                out += ((a_t - a_new) & 0xFFFF).to_bytes(2, "little")
            else:  # FB/FD 8비트 ×n (n ≤ 5)
                for k, t in enumerate(it.targets):
                    if k in it.dead:
                        out.append(it.args[k])
                        continue
                    d = place.get(t, t) - new_off
                    if not (0 <= d < 256):
                        if strict:
                            raise AssertionError(f"{c:02X} 오프셋이 8비트를 넘는다: {d}")
                        d = 0
                    out.append(d)
        else:
            out += it.args
    return bytes(out)


def pointer_anchors(rom: bytes) -> set[int]:
    return {common.snes2off(p) for n in text.MSG_TABLES for p in text.msg_pointers(n, rom)}


def identity_place(items: list[Item]) -> dict[int, int]:
    return {it.off: it.off for it in items}


def check_targets(items: list[Item], start: int, end: int) -> dict:
    """참조 목표가 전부 항목 시작에 떨어지는가 — 라벨 모델의 분모.
    구간 밖 목표(뱅크 $05·$1E 쪽)는 `outside`, $FB/$FD 죽은 슬롯은 `dead` 로 따로 센다."""
    starts = {it.off for it in items}
    ok = bad = outside = dead = 0
    bad_list = []
    for it in items:
        for k, t in enumerate(it.targets):
            if t in starts:
                ok += 1
            elif k in it.dead:
                dead += 1
            elif not (start <= t < end):
                outside += 1
            else:
                bad += 1
                bad_list.append(
                    (
                        common.fmt(common.off2snes(it.off)),
                        f"{it.code:02X}",
                        common.fmt(common.off2snes(t)) if t >= 0 else "?",
                    )
                )
    return {"ok": ok, "outside": outside, "dead": dead, "bad": bad, "bad_list": bad_list[:10]}


def roundtrip(rom: bytes, start: int = MAIN_REGION[0], end: int = MAIN_REGION[1]) -> dict:
    s, e = common.snes2off(start), common.snes2off(end)
    items = parse_region(rom, s, e, pointer_anchors(rom))
    place = identity_place(items)
    # 라벨 목표가 항목 시작이 아니면 place 에 없다 — 그건 곧 실패다
    out = emit(items, place)
    same = out == rom[s:e]
    if not same:
        k = next(i for i in range(min(len(out), e - s)) if out[i] != rom[s + i])
        first_diff = common.fmt(common.off2snes(s + k))
    else:
        first_diff = None
    return {
        "items": len(items),
        "bytes": e - s,
        "identical": same,
        "first_diff": first_diff,
        "targets": check_targets(items, s, e),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--roundtrip", action="store_true", help="본체 구간을 라벨로 풀었다 되써서 바이트 대조"
    )
    a = ap.parse_args()
    if a.roundtrip:
        r = roundtrip(common.rom_bytes())
        t = r.pop("targets")
        print(r, "targets", {k: v for k, v in t.items() if k != "bad_list"})
        for b in t["bad_list"]:
            print("   bad:", b)
        if not r["identical"] or t["bad"]:
            raise SystemExit(1)
        print("왕복 OK — 라벨 모델이 원본을 재현한다")
    else:
        ap.print_help()
