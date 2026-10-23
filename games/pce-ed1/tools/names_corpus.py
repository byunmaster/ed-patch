"""공용 이름 검사(`scripts/check/check_names.py`)의 pce-ed1 어댑터 — `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름을 **들지 않는다**(마스터 10-07 「워커는 독자 데이터를 못 갖는다」) — 원문(`work/derived/`)과 우리 문안(`script/`)을
읽어 짝지어 넘길 뿐이다. 미번역 줄은 None 으로 낸다(분모에 든다). 화면에 나가는 값을 그대로 넘기려고, 빌드가 고르는 것과
같은 순서로 우리 줄을 고른다(시스템 고정표 = `names.json` 덮어쓰기 → 사전 · 전투 이름칸 = `battle.kr_names`).

갈래(마스터 10-07 「대사·비대사를 나눠라」): `"dialog"` = 대사 창에 흐르는 글(씬 대사 · 전투 문구 · 시스템 메시지 — 이어 쓰는
문장이라 지명을 띄어 쓴다) · `"slot"` = 칸에 담긴 이름(입장 배너 `scn000` 의 `raw` 항목 · 지명·파일 선택·아이템·주문 고정표 · 메뉴 라벨 ·
부팅 화면 · 전투 이름칸 · HUD 판 — 칸 폭에 맞춰 붙여 쓴다). 오프닝·엔딩 자막은 원문 글이 없어 이 어댑터가 안 낸다(아래).

자리 이름 규약: `scnNNN:<열쇠>` · `battle:<열쇠>` · `battle-name:<rel>:<블록>:<오프셋>` · `sysmsg:<주소>` ·
`fixed:<가족>#<순번>` · `label:<주소>` · `screen:<열쇠>#<줄>` · `extras:<열쇠>#<항목>` · `inline:<열쇠>` · `hud:<원문>`.

원문 **글**이 없는 자리(오프닝·엔딩 음성 자막 · 장 제목 띠 · 엔딩 카드 · 오마케 간판)는 `jp` 를 빈 줄로 **우리 줄만** 낸다(`_subs`) —
이름 검사는 못 하지만(짝이 없다) 화면 일본어 게이트는 우리 줄의 가나·한자를 잡는다. 도감(rel 459~463)은 `_dex` — 미착수라 우리 줄 None.
⚠ 스태프롤(`staffroll.py`)은 안 낸다 — 사람 이름만 원문이 남는 게 확정이라 일본어 게이트가 늘 울리고, 이름 표는 게임 폴더에 두는 예외(마스터 10-08).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle
import common
import hud_plate
import messages as M
import sysbuild
import sysstrings as S

CANON = "ed1"  # 공통 문안 정본(`shared/canon/ed1.json` — PS1 씨앗, 마스터 10-08) — `check_canon.py` 가 읽는다
CANON_GATE = True  # 어긋남 0(승인 예외 제외)이면 켠다 — 켜면 `check_canon` 어긋남이 실패다

DERIVED = common.GAME_DIR / "work" / "derived"
SCRIPT = common.GAME_DIR / "script"


def _load(p: Path):
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


_TAG = re.compile(r"\{([0-9A-Fa-f]{2,})\}")
_HARD = re.compile(r"\{(?:00|06|07|0[Ff][0-9A-Fa-f]*)\}")  # 종료·점프
_END = re.compile(r"(?:\{(?:00|06|07|0[Ff][0-9A-Fa-f]*)\})+$")


def _plain(s):
    """제어 태그를 걷어 정본의 줄 전체 대조(`^…$`)에 걸리게 한다 — 태그가 줄 끝에 붙어 정본 검사가 전투·시스템 문구를 못 쟀다(md 실측 10-08).
    `{02}`(대상 이름 자리) → `{name}`, 줄바꿈·색·대기 따위는 글이 아니라 뺀다. 🔴 **종료·점프(`00`·`06`·`07`·`0F…`)는 뺄 수 없다** —
    메시지 둘이 이어 붙어 정본 열쇠가 거짓으로 걸린다(「의 독이 사라졌다.」+「…입구로 돌아갑니다」). 끝에 오면 버리고, 가운데면 `┃` 로 막는다."""
    if not isinstance(s, str):
        return s
    s = _END.sub("", s)
    s = _HARD.sub("┃", s)
    return _TAG.sub(lambda m: "{name}" if m.group(1).upper() == "02" else "", s)


_PARTICLES = "をはがにのとでもへや"


def _pair(jp, kr):
    """전투·시스템 한 줄 → (원문, 우리 줄) — 태그를 걷고(`_plain`), **이름이 앞에 숨은 조각**(「は逃げ出した。」 — 엔진이 런타임에 이름을 앞에 붙인다)에는
    양쪽에 `{name}` 을 앞세운다. 안 그러면 정본 열쇠(`{name}は逃げ出した。`)의 줄 전체 대조가 조각 줄에 안 걸려 **전투 문구의 절반을 못 쟀다**(느슨 203 중 엄격 114)."""
    jp, kr = _plain(jp), _plain(kr)
    if isinstance(jp, str) and jp[:1] in _PARTICLES:
        jp = "{name}" + jp
        if kr is not None:
            kr = "{name}" + kr
    return jp, kr


def _scenes():
    for p in sorted((DERIVED / "messages").glob("scn*.json")):
        kr = M.load_translations(int(p.stem[3:]))  # 입장 배너(scn000)는 사전에서 풀린 문안
        for r in json.loads(p.read_text("utf-8")):
            e = kr.get(r["key"]) or {}
            # `raw` = 씬 0 의 입장 배너 표(원판이 가운데맞춤 공백을 구워 낸 고정폭 칸) — 비대사
            yield (
                f"{p.stem}:{r['key']}",
                r["jp"],
                e.get("t") or None,
                "slot" if e.get("raw") else "dialog",
            )


SLOT_OPS = frozenset(range(0x0A, 0x0F))  # 이름·아이템·수 자리 — 엔진이 런타임에 글을 끼운다


def _joined():
    """**이어진 문장** — 메시지 조각(종료 없이 옵코드 앞에서 끊긴 것)을 그 뒤로 이어 읽히는 메시지와 한 줄로 낸다.

    🔴 이 어댑터는 조각 단위로만 줄을 내서 이름 슬롯·점프로 이어진 문장(「…제르만」+슬롯+「제르만님께서도」)을 이름·정본·인사 검사기 셋이 못 봤다
    (sfc-ed2 실측 부류, 10-20). 조각 끝에서 앞으로 **글이 아닌 바이트**(슬롯·쪽·조건 옵코드)를 건너 다음 메시지 머리나 `0F` 점프 목적지에 닿으면
    둘을 이어 한 줄로 낸다(슬롯 자리는 `{name}`). 자리 이름 `scnNNN:<열쇠>+<열쇠>`.
    """
    import containers

    blocks = {}
    for c in containers.scan():
        for b in c["blocks"]:
            blocks.setdefault(b["id"], b["data"])
    for p in sorted((DERIVED / "messages").glob("scn*.json")):
        sid = int(p.stem[3:])
        blk = blocks.get(sid)
        if blk is None:
            continue
        kr = M.load_translations(sid)
        msgs = {m.start: m for m in M.parse(blk)}
        for m in msgs.values():
            if m.terminated or m.pinned:
                continue
            i, slot, seen = m.end, False, 0
            nxt = []
            while i < len(blk) and seen < 12:
                seen += 1
                if i in msgs and i != m.start:
                    nxt.append((msgs[i], slot))
                    break
                b = blk[i]
                if b == 0x0F and i + 2 < len(blk):
                    t = (blk[i + 1] | blk[i + 2] << 8) - M.BASE
                    if t in msgs:
                        nxt.append((msgs[t], slot))
                    break
                if b in SLOT_OPS:
                    slot = True
                    i += 1
                elif b in (0x01, 0x03, 0x05):
                    i += 1
                elif 0x11 <= b <= 0x15 and i + 2 < len(blk):  # 조건·플래그 — 한 갈래만(떨어지는 쪽 + 점프 목적지)
                    t = (blk[i + 1] | blk[i + 2] << 8) - M.BASE
                    if t in msgs and t != m.start:
                        nxt.append((msgs[t], slot))
                    i += 3
                else:
                    break
            for n, sl in nxt:
                a, b2 = kr.get(m.key) or {}, kr.get(n.key) or {}
                ta, tb = a.get("t"), b2.get("t")
                # 화자 머리만 든 메시지(원문이 공백·개행뿐)는 번역기가 정본 화자 사전으로 자동 번역한다(`translate_block`) — 항목이 없어도 번역된 쪽이다
                ta = "" if ta is None and not m.jp.strip() else ta
                tb = "" if tb is None and not n.jp.strip() else tb
                if ta is None or tb is None:  # 한쪽이라도 번역이 없으면 이은 줄이 아니다 — 미번역은 조각 줄이 이미 센다(화면 일본어 게이트가 이은 줄을 또 세지 않게)
                    continue
                yield (
                    f"scn{sid:03d}:{m.key}+{n.key}",
                    m.jp + ("{name}" if sl else "") + n.jp,
                    ta + ("{name}" if sl else "") + tb,
                    "dialog",
                )


def _battle():
    kr = _load(SCRIPT / "sys" / "battle.json").get("messages", {})
    for k, r in _load(DERIVED / "battle" / "messages.json").items():
        yield (f"battle:{k}", *_pair(r["tokens"], kr.get(k)), "dialog")
    names, _missing = battle.kr_names()
    for jp, spots in battle.names().items():
        for rel, blk, off in spots:
            yield (f"battle-name:{rel}:{blk}:{off:04X}", jp, names.get(jp), "slot")


def _system():
    msgs = _load(SCRIPT / "sys" / "sysmsg.json").get("messages", {})
    for r in S.read_sysmsg():
        yield (f"sysmsg:{r['addr']:04X}", *_pair(r["jp"], msgs.get(r["key"])), "dialog")
    names = _load(SCRIPT / "sys" / "names.json")
    gl = sysbuild.glossary()
    for fam in S.FIXED:
        for r in S.read_fixed(fam):
            if r["jp"]:
                kr = sysbuild.fixed_kr(fam, r["jp"], names, gl)
                yield (f"fixed:{fam}#{r['i']}", r["jp"], kr, "slot")
    for r in S.read_labels():
        yield (
            f"label:{r['addr']:04X}",
            r["jp"],
            sysbuild.label_kr(r),
            "slot",
        )  # 정본 ui 에서 읽은 라벨(+ labels.json 잔여)
    screens = _load(SCRIPT / "sys" / "screens.json")
    for sc in S.read_screens():
        kr = screens.get(sc["key"])
        for i, ln in enumerate(sc["lines"]):
            yield (
                f"screen:{sc['key']}#{i}",
                ln["jp"],
                kr[i] if kr and i < len(kr) else None,
                "slot",
            )
    extras = _load(SCRIPT / "sys" / "extras.json")
    for ex in S.read_extras():
        kr = extras.get(ex["key"])
        for i, jp in enumerate(ex["items"]):
            yield (f"extras:{ex['key']}#{i}", jp, kr[i] if kr and i < len(kr) else None, "slot")
    inline = _load(SCRIPT / "sys" / "inline.json")
    for r in S.read_inline():
        yield (f"inline:{r['key']}", r["jp"], inline.get(r["key"]), "slot")


def _hud():
    for _off, jp, kr in hud_plate.PLATES:
        yield (f"hud:{jp}", jp, kr, "slot")
    for _tiles, jp, kr in hud_plate.STATUS:
        yield (f"hud:{jp}", jp, kr, "slot")


DEX_REL, DEX_SPAN = (
    459,
    (0x300, 4 * 2048 + 0x200),
)  # 몬스터 도감(rel 459~463) — 원문 평문. 번역 미착수(status 「남은 일」)


def _dex():
    """몬스터 도감 — 이름(정본)과 설명 88건. 원문은 원본 레코드에서 읽고(커밋 안 함), 우리 줄은 정본 이름 · `script/sys/dex.json`."""
    import omake_font as O

    d, recs = O._dex_original()
    kr_desc = _load(SCRIPT / "sys" / "dex.json")["desc"]
    kr_names = O.dex_names()
    for k, (i, j) in enumerate(recs):
        rec = d[i:j]
        name = rec[1 : rec.index(b"\x04")].decode("cp932")
        body = rec[rec.index(b"\x01\x05") + 2 : -1].replace(b"\x01", b"").decode("cp932")
        yield (f"dex-name:{k}", name, kr_names[k], "slot")
        yield (f"dex:{k}", body, kr_desc[k], "dialog")


def _subs():
    """원문 글이 없는 출처(음성 자막 · 그림 글자) — `jp` 는 빈 줄. 우리 줄만 낸다 → 화면 일본어 게이트가 우리 줄의 가나·한자를 잡는다."""
    import chapter_band
    import gfx_text

    for name in ("opening_sub", "ending_sub"):
        for i, ln in enumerate(_load(SCRIPT / f"{name}.json").get("lines", [])):
            yield (f"{name}:{i}", "", ln[2], "dialog")
    for i, t in enumerate(chapter_band.KR_TITLES):
        yield (f"chapter-band:{i}", "", t, "slot")
    for i, (t, *_rest) in enumerate(gfx_text.CARD_LINES):
        yield (f"gfx-card:{i}", "", t, "slot")
    yield ("gfx-banner:0", "", gfx_text.BANNER_TEXT, "slot")


def pairs():
    """문안 전체 — 원본 파생물(`work/derived/`)이 없으면 빈 목록(이 트리는 못 잰다)."""
    if not (DERIVED / "messages").exists():
        return []
    return [*_scenes(), *_joined(), *_battle(), *_system(), *_hud(), *_dex(), *_subs()]


if __name__ == "__main__":
    ps = pairs()
    print(len(ps), sum(1 for p in ps if p[2] is not None))
