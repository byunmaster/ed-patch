"""오프닝 자막 · 엔딩 나레이션 · 엔딩 대사 — 워드 스크립트 드라이버($14E44)의 표와 문안 영역.

표는 워드 열이다: 상위 니블 = 오프코드(0 문안 · 2 대기 · 4 페이드 · 6 팔레트 · 8 그림 · C 선택), 하위
12비트 = 인자, `FFFF` 로 끝난다. 오프코드 0 의 인자는 **표 머리(a3) 기준 전방 12비트 오프셋**
(`lea (a3,d2.w),a1` → 렌더러 $978C)이라 문안은 표 뒤 4,095B 안에 있어야 한다. 스트림은 대사와 같은
제어코드(`fe 0e` 피치 14 · `01` 줄바꿈 · `06` 끝)라 `scene.parse_stream` 으로 읽는다.

재삽입: 가족(표 묶음 + 문안 영역)마다 영역을 **제자리에서** 다시 채우고(원본 순서 · 짝수 정렬 · 남는
자리는 0), 표의 오프코드 0 워드를 새 오프셋으로 고친다. 영역 뒤는 코드·그래픽이라 넘치면 실패다.
"""

import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import scene
import sysmsg

# (이름, 표 머리들, 문안 영역) — 영역 끝은 다음 자료의 머리(코드 · lea 로 참조되는 자료)
FAMILIES = [
    ("opening", (0x16224,), (0x16268, 0x16684)),  # 오프닝 자막 8 — 뒤는 코드
    ("ending-narr", (0x2DE9E,), (0x2DF0E, 0x2E14E)),  # 엔딩 나레이션 11 — 뒤는 그래픽 자료
    (
        "ending",  # 엔딩 대사 8화면 — 공용 지우기 스트림 <08><06> 이 머리에 있다(나레이션 표도 쓴다)
        (0x2ED38, 0x2ED46, 0x2ED84, 0x2EDB6, 0x2EDD0, 0x2EDDE, 0x2EE04, 0x2EE1E),
        (0x2EE2C, 0x2F1FE),
    ),
]
# 글꼴은 **스트림마다** 고른다 — 정본이 머리에 `<fd85>`(와이드 글꼴 5)를 달면 그 자막만 리소스 5 로 그리고
# 끝에 `<fd80>` 으로 대사 글꼴(리소스 0)로 되돌린다. 칸 16×16·피치 16(`<fe10>`) — 한 줄 14칸.
# 자막 글꼴 = **네오둥근모 16px**(마스터 확정 2026-10-08 — 원판 오프닝·엔딩 자막이 같은 굵은 글꼴이라 되돌렸다. 아래는 그 전 이력).
# 이전 = **Galmuri11**(마스터 확정 2026-09-17 — 네오둥근모·갈무리14·갈무리11 세 후보를 같은 화면으로
# 비교, "크게 느껴진다"는 지적에 갈무리11 로). 그 전엔 네오둥근모였다(2026-09-06, 7줄 화면도 안 잘리고
# 여백비가 원본에 가깝다는 이유) — 그 전엔 Galmuri14 였다가 "붙어 보인다/가독성 저하"로 걷어냈다
# (여백 좌우2px·상하4px 인 원본 대비 Galmuri14 는 1px·2px 뿐이었다). `docs/devlog.md` 2026-09-06·09-17.
FONT_ID = 5
FONT_TAG = "<fd85>"
# 네오둥근모면 **반각(ASCII)도 리소스 5** 로 그린다 — 머리에 `<fd05>`(반각 글꼴 5), 끝에 `<fd00>`(반각 글꼴 되돌림).
# 반각 글리프는 리소스 1(대사창과 공유, 원판 꼴) 뿐이라 부호가 1~2px 점이었다(마스터 2026-10-08). 전진은 피치/2 그대로.
NARROW_ON, NARROW_OFF = "<fd05>", "<fd00>"
FONT_CELL = int(os.environ.get("MD_CAPTION_CELL", "16"))
# 후보 비교용 — 정본은 상수, `MD_CAPTION_FONT` 로 한 번씩 바꿔 구워 본다(실험 전용, 배포 빌드는 상수를 고친다).
FONT_SRC = os.environ.get("MD_CAPTION_FONT", "neodgm")


