"""화면 일본어 게이트 — **분모는 파서가 아니라 최종 디코드 바이트의 가나 글줄 전수 스캔**이다.

    python3 tools/build.py --check          # 빌드 중 이 게이트가 돈다
    python3 tools/build.py --freeze-kana    # 남은 것을 기준선으로 박는다(사람이 보고 나서만)

🔴 왜 파서 출력이 분모면 안 되나(2026-10-13): 번역 도구는 `scene.parse_module` 이 찾은 스트림만 센다. 파서가 스트림을 못 찾으면
「번역 대상 0건 · 남은 일본어 0건」이 되어 게이트가 초록이다 — 실제로 가나 글줄이 **약 3,300줄** 빠져 있었다(화자 이름에 공백 ·
F6/F8 조건 사슬 · lea a3/a6 · 머리 표 레코드 · 절대 워드 표 · 제자리 고정 가나 글줄). 그래서 이 게이트는 **빌드된 모듈 바이트**
에서 가나(히라가나 `82 9F~F1` · 가타카나 `83 40~96`) 두 글자 이상 이어진 글줄과 `<1e>이름<04>` 화자 머리(한자 이름)를 직접 센다.

- 기준선(`textmap/kana_baseline.json`) = 번역 대상이 아닌 것으로 **사람이 확인한** 글줄(코드 바이트가 우연히 가나 꼴 · 지명 배너 표의
  못 채운 칸 · 쓰레기 스트림). 모듈별 「글줄 해시 → 개수」 — 오프셋이 아니라 해시라 모듈 안에서 자리가 옮겨져도 안 흔들린다.
- 기준선보다 **늘면 실패**한다. 줄면 알린다(`--freeze-kana` 로 내린다 — 래칫).
"""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

KANA = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){2,}")
SPEAKER = re.compile(rb"\x1e((?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|\x20){1,12})\x04")
BASELINE = Path(__file__).resolve().parents[1] / "textmap" / "kana_baseline.json"
HANGUL_CODES = Path(__file__).resolve().parents[1] / "textmap" / "hangul_codes.json"


def _hangul_pairs() -> set[bytes]:
    d = json.loads(HANGUL_CODES.read_text(encoding="utf-8"))
    return {v.to_bytes(2, "big") for v in d.values() if isinstance(v, int)}


def _is_korean(name: bytes, pairs: set[bytes]) -> bool:
    """화자 이름 바이트가 전부 우리 한글 코드(+ 반각 공백)인가 — 한글 코드는 SJIS 한자 선두 범위(0x8A~)에 앉아 정규식만으론 못 가른다."""
    i = 0
    while i < len(name):
        if name[i] == 0x20:
            i += 1
        elif name[i : i + 2] in pairs:
            i += 2
        else:
            return False
    return True


def _h(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:10]


def scan(blocks: list[bytes], sizes: list[list[int]]) -> dict[str, Counter]:
    """{"블록-모듈": Counter({해시: 개수})} — 가나 글줄 + 한자 화자 머리. 해시 앞 `k:`(가나) · `s:`(화자)."""
    out: dict[str, Counter] = {}
    pairs = _hangul_pairs()
    for i, sz in enumerate(sizes):
        if i >= len(blocks):
            break
        at = 0
        for k, n in enumerate(sz):
            mod = blocks[i][at : at + n]
            at += n
            c: Counter = Counter()
            for m in KANA.finditer(mod):
                c["k:" + _h(m.group())] += 1
            for m in SPEAKER.finditer(mod):
                if not _is_korean(m.group(1), pairs):
                    c["s:" + _h(m.group())] += 1
            if c:
                out[f"{i}-{k}"] = c
    return out


def sample(blocks, sizes, key: str, h: str) -> str:
    i, k = map(int, key.split("-"))
    at = sum(sizes[i][:k])
    mod = blocks[i][at : at + sizes[i][k]]
    rx = KANA if h.startswith("k:") else SPEAKER
    for m in rx.finditer(mod):
        if _h(m.group()) == h[2:]:
            lo = max(0, m.start() - 4)
            return f"@{m.start():#x} " + mod[lo : m.end() + 6].decode("cp932", "replace")
    return "?"


def load_baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}


