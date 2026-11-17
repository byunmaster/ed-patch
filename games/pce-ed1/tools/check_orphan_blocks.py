"""컨테이너 밖 씬 블록 사본 게이트 — 원판 데이터 트랙에는 씬 블록의 LZ 스트림이 **컨테이너(24개) 밖에도** 있다(맵 레코드 구역 rel ~1100~1250 등).
빌드는 컨테이너만 고쳐서 그 사본이 **원판(일본어) 그대로** 남으면, 게임이 그 사본을 읽는 길(정상 진행으로 맵에 들어갈 때)에서 미번역 장면이 뜬다
(11-17 마스터: 2장 노부부의 집 씬 54 전체가 일본어 · rel 1141 오프셋 1772 의 사본 — 시험 롬에서 그 섹터를 지우면 그 집에서 멈춘다).
구조 대조·일본어 게이트는 컨테이너 블록만 분모로 삼아 이걸 못 봤다.

방법: 원판 트랙의 모든 씬 블록 LZ 스트림(컨테이너 디렉터리가 가리키는 구간)을 원판 트랙 전체(컨테이너 16섹터 구간 밖)에서 바이트로 찾고,
그 블록이 번역으로 바뀌었는데(제품 롬 컨테이너의 같은 (컨테이너, id) 블록이 원판과 다르다) 같은 자리에 원판 스트림이 그대로 남아 있으면 「남은 사본」이다.

    python3 tools/check_orphan_blocks.py            # 게이트 — 기준선(`script/orphan_blocks_baseline.json`)에 없던 사본이 생기면 실패
    python3 tools/check_orphan_blocks.py --list     # 남은 사본 전체 목록
    python3 tools/check_orphan_blocks.py --strict   # 하나라도 남아 있으면 실패(고침이 끝나면 기준선을 비우고 이걸 기본으로)
    python3 tools/check_orphan_blocks.py --freeze   # 기준선을 지금 목록으로(줄어들 때만 — 늘었으면 먼저 고쳐라)
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
import containers
import lz

BASELINE = HERE.parent / "script" / "orphan_blocks_baseline.json"
MIN_LEN = 40  # 이보다 짧은 스트림은 우연 일치가 생긴다
SPAN = 16 * common.USER  # 컨테이너 한 칸(원판 최대 16섹터)


def read_track(path: Path) -> bytes:
    out = []
    with path.open("rb") as f:
        for rel in range(common.T2_LEN):
            f.seek((common.T2_SECTOR + rel) * common.RAW + common.USER_OFF)
            out.append(f.read(common.USER))
    return b"".join(out)


def same_block(track: bytes, at: int, b: dict) -> bool:
    """`track` 의 `at` 에서 LZ 로 풀면 원판 블록 `b` 가 나오나."""
    try:
        out, _ = lz.decode(track[at : at + b["packed"] + 64], b["len"])
    except (IndexError, ValueError):
        return False
    return out == b["data"]


def orphans(prod: bytes) -> list[dict]:
    orig = common.track_data()
    fo = containers.scan(orig)
    fp = containers.scan(prod)
    prod_blocks = {(c["rel"], b["id"]): b["data"] for c in fp for b in c["blocks"]}
    spans = [(c["rel"] * common.USER, c["rel"] * common.USER + SPAN) for c in fo]

    def inside(off):
        return any(a <= off < b for a, b in spans)

    rows = []
    seen = set()
    for c in fo:
        cont = orig[c["rel"] * common.USER : c["rel"] * common.USER + containers.CONTAINER_SPAN]
        for b in c["blocks"]:
            stream = bytes(cont[b["src"] : b["src"] + b["packed"]])
            if len(stream) < MIN_LEN:
                continue
            if prod_blocks.get((c["rel"], b["id"])) == b["data"]:  # 번역이 안 닿은 블록 — 사본이 원판이어도 같은 내용이다
                continue
            if (c["rel"], b["id"]) not in prod_blocks and not any(k[1] == b["id"] for k in prod_blocks):
                continue
            needle = stream[:MIN_LEN]
            pos = 0
            while True:
                i = orig.find(needle, pos)
                if i < 0:
                    break
                pos = i + 1
                if inside(i):
                    continue
                if not same_block(orig, i, b):  # 우연 일치 — 풀어서 그 블록이 나오는지 본다(스트림 끝 몇 바이트는 뒤 자료와 겹쳐 바이트 비교가 안 맞는다)
                    continue
                if not same_block(prod, i, b):
                    continue  # 제품 롬에서 이미 바뀐 자리
                key = (b["id"], i // common.USER, i % common.USER)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"id": b["id"], "rel": i // common.USER, "off": i % common.USER, "packed": b["packed"], "from": c["rel"]})
    return sorted(rows, key=lambda r: (r["rel"], r["off"]))


def stale_places(prod: bytes) -> list[dict]:
    """이사한 컨테이너의 옛 자리 — 컨테이너를 트랙 끝 빈 구간으로 옮기면(`build.patch_ref_table`) 참조표만 새 자리를 가리키고 옛 자리는 원판(일본어) 그대로 남는다.
    번역이 있는 블록(`script/scnNNN.json` 에 줄이 있다)이 제품 롬의 **같은 컨테이너 자리**에서 원판과 같으면 옛 자리가 원판으로 남은 것이다. 다른 경로가 옛 자리를 읽으면 미번역 장면이 뜬다(11-17: 블록 0 의 입장 배너 · 1300·1604)."""
    fo = containers.scan(common.track_data())
    fp = containers.scan(prod)
    prod_blocks = {(c["rel"], b["id"]): b["data"] for c in fp for b in c["blocks"]}
    rows = []
    for c in fo:
        same = []
        for b in c["blocks"]:
            if prod_blocks.get((c["rel"], b["id"])) != b["data"]:
                continue
            f = common.GAME_DIR / "script" / f"scn{b['id']:03d}.json"
            if not f.exists():
                continue
            if any(v.get("t") or v.get("jp") for v in json.loads(f.read_text()).get("messages", {}).values()):
                same.append(b["id"])
        if same:
            rows.append({"rel": c["rel"], "ids": same})
    return rows


def key(r) -> str:
    return f"{r['id']}@{r['rel']}:{r['off']}"


def main() -> int:
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print(f"✘ {iso} 가 없다 — 빌드가 먼저 돌아야 한다")
        return 1
    prod = read_track(iso)
    rows = orphans(prod)
    keys = sorted(key(r) for r in rows)
    stale = stale_places(prod)
    keys += sorted(f"old:{r['rel']}" for r in stale)
    if "--list" in sys.argv:
        for r in rows:
            print(f"  씬 블록 {r['id']:>3}  rel {r['rel']}:{r['off']}  ({r['packed']}B · 컨테이너 {r['from']} 에서 온 사본)")
        for r in stale:
            print(f"  옛 자리 컨테이너 rel {r['rel']} — 번역 있는 블록 {len(r['ids'])}개가 원판 그대로({r['ids']})")
        print(f"  남은 사본 {len(rows)} · 옛 자리 {len(stale)}")
        return 0
    if "--freeze" in sys.argv:
        BASELINE.write_text(json.dumps(keys, indent=1) + "\n")
        print(f"  기준선 {len(keys)}건 기록: {BASELINE}")
        return 0
    base = set(json.loads(BASELINE.read_text())) if BASELINE.exists() else set()
    new = [k for k in keys if k not in base]
    if "--strict" in sys.argv:
        new = keys
    print(f"  컨테이너 밖 씬 블록 사본(원판 그대로 남음) {len(keys)}건 — 기준선 {len(base)}건")
    if new:
        print("✘ 번역이 안 닿은 컨테이너 밖 사본:")
        for k in new:
            print("   ", k)
        return 1
    if keys:
        print("  ⚠ 알려진 미해결(고칠 대상): " + ", ".join(keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