def font_tags(ours: str) -> str:
    """정본 문안의 글꼴 머리·꼬리에 반각 글꼴 선택을 덧붙인다(빌드 시점 — 정본은 `<fd85>`…`<fd80>` 그대로)."""
    if FONT_SRC != "neodgm" or FONT_TAG not in ours or NARROW_ON in ours:
        return ours
    return ours.replace(FONT_TAG, FONT_TAG + NARROW_ON, 1).replace("<fd80>", "<fd80>" + NARROW_OFF, 1)
WIDTH = 16  # 피치 14 × 16 = 224px
WIDTH_P16 = 14  # 피치 16 × 14 = 224px (네오둥근모)
OFF_MAX = 0xFFF
# 한 화면 줄 수 상한 — 엔딩은 **3줄이면 첫 줄이 위로 밀려 사라진다**(마스터 실기 2026-09-26, 원문도 전 화면 2줄 이하).
# 오프닝은 7줄까지 본다(docs/status.md 「화면 줄 수 상한」).
MAX_LINES = {"ending-narr": 2, "ending": 2}
# 엔딩 자막 창(픽셀) — 렌더러는 글을 w/8×h/8 타일 비트맵(**플레인 B**, 128칸 폭 = 줄 256B)에 그리고, 글자
# 시작이 `w − 26`px 를 넘으면 스스로 줄을 바꾼다(`$a9b8`: 커서 바이트 > w/2 − 13). 원본은 나레이션·대사가 한
# 서술자(0x2DE7A, x48·y184·w240·h48)를 같이 쓴다. 나레이션만 **x48·w256** 으로 넓혀 들여쓰기 없이 x=48 에서
# 시작한다 — 대사의 이름 시작(x=48)과 같은 자리(마스터 2026-09-26: 「오른쪽으로 치우쳐 보인다」→ 대사와 맞춤).
# VRAM: 비트맵 $3040~ 뒤 $46C0~ 는 나레이션 동안 0 으로만 지워지고(w256 = 192타일 → $4840) 초상 적재($180DA)는
# 나레이션이 끝난 뒤다(write BP 실측). ⚠ 대사는 초상마다 비트맵 자리가 달라($5B00·$6480·$7FC0·$89C0) 그 뒤가
# 전부 초상 자료라 못 넓힌다(네 변형 VRAM 실측).
WINDOW_W = {"ending-narr": 256, "ending": 240}
NARR_WINDOW = struct.pack(">6H", 48, 184, 256, 48, 0x0200, 0x0002)
NARR_SETUP = (
    0x2DDF2,
    0x2DE7A,
)  # 창 준비 루틴(서술자 복사 → 비트맵·네임테이블) — 사본을 꼬리에 둔다
NARR_SETUP_LEA = 0x2DE08  # 그 안의 `lea $2de7a.l,a0` 피연산자
NARR_CALL = 0x2DE8C  # 나레이션의 `jsr $2ddf2.l` 피연산자(0x2DE8A)
# 나레이션이 끝나면 **자막 띠(플레인 B row 23~28 × col 0~39)를 통째로 비운다** — 대사 창(x48~288, col 6~35)은
# 나레이션이 넓힌 칸(col 36·37)을 다시 안 그려서, 옛 매핑이 초상 적재로 채워진 타일을 가리켜 조각이 떴다(실측).
# 초상은 이 뒤에 그려지므로 띠를 비워도 잃는 게 없다. 나레이션의 `jsr $14e44.l`(0x2DE96) 을 이 스텁으로 돌린다.
# 손인코딩 — 디스어셈블 검산(devlog 09-26):
#   jsr $14e44.l · movem.l d0-d3/a0-a1,-(a7) · move.w sr,-(a7) · move.w #$2700,sr
#   lea $c00004.l,a0 · lea $c00000.l,a1 · move.w #$8f02,(a0) · moveq #5,d1 · moveq #0,d2
#   move.l #$77000003,d0 (VRAM 쓰기 $F700 = $E000+23*256) · row: move.l d0,(a0) · moveq #19,d3
#   col: move.l d2,(a1) · dbra d3,col · add.l #$1000000,d0 · dbra d1,row
#   move.w (a7)+,sr · movem.l (a7)+,d0-d3/a0-a1 · rts
# ⚠ clr.l 은 68000 에서 먼저 읽는다 — VDP 데이터 포트엔 move 로만 쓴다.
# ⚠ 자막은 **플레인 B** 다 — `$FF200A`=$C000 은 플레인 주소가 아니라 타일 속성(우선순위+팔레트)이었다.
#   처음에 플레인 A·64칸으로 짚어 엉뚱한 칸을 지웠다(레이어 토글로 확인).
NARR_CLEAR = bytes.fromhex(
    "4eb900014e4448e7f0c040e746fc270041f900c0000443f900c0000030bc8f0272057400"
    "203c7700000320807613228251cbfffcd0bc0100000051c9ffee46df4cdf030f4e75"
)
NARR_DRIVER_CALL = 0x2DE98  # 나레이션의 `jsr $14e44.l` 피연산자(0x2DE96)
# 꼬리로 옮기는 가족 — (표 머리, 표 포인터 피연산자 자리). 드라이버는 오프코드 0 의 인자를
# **표 머리 기준 12비트 전방 오프셋**으로 읽으므로 표와 문안을 같이 옮기면 그대로 돈다.
# 제자리 영역이 만원이라(오프닝 1,052/1,052B · 나레이션 576/576B) 원문에 있는 말을 눌러 쓰고 있었다
# (2026-09-06 대조: 「어쩌면」·「필사적으로 싸웠고」·「살해」·「16세 생일」 …).
# ⚠ 옛 영역은 **0 으로 지운다** — 원문 바이트를 남기면 「남은 일본어」 검사가 그만큼 눈이 먼다.
RELOCATE = {
    "opening": [(0x16224, 0x13782)],  # lea $16224.l,a3 @0x13780
    "ending-narr": [(0x2DE9E, 0x2DE92)],  # lea $2de9e.l,a3 @0x2de90
    # 엔딩 대사 — 표 여덟이 저마다 `lea $2edXX.l,a3` 로 불린다(978B 제자리가 이름 한 줄·들여쓰기로 넘쳤다)
    "ending": [
        (0x2ED38, 0x2C34C),
        (0x2ED46, 0x2C452),
        (0x2ED84, 0x2C4E8),
        (0x2EDB6, 0x2C5D2),
        (0x2EDD0, 0x2C656),
        (0x2EDDE, 0x2C682),
        (0x2EE04, 0x2C76C),
        (0x2EE1E, 0x2C7F0),
    ],
}
EXPECT = (
    10,
    39,
)  # 표 · 고유 스트림 (2026-09-05 실측 — 지우기 스트림 <08><06> 을 표 9개가 같이 쓴다)
MAP_JSON = common.GAME_DIR / "textmap" / "captions.json"


