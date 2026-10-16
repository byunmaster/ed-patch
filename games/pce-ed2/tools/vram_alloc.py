"""대관식 자막(ending_sub) 의 VRAM 블록 배정 — 에뮬 세이브스테이트(5초 간격)에서 장면마다 **쓰이지 않는** 128워드 블록을 골라 쪽마다 적는다.

왜: 패키지 38 의 장면 그림은 VRAM 을 거의 다 쓰고(BAT 64×64 + 그림 타일 + 다음 장면 미리 올림 + 스프라이트 패턴) **비는 곳이 장면마다 다르다**
(에뮬 실측 10-14: 고정 구간 0x4C00·0x7800·0x3000 은 장면에 따라 그림·캐릭터 패턴과 겹쳐 깨졌다). 그래서 쪽마다 비는 블록을 따로 적는다.
방법: 세이브스테이트의 VRAM 에서 BAT(64×64)가 가리키는 타일 + SAT(우리 몫 앞 16 슬롯 제외)가 가리키는 스프라이트 패턴을 「쓰는 곳」으로 치고,
쪽이 보이는 동안(올리기 ~ 지우기) 앞뒤 스냅샷의 합집합에서 안 쓰는 8타일(=128워드, 32×16 스프라이트 하나) 정렬 블록을 쓴다.
스냅샷 얻는 법: **자막을 안 올리는** 시험 빌드(`ED_SUB_PROBE=1` — 카운터만 돈다)를 에뮬로 패키지 38 직행으로 돌려(자막 빌드의 스냅샷은 글자가 VRAM 을 오염시킨다) `save_state`(emucap) 를 5초마다(300프레임) 떠 `snap/*.mc` 로 둔다. V_FR(`$22E0`)이 시각이다.
출력: `data/ending_vram.json` — 쪽마다 블록 워드 주소 목록. 자막 문안·시각이 바뀌면 다시 돌린다(쪽 수가 같고 구간이 비슷하면 그대로 써도 된다).
"""

import glob
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import ending_sub as e

SPR_PAD = 24  # 게임 스프라이트 패턴 타일 둘레 여유(타일 수) — 기본값
SPR_SPAN_LO, SPR_SPAN_HI = 0x80, 0x40  # 스프라이트 패턴 범위 위·아래 여유(타일)
LEFT_PAD = 64  # 내용 있는 남은 블록은 스프라이트 패턴에서 이만큼(타일) 떨어져야 한다
PADS = (24, 16, 8, 0)  # 쪽마다 큰 것부터 시도
OUT = common.GAME_DIR / "data" / "ending_vram.json"
PAT = bytes(
    [0xE6, 0x2F, 0x07, 0x38, 0xAD, 0xE2, 0x22]
)  # 트램펄린 — 시스템 RAM 안 위치로 `$22E0`(V_FR)을 찾는다


def vram_of(b: bytes) -> bytes:
    i = b.find(b"\x04VRAM\x00\x00\x01\x00")
    return b[i + 9 : i + 9 + 65536]


