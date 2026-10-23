"""공용 이름 검사(`scripts/check/check_names.py`)의 pce-ed2 어댑터 — `(자리, 원문 줄, 우리 줄|None, 갈래)` 를 문안 전체에 대해 낸다.

🔴 이름을 **들지 않는다**(마스터 10-07) — 원본 패키지의 줄과 우리 문안(대사 번역 · 제어 줄 틀 · 정본 조회)을 읽어 짝지어 넘길 뿐이다.
미번역 줄은 None 으로 낸다(분모에 든다). 갈래: `"dialog"` = 대사 창에 흐르는 글(씬 대사 · 상점·수령 문구 · 전투 문구) ·
`"slot"` = 칸에 담긴 이름(지명 라벨 · 몬스터 이름 라벨).

범위(솔직하게): ED2 본편 씬 패키지 13개의 줄(rel 386~1794 + 최종 장면 2690). 시스템 문구 표(뱅크 0x68~, 메뉴·설정·아이템·주문·지명 표)·오프닝/엔딩 자막·스태프롤은
이 어댑터가 안 낸다(스태프롤은 정본 대상이 아니다 — 마스터 10-08 · 자막은 원문 글이 없다).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import battle
import chapter
import common
import ctrllines
import dialogue
import jptext
import labels
import msgs
import package

TITLE = "eiyuu"
CANON = "ed2"  # 공통 문안 정본 — PS1 ED2 기반(마스터 10-08). 안 두면 ed1 정본으로 재서 ED2 값(길게 울부짖고 · 포효를 내질렀다 …)이 안 잡힌다(10-21)
CANON_SKIP = r"^script:"  # 장면 대사(전투 덩이 밖 줄)는 정본 범위 밖(마스터 10-08) — 정본은 메뉴·호칭·시스템·전투 문구
CANON_GATE = True  # 정본(shared/canon) 어긋남을 실패로 친다 — 어긋남 0 확인 뒤 켬(마스터 10-18 재검수)
_TAG = re.compile(r"\{[^}]*\}")
_JP = re.compile(r"[぀-ヿ一-鿿]")


def _plain(raw: bytes) -> str:
    return _TAG.sub("", jptext.decode(raw)).replace("\n", "")


def _kr_of_template(tmpl: str) -> str:
    return ctrllines.strip_refs(tmpl).replace("\n", " ").replace("\f", " ")


def _label_kr(line: bytes) -> str | None:
    s = labels.split(line)
    if s is None:
        return None
    return labels.lookup(s[2])


def _battle_kr(line: bytes) -> str | None:
    sp = msgs.split(line, msgs.BATTLE_NAME, set())
    if sp is None:
        return None
    _lead, content, _trail = sp
    tmpl, _n, _m = msgs.template(content, msgs.BATTLE_NAME, set())
    hit = msgs.index().get(msgs.norm(tmpl))
    if hit is None and msgs.norm(tmpl).startswith("{name}"):
        hit = msgs.index().get(msgs.norm(tmpl)[len("{name}") :])
    if hit is None:  # 긴 행동 문장 — 해시 열쇠 표(원문이 소스에 못 있다)
        key = msgs.norm(tmpl)
        v = msgs.long_hit(key) or (msgs.long_hit(key[len("{name}") :]) if key.startswith("{name}") else None)
        return v.replace("\n", " ") if v else None
    return hit[2].replace("\n", " ")


_SENT_END = re.compile(r"[。！？｜!?」』]$")


def _joined(out: list) -> list:
    """한 문장이 **줄 둘 이상**에 이어진 곳을 한 줄로도 낸다(10-20 sfc-ed2 부류 — 조각 단위로만 내면 이어진 자리를 검사기 셋이 못 본다).
    같은 덩이의 바로 다음 줄이고, 앞 줄 원문이 문장 끝(。！？｜」)으로 안 끝나면 이어진 것으로 보고 `<앞>+<뒤>` 열쇠로 원문·한글을 이어 낸다(셋 이상도 잇는다)."""
    extra = []
    i = 0
    while i < len(out) - 1:
        where, jp, kr, kind = out[i]
        j = i
        while (
            kind == "dialog"
            and kr
            and j + 1 < len(out)
            and out[j + 1][3] == "dialog"
            and out[j + 1][2]
            and out[j + 1][0].rsplit(":", 1)[0] == where.rsplit(":", 1)[0]
            and int(out[j + 1][0].rsplit(":", 1)[1]) == int(out[j][0].rsplit(":", 1)[1]) + 1
            and not _SENT_END.search(out[j][1])
        ):
            j += 1
        if j > i:
            extra.append(("+".join(out[k][0] for k in range(i, j + 1)), "".join(out[k][1] for k in range(i, j + 1)), " ".join(out[k][2] for k in range(i, j + 1)), "dialog"))
            i = j
        else:
            i += 1
    return extra


def pairs():
    out = _pairs_lines()
    return out + _joined(out)


def _pairs_lines():
    out = []
    ctab = ctrllines.table()
    for rel in sorted(dialogue.package_chars()):
        po = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(po):
            if po[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(po, a, b)[0]
            lines = d.split(b"\x00")
            cand = {li: (spk, txt) for li, _p, spk, txt in dialogue.candidates(rel, a, d)}
            is_battle = battle.is_battle_chunk(d)
            for i, line in enumerate(lines):
                if not line:
                    continue
                jp = _plain(line)
                if not _JP.search(jp):
                    continue
                where = f"{rel}:{a}:{i}"
                dwhere = where if is_battle else "script:" + where  # 장면 대사는 정본(공통 문안) 범위 밖 — `CANON_SKIP` 이 건너뛴다(마스터 10-08). 이름 검사는 그대로 잰다
                if chapter.is_chapter_chunk(d) and i < chapter.KEY_LINES:  # 장 제목 띠 — 정본 `chapter` 범주(번호 + 제목)
                    try:
                        out.append((where, jp, " ".join(chapter._entry(jp)), "slot"))
                    except KeyError:
                        out.append((where, jp, None, "slot"))
                    continue
                kr = _label_kr(line)  # 칸에 담긴 이름이 먼저다(PS1 짝이 붙은 지명 줄도 칸 꼴이 맞다)
                if kr is not None:
                    out.append((where, jp, kr, "slot"))
                    continue
                if i in cand:
                    spk, txt = cand[i]
                    out.append((dwhere, jp, ((spk + " ") if spk else "") + txt.replace("\f", " "), "dialog"))
                    continue
                skel, _c, _h = ctrllines.parse(line)
                t = ctab.get(ctrllines.key_of(skel))
                if t is not None:
                    out.append((dwhere, jp, _kr_of_template(t), "dialog"))
                    continue
                kr = _battle_kr(line) if is_battle else None
                if kr is None and is_battle:
                    kr = battle.appear_text(line)
                out.append((dwhere, jp, kr, "dialog"))
    return out