def words(d: bytes, base: int) -> list[tuple[int, int, int]]:
    """표 → [(워드 자리, 오프코드, 인자)] — FFFF 앞까지."""
    out = []
    p = base
    while True:
        w = struct.unpack(">H", d[p : p + 2])[0]
        if w == 0xFFFF:
            return out
        out.append((p, w >> 12, w & 0xFFF))
        p += 2


def streams(d: bytes) -> dict[int, dict]:
    """문안 시작 → {stream, family, refs:[(표 머리, 워드 자리)]}."""
    out: dict[int, dict] = {}
    for _name, bases, _area in FAMILIES:
        for base in bases:
            for pos, op, arg in words(d, base):
                if op != 0:
                    continue
                t = base + arg
                if t not in out:
                    st = scene.parse_stream(d, t)
                    fam = next(n for n, _, (a, b) in FAMILIES if a <= t < b)
                    out[t] = {"stream": st, "family": fam, "refs": []}
                out[t]["refs"].append((base, pos))
    return dict(sorted(out.items()))


def targets(ws: list, base: int) -> list[tuple[int, int]]:
    """표 워드 → [(오프코드, 인자)] — 오프코드 0 의 인자는 **원본 대상 자리**로 푼다(옮겨도 다시 잴 수 있게)."""
    return [(op, base + arg if op == 0 else arg) for _pos, op, arg in ws]


