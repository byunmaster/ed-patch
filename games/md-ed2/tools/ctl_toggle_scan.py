"""런타임 제어 바이트 토글 스캔 — 원판 코드가 `lea d(pc),aN` 로 **문안 스트림 안의 바이트**를 가리켜 `move.b …,(aN)` 로 런타임에 바꾸는 자리를 찾고,
한글 롬에서도 같은 자리가 안전한지 센다(md-ed1 에서 「하이 길도」 빈 글리프·문장 통째 누락).

    python3 tools/ctl_toggle_scan.py [롬] [--verbose]      # 빌드 게이트(check.sh 5d) — 어긋남이 있으면 실패

· 전투 블록(99): 대상이 스트림 **한복판**(스트림 시작·참조 시작이 아닌 곳)이면 쓰기 자리 — 한글 블록의 같은 오프셋 바이트가 원판과 같아야 한다.
· 씬 모듈(356): 대상이 **번역되는 글 스트림**(SJIS 6B↑) 안이고 뒤따르는 명령이 `(aN)` 로 쓰면 쓰기 자리 — `ALLOW` 에 사유가 적힌 것만 허용, 나머지는 같은 오프셋 바이트 비교.
결과 한 줄: 「쓰기 자리 n · 어긋남 m」.
"""

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import common
import scene

LEA = re.compile(rb"([\x41\x43\x45\x47\x49\x4b\x4d])\xfa(..)", re.DOTALL)
# 허용 — (전투 블록 n | 씬 「BBB-K」, lea 자리): 사유
ALLOW = {
    (
        82,
        0x8E2,
    ): "보스 블록 82 — `patch_boss_block` 이 루틴(`$8DE`)과 `$A13` 꼬리를 한글 방식으로 다시 쓴다(4B 덮어쓰기를 걷음)",
    ("023-1", 0x1158): "`$1200` 은 플래그 변수 바이트(데이터 — 가짜 스트림) · 롬 바이트 동일",
    ("023-1", 0x1296): "위와 같다",
    ("023-1", 0x1376): "위와 같다",
    (
        "031-2",
        0xAD8,
    ): "스트림 머리 한 바이트(`>`↔`,`) 토글 — 한글 스트림은 옮겨져 옛 자리에 쓰는 쪽이 무해(0 칸)",
    ("083-1", 0x620): "`$1BBE` 는 코드 자리 워드(`4E71`) — 한글 모듈도 같은 바이트·같은 자리",
    ("083-1", 0x6E0): "위와 같다",
    (
        "023-1",
        0x11CE,
    ): "루틴(`$11C8`)을 `build.apply_weapon_branch` 가 통째로 다시 쓴다 — 정본 두 문안 + 무기 번호 분기(보스 82 방식)",
}
# 「다시 쓴다」고 허용한 자리는 **정말 다시 써졌는지** 구운 모듈에서 확인한다 — 허용만 적고 적용이 빠져도 게이트가 초록이던 구멍(2026-10-20: 023-1 무기 분기 호출이
# 빌드에서 사라졌는데 화면에 では/ので 가 남는 롬이 나갔다). (모듈, lea 자리): (확인 자리, 새 바이트 머리)
MUST_CHANGE = {("023-1", 0x11CE): (0x11C8, bytes.fromhex("48e78060"))}
# 중화 표(현재 비어 있다) — 씬 모듈의 4B 복사 루틴이 글 한복판을 덮는 자리를 자료 위로 돌리는 용도. 023-1 은 처음 이렇게 중화했다가 정본 두 문안 + 무기 번호 분기(build.apply_weapon_branch)로 바꿨다.
NEUTRAL: dict[
    tuple[str, int], int
] = {}  # (모듈, lea 자리): 새 대상 — 023-1 은 루틴을 통째로 바꿔(build.apply_weapon_branch) 중화가 필요 없어졌다


def neutralize(blk: int, k: int, module: bytes) -> bytes:
    """`NEUTRAL` 에 적힌 모듈의 `lea d(pc),a2` 변위를 새 대상으로 다시 쓴다 — 원판 코드가 글 한복판 4B 를 덮는 루틴이 한글 글자를 깨던 것을 막는다."""
    key = f"{blk:03d}-{k}"
    out = bytearray(module)
    for (kk, i), tgt in NEUTRAL.items():
        if kk != key:
            continue
        if out[i : i + 2] != b"\x45\xfa":
            raise SystemExit(f"{key} {i:#x} 가 lea d(pc),a2 가 아니다 — 중화 자리가 바뀌었다")
        out[i + 2 : i + 4] = struct.pack(">h", tgt - (i + 2))
    return bytes(out)