def used_tiles(v: bytes, skip_slots: int):
    """→ (참조 마스크[BAT·SAT 가 가리키는 타일], BAT 만 가리키는 마스크, 내용 있는 마스크)"""
    words = struct.unpack("<32768H", v)
    m = bytearray(0x800)
    bat = bytearray(0x800)
    sp = bytearray(0x800)  # 게임 스프라이트(SAT)가 가리키는 패턴 타일만 — 애니메이션 프레임은 이웃에 있어 여유를 둔다
    for w in words[:4096]:  # BAT 64×64
        m[w & 0x7FF] = 1
        bat[w & 0x7FF] = 1
    for s in range(64):
        y, x, pat, attr = words[0x7F00 + 4 * s : 0x7F00 + 4 * s + 4]
        if s < skip_slots or (y == 0 and x == 0 and pat == 0 and attr == 0):
            continue
        a = (pat & 0x7FE) << 5
        n = 64 * (2 if (attr >> 8) & 1 else 1) * (1 << {0: 0, 1: 1, 3: 2}.get((attr >> 12) & 3, 0))
        for t in range(a // 16, min((a + n + 15) // 16, 0x800)):
            m[t] = 1
            sp[t] = 1
    nz = bytearray(0x800)
    for t in range(0x7F0):
        if any(v[t * 32 : t * 32 + 32]):
            nz[t] = 1
    for t in range(0x100):  # BAT 자리
        m[t] = 1
    for t in range(0x7F0, 0x800):  # SAT 자리
        m[t] = 1
    return m, bat, nz, sp


def load(snapdir: str):
    out = []
    for p in glob.glob(f"{snapdir}/*.mc"):
        b = Path(p).read_bytes()
        base = b.find(PAT) - 0x2C0
        t = struct.unpack("<H", b[base + 0x2E0 : base + 0x2E2])[0] / e.FPS
        v = vram_of(b)
        m, bat, nz, sp = used_tiles(v, 16)
        out.append((t, m, bat, nz, v, sp))
    out.sort(key=lambda x: x[0])
    return [(t, bytes(m), bytes(bat), bytes(nz), v, bytes(sp)) for t, m, bat, nz, v, sp in out]


def stale_ok(snaps, win, tile):
    """내용이 있는데 참조되지 않는 타일이 「이전 장면 그림의 잔재」(밟아도 되는 것)인가 — 창 앞쪽 스냅샷에서 **BAT 가 가리켰고 내용이 지금과 같고**, 그 뒤 창 끝까지 SAT(스프라이트)가 가리킨 적이 없다.
    그렇지 않은 내용 있는 타일(처음부터 BAT 에 없던 것)은 스프라이트 프레임 자료다 — 입·눈 애니메이션 프레임은 5초 스냅샷에 SAT 로 안 잡혀도 VRAM 에 올라 있다(에뮬 실측 10-14: 마스터 「아트라스 입 움직일때 깨짐」, 입 프레임 자리 0x4C00 을 「남은 블록」으로 잡아 글자가 입에 찍혔다).
    전체 이력의 BAT 참조로 보면 다른 장면이 쓴 흔적까지 잔재로 오인한다(옛 규칙의 구멍) — 시간순으로 본다."""
    t_first = win[0][0]
    now = win[0][4][tile * 32 : tile * 32 + 32]
    seen_bat = False
    for t, _m, bat, _nz, v, sp in snaps:
        if t > win[-1][0]:
            break
        if t < t_first:
            if bat[tile] and v[tile * 32 : tile * 32 + 32] == now:
                seen_bat = True
            elif bat[tile]:
                seen_bat = False  # 그 뒤 내용이 바뀌었다
        if seen_bat and sp[tile]:
            return False
    return seen_bat


def dead_forward(snaps, win, tile):
    """내용 있는 타일이 창 뒤로 **다시 안 쓰이나** — 창 끝 이후 스냅샷에서 내용이 그대로인 채 BAT·SAT 가 가리키면 살아 있는 자료(미리 올려 둔 다음 장면 그림·프레임)라 밟으면 나중에 깨진다.
    내용이 바뀌면(게임이 새로 올림) 그 뒤는 상관없다. 옛 「잔재」 판정(`stale_ok`, 앞쪽만 봄)이 놓친 구멍 — 에뮬 실측 10-14: 쪽 17 이 밟은 0x4C00 은 다음 장면 입 프레임이었다."""
    now = win[-1][4][tile * 32 : tile * 32 + 32]
    for t, _m, bat, _nz, v, sp in snaps:
        if t <= win[-1][0]:
            continue
        if v[tile * 32 : tile * 32 + 32] != now:
            return True
        if bat[tile] or sp[tile]:
            return False
    return True


def free_blocks(snaps, t0, t1, margin, pad=SPR_PAD, strict=2):
    """쓸 수 있는 8타일 블록 → [(타일 번호, 지울지)] — 창(올리기~지우기 ± margin) 안의 **모든** 스냅샷에서
    ① BAT·SAT 가 가리키지 않고 ② 내용이 안 바뀌고(게임이 그 사이 미리 올리면 바뀐다) ③ 내용이 있으면 이전 장면 그림의 잔재(`stale_ok`)인 블록.
    내용이 전부 0 이면 「0 블록」(숨길 때 0 으로 되돌린다 — 장면은 안 쓰는 VRAM 이 0 이라고 믿는다), 아니면 「남은 블록」(**지우지 않는다**:
    0 으로 밀면 그 사이 게임이 올린 그림이 사라진다. 에뮬 실측 10-14: 장면 후반 아래쪽에 검은 띠).
    쓰는 타일에서 먼 것부터(애니메이션 프레임이 이웃에 있는 경우가 많다: 에뮬 실측 10-14, 가까이 두니 눈·입 프레임을 밟았다)."""
    win = [s for s in snaps if t0 - margin <= s[0] <= t1 + margin]
    if not win:  # 창 안에 스냅샷이 없으면 가장 가까운 하나만 본다(margin 0 — 가장 불확실한 마지막 수단)
        win = [min(snaps, key=lambda s: abs(s[0] - (t0 + t1) / 2))]
    u = bytearray(0x800)
    for _t, m, _bat, _nz, _v, _sp in win:
        for i in range(0x800):
            if m[i]:
                u[i] = 1
    # 게임 스프라이트 패턴 둘레 ±pad 타일도 쓰지 않는다(애니메이션 프레임은 쓰는 패턴 이웃에 올라온다)
    zone = bytearray(0x800)
    for _t, _m, _bat, _nz, _v, sp in snaps:  # 쪽 창 밖 스냅샷도 본다 — 같은 장면의 프레임 자리는 창 밖에서도 같다
        if pad and win[0][0] - 15 <= _t <= win[-1][0] + 15:
            for i in range(0x800):
                if sp[i]:
                    for j in range(max(0, i - pad), min(0x800, i + pad + 1)):
                        zone[j] = 1
    for i in range(0x800):
        if zone[i]:
            u[i] = 1
    sp_any = bytearray(0x800)  # 쪽 창 ±15초 안 스냅샷에서 게임 스프라이트가 가리킨 모든 타일
    for _t, _m, _bat, _nz, _v, sp in snaps:
        if win[0][0] - 15 <= _t <= win[-1][0] + 15:
            for i in range(0x800):
                if sp[i]:
                    sp_any[i] = 1
    sp_idx = [i for i in range(0x800) if sp_any[i]]
    sp_lo, sp_hi = (min(sp_idx), max(sp_idx)) if sp_idx else (None, None)
    used = [i for i in range(0x800) if u[i]]

    def dist(b):
        return min(min(abs(b - i), abs(b + 7 - i)) for i in used) if used else 9999

    out = []
    for b in range(0x100, 0x7E0, 8):  # 0x7E00~ 는 쓰지 않는다 — 게임 SAT(0x7F00) 이웃·합성 SAT 자리(옛 배정이 0x7E80 을 써서 아트라스 턱 스프라이트가 깜빡였을 가능성, 마스터 10-15)
        if any(u[b : b + 8]):
            continue
        ch = [w[4][b * 32 : (b + 8) * 32] for w in win]
        if any(c != ch[0] for c in ch):
            continue
        if strict == 2 and any(ch[0]) and not all(
            stale_ok(snaps, win, t) for t in range(b, b + 8) if any(ch[0][(t - b) * 32 : (t - b) * 32 + 32])
        ):
            continue
        risk = 0
        if any(ch[0]):  # 내용 있는 「남은 블록」 — 엄격할수록 위험한 것을 거른다. 마지막 수단(0)은 거르지 않고 위험이 낮은 것부터 고른다
            nzt = [t for t in range(b, b + 8) if any(ch[0][(t - b) * 32 : (t - b) * 32 + 32])]
            alive = not all(dead_forward(snaps, win, t) for t in nzt)  # 창 뒤에 다시 쓰이는 자료(미리 올린 다음 장면·프레임)
            near = any(sp_any[t] for t in range(max(0, b - LEFT_PAD), min(0x800, b + 8 + LEFT_PAD)))  # 스프라이트 패턴 둘레(입 프레임 자리)
            span = sp_lo is not None and sp_lo - SPR_SPAN_LO <= b + 7 and b <= sp_hi + SPR_SPAN_HI  # 장면 스프라이트 범위 안
            risk = 4 * alive + 2 * span + near
            if strict >= 1 and risk:
                continue
        out.append((b, any(ch[0]), risk))
    zero = sorted((b for b, nz, _r in out if not nz), key=lambda b: (-dist(b), b))
    left = sorted(((b, r) for b, nz, r in out if nz), key=lambda x: (x[1], -dist(x[0]), x[0]))
    left = [b for b, _r in left]
    return [(b, True) for b in zero] + [(b, False) for b in left]


def main(snapdir: str) -> None:
    snaps = load(snapdir)
    pages = e.build_pages(None, False)
    alloc = []
    for i, p in enumerate(pages):
        need = (len(p["cells"]) + 1) // 2
        v0 = (
            e.f(p["t0"]) / e.FPS - e.UPLOAD_LEAD / e.FPS - 0.2
        )  # 우리 카운터(V_FR) 시각 — 오디오 시각 + AUDIO_LAG
        v1 = e.f(p["t1"]) / e.FPS + 0.4
        tier = 2
        fb = []
        for strict in (2, 1, 0):  # 엄격한 규칙(잔재만)으로 모자란 쪽만 옛 규칙으로 — 그런 쪽은 「위험」으로 적는다
            for margin in (30.0, 20.0, 12.0, 7.5, 5.0, 2.5, 0.0):  # 스냅샷이 2.5초 간격이라 넓은 창(앞뒤 30·20·12초)부터 — 그 안에서 한 번도 안 바뀐 블록만 먼저 쓴다(10-15: 애니메이션 프레임 자리에 걸려 깨졌다)  # 5초 스냅샷 사이에서 일어난 일은 못 본다 — 2.5 는 앞 둘로도 모자란 쪽만(그런 쪽은 아래 「위험」 표시와 별개로 보고)
                for pad in PADS:  # 스프라이트 둘레 여유를 큰 것부터 — 넉넉히 비는 쪽만 가장 안전하게 잡고, 모자라면 줄인다
                    fb = free_blocks(snaps, v0, v1, margin, pad, strict)
                    if len(fb) >= need:
                        break
                if len(fb) >= need:
                    break
            if len(fb) >= need:
                tier = strict
                break
        assert len(fb) >= need, (i, need, len(fb), p["lines"])
        # 앞쪽 주소부터 쓰되 이웃 쪽과 겹치게 — 같은 블록이면 올릴 때 덮어쓸 뿐이라 안전
        pick = sorted(fb[:need])
        # 5초 스냅샷 사이를 못 믿는 쪽(margin < 5)은 0 블록도 지우지 않는다 — 그 사이 게임이 이 블록에 올린 자료(대관식 신디 머리 스프라이트: 에뮬 실측 10-14 「신디 얼굴 깨짐」)를 숨길 때 0 으로 밀어 구멍이 났다
        unstable = margin < 5.0
        alloc.append(
            [b * 16 | (0 if clear and not unstable else 1) for b, clear in pick]
        )  # 타일 번호 → 워드 주소(128 의 배수) — 하위 비트 1 = 지우지 않는 블록
        print(
            i,
            f"{v0:.1f}-{v1:.1f}",
            "need",
            need,
            "free",
            len(fb),
            "(0 블록",
            sum(1 for _b, c in fb if c),
            ") margin",
            margin,
            "pad",
            pad,
            {2: "안전", 1: "중간", 0: "위험"}[tier],
        )
    OUT.write_text(
        json.dumps(
            {
                "note": "대관식 자막 VRAM 블록 배정(vram_alloc.py 가 만든다) — 쪽마다 128워드 블록 주소",
                "pages": alloc,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "snap")