SENTENCE_END = tuple(".?!…」")


def end_warnings(d: bytes, textmap: dict) -> list[str]:
    """엔딩 화면 끝이 문장 끝이 아닌 자리 — **경고만**(마스터 원칙: 웬만하면 화면마다 완결, 여의치 않으면 분배)."""
    import re

    out = []
    for t, e in streams(d).items():
        ours = textmap.get(f"{t:06x}", {}).get("ours", "")
        if e["family"] not in MAX_LINES or not ours:
            continue
        tail = re.sub(r"<[^>]*>", "", ours).rstrip()
        if tail and not tail.endswith(SENTENCE_END):
            out.append(f"  ⚠ captions {t:06x}: 화면 끝이 문장 끝이 아니다 — …{tail[-8:]!r}")
    return out


def check(d: bytes) -> None:
    strs = streams(d)
    ntab = sum(len(b) for _, b, _ in FAMILIES)
    for name, _, (lo, hi) in FAMILIES:
        mine = [s for s in strs.values() if s["family"] == name]
        used = max(s["stream"].end for s in mine) - lo
        print(f"  {name}: 스트림 {len(mine)} · 영역 {lo:#x}~{hi:#x} {hi - lo}B 중 {used}B")
        if any(s["stream"].end > hi for s in mine):
            raise SystemExit(f"{name}: 스트림이 영역을 넘는다")
    if (ntab, len(strs)) != EXPECT:
        raise SystemExit(f"자막 분모가 갈렸다 {(ntab, len(strs))} (기대 {EXPECT})")
    if MAP_JSON.exists():
        tm = json.loads(MAP_JSON.read_text(encoding="utf-8"))
        for w in end_warnings(d, tm):
            print(w)
        row = []
        narr = [t for t, e in strs.items() if e["family"] == "ending-narr"]
        for n, t in enumerate(narr):
            ours = tm.get(f"{t:06x}", {}).get("ours", "")
            if ours:
                row.append(f"N{n + 1}=i{narr_layout(f'{t:06x}', ours)[1]}")
        print("  나레이션 시작 x: " + " ".join(row))
        dl = [
            t
            for t, e in strs.items()
            if e["family"] == "ending" and tm.get(f"{t:06x}", {}).get("ours")
        ]
        print(
            "  대사 배치: "
            + " ".join(
                f"D{n + 1}={dlg_layout(f'{t:06x}', tm[f'{t:06x}']['ours'])[1]}"
                for n, t in enumerate(dl)
            )
        )


def seed(d: bytes) -> None:
    strs = streams(d)
    cur = json.loads(MAP_JSON.read_text(encoding="utf-8")) if MAP_JSON.exists() else {}
    lines = []
    fam = None
    for t, e in strs.items():
        if e["family"] != fam:
            fam = e["family"]
            lines.append(f"# {fam}")
        st = e["stream"]
        k = f"{t:06x}"
        cur.setdefault(k, {"jp": sysmsg.jp_key(st), "ours": ""})
        lines.append(f"{k}\t{st.end - t}B\t{len(e['refs'])}ref\t{sysmsg.render(st)!r}")
    MAP_JSON.parent.mkdir(exist_ok=True)
    MAP_JSON.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    out = common.OUT_DIR / "text" / "captions.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {MAP_JSON}: {len(cur)} · 원문 {out}")


def cells(s: str) -> float:
    """화면 칸 — 이 렌더러는 **1바이트로 싣는 글자(ASCII)가 반각**이다. `krwrap.text_width` 는 `. , ! ?` 를
    전각으로 세지만(다른 기종 규칙) 여기선 반각 글리프(리소스 1)로 나간다(2026-09-26 실측: 「…지배한다.」 188px)."""
    return sum(0.5 if ord(c) < 0x80 else 1 for c in s)


