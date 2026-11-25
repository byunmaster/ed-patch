"""화면 몫으로 남겨 둔 조판 규칙 셋을 구운 롬 짝 표에서 정적으로 센다(마스터 11-02 「1번도 같이 진행해」).

  2-8  가운데 맞춤   손으로 앞 공백을 넣어 가운데 맞춘 줄(오프닝·엔딩 기도문)을 실제 출력 폭(전각 12px · 반각·공백 8px, 줄 끝 `. , …` 는 폭에서 뺌)과
                    글리프 비트맵 잉크 끝으로 재서 좌우 여백 차(= 2 × 중심 어긋남)가 1px 를 넘는 줄을 센다. 앞 패딩은 8a+12b(반각 공백·전각 공백) 라 중심이 2px
                    단위로만 움직인다 — 패딩을 바꿔 어긋남이 줄어드는 줄(고칠 수 있음)은 0 이어야 하고, 그 단위 때문에 못 줄이는 줄은 한도(남김)다.
  2-10 한 줄 문장    줄 가운데서 시작해 다음 줄로 넘어가는 문장이 한 줄(50단위)에 들어가는데 쪼개진 곳. 조판기(`typeset._fresh_sentence`)가 새 줄로 옮기고,
                    이름 변수·앞 구간에 이어 붙는 구간처럼 폭을 모르는 자리만 남는다(한도).
  2-13 쉼표          ⑨ `~는데,` `~지만,` `~만,` 앞 절이 11음절 이하인데 쉼표가 있는 곳은 0. 짧은 연결 어미(`~하고,` `~시고,` `~으며,`) 뒤 쉼표는 한도(규칙 「뺀다」 부류이나
                    부르는 말·나열과 꼴이 같은 애매한 것은 사람 몫이라 목록으로 둔다).

    python3 check_rules_static.py [롬] [--list 축] [--freeze]
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_typeset_rom as R
import common
import hangul_font as H
import typeset as T

BASE = Path(__file__).resolve().parents[1] / "rules_static_baseline.json"
KEYS = ["C8_fix", "C8_res", "S10", "K13_9", "K13_conn", "HUD_fix"]
HARD = ["C8_fix", "K13_9", "HUD_fix"]
SKIP = {"원문 바이트 그대로", "그래픽·표 데이터"}
# 가운데 맞춤 줄 구간(짝 표 주소) → 줄 시작 x. 오프닝 글 영역은 x=24, 엔딩 기도문은 x=16.
CENTER = (("D7E137", "D7E600", 24), ("D707CF", "D708B0", 16))
CENTER_X = 128
LIMIT = 232


def _adv(c: str) -> int:
    return 8 if 0x20 <= ord(c) <= 0x7E else 12


def _ink(c: str):
    if c == "　" or c == " ":
        return None
    if 0x20 <= ord(c) <= 0x7E:
        return (0, 7)
    g = H.glyph12(c)
    cols = []
    for k in range(0, 18, 3):
        v = int.from_bytes(g[k : k + 3], "big")
        for r in ((v >> 12) & 0xFFF, v & 0xFFF):
            cols += [x for x in range(12) if (r >> (11 - x)) & 1]
    return (min(cols), max(cols)) if cols else None


def ink_span(line: str, x0: int):
    s = re.sub(r"[.,…]+$", "", line.rstrip(" 　"))
    x, lo, hi = x0, None, None
    for c in s:
        i = _ink(c)
        if i:
            lo = x + i[0] if lo is None else lo
            hi = x + i[1] + 1
        x += _adv(c)
    return lo, hi


def center_off(line: str, x0: int) -> float | None:
    lo, hi = ink_span(line, x0)
    return None if lo is None else (lo + hi) / 2 - CENTER_X


def best_off(core: str, x0: int) -> float:
    """앞 패딩을 8a+12b 로 바꿔 얻을 수 있는 가장 작은 |중심 어긋남|."""
    lo, hi = ink_span(core, 0)
    c = []
    for a in range(16):
        for b in range(6):
            p = 8 * a + 12 * b
            if hi + p + x0 <= LIMIT + 8:
                c.append(abs((lo + hi) / 2 + p + x0 - CENTER_X))
    return min(c)


def scan_center(rows):
    fix, res = [], []
    for a, kr in rows:
        for lo, hi, x0 in CENTER:
            if lo <= a <= hi and kr.strip() and "↵" not in kr and "⏎" not in kr:
                off = center_off(kr, x0)
                if off is None or abs(off) <= 0.5:
                    continue
                core = kr.lstrip(" 　")
                if abs(off) > best_off(core, x0) + 0.01:
                    fix.append(f"{a} {off:+.1f}px {core[:14]!r}")
                else:
                    res.append(f"{a} {off:+.1f}px {core[:14]!r}")
    return fix, res


def scan_sentence(rows):
    """줄 가운데서 시작해 다음 줄로 넘어가는 한 줄짜리 문장(이름 변수 든 칸 제외)."""
    out = []
    sent = re.compile(r"[.!?…~」』][)」』]*(?= |$)")
    for a, kr in rows:
        if "{" in kr or "<" in kr:
            continue
        for pg in kr.split("⏎"):
            ls = [x for x in pg.split("↵") if not R.HDR.match(x)]
            for i in range(len(ls) - 1):
                x, y = ls[i].rstrip(), ls[i + 1]
                ends = list(sent.finditer(x))
                if not x or not y.strip() or not ends or ends[-1].end() >= len(x):
                    continue
                m = sent.search(y)
                head = x[ends[-1].end() :].strip()
                if head and m and sum(T.width(c) for c in head + " " + y[: m.end()]) <= T.LINE_UNITS:
                    out.append(f"{a} {head} / {y[: m.end()]}")
    return out


def _syl(s: str) -> int:
    return sum(1 for c in s if "가" <= c <= "힣" or c.isalnum())


def scan_comma(rows):
    nine, conn = [], []
    for a, kr in rows:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]*>|\{[^}]*\}", "", kr).replace("↵", " ").replace("⏎", " "))
        for m in re.finditer(r"([가-힣]*(?:는데|인데|지만|만)),(?= )", t):
            pre = t[: m.end() - 1]
            cut = max(pre.rfind(". "), pre.rfind("? "), pre.rfind("! "), pre.rfind("… "), pre.rfind(", "), pre.rfind("〕 "))
            if cut < 0:
                continue  # 조각 머리 — 앞 절을 모른다
            cl = re.sub(r"^〔[^〕]*〕\s*", "", pre[cut + 2 :])
            if _syl(cl) <= 11:
                nine.append(f"{a} {cl}, ")
        for m in re.finditer(r"([가-힣]{2,}(?:시고|하고|되고|있고|없고|으며|하며|이며)),(?= )", t):
            conn.append(f"{a} {m.group(1)}, ")
    return nine, conn


HUD_TABLE = 0xD8F900  # 필드 HUD 전용 지명 표(`patches.HUD_NAMES`) — 포인터 64(뱅크 D8) + 앞 패딩을 붙인 문자열
HUD_BOX_PX = 72  # 박스 안쪽 폭(타일 21~29, x 168~240)
HUD_COUNT = 64


def scan_hud(rom: bytes) -> list[str]:
    """2-8 HUD 지명 박스 가운데 맞춤(마스터 11-04/05) — 새 표의 지명마다 (앞 패딩 + 글자 폭/2) 가 박스 가운데(36px)에서 딱 가운데(±1px)가 아니면서 왼쪽으로 3.5px 넘게 쏠려도(왼 ≤ 오, 마스터 11-08) 센다.
    글자가 박스보다 넓은 이름(길 이름)은 가운데 맞출 수 없어 뺀다. 토큰은 전각 `$80~$87`+1B(2B 12px) · `$14` 4px · 그 밖 1B 8px."""
    base = common.snes2off(HUD_TABLE)
    out = []
    for i in range(HUD_COUNT):
        p = rom[base + 2 * i] | rom[base + 2 * i + 1] << 8
        a = common.snes2off(0xD80000 | p)
        toks = []
        while rom[a] != 0:
            n = 2 if 0x80 <= rom[a] < 0x88 else 1
            toks.append(rom[a : a + n])
            a += n
        lead = 0
        while lead < len(toks) and toks[lead] in (b" ", b"\x80\x00", b"\x14"):
            lead += 1
        end = len(toks)
        while end > lead and toks[end - 1] in (b" ", b"\x80\x00", b"\x14"):
            end -= 1
        px = lambda ts: sum(12 if len(t) == 2 else 4 if t == b"\x14" else 8 for t in ts)
        core, pad = px(toks[lead:end]), px(toks[:lead])
        if core == 0 or core >= HUD_BOX_PX:
            continue
        off = pad + core / 2 - HUD_BOX_PX / 2
        # 마스터 11-08: 딱 가운데가 안 되면 왼쪽 여백을 더 짧게(왼 ≤ 오) — 패딩은 4px 단위(`$14` 4px 빈 칸 · 반각 8 · 전각 12)라 모자람은 4px 미만이다.
        # 획이 칸 오른쪽 끝에서 1px 비므로 off 는 (패딩−want)−0.5: 딱 가운데(±1px, off −1~0)거나 왼쪽 여백이 짧아야(off −3.5 이상 0 이하, 4px 단위 한계) 한다.
        bad = abs(off + 0.5) > 2.0  # 마스터 11-09 「최대한 가운데」: 패딩이 want 에 가장 가까운 4px 배수(거리 ≤ 2px)
        if bad:
            out.append(f"HUD[{i}] 앞 패딩 {pad}px · 글자 {core}px · 가운데 어긋남 {off:+.1f}px (최대한 가운데 — 거리 ≤ 2px)")
    return out


def scan(rom_lines, rom: bytes | None = None):
    rows = []
    for ln in rom_lines:
        f = ln.split("\t")
        if len(f) < 3 or (f[3:4] and f[3] in SKIP) or R.KANA.search(f[2]):
            continue
        rows.append((f[0], f[2]))
    fix, res = scan_center(rows)
    nine, conn = scan_comma(rows)
    return {"C8_fix": fix, "C8_res": res, "S10": scan_sentence(rows), "K13_9": nine, "K13_conn": conn, "HUD_fix": scan_hud(rom) if rom is not None else []}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rom = Path(args[0]) if args and Path(args[0]).suffix == ".sfc" else common.BUILD_DIR / common.BUILD_TAG / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    bad = scan(R.rom_pairs(rom), rom.read_bytes())
    cnt = {k: len(v) for k, v in bad.items()}
    if "--list" in sys.argv:
        print("\n".join(bad[sys.argv[sys.argv.index("--list") + 1]]))
        return
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps({k: cnt[k] for k in KEYS if k not in HARD}, indent=1) + "\n", encoding="utf-8")
        print("기준선 갱신:", cnt)
        return
    base = json.loads(BASE.read_text()) if BASE.exists() else {}
    print(f"규칙 정적 점검 [sfc-ed2] 2-8 고칠 수 있는 어긋남 {cnt['C8_fix']} · 못 줄이는 어긋남 {cnt['C8_res']} · 2-10 {cnt['S10']} · 2-13 ⑨ {cnt['K13_9']} · 짧은 연결 어미 뒤 쉼표 {cnt['K13_conn']} · HUD 지명 가운데 {cnt['HUD_fix']} (기준선 " + " · ".join(f"{k} {v}" for k, v in base.items()) + ")")
    fail = [f"{k} {cnt[k]}" for k in HARD if cnt[k]] + [f"{k} {cnt[k]} > 기준선 {base[k]}" for k in KEYS if k in base and cnt[k] > base[k]]
    for k in HARD:
        for x in bad[k][:5]:
            print(f"  {k} {x}")
    if fail:
        print("규칙 위반:", "; ".join(fail))
        sys.exit(1)
    print("규칙 위반 0")


if __name__ == "__main__":
    main()