def check(blocks, sizes, *, freeze: bool = False) -> None:
    left = scan(blocks, sizes)
    total = sum(sum(c.values()) for c in left.values())
    if freeze:
        BASELINE.write_text(
            json.dumps(
                {k: dict(sorted(c.items())) for k, c in sorted(left.items())},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  가나 기준선 박음: 모듈 {len(left)}곳 · 글줄 {total}")
        return
    base = load_baseline()
    new: list[str] = []
    shrunk = 0
    for key, c in left.items():
        b = base.get(key, {})
        for h, n in c.items():
            if n > b.get(h, 0):
                new.append(f"블록 {key} {h} ×{n - b.get(h, 0)}: {sample(blocks, sizes, key, h)}")
    for key, b in base.items():
        for h, n in b.items():
            if left.get(key, Counter()).get(h, 0) < n:
                shrunk += n - left.get(key, Counter()).get(h, 0)
    print(
        f"  화면 일본어(가나 글줄·한자 화자) 전수 스캔 — 남은 {total}줄 · 기준선 밖 {len(new)}줄"
        + (f" · 기준선보다 줄어든 것 {shrunk}줄(--freeze-kana 로 내린다)" if shrunk else "")
    )
    if new:
        raise SystemExit(
            "❌ 기준선 밖의 일본어가 화면에 남는다 — 파서가 못 본 대본이거나 번역 누락이다:\n    "
            + "\n    ".join(new[:60])
            + (f"\n    … 외 {len(new) - 60}줄" if len(new) > 60 else "")
        )


# ── 롬 전체 잔존 게이트 (2026-10-18, sfc-ed2 꼴) ───────────────────────────────────────────
# 위 `scan`/`check` 는 **대본 모듈 바이트**만 본다. 코드 영역·전투 아카이브·아카이브 밖 문안이 분모에서 빠지면(sfc-ed2 에서 전투 등장 문구 둘이
# 스캐너 필터에 걸려 통째로 빠졌고 일본어로 나왔다) 아무도 못 본다. 그래서 **최종 롬 전체**에서 원문 일본어 런을 센다:
#  - 영역: 롬 원바이트(압축 밖) + 압축 아카이브 7개를 푼 바이트(영역 이름은 `raw`·`gfx_a`…`script`)
#  - 런: 가나 연속 4자↑ (문안 아닌 영역) · 문안 아카이브 battle·script 는 가나·한자 섞인 런 4자↑(가나 하나↑) · 한자만 8자↑ · 반각 가타카나 4바이트↑ — 한자는 우리 한글 코드 쌍을 뺀 SJIS 쌍
#  - 기준선 `textmap/kana_rom_baseline.json` = 영역별 「런 해시 → 개수」(사람이 보고 박은 것 — 코드 바이트가 우연히 가나 꼴인 것 등).
#    **기준선보다 늘면 빌드 실패**, 줄면 알린다(`--freeze-kana` 로 내린다). 영역별 해시라 오프셋이 옮겨져도 안 흔들린다.
ROM_BASELINE = Path(__file__).resolve().parents[1] / "textmap" / "kana_rom_baseline.json"
KANA_RUN = re.compile(rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){4,}")
HW_RUN = re.compile(rb"[\xa1-\xdf]{4,}")
TEXT_AREAS = ("battle", "script")


def _jp_runs(buf: bytes, pairs: set[bytes], need_mixed: int = 4, need_kanji: int = 8):
    """우리 한글 코드 쌍이 아닌 SJIS 두 바이트(가나·한자 꼴)가 이어진 런 — 한글 코드는 한자 선두 범위(0x8A~)에 앉아 정규식만으론 못 가른다.
    **가나가 하나라도 낀 런은 `need_mixed`(4)자↑, 한자만인 런은 `need_kanji`(8)자↑**. 가나 연속만 세면 「…が現れた」처럼 한자가 사이에 낀 짧은 문장이
    가나 런이 3자 이하로 끊겨 샌다(md-ed1·sfc-ed2 가 같은 구멍으로 일본어를 화면에 내보냈다 — 2026-10-18)."""
    i, n, start, cnt, kana = 0, len(buf), 0, 0, 0
    while i < n - 1:
        a, b = buf[i], buf[i + 1]
        is_kana = (a == 0x82 and 0x9F <= b <= 0xF1) or (a == 0x83 and 0x40 <= b <= 0x96)
        is_kanji = (
            (0x88 <= a <= 0x9F or 0xE0 <= a <= 0xEA)
            and (0x40 <= b <= 0xFC and b != 0x7F)
            and buf[i : i + 2] not in pairs
        )
        if is_kana or is_kanji:
            if cnt == 0:
                start, kana = i, 0
            cnt += 1
            kana += is_kana
            i += 2
            continue
        if cnt >= (need_mixed if kana else need_kanji):
            yield buf[start:i]
        cnt = 0
        i += 2 if buf[i : i + 2] in pairs else 1  # 우리 한글 코드 쌍은 두 바이트째로 어긋나지 않게 통째로 넘는다
    if cnt >= (need_mixed if kana else need_kanji):
        yield buf[start:n]


def _runs(region: str, buf: bytes, pairs: set[bytes]):
    if region in TEXT_AREAS:  # 문안 아카이브: 가나·한자 섞인 런(위) + 반각 — 압축 데이터·그래픽에선 우연히 잔뜩 걸리니 여기서만
        for r in _jp_runs(buf, pairs):
            yield "j:" + _h(r), r, buf.find(r)
        for m in HW_RUN.finditer(buf):
            yield "h:" + _h(m.group()), m.group(), m.start()
        return
    for m in KANA_RUN.finditer(buf):
        yield "k:" + _h(m.group()), m.group(), m.start()


def scan_rom(rom: bytes) -> tuple[dict[str, Counter], dict[tuple[str, str], str]]:
    """({영역: Counter(해시: 개수)}, {(영역, 해시): 샘플 문자열})."""
    import archives

    pairs = _hangul_pairs()
    regions: dict[str, bytes] = {"raw": rom}
    for name, (base, *_rest) in archives.ARCHIVES.items():
        regions[name] = b"".join(blk[1] for blk in archives.blocks(rom, base))
    out: dict[str, Counter] = {}
    samples: dict[tuple[str, str], str] = {}
    for region, buf in regions.items():
        c: Counter = Counter()
        for h, run, at in _runs(region, buf, pairs):
            c[h] += 1
            if (region, h) not in samples:
                lo = max(0, at - 4)
                samples[(region, h)] = f"@{at:#x} " + buf[lo : at + len(run) + 6].decode(
                    "cp932", "replace"
                )
        if c:
            out[region] = c
    return out, samples


def check_rom(rom: bytes, *, freeze: bool = False) -> None:
    left, samples = scan_rom(rom)
    total = sum(sum(c.values()) for c in left.values())
    if freeze:
        ROM_BASELINE.write_text(
            json.dumps(
                {k: dict(sorted(c.items())) for k, c in sorted(left.items())},
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"  롬 전체 잔존 기준선 박음: 영역 {len(left)}곳 · 런 {total}")
        return
    base = json.loads(ROM_BASELINE.read_text(encoding="utf-8")) if ROM_BASELINE.exists() else {}
    new, shrunk = [], 0
    for region, c in left.items():
        b = base.get(region, {})
        for h, n in c.items():
            if n > b.get(h, 0):
                new.append(f"[{region}] {h} ×{n - b.get(h, 0)}: {samples[(region, h)]}")
    for region, b in base.items():
        for h, n in b.items():
            shrunk += max(0, n - left.get(region, Counter()).get(h, 0))
    print(
        f"  롬 전체 일본어 잔존 스캔(가나 4자↑·반각 4B↑·한자 8자↑, 압축 해제 포함) — {total}런 · 기준선 밖 {len(new)}"
        + (f" · 기준선보다 줄어든 것 {shrunk}(--freeze-kana 로 내린다)" if shrunk else "")
    )
    if new:
        raise SystemExit(
            "❌ 최종 롬에 기준선 밖의 일본어 런이 남는다 — 분모에서 빠진 문안이다(번역 누락·스캐너 필터):\n    "
            + "\n    ".join(new[:60])
            + (f"\n    … 외 {len(new) - 60}건" if len(new) > 60 else "")
        )