def _width_errors(k: str, ours: str, fam: str | None = None) -> list[str]:
    import re

    # 피치가 폭을 정한다 — **마지막** 피치 태그가 이긴다. 엔딩은 `<fe10><fe0e>` 라 피치 14 다
    # (2026-09-26 실측: 전각 14px·반각 7px. 전엔 `<fe10>` 만 보고 14칸으로 막아 멀쩡한 줄을 깎았다).
    pitches = re.findall(r"<fe(0e|10)>", ours)
    p16 = bool(pitches) and pitches[-1] == "10"
    win = WINDOW_W.get(fam, 240)
    limit = WIDTH_P16 if p16 else win / 14
    errs = []
    for ln in re.sub(r"<[^>]*>", "", ours).split("\n"):
        ln = ln.rstrip()
        w = cells(ln)
        if w > limit:
            errs.append(f"captions {k}: 줄 {w}칸 > {limit:.2f}: {ln!r}")
        # 🔴 피치 14 는 **글자 시작**이 `w − 26`px 을 넘으면 렌더러가 스스로 줄을 바꾼다 — 3줄이 되어 첫
        # 줄이 밀려 사라진다(2026-09-26 실측: 창 240 에서 15.5칸 시작 「.」은 넘어가고 15.0칸 시작 「」」은
        # 멀쩡했다. 루틴 `$a9b8` 로 확인). 폭 합만 보면 이걸 못 잡는다.
        elif (
            not p16
            and ln
            # 반각 부호(. , ! ?)는 엔진 비교에 4px 더 허용(`tools/punctwrap.py`)
            and (w - cells(ln[-1])) * 14 > win - 26 + (4 if ln[-1] in ".,!?" else 0)
        ):
            errs.append(
                f"captions {k}: 끝 글자가 {w - cells(ln[-1])}칸에서 시작 — 자동 줄바꿈: {ln!r}"
            )
    return errs


# 엔딩 **나레이션** 배치(초상화 없는 화면만, 대사 장면은 `dlg_layout` 이 원래대로) — 마스터 10-08: 「그림 안에 들어오는 문장은 그림 왼쪽 끝 기준, 그림 폭을 넘치는 긴 문장은 왼쪽으로 한두 칸」
# (한 글자 정도만 넘치면 그대로 그림 왼쪽 끝에 맞추고 오른쪽으로 삐져나가도 된다).
# 실측(마스터 캡처 ed1-kr-0000~0031): 그림 = x64~256(폭 192) 전 장면 같다. 엔딩 피치 14·반각 7px, 글자 시작은 창 원점
# 첫 글자 **잉크 시작 = 49 + 7n**(실화면 실측 n=0:49 · 1:56 · 3:70 — 칸 원점이 아니라 잉크 기준) ⇒ n=2 가 x≈63(그림 왼쪽 끝 64 와 1px 안). 블록(한 화면) 단위로 같은 n —
# 줄마다 들쑥날쑥하지 않게. 이름 줄과 이어지는 줄의 상대 들여쓰기(「이름「」 폭만큼 반각)는 문안 안에 있어 그대로 유지된다.
FRAME_X = 64
FRAME_W = 192
IND_BASE = 2  # 반각 둘 = 14px → 첫 글자 잉크 x≈63 (실화면 실측: 잉크 시작 = 49 + 7n)
IND_STEP_PX = 7
FIT_OVER_PX = 28  # 마스터 10-08: 한 글자 정도 넘침(ed1-kr-0004 = 시작 x63 에서 24px)은 그림 왼쪽 끝 기준 그대로 — 오른쪽으로 삐져나가도 된다
CELL_PX = 14  # 엔딩 피치
START_X = 63  # n=IND_BASE 일 때 첫 글자 잉크 시작


