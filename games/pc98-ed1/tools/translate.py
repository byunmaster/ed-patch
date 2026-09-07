#!/usr/bin/env python3
"""번역 정본 — 사전을 붙이고, 남은 걸 검토표로 내고, 번역을 받아 넣는다.

    tools/translate.py seed [--dict …]    사전(JP 원문→우리 문안)을 정본에 자동 반영
    tools/translate.py stat               지금 얼마나 덮였나
    tools/translate.py fit                번역이 원래 자리에 들어가나(재삽입 전략)
    tools/translate.py payload [--n 200]  아직 안 된 것 중 「사람이 볼 값어치」 순으로 검토표
    tools/translate.py apply <검토표…>    검토표의 「번역」을 정본에 넣는다

## 무엇이 정본인가

`games/pc98-ed1/script/scn.json` — **열쇠(JP 원문 sha1) → 우리 문안**. 커밋된다.
🔴 **JP 원문은 안 담는다**(루트 「저작권」). 원문은 `work/derived/` 에만 있고 열쇠는
`shared/text/line_key.py` 가 만든다 — 그래서 정본만 봐서는 원문을 복원할 수 없다.

⚠ **열쇠는 위치가 아니라 원문**이다. 덤프의 `k`/`o`(트랙·오프셋)를 키로 쓰면 재삽입 단위를
세우다 오프셋이 한 번만 밀려도 번역이 통째로 어긋난다. 원문 해시면 **덤퍼를 고쳐도 산다.**

## 왜 사전이 먼저인가

같은 팔콤 원문을 여러 이식판이 나눠 갖는다. `games/ps1-ed1+2/line_dict.json` 이 그
창구고(PS1 이 만들고 새턴이 읽는다), **PC-98 이 셋째 소비자**다. 우리가 PS1 에서 이미
번역한 대사를 여기서 다시 번역하면 **같은 대사가 두 벌로 갈린다** — 새턴에서 실제로
겪었다(파일럿 35줄 중 24가 그 경우, `shared/text/line_key.py`).

⚠ 사전이 덮는 건 하한선이다 — 1989 원작과 1998 리메이크는 문안 자체가 다른 데가 있다.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import reuse
from text.line_key import key as line_key

SCRIPT = common.ROOT / "games" / "pc98-ed1" / "script" / "scn.json"
DICT = common.ROOT / "games" / "ps1-ed1+2" / "line_dict.json"
PAYLOAD_DIR = common.REVIEW_DIR / "translate"

# 덤프에는 코드가 SJIS 로 잘못 읽힌 잡음이 섞여 있다(`dump_scn.py` 머리말 — 옵코드를 안
# 따라가고 「텍스트로 보이는 최대 구간」을 뜬다). 사람에게 보일 땐 걸러야 한다.
_JA = re.compile(r"[ぁ-んァ-ン一-龥、。！？「」…ー]")
_NOISE = re.compile(r"[｡-ﾟ]")  # 반각 가나 — 코드가 이렇게 읽히는 게 대부분이다


def blocks() -> list[dict]:
    """덤프 넷을 한 줄로 이어 읽는다 — `reuse.pc98_lines()` 와 같은 자리를 본다."""
    out = []
    for name in ("scn_jp/scenario", "scn_jp/combat", "sys_jp/event", "sys_jp/program"):
        path = common.OUT_DIR / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"덤프가 없다: {path}\n  tools/dump_scn.py · dump_sys.py 를 먼저.")
        for b in json.loads(path.read_text(encoding="utf-8")):
            b["src"] = name
            out.append(b)
    return out


def looks_text(t: str) -> bool:
    """사람이 볼 값어치가 있나 — 일본어 글자가 3자 이상이고 반각 잡음이 그보다 적다."""
    ja = len(_JA.findall(t))
    return ja >= 3 and len(_NOISE.findall(t)) < ja


def load_script() -> dict:
    if SCRIPT.exists():
        return json.loads(SCRIPT.read_text(encoding="utf-8"))
    return {}


def save_script(data: dict) -> None:
    SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def keyed(bs: list[dict]) -> list[tuple[str, dict]]:
    return [(line_key(reuse.normalise(b)), b) for b in bs]


def cmd_seed(args) -> int:
    dic = json.loads(Path(args.dict).read_text(encoding="utf-8"))["lines"]
    data = load_script()
    bs = keyed(blocks())
    hit = new = 0
    for k, _b in bs:
        if k not in dic:
            continue
        hit += 1
        if k in data:  # ⚠ 이미 든 판단을 자동으로 밀어내지 않는다(patcher-checklist 6)
            continue
        data[k] = {"t": dic[k]["t"], "by": "dict"}
        new += 1
    if not args.dry:
        save_script(data)
    uniq = {k for k, _ in bs}
    print(f"블록 {len(bs):,} · 고유 열쇠 {len(uniq):,}")
    print(f"사전 적중 {hit:,} 블록 · 정본에 새로 넣은 것 {new:,}")
    print(f"정본 총 {len(data):,} 줄 ({'미저장 --dry' if args.dry else SCRIPT})")
    return 0


def cmd_stat(args) -> int:
    data = load_script()
    bs = keyed(blocks())
    text = [(k, b) for k, b in bs if looks_text(b["t"])]
    done = sum(1 for k, _ in text if k in data)
    chars = sum(len(b["t"]) for _, b in text)
    dchars = sum(len(b["t"]) for k, b in text if k in data)
    print(f"정본 {len(data):,} 줄")
    print(f"볼 값어치 있는 블록 {len(text):,} / 전체 {len(bs):,}")
    print(f"  덮인 블록 {done:,} = {done / max(1, len(text)):.1%}")
    print(f"  덮인 글자 {dchars:,} / {chars:,} = {dchars / max(1, chars):.1%}")
    return 0


def cmd_payload(args) -> int:
    """아직 안 된 것을 **긴 것부터** 낸다 — 긴 블록이 대사고, 짧은 건 잡음이 많다.

    ⚠ 원문이 담기므로 **`work/review/` 밖으로 내보내지 않는다**(루트 「저작권」).
    """
    data = load_script()
    seen = set()
    rows = []
    for k, b in keyed(blocks()):
        if k in data or k in seen or not looks_text(b["t"]):
            continue
        seen.add(k)
        rows.append({"열쇠": k, "화자": b.get("s") or "", "원문": b["t"], "번역": ""})
    rows.sort(key=lambda r: -len(r["원문"]))
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out = PAYLOAD_DIR / f"{args.name}.json"
    out.write_text(
        json.dumps(rows[: args.n], ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"남은 고유 블록 {len(rows):,} · 검토표에 {min(args.n, len(rows)):,} 줄 → {out}")
    return 0


def contract(t: str) -> tuple[int, int]:
    """구조 계약 — 페이지·대기 마커의 **개수**. 하나만 어긋나도 화면 흐름이 깨진다.

    ⚠ `\\n` 은 안 센다 — 줄나눔은 언어마다 다르고, 조판이 다시 잡는다.
    """
    return t.count("<PAGE>"), t.count("<WAIT>")


def cmd_apply(args) -> int:
    data = load_script()
    # 🔴 원문을 열쇠로 되찾아 **계약을 대조한다.** 검토표만 믿으면 마커가 빠진 줄이
    #    조용히 정본에 들어간다(이 레포가 세는 종류의 사고다 — patcher-checklist 12).
    src = {}
    for k, b in keyed(blocks()):
        src.setdefault(k, b["t"])
    put = skip = bad = broke = 0
    for path in args.files:
        for row in json.loads(Path(path).read_text(encoding="utf-8")):
            k, kr = row.get("열쇠"), (row.get("번역") or "").strip()
            if not kr:
                continue
            if not k or len(k) != 16:
                bad += 1
                continue
            if k in data and not args.force:  # ⚠ 이미 든 판단은 --force 로만 덮는다
                skip += 1
                continue
            if k in src and contract(src[k]) != contract(kr):
                print(f"  ⛔ 계약 어긋남 {k}: 원문 {contract(src[k])} ≠ 번역 {contract(kr)}")
                broke += 1
                continue
            data[k] = {"t": kr, "by": "human"}
            put += 1
    if not args.dry:
        save_script(data)
    print(
        f"넣음 {put:,} · 건너뜀 {skip:,} · 열쇠 이상 {bad:,} · 계약 어긋남 {broke:,} "
        f"· 정본 {len(data):,}"
    )
    return 1 if broke else 0


def _kr_bytes(t: str) -> int:
    """한글은 **빈 한자 자리**에 앉히므로 2B, 반각 부호·숫자·공백은 1B."""
    return sum(2 if "가" <= c <= "힣" else 1 for c in t)


def _jp_bytes(t: str) -> int:
    return sum(1 if (ord(c) < 0x80 or 0xFF61 <= ord(c) <= 0xFF9F) else 2 for c in t)


def _markers(t: str) -> str:
    """마커를 원래 1바이트 코드로 되돌린다 — 양쪽 다 같은 바이트 수라야 견줄 수 있다."""
    return t.replace("<PAGE>", "\x05").replace("<WAIT>", "\x03").replace("\\n", "\x01")


def cmd_fit(args) -> int:
    """번역이 **원래 자리에 들어가나** — 재삽입 전략을 가르는 자.

    `0F <주소 2B>` 가 무조건 점프라(`tools/units.py`), 남는 틈이 **3바이트 이상이면**
    제자리에 넣고 틈을 건너뛸 수 있다. 1~2바이트면 그럴 자리가 없어 **반각 공백으로
    메운다.** 넘치면 밖으로 뺀다.
    """
    data = load_script()
    buckets = {
        "꼭 맞는다": 0,
        "틈 3+ (0F 로 건너뛴다)": 0,
        "틈 1~2 (공백으로 메운다)": 0,
        "넘친다 (밖으로)": 0,
    }
    over = jt = kt = 0
    n = 0
    for k, b in keyed(blocks()):
        if k not in data:
            continue
        n += 1
        d = _jp_bytes(_markers(b["t"])) - _kr_bytes(_markers(data[k]["t"]))
        jt += _jp_bytes(_markers(b["t"]))
        kt += _kr_bytes(_markers(data[k]["t"]))
        if d == 0:
            buckets["꼭 맞는다"] += 1
        elif d >= 3:
            buckets["틈 3+ (0F 로 건너뛴다)"] += 1
        elif d > 0:
            buckets["틈 1~2 (공백으로 메운다)"] += 1
        else:
            buckets["넘친다 (밖으로)"] += 1
            over += -d
    print(f"대조 {n:,} 런 · JP {jt:,}B → KR {kt:,}B = {kt / max(1, jt):.1%}")
    for key, v in buckets.items():
        print(f"  {key:28s} {v:6,} = {v / max(1, n):6.1%}")
    print(f"  밖으로 뺄 때 필요한 바이트 {over:,}B")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed")
    s.add_argument("--dict", default=str(DICT))
    s.add_argument("--dry", action="store_true")
    s.set_defaults(fn=cmd_seed)
    s = sub.add_parser("stat")
    s.set_defaults(fn=cmd_stat)
    s = sub.add_parser("fit")
    s.set_defaults(fn=cmd_fit)
    s = sub.add_parser("payload")
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--name", default="batch")
    s.set_defaults(fn=cmd_payload)
    s = sub.add_parser("apply")
    s.add_argument("files", nargs="+")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry", action="store_true")
    s.set_defaults(fn=cmd_apply)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
