"""다른 아카이브(그래픽 넷 + misc)를 최적 파싱으로 다시 눌러 **빈 칸을 만든다** — 대본(한국어)이 압축이 안 돼 칸이 모자라기 때문이다.

    python3 tools/repack.py        # 아카이브별 원본/재압축 크기 · 같은 블록 공유 · 빈 칸

색인은 `BE32 × n`(첫 값 4n) + 블록들이고 오프셋은 **색인 시작 기준 32비트**다 — 로더(`$DD4`)가 `lea (a1,d1.l),a1` 로 더해 읽어
블록은 롬 어디에든 앉을 수 있다(음수 오프셋도 감김으로 된다). 그래서 여기서 다시 누르면 각 아카이브 끝에 빈 칸이 남고,
대본 블록이 그 칸에 앉는다(`build.pack_script`).

- 같은 디코드 블록(gfx_a 18 = 17)은 압축본 하나를 가리킨다(색인 두 항목이 같은 오프셋).
- 코드 쪽에서 **블록 하나를 색인 없이 직접 가리키는** 곳(gfx_a 0x107BA → 0x8E838)은 새 자리로 고친다.
- 결정적이다 — 입력이 같으면 같은 바이트(인코더는 순수 DP). 느리므로(약 1분) 결과를 `work/derived/repack/` 에 캐시한다(열쇠 = 입력 sha1).
"""

import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import lz

OTHER = ("gfx_a", "gfx_b", "gfx_c", "gfx_d", "misc")
CODE_END = 0x88F4E  # 이 앞이 코드 — 직접 참조를 찾는 범위
CACHE = common.OUT_DIR / "repack"


def _pack(blocks: list[bytes]) -> tuple[bytes, list[int]]:
    """디코드 블록들 → (색인+압축 블록들, 블록별 아카이브 안 오프셋). 같은 블록은 한 번만 싣는다."""
    n = len(blocks)
    seen: dict[str, int] = {}
    body = bytearray()
    offs = []
    cur = 4 * n
    for b in blocks:
        h = hashlib.sha1(b).hexdigest()
        if h in seen:
            offs.append(seen[h])
            continue
        p = lz.encode(b)
        p += b"\x00" * (len(p) & 1)
        seen[h] = cur
        offs.append(cur)
        body += p
        cur += len(p)
    return struct.pack(f">{n}I", *offs) + bytes(body), offs


def plan(orig: bytes):
    """→ (writes[(라벨, 자리, 바이트)], free[(lo, hi)], 요약[(이름, 원본 크기, 새 크기)]). 라벨 = `archive:<이름>` · `archive-ref:<자리>`."""
    writes: list[tuple[str, int, bytes]] = []
    free: list[tuple[int, int]] = []
    info = []
    for name in OTHER:
        base, n, _tot = archives.ARCHIVES[name]
        bl = archives.blocks(orig, base)
        old_end = max(e for _s, _b, e in bl)
        key = hashlib.sha1(orig[base:old_end]).hexdigest()[:16]
        cp = CACHE / f"{name}-{key}.bin"
        if cp.exists():
            data = cp.read_bytes()
            offs = list(struct.unpack(f">{n}I", data[: 4 * n]))
        else:
            data, offs = _pack([b for _s, b, _e in bl])
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(data)
        if base + len(data) > old_end:
            raise SystemExit(f"repack {name}: 재압축본이 원본 칸을 넘는다")
        # 같은 블록 공유로 색인이 달라졌다 — 되읽어 의도(원본 디코드)와 대조한다
        got = archives.blocks(b"\x00" * base + data, base)
        if [b for _s, b, _e in got] != [b for _s, b, _e in bl]:
            raise SystemExit(f"repack {name}: 되읽기가 원본 디코드와 다르다")
        writes.append((f"archive:{name}", base, data))
        lo = base + len(data)
        lo += lo & 1
        if lo < old_end:
            free.append((lo, old_end))
        info.append((name, old_end - base, len(data)))
        # 코드가 색인 없이 블록을 직접 가리키는 자리 — 새 자리로
        olds = {s: base + o for (s, _b, _e), o in zip(bl, offs, strict=True)}
        for p in range(0, CODE_END, 2):
            v = struct.unpack(">I", orig[p : p + 4])[0]
            prev = struct.unpack(">H", orig[p - 2 : p])[0] if p >= 2 else 0
            # 🔴 앞 워드가 주소를 피연산자로 받는 명령(lea.l abs · pea · move.l #imm)일 때만 참조다 — 0x107BA 는 우연히 블록 시작과 같은 값의
            # `move.b #8,d0 / ror.b d4,d0` 명령 바이트였고, 고쳤다가 입력 대기 루프가 깨져 전투가 멈췄다(마스터 10-13)
            is_ptr = (prev & 0xF1FF) == 0x41F9 or prev == 0x4879 or (prev & 0xF03F) in (0x203C, 0x207C)
            if v != base and v in olds and olds[v] != v and is_ptr:
                writes.append((f"archive-ref:{p:x}", p, struct.pack(">I", olds[v])))
    return writes, free, info


def allowed(orig: bytes, writes) -> dict[str, tuple[int, int]]:
    out = {}
    for label, pos, body in writes:
        if label.startswith("archive:"):
            name = label.split(":")[1]
            base = archives.ARCHIVES[name][0]
            old_end = max(e for _s, _b, e in archives.blocks(orig, base))
            out[label] = (base, old_end)
        else:
            out[label] = (pos, pos + len(body))
    return out


if __name__ == "__main__":
    o = common.rom()
    w, fr, info = plan(o)
    tot = 0
    for name, a, b in info:
        print(f"  {name:6s} {a:8,}B → {b:8,}B  ({a - b:+,}B)")
        tot += a - b
    print(
        f"  빈 칸 {sum(h - lo for lo, h in fr):,}B · 구간 {[(hex(lo), h - lo) for lo, h in fr]} · 직접 참조 고침 {[hex(p) for l, p, _ in w if l.startswith('archive-ref')]}"
    )