def block_indent(lines: list[str]) -> tuple[int, int]:
    """한 화면 블록의 들여쓰기 반각 수 n 과 넘침 px. 넘침 ≤ 16px 이면 n=3(그림 왼쪽 끝), 더 넘치면 넘친 만큼(반각 단위) 왼쪽으로."""
    import math

    w = max((cells(ln.rstrip()) * CELL_PX for ln in lines), default=0)
    over = START_X + w - (FRAME_X + FRAME_W)
    if over <= FIT_OVER_PX:
        return IND_BASE, max(0, round(over))
    return max(0, IND_BASE - math.ceil(over / IND_STEP_PX)), round(over)


def _place(k: str, head: str, lines: list[str], tail: str, fam: str) -> tuple[str, int]:
    n, _over = block_indent(lines)
    for m in range(n, -1, -1):  # 창 wrap 게이트를 못 넘으면 더 왼쪽으로
        moved = head + "\n".join(" " * m + ln for ln in lines) + tail
        if not _width_errors(k, moved, fam):
            return moved, m
    return head + "\n".join(lines) + tail, 0


def narr_layout(k: str, ours: str) -> tuple[str, int]:
    """나레이션 화면 배치 — `block_indent` 규칙(그림 왼쪽 끝 기준, 넘치면 왼쪽). 반환: (배치된 문안, 들여쓰기 반각 수)."""
    import re

    head, body, tail = re.match(r"((?:<[^>]*>)*)(.*?)((?:<[^>]*>)*)$", ours, re.DOTALL).groups()
    return _place(k, head, [ln.lstrip(" ") for ln in body.split("\n")], tail, "ending-narr")


def dlg_layout(k: str, ours: str) -> tuple[str, int]:
    """엔딩 대사 배치 — **원래대로**(마스터 10-08: 「캐릭터 대사 장면은 그대로 유지」): 이름 있는 화면(「이름「…」)은 그대로 x=48(n=0),
    이름 없는 이어지는 화면은 반각 둘(14px)을 들이고, 창 wrap 게이트를 못 넘으면 그대로 둔다. 초상화가 그림 가장자리를 덮는
    장면이라 그림 왼쪽 끝 기준 규칙(`block_indent`)을 적용하지 않는다. 반환: (배치된 문안, 들여쓰기 반각 수)."""
    import re

    head, body, tail = re.match(r"((?:<[^>]*>)*)(.*?)((?:<[^>]*>)*)$", ours, re.DOTALL).groups()
    first = body.split("\n")[0].lstrip(" ")
    if not first.startswith("「") and "「" in first:
        return ours, 0
    moved = head + "\n".join("  " + ln for ln in body.split("\n")) + tail
    if not _width_errors(k, moved, "ending"):
        return moved, 2
    return ours, 0


def font5_chars(textmap: dict) -> set[str]:
    """리소스 5 로 그리는 자막이 쓰는 글자 — 그만큼만 글리프를 만든다."""
    import re

    out: set[str] = set()
    for e in textmap.values():
        if FONT_TAG in e.get("ours", ""):
            out.update(re.sub(r"<[^>]*>", "", e["ours"]))
    return out