def _real(st) -> bool:
    return any(t.kind == "text" and sum(1 for c in t.raw if c >= 0x80) >= 6 for t in st.tokens)


def scene_sites(m: bytes):
    """(lea 자리, 대상) — 글 스트림 안을 가리키고 뒤따르는 명령이 그 레지스터로 쓰는 것."""
    from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs

    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    mod = scene.parse_module(m)
    out = []
    for mm in LEA.finditer(m):
        i = mm.start()
        t = i + 2 + struct.unpack(">h", mm.group(2))[0]
        if not 0 <= t < len(m) or not any(
            s <= t < st.end and _real(st) for s, st in mod.streams.items()
        ):
            continue
        reg = (mm.group(1)[0] - 0x41) // 2
        for x in list(md.disasm(m[i + 4 : i + 44], i + 4))[:16]:
            if x.mnemonic in ("jsr", "rts", "bra", "jmp"):
                break
            # 마지막 피연산자가 (aN)·(aN)+·-(aN)·d(aN)·d(aN,dM) 인 명령 전부 — move.b/w/l · bset/bclr/bchg · addq/subq · eori/ori/andi · clr · not · neg · tas …
            if re.search(
                rf"(^|,)\s*-?\(?\$?-?[0-9a-fx]*\(a{reg}(,\s*[da]\d(\.[wl])?)?\)\+?\s*$", x.op_str
            ):
                out.append((i, t))
                break
    return out


def battle_sites(j: bytes, refs: dict, streams: dict):
    out = []
    for m in LEA.finditer(j):
        i = m.start()
        t = i + 2 + struct.unpack(">h", m.group(2))[0]
        if not 0 <= t < len(j) or t in refs:
            continue
        if any(s < t < e for s, e in streams.items()):
            out.append((i, t))
    return out


def main() -> None:
    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom = (Path(args[0]) if args else common.BUILD_DIR / "ed2-kr.bin").read_bytes()
    orig = common.rom()
    n_sites = n_bad = 0
    # 전투
    kb = [b for _s, b, _e in battle.blocks(rom)]
    for n, (k, j) in enumerate(zip(kb, [b for _s, b, _e in battle.blocks(orig)], strict=True)):
        refs = battle.refs(j)
        streams = {s: v["stream"].end for s, v in refs.items()}
        for i, t in battle_sites(bytes(j), refs, streams):
            n_sites += 1
            kt = i + 2 + struct.unpack(">h", bytes(k[i + 2 : i + 4]))[0]
            # 스트림이 옮겨져 lea 가 새 자리를 가리켜도(kt≠t) 가리킨 바이트가 원판과 같으면 된다
            ok = (n, i) in ALLOW or k[kt] == j[t]
            if verbose or not ok:
                print(
                    f"전투 {n:02d} lea@{i:#x}→{t:#x} 원판 {j[t]:#04x} 한글 {k[kt]:#04x}{' (허용)' if (n, i) in ALLOW else ''}"
                )
            n_bad += not ok
    # 씬
    import scene_sweep as ss

    km = {(b, k): m for b, k, m in ss.built_modules(rom)}
    for (b, kk), j in {(b, k): m for b, k, m in archives.modules(orig)}.items():
        key = f"{b:03d}-{kk}"
        k = km[(b, kk)]
        for i, t in scene_sites(bytes(j)):
            n_sites += 1
            kt = i + 2 + struct.unpack(">h", bytes(k[i + 2 : i + 4]))[0]
            if (key, i) in NEUTRAL:
                ok = kt == NEUTRAL[(key, i)]
                why = f"중화 → {NEUTRAL[(key, i)]:#x}"
            elif (key, i) in ALLOW:
                ok, why = True, "허용"
                if (key, i) in MUST_CHANGE:
                    at, head = MUST_CHANGE[(key, i)]
                    if bytes(k[at : at + len(head)]) != head:
                        ok, why = (
                            False,
                            f"허용 사유는 「다시 쓴다」인데 {at:#x} 가 원판 그대로다 — 적용이 빠졌다",
                        )
            else:
                ok, why = k[kt : kt + 2] == j[t : t + 2], ""
            if verbose or not ok:
                print(
                    f"씬 {key} lea@{i:#x}→{t:#x} 원판 {j[t]:#04x} 한글(같은 변위) {k[kt]:#04x} {why}"
                )
            n_bad += not ok
    print(f"쓰기 자리 {n_sites} · 어긋남 {n_bad}")
    sys.exit(1 if n_bad else 0)


if __name__ == "__main__":
    main()
