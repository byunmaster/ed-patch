"""전투 덩이 문구 — 「<몬스터>가 나타났다」와 「<행동한 쪽 이름>의 …」 줄을 정본 battle 틀로 바꾼다.

덩이 꼴(실측): 첫 줄 `[0E]몬스터[0F]が現れた{12}`(이름은 **글 속 리터럴**), 그다음 줄은 이름 라벨(`몬스터{06}Ａ{04}` — 이름 버퍼를 채운다)과
`{1B}…`(**이름 버퍼 출력 + 술어**) 쌍이다. 라벨 줄은 `labels` 가, 여기서는 첫 줄과 `{1B}` 줄을 맡는다.
- 첫 줄: 리터럴 이름이라 조사를 **빌드 때 푼다**(정본 「{name}이(가) 나타났다.」 → 「슬라임이 나타났다.」). 여럿이면 `와/과` 로 잇는다.
- `{1B}` 줄: 정본 틀(`の攻撃` → 「의 공격」 …)과 맞으면 바꾸고, 정본에 없는 몬스터 고유 술어는 원문 그대로 두고 `missing` 에 모은다(관리자 후보).
조사는 정본 병기 꼴 그대로다(행동한 쪽 이름은 런타임 버퍼라 받침을 모른다 — P2 조사 훅 몫).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import canon
import jptext
import msgs
import systext
from text import josa

APPEAR = "が現れた"


def _plain(raw: bytes) -> str:
    return jptext.decode(raw).replace("{0E}", "").replace("{0F}", "")


def is_battle_chunk(d: bytes) -> bool:
    lines = d.split(b"\x00")
    if APPEAR in _plain(lines[0]).replace("\n", ""):
        return True
    # 최종 보스 덩이(패키지 2690 메시지 25·26) — 첫 줄이 「…との戦闘だ」/빈 줄이라 나타남 문구가 없다. 행동한 쪽 이름(`1B`)으로 시작하는 줄이 둘↑이면 전투 로그다
    return sum(1 for ln in lines if ln.startswith(b"\x1b")) >= 2


def appear_text(line: bytes) -> str | None:
    """나타남 줄의 한국어 글(정본 몬스터 이름 + 「이(가) 나타났다.」) — 정본에 없으면 None. 이름 검사 어댑터도 쓴다."""
    jp = re.sub(r"\{[^}]*\}", "", _plain(line)).replace("\n", "").replace("\u3000", "")
    m = re.match(rf"^(.+?){APPEAR}", jp)
    if not m:
        return None
    names = m.group(1).split("と")
    krs = [canon.lookup(n, "monster", "ed2") for n in names]
    tail = canon.lookup("{name}が現れた。", "battle", "ed2")
    if None in krs or not tail or not tail.startswith("{name}이(가)"):
        return None
    text = krs[0]
    for prev, nxt in zip(krs, krs[1:], strict=False):
        text = text + josa.josa(prev, "과/와") + " " + nxt  # 이름 사이 띄움(qa 10-20 「지팡이술사와다그니아가」)
    return text + josa.josa(krs[-1], "이/가") + tail[len("{name}이(가)") :]


def _appear(line: bytes, tab, missing: set) -> bytes:
    toks = systext.tokens(line)
    glyph_at = [k for k, (kind, _b) in enumerate(toks) if kind == "glyph"]
    if not glyph_at:
        return line
    trail = b"".join(b for kind, b in toks[glyph_at[-1] + 1 :] if kind == "ctrl")
    jp = re.sub(r"\{[^}]*\}", "", _plain(line)).replace("\n", "").replace("\u3000", "")
    text = appear_text(line)
    if text is None:
        if re.match(rf"^(.+?){APPEAR}", jp):
            missing.add(jp)
        return line
    return tab.enc(text) + trail  # 줄은 엔진이 어절 단위로 넘긴다(`wrap.py` 훅, 마스터 10-18) — 빌드는 개행을 박지 않는다


def _label_class(raw: bytes) -> str | None:
    """이름 라벨 줄(`06…04` 로 감싼 이름)이면 한국어 이름의 받침 부류 — 영문 끝(A~D)·받침 없음 = `none`, 받침 = `yes`. 라벨이 아니면 None."""
    import font
    import labels

    if raw.startswith((b"\x1b", b"\x07")) or not raw:
        return None
    s = labels.split(raw)  # `06…04` 색 표지는 있어도 없어도 된다(「浮遊王」 처럼 맨 글 라벨도 있다 — qa 「부유왕는」)
    if s is None or APPEAR in s[2] or b"\x12" in raw or not labels.is_monster(s[2]):
        return None
    kr = labels.lookup(s[2])
    if not kr:
        return None
    if re.search(r"[A-Za-z]$", kr):
        return "none"
    return "yes" if font._batchim_before(kr[-1]) else "none"


def edit_chunk(d: bytes, tab, missing: set) -> bytes:
    """전투 덩이 한 개의 줄을 바꾼다 — 이미 정본에 있는 것만(없는 술어는 `missing`)."""
    lines = d.split(b"\x00")
    n = len(lines) - 1
    # 행동 줄(`1B`)이 끼우는 이름 버퍼는 **직전 이름 라벨**의 이름이다(실측: 한 덩이에 「부두A」·「샨샨」 라벨이 섞여도 행동 줄은 자기 라벨 뒤에 놓인다) — 줄마다 그 라벨의 받침 부류로 조사를 푼다
    classes = {c for c in (_label_class(r) for r in lines[:n]) if c}
    cur = next((c for c in (_label_class(r) for r in lines[:n]) if c), "none")
    seventh = "dyn" if "yes" in classes else "none"  # `07` 줄(둘째 이름 버퍼 — 다른 몬스터를 가리킬 수 있다 「샨샨이 도우러 왔다」): 받침 있는 이름이 섞인 덩이만 런타임 훅에 맡긴다
    for i in range(n):
        raw = lines[i]
        cls = _label_class(raw)
        if cls:
            cur = cls
        msgs.BATTLE_JOSA = seventh if raw.lstrip(b"\x0c").startswith(b"\x07") else cur
        if i == 0 or (APPEAR in _plain(raw) and not raw.startswith(b"\x1b")):  # 나타남 줄이 첫 줄이 아닌 덩이(「木人が現れた」 — 앞에 「…と…が現れた」 줄이 따로 있다)
            lines[i] = _appear(raw, tab, missing)
            continue
        if not raw.lstrip(b"\x0c").startswith((b"\x1b", b"\x07")):  # `1B`(행동한 쪽) · `07`(대상 쪽) 이름으로 시작하는 줄 — 창 열기(`0C`)가 앞에 붙은 줄도(2690:27:12)
            continue
        new = msgs.translate(raw, tab, battle=True)
        if new is None:
            missing.add(_plain(raw).replace("\n", "/"))
        else:
            lines[i] = new
    return b"\x00".join(lines)