def plan(
    d: bytes, textmap: dict, encode, tail_at: int | None = None
) -> list[tuple[str, int, bytes]]:
    """정본 → 쓰기 목록. 번역이 하나라도 있는 가족만 영역·표를 다시 쓴다.

    `tail_at` 을 주면 `RELOCATE` 가족은 **표+문안을 꼬리로** 옮기고 표 포인터를 고친다(제자리 칸을
    안 쓰므로 문안 길이가 자유롭다). 옛 영역은 0 으로 지운다.
    """
    strs = streams(d)
    writes: list[tuple[str, int, bytes]] = []
    errs: list[str] = []
    newpos: dict[int, int] = {}
    areas: dict[str, bytes] = {}
    touched_fams = set()
    for name, _bases, (lo, hi) in FAMILIES:
        mine = [(t, e) for t, e in strs.items() if e["family"] == name]
        area = bytearray()
        for t, e in mine:
            st = e["stream"]
            k = f"{t:06x}"
            ent = textmap.get(k)
            if ent and ent.get("ours"):
                if ent["jp"] != sysmsg.jp_key(st):
                    raise SystemExit(f"captions {k}: 원문 해시가 갈렸다")
                ours = ent["ours"]
                if name == "ending-narr":
                    ours, _ = narr_layout(k, ours)
                elif name == "ending":
                    ours, _ = dlg_layout(k, ours)
                errs += _width_errors(k, ours, name)
                n = len(ours.split("\n"))
                if n > MAX_LINES.get(name, 99):
                    errs.append(f"captions {k}: {n}줄 > {MAX_LINES[name]}줄 ({name})")
                ours = font_tags(ours)
                body = b"".join(tk.raw for tk in sysmsg._tokens_from_ours(st, ours, encode))
                touched_fams.add(name)
            else:
                body = d[t : st.end]
            if len(area) & 1:
                area.append(0)
            newpos[t] = lo + len(area)
            area += body
        if tail_at is not None and name in RELOCATE and name in touched_fams:
            areas[name] = bytes(area)  # 자리는 표 길이를 안 뒤에 잡는다(아래 2패스)
            continue
        if len(area) > hi - lo:
            errs.append(f"captions {name}: 영역 {hi - lo}B 를 {len(area) - (hi - lo)}B 넘는다")
            continue
        area += b"\x00" * (hi - lo - len(area))
        if name in touched_fams:
            writes.append((f"captions:{name}", lo, bytes(area)))
    if errs:
        raise SystemExit("\n".join(errs))
    moved: dict[int, int] = {}  # 원래 표 머리 → 꼬리의 표 머리
    local: dict[str, dict[int, int]] = {}  # 가족 → {스트림: 그 가족 블롭 안의 자리}(사본용)
    if tail_at is not None:
        cur = tail_at
        for name, tables in RELOCATE.items():
            if name not in areas:
                continue
            # 표를 먼저 줄지어 놓고 그 뒤에 문안 — 오프셋이 표 머리 기준 **전방** 12비트라서다
            for base, _ptr in tables:
                moved[base] = cur
                cur += len(words(d, base)) * 2 + 2
            text_at = cur
            lo = next(a for n, _b, (a, _h) in FAMILIES if n == name)
            for t in list(newpos):
                if strs[t]["family"] == name:
                    newpos[t] = text_at + (newpos[t] - lo)  # 옛 영역 기준 → 꼬리 기준
            # ⚠ 표가 **다른 가족의 스트림**을 가리키기도 한다(공용 지우기 스트림 `<08><06>` — 문서 6절).
            # 옮긴 표에서 그 자리를 12비트로 못 짚으므로 **사본을 블롭에 같이 싣는다**(2B 짜리다).
            blob = bytearray(areas[name])
            for base, _ptr in tables:
                for op, t in targets(words(d, base), base):
                    if op != 0 or t in local.get(name, {}) or strs[t]["family"] == name:
                        continue
                    if len(blob) & 1:
                        blob.append(0)
                    # 🔴 **원본 newpos 를 덮지 않는다** — 제자리에 남는 다른 가족의 표가 그 값을 쓴다
                    local.setdefault(name, {})[t] = text_at + len(blob)
                    blob += d[t : strs[t]["stream"].end]
            areas[name] = bytes(blob)
            writes.append((f"captions-tail:{name}", text_at, areas[name]))
            for base, ptr in tables:
                writes.append((f"captions-ptr:{base:06x}", ptr, struct.pack(">I", moved[base])))
            _lo, _hi = next((a, h) for n, _b, (a, h) in FAMILIES if n == name)
            writes.append((f"captions:{name}", _lo, b"\x00" * (_hi - _lo)))  # 옛 영역 지우기
            cur = text_at + len(areas[name])
            cur += cur & 1
        if "ending-narr" in areas:
            lo_, hi_ = NARR_SETUP
            if d[NARR_CALL - 2 : NARR_CALL + 4] != b"\x4e\xb9" + struct.pack(">I", lo_):
                raise SystemExit("captions: 나레이션 창 호출 자리가 원본과 다르다")
            if d[NARR_SETUP_LEA - 2 : NARR_SETUP_LEA + 4] != b"\x41\xf9" + struct.pack(">I", hi_):
                raise SystemExit("captions: 창 준비 루틴의 서술자 lea 가 원본과 다르다")
            stub = bytearray(d[lo_:hi_])  # 상대 분기(dbra)뿐이라 통째로 옮겨도 돈다
            desc = cur + len(stub)
            o = NARR_SETUP_LEA - lo_
            stub[o : o + 4] = struct.pack(">I", desc)
            writes.append(("captions-tail:narr-window", cur, bytes(stub) + NARR_WINDOW))
            writes.append(("captions-call:narr-window", NARR_CALL, struct.pack(">I", cur)))
            cur = desc + len(NARR_WINDOW)
            if d[NARR_DRIVER_CALL - 2 : NARR_DRIVER_CALL + 4] != NARR_CLEAR[:6]:
                raise SystemExit("captions: 나레이션 드라이버 호출 자리가 원본과 다르다")
            writes.append(("captions-tail:narr-clear", cur, NARR_CLEAR))
            writes.append(("captions-call:narr-clear", NARR_DRIVER_CALL, struct.pack(">I", cur)))
            cur += len(NARR_CLEAR)
    # 표 — 참조하는 문안이 하나라도 옮겨졌으면 표 전체를 다시 쓴다(오프코드 0 워드만 바뀐다)
    for _name, bases, _area in FAMILIES:
        for base in bases:
            ws = words(d, base)
            if not any(strs[base + a]["family"] in touched_fams for _, op, a in ws if op == 0):
                continue
            seq = targets(ws, base)
            here = moved.get(base, base)  # 옮겼으면 꼬리의 표 머리가 기준이다
            tbl = bytearray()
            for op, arg in seq:
                if op == 0:
                    tgt = local.get(_name, {}).get(arg, newpos[arg])
                    arg = tgt - here
                    if not 0 <= arg <= OFF_MAX:
                        raise SystemExit(
                            f"captions 표 {base:#x}: 오프셋 {arg:#x} 이 12비트를 넘는다"
                        )
                tbl += struct.pack(">H", op << 12 | arg)
            tbl += b"\xff\xff"
            writes.append((f"captions-table:{base:06x}", here, bytes(tbl)))
    return writes


