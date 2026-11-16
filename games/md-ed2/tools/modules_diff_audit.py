"""모듈 변경 바이트 감사 — 원판 대비 제품 씬 모듈에서 바뀐 바이트를 분류한다(전체 패턴 치환 부작용 점검).

    python3 tools/modules_diff_audit.py [롬.bin] [--list]

분류: 글(원·새 스트림 구간) · lea 변위(`xxFA` 뒤 워드) · 표·머리(protected) · 꼬리 연장(원판 길이 밖) · **기타** — 기타가 있으면 한 건씩 사유를 본다.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene
import scene_sweep


def audit(kr: bytes):
    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    tot = Counter()
    other = []
    for b, k, om in archives.modules(orig):
        nm = km[(b, k)]
        omod = scene.parse_module(om)
        nmod = scene.parse_module(nm)
        cov = bytearray(max(len(om), len(nm)))
        for mod in (omod, nmod):
            for st in mod.streams.values():
                for q in range(st.start, min(st.end, len(cov))):
                    cov[q] = 1  # 글
        for mod in (omod, nmod):
            for a in mod.tables:
                cov[a.word : a.word + 2] = b"\x02\x02"
            for e, ln in mod.entries.items():
                cov[e : e + ln] = b"\x02" * ln
        n = min(len(om), len(nm))
        for q in range(n):
            if om[q] == nm[q]:
                continue
            if cov[q] == 1:
                tot["글"] += 1
            elif cov[q] == 2:
                tot["표·머리"] += 1
            else:
                # lea 변위: 바로 앞 워드가 xxFA(lea d(pc),aN = 0x41FA|reg<<9)이고 q 가 변위 워드 안
                ok = False
                for s in (q - 2, q - 3):
                    if s >= 0 and (int.from_bytes(nm[s : s + 2], "big") & 0xF1FF) == 0x41FA:
                        ok = True
                if ok:
                    tot["lea 변위"] += 1
                else:
                    tot["기타"] += 1
                    other.append((f"{b:03d}-{k}", q))
        tot["꼬리 연장(바이트)"] += max(0, len(nm) - len(om))
    return tot, other


def lea_target_problems(kr: bytes) -> list:
    """바뀐 `lea d(pc),aN` 의 원판 목적지가 옮긴 스트림 시작 · 원판 스트림 안쪽(공유 머리) · 머리 표 레코드가 아니면 보고한다 —
    전체 패턴 치환이 우연히 같은 바이트의 자료를 고친 흔적."""
    import csv

    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    rows: dict[str, set[int]] = {}
    with open(common.GAME_DIR / "relocations.tsv", encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if len(r) > 3 and r[1] == "옮김" and r[3]:
                rows.setdefault(r[0], set()).add(int(r[2], 16))
    out = []
    for b, k, om in archives.modules(orig):
        nm = km[(b, k)]
        key = f"{b:03d}-{k}"
        omod = scene.parse_module(om)
        spans = [(st.start, st.end) for st in omod.streams.values()]
        n = min(len(om), len(nm))
        for s in range(0, n - 3, 2):
            if (int.from_bytes(nm[s : s + 2], "big") & 0xF1FF) != 0x41FA or om[s : s + 2] != nm[
                s : s + 2
            ]:
                continue
            if om[s + 2 : s + 4] == nm[s + 2 : s + 4]:
                continue
            d = int.from_bytes(om[s + 2 : s + 4], "big")
            d -= 0x10000 if d >= 0x8000 else 0
            t = s + 2 + d
            if t in rows.get(key, set()):
                continue
            if any(a <= t < e for a, e in spans) or any(
                e <= t < e + ln for e, ln in omod.entries.items()
            ):
                continue
            out.append((key, hex(s), hex(t)))
    return out


def header_changed(kr: bytes) -> list:
    """맵 모듈 머리(워드 표 + NPC 항목 = 앞 `머리[3]` 바이트)는 번역이 건드릴 까닭이 없다 — 하나라도 다르면 그 자체가 결함이다
    (060-3: 가짜 표가 NPC 항목의 조건 바이트를 0x00→0x96 으로 고쳤다, 11-08)."""
    orig = common.rom()
    km = {(b, k): m for b, k, m in scene_sweep.built_modules(kr)}
    out = []
    for b, k, om in archives.modules(orig):
        if int.from_bytes(om[:2], "big") != 0x12:
            continue
        hs = int.from_bytes(om[6:8], "big")
        if 0x12 <= hs <= min(len(om), 0x400) and om[:hs] != km[(b, k)][:hs]:
            out.append(f"{b:03d}-{k}")
    return out


BASELINE = common.GAME_DIR / "modules_diff_baseline.json"


def gate(kr: bytes) -> int:
    import json

    tot, other = audit(kr)
    per: dict[str, int] = {}
    for key, _q in other:
        per[key] = per.get(key, 0) + 1
    leas = lea_target_problems(kr)
    hdr_bad = header_changed(kr)
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    print(
        f"모듈 변경 바이트 감사 [md-ed2] — 글 {tot['글']:,} · lea 변위 {tot['lea 변위']} · 표·머리 {tot['표·머리']} · "
        f"기타 {sum(per.values())} ({len(per)}개 모듈, 기준선 {sum(base.values())}) · 엉뚱한 lea 목적지 {len(leas)} · 머리 구간 바뀐 모듈 {len(hdr_bad)}"
    )
    bad = [f"{k}: {v} > {base.get(k, 0)}" for k, v in per.items() if v > base.get(k, 0)]
    for x in hdr_bad[:10]:
        bad.append(f"머리·NPC 항목 구간이 원판과 다르다 {x}")
    for x in leas[:10]:
        bad.append(f"lea 목적지가 옮긴 스트림이 아니다 {x}")
    if bad:
        print("❌ 선언 없는 모듈 변경 —", *bad[:12], sep="\n   ")
        print("   (의도한 번역·자기수정이면 사유를 devlog 에 적고 --freeze)")
        return 1
    return 0


def main():
    if "--freeze" in sys.argv:
        import json

        kr = (common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin").read_bytes()
        _tot, other = audit(kr)
        per: dict[str, int] = {}
        for key, _q in other:
            per[key] = per.get(key, 0) + 1
        BASELINE.write_text(json.dumps(per, indent=1, sort_keys=True))
        print("기준선 갱신", per)
        return 0
    if "--gate" in sys.argv:
        kr = (common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin").read_bytes()
        return gate(kr)
    kr = (
        Path(sys.argv[1]).read_bytes()
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
        else (common.BUILD_DIR / common.BUILD_TAG / "ed2-kr.bin").read_bytes()
    )
    tot, other = audit(kr)
    print("모듈 변경 바이트 감사 [md-ed2]", dict(tot))
    runs = {}
    for key, q in other:
        runs.setdefault(key, []).append(q)
    for key, qs in runs.items():
        print(" 기타", key, len(qs), [hex(x) for x in qs[:8]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
