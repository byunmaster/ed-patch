"""장 카드 · HUD 장 제목 — 정본(`shared/canon/ed2.json` 장 제목 범주)에서 읽어 `sysmsg` 문안(`ours`)을 만든다.

    python3 tools/chapters.py            # 자리·문안 미리보기(원문은 해시만 — 장 제목은 단어 수준 명칭이라 정본 열쇠로 적는다)

ED1(`docs/status.md` 4e)과 같은 계약이다 — 한 스트림에 계약이 둘:
- **HUD 제목 스트림** — 앞 **30바이트**가 HUD 왼쪽 위 장 제목이다(모듈 코드가 정확히 30B 를 `$FF1B3C` 로 복사한다).
  뒤 3~4B(`<02>…`)는 그대로 둔다. 모자라면 뒤 스트림 바이트가 HUD 에 딸려 올라온다 ⇒ **공백으로 30B 를 채운다.**
- **카드 스트림** — 장 끝 카드(「제１장 …」 + 빈 줄 + 「　　　　　　　　끝」). 조판기를 안 태운다(여백까지 우리 자리).
- 중앙 정렬은 원본에서 재서 맞춘다(ED1 실측) — 반각 6px · 전각 12px, **HUD 제목 중심 90px · 카드 중심 102px**.
- 형식: 「제１장」(번호는 정본 `@번호` 열쇠) + 반각 2칸 + 제목. 「完」 자리는 「끝」(정본 카드 문안, ed2 `system`).

⚠ 서장(序章)은 HUD 표(`0x3A194`, 30B 00 종결)에 있고 카드가 없다 — `tables.py` `chapter` 가 맡는다.
"""

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import scene
import textmap

from shared import canon

HUD_CENTER, CARD_CENTER = 90, 102  # px (ED1 실측 — 원본 다섯 장 카드·네 HUD 제목)
HUD_W = 30  # HUD 제목 바이트
GAP = "  "  # 번호–제목 반각 2칸
END_WORD = "끝"  # 「完」 — 정본 카드 문안(ed2 system)의 끝 자리
# 장 제목 열쇠(원문) → (HUD 스트림 자리, 카드 스트림 자리 또는 None)
STREAMS = {
    "開かれた奈落": (0x37646, 0x37686),
    "英雄たちの行方": (0x37924, 0x37964),
    "竜の卵": (0x37FC0, 0x38000),
    "暗黒の支配者": (0x382DA, 0x3831A),
    "祈り、そして希望": (0x39556, None),
}
NUM = {  # 번호 라벨 열쇠 — 정본 `@번호`
    k: canon.lookup(f"{k}@번호", "chapter", "ed2") for k in STREAMS
}


def px(s: str) -> int:
    return sum(6 if ord(c) < 0x80 else 12 for c in s)


def title_of(key: str) -> str | None:
    n, t = NUM.get(key), canon.lookup(key, "chapter", "ed2")
    return None if n is None or t is None else n + GAP + t


def centered(text: str, center: int) -> str:
    """가운데가 `center`px 에 오도록 앞을 반각 공백으로 민다(뒤는 호출쪽이 채운다)."""
    lead = max(0, round((center - px(text) / 2) / 6))
    return " " * lead + text


def hud(key: str) -> str:
    """앞 30바이트 — 가운데 정렬 + 뒤 공백 패딩."""
    s = centered(title_of(key), HUD_CENTER)
    n = sum(1 if ord(c) < 0x80 else 2 for c in s)
    if n > HUD_W:
        raise SystemExit(f"장 HUD 제목 {s!r} 이 {HUD_W}B 를 넘는다({n}B)")
    return s + " " * (HUD_W - n)


def card_first_line(key: str) -> str:
    return centered(title_of(key), CARD_CENTER)


def card_end_line() -> str:
    return "　" * 8 + END_WORD  # 원본 「　×8 + 完」 — 중심 96+6=102


def key_of(jp_text: str) -> str | None:
    """원문 첫 텍스트 덩이(공백·번호 포함) → 장 제목 열쇠."""
    t = unicodedata.normalize("NFKC", jp_text).replace("　", " ").strip()
    m = re.match(r"第\d章 *(.+)$", t) or re.match(r"終章 *(.+)$", t)
    if not m:
        return None
    for k in STREAMS:
        if unicodedata.normalize("NFKC", k).replace(" ", "") == m.group(1).replace(" ", ""):
            return k
    return None


def plan(strs: dict[int, dict]) -> dict[str, str]:
    """{"주소6자리": ours} — sysmsg 정본에 덮어쓸 문안. 원본 스트림에서 제목 덩이를 찾아 만든다(자리 하드코딩 아님)."""
    out: dict[str, str] = {}
    for key, (a_hud, a_card) in STREAMS.items():
        if title_of(key) is None:
            continue  # 정본에 장 제목이 없으면 건드리지 않는다
        st = strs[a_hud]["stream"]
        toks = st.tokens
        t0 = toks[0]
        if t0.kind != "text" or key_of(t0.raw.decode("cp932")) != key or len(t0.raw) != HUD_W:
            raise SystemExit(f"장 HUD 스트림 {a_hud:#x} 가 예상과 다르다 ({t0.raw!r})")
        tail = "".join(
            _tag(t, raw_text=True) for t in toks[1:]
        )  # 제목 뒤 꼬리는 바이트 그대로(글자로 다시 인코딩하지 않는다)
        out[f"{a_hud:06x}"] = hud(key) + tail
        # 꼬리(+30)를 따로 가리키는 참조가 있으면 그 스트림도 같은 꼬리로 — 앞 스트림의 접미로 같이 앉아야 한다(is_suffix 는 토큰 꼴을 맞댄다)
        if a_hud + HUD_W in strs:
            out[f"{a_hud + HUD_W:06x}"] = tail
        if a_card is not None:
            ct = strs[a_card]["stream"].tokens
            body = [t for t in ct if t.kind == "text"]
            if key_of(body[0].raw.decode("cp932")) != key:
                raise SystemExit(f"장 카드 스트림 {a_card:#x} 의 제목이 {key} 가 아니다")
            head = _tag(ct[0]) if ct[0].kind != "text" else ""  # `<08>`
            out[f"{a_card:06x}"] = head + card_first_line(key) + "\n\n" + card_end_line() + "\n<00>"
    return out


def _tag(t: scene.Token, raw_text: bool = False) -> str:
    if t.kind == "text":
        return f"<{t.raw.hex()}>" if raw_text else t.raw.decode("cp932")
    if t.kind == "end":
        return f"<{t.code:02x}>"
    if t.code == 0x01:
        return "\n"
    if t.ref:
        return f"<{t.code:02x}:{t.target:06x}>"
    return f"<{t.raw.hex()}>"


if __name__ == "__main__":
    import common
    import sysmsg

    d = common.rom()
    ours = plan(sysmsg.streams(d))
    for a, s in sorted(ours.items()):
        print(a, repr(s))
    _ = textmap