def allowed_tail(at: int, size: int) -> dict[str, tuple[int, int]]:
    """꼬리로 옮길 때 여는 자리 — 블롭·옮긴 표·표 포인터 피연산자.

    ⚠ 옮긴 표는 `allowed()` 가 이미 **제자리** 범위로 연 라벨과 이름이 같다. 두 자리 중 어디에 써도
    되게 **합집합**으로 넓힌다(제자리 자리는 옛 영역 지우기에 쓴다)."""
    out = {f"captions-tail:{n}": (at, at + size) for n in [*RELOCATE, "narr-window", "narr-clear"]}
    out["captions-call:narr-window"] = (NARR_CALL, NARR_CALL + 4)
    out["captions-call:narr-clear"] = (NARR_DRIVER_CALL, NARR_DRIVER_CALL + 4)
    out.update({f"captions-ptr:{b:06x}": (p, p + 4) for ts in RELOCATE.values() for b, p in ts})
    return out


def widen_for_tail(base: dict, at: int, size: int) -> dict:
    """`allowed()` 의 표 라벨을 꼬리까지 넓힌다 — 옮긴 표는 꼬리에 쓰인다."""
    out = dict(base)
    for b, _p in (bp for ts in RELOCATE.values() for bp in ts):
        k = f"captions-table:{b:06x}"
        lo, hi = out.get(k, (at, at + size))
        out[k] = (min(lo, at), max(hi, at + size))
    return out


def allowed(d: bytes) -> dict[str, tuple[int, int]]:
    out = {}
    for name, bases, (lo, hi) in FAMILIES:
        out[f"captions:{name}"] = (lo, hi)
        for base in bases:
            out[f"captions-table:{base:06x}"] = (base, base + len(words(d, base)) * 2 + 2)
    return out


if __name__ == "__main__":
    d = common.rom()
    if "--seed" in sys.argv:
        seed(d)
    else:
        check(d)
