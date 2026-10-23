"""번역 정본 → 씬 블록 바이트 합성.

정본(커밋):
    script/speakers.json      {"侍女": "시녀", …}   화자 이름(JP 는 단어 수준이라 커밋 OK)
    script/scnNNN.json        {"messages": {열쇠: {"t": "우리 문안"}}}   열쇠 = messages.Message.key
        `t` 는 산문. `\\n` 하드 개행 · `\\f` 강제 페이지. 조판은 typeset.pages 가 한다.
JP 원문은 정본에 없다 — `work/derived/messages/scnNNN.json` 이 열쇠↔원문 대조표다(커밋 안 함).

합성: [1F 화자 04 | 09 nn] + (원문이 화자 뒤 01 로 시작했으면 01) + 줄들(01) · 창(05) + 종료(원문 것).
종료가 없는 조각(화자 전환·옵코드 앞에서 끊긴 메시지)은 splice 가 `0F` 로 다음 자리에 잇는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font
import messages as M
import typeset

PAGE = 0x05
NL = 0x01


class TranslateError(Exception):
    pass


def body_chars(scene_id: int) -> set[str]:
    """씬 하나의 대사 본문이 쓰는 우리 글리프 글자(화자 이름은 `name_chars`)."""
    out: set[str] = set()
    for e in M.load_translations(scene_id).values():
        out |= {ch for ch in font.expand_packed(e["t"]) if font.needs_glyph(ch)}
    return out


def _jp_corpus() -> str:
    """이 게임 원문 전체(씬 대사·시스템 표·전투 표의 JP 문자열)를 한 덩이로 — 정본 이름이 이 게임에 나오나 가르는 데 쓴다.
    ⚠ 부분 문자열 일치라 넉넉하게 잡힌다(과포함은 안전, 누락은 없다). 파생물이 없으면 죽는다 — 조용히 전체로 돌아가지 않는다."""
    import glob
    import json

    out: list[str] = []

    def walk(o) -> None:
        if isinstance(o, str):
            out.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                out.append(str(k))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    import common

    root = common.OUT_DIR
    files = [f for d in ("messages", "sys", "battle") for f in sorted(glob.glob(str(root / d / "*.json")))]
    if not files:
        raise FileNotFoundError(f"원문 파생물이 없다: {root}/(messages|sys|battle)")
    for f in files:
        walk(json.loads(Path(f).read_text("utf-8")))
    return "\n".join(out)


def name_chars() -> set[str]:
    """씬 대사 밖에서 오는 우리 글리프 글자 — 공용 정본(고유명사·UI·화자)의 화면 표기. 🔴 늘 상주한다."""
    # 🔑 **화면에 나가는 표기만** 공용에서 받는다(`kr_texts`) — 열쇠도 `_aliases` 도 안 온다.
    #    ⚠ `load_speakers()` 는 **맵**이라 조판이 쓰고, 글리프 커버리지는 이쪽이다.
    import canon  # shared/ — 공통 문안 정본(ED1 = PS1 씨앗)

    # 정본은 화면에 나가는 범주만(ui·speaker) — system·battle 문구 조각은 이 게임이 안 쓰는 것이 많아 글리프를 낭비한다
    chars: set[str] = set()
    canon_vals = [v for c in ("ui", "speaker") for v in canon.table(c, "ed1").values()]
    # 🔴 고유명사는 **이 게임 원문에 실제로 나오는 이름만** — 정본은 ED1·ED2 공통이라 전체를 잡으면 다른 게임이 이름을
    #    더할 때마다 이 게임의 상주 칸이 깎인다(10-18 「흰슬러그」·「넬」). 안 나오는 이름의 글자는 상주 대상이 아니고,
    #    대사 본문에만 쓰이면 `body_chars` → 블록 동적 칸으로 간다. 상주 순서(`glyph_order.json`)는 안 건드린다.
    corpus = _jp_corpus()
    names = [kr for _c, jp, kr in canon.all_names("ed1") if jp in corpus]
    for v in names + canon_vals + list(M.load_speaker_overrides().values()):
        chars |= {ch for ch in v if font.needs_glyph(ch)}
    return chars


def all_glyph_chars() -> set[str]:
    """정본 전체가 쓰는 우리 글리프 글자(한글·부호·숫자) — 대사 본문 + 이름. 상주/동적 가름은 `glyphdyn`."""
    chars = set(name_chars())
    for p in sorted(M.SCRIPT_DIR.glob("scn*.json")):
        chars |= body_chars(int(p.stem[3:]))
    return chars


def compose(m: M.Message, tr: dict, table: dict[str, bytes], speakers: dict[str, str]) -> bytes:
    out = bytearray()
    if m.speaker is not None:
        name = speakers.get(m.speaker, m.speaker)
        out += b"\x1f" + font.encode(name, table, msg=True) + b"\x04"  # 화자명도 대사창 — 공백 반각
    elif m.common is not None:
        out += bytes([0x09, m.common])
    lead_nl = bool(m.tokens) and m.tokens[0] == ("op", NL)
    if lead_nl:
        out.append(NL)
    if tr.get("raw"):
        # 🔴 **조판기(`typeset.pages`→공용 `krwrap`)를 아예 안 거친다** — 원판이 가운데맞춤을 앞뒤
        #    전각 공백으로 **미리 구워** 낸 고정폭 표(필드 입장 배너 지명 46개, `scn000.json`)라 어절
        #    경계 공백을 지우는 일반 대사 조판기를 태우면 공백이 사라져 왼쪽 정렬이 된다(devlog 09-27).
        #    `krwrap` 은 공용(`shared/`)이라 이 게임에서 못 고친다 — 문안 쪽에서 통째로 비켜 간다.
        out += font.encode(tr["t"], table)
    else:
        # 🔴 **줄머리 공백은 조판기가 지우므로 여기서 따로 낸다** — 앞 메시지가 찍은 품목 이름 바로 뒤에 이어지는 문안
        #    (「약초 말이군. 정말 고마워.」)은 이름과 띄어야 하는데, `krwrap` 이 줄머리 공백을 먹어 「약초말이군」으로 붙었다.
        lead_sp = len(tr["t"]) - len(tr["t"].lstrip(" "))
        if lead_sp:
            out += font.encode(" " * lead_sp, table, msg=True)
        pgs = typeset.pages(
            font.expand_packed(tr["t"].lstrip(" ")),
            speaker=m.speaker is not None or m.common is not None,
        )
        # 하드 개행이 든 화자 없는 창(장 끝 카드)은 줄을 그대로 둔 것이라 **개행도 그대로** 넣는다 —
        # 꽉 찬 제목 줄 뒤의 빈 줄이 먹혔다(종장 카드 화면 2026-09-25: 13칸 제목 바로 밑에 「끝」).
        verbatim = "\n" in tr["t"] and m.speaker is None and m.common is None
        for i, pg in enumerate(pgs):
            if i:
                out.append(PAGE)
            for j, line in enumerate(pg):
                # 🔴 **틀을 꽉 채운 줄 뒤에는 개행을 안 넣는다** — 인터프리터가 열 ≥ $99(13)에서 스스로
                #    넘기므로 우리 `01` 이 얹히면 **빈 줄**이 된다(our-findings 2026-08-30, PS1 이 122곳).
                if j and (verbatim or typeset.cols(pg[j - 1]) < typeset.FULL):
                    out.append(NL)
                # 장 끝 카드(verbatim)는 원문이 전각 공백으로 맞춘 줄이라 공백을 12px 그대로 둔다
                out += font.encode(line, table, msg=not verbatim)
    if m.terminated:
        out.append(m.tokens[-1][1])
    elif m.tokens and m.tokens[-1] in (("op", PAGE), ("op", 0x03)):
        # 화자 전환 앞의 페이지 옵코드는 원문 흐름의 일부다 — 빼먹으면 다음 화자가 같은 창에 이어 붙는다(실측)
        out.append(m.tokens[-1][1])
    return bytes(out)


def translate_block(scene_id: int, block: bytes, table: dict[str, bytes]) -> tuple[bytes, int]:
    """번역이 있는 메시지를 합성해 splice. (새 블록, 넣은 메시지 수)."""
    trs = M.load_translations(scene_id)
    if not trs:
        return block, 0
    speakers = M.load_speakers()
    msgs = M.parse(block)
    edits = []
    seen = set()
    for m in msgs:
        tr = trs.get(m.key)
        if tr is None and m.speaker in speakers and not m.jp.strip():
            tr = {
                "t": ""
            }  # 이름만 있는 메시지(이벤트 코드가 화자 표시용으로 부른다) — speakers.json 으로 자동
        if tr is None:
            continue
        if m.pinned:
            raise TranslateError(
                f"scn {scene_id} 열쇠 {m.key}: pinned(안쪽 참조) — 자리 규칙으로 못 넣는다"
            )
        edits.append((m, compose(m, tr, table, speakers)))
        seen.add(m.key)
    missing = set(trs) - seen
    if missing:
        raise TranslateError(
            f"scn {scene_id}: 정본 열쇠 {sorted(missing)} 가 블록에 없다(원문이 바뀌었나)"
        )
    return apply_orphans(scene_id, block, M.splice(block, edits), table, speakers), len(edits)


# 🔴 **메시지 밖에 서 있는 조각** — `messages.parse` 는 두 글자 미만의 가나·한 글자 화자 머리를 메시지로 안 잡아 번역이 닿지 않고 일본어가 그대로 남았다
#    (10-20 짝 표·화면 확인 — 마스터 「A」):
#    ① 슬롯 옵코드(`0B`·`0E`) 곁의 한 글자 조사 「は」「を」 → 같은 2바이트 동적 조사 토큰(`F9 24` 은/는 · `F9 26` 을/를). 슬롯 이름 바로 뒤에 붙으면
#       「류난은약초를」처럼 붙어서 반 칸 공백(`F8 24`)을 더 넣는 자리는 공간이 모자라 **블록 끝으로 잇는다**(`0F` 점프 · 같은 방식 splice).
#    ② 한 글자 화자 머리 「男」「女」「娘」(`1F 이름 04`) → 정본 화자 표기(남자·여자·소녀). 이름칸이 더 길어 역시 블록 끝으로 잇는다.
#    바이트가 기대와 다르면 빌드가 죽는다 — 원문과 다른 글자는 건드리지 않는다.
def _orphan_patches() -> dict[int, list[tuple[int, bytes, bytes]]]:
    j = font.josa_code
    sp = font.HALF_SPACE
    return {
        # 씬 50 갈래 이음: 「また」 뒤 조건(11 00 04)이 참이면 「盗ま」 조각 → 점프로 「荒らされている」 한가운데(れている)로 들어가 두 갈래가 꼬리를 나눠 쓴다.
        #   한글은 두 갈래가 각자 끝까지 쓰므로(「도둑맞았어.」·「뒤져져 있어.」) 「盗ま」 조각 뒤 점프 목적지를 꼬리 한가운데가 아니라 다음 메시지(0xC1A)로 돌린다.
        50: [(0xC06, b"\x0f\x0f\xac", b"\x0f\x1a\xac")],
        56: [(0x879, b"\x82\xcd", j("은/는")), (0x87D, b"\x82\xf0", j("을/를"))],
        133: [(0x2C6, b"\x0b\x82\xcd\x0e", b"\x0b" + j("은/는") + sp + b"\x0e")],
        195: [(0xADC, b"\x0b\x82\xcd", b"\x0b" + j("은/는") + sp)],
        197: [
            (0x923, b"\x0b\x82\xcd\x0e", b"\x0b" + j("은/는") + sp + b"\x0e"),
            (0x927, b"\x82\xf0", j("을/를")),
        ],
        220: [(0x4C2, b"\x82\xcd", j("은/는"))],
    }


ORPHAN_SPEAKERS = ("男", "女", "娘")


def apply_orphans(
    scene_id: int, orig: bytes, block: bytes, table: dict[str, bytes], speakers: dict[str, str]
) -> bytes:
    """`orig` = 번역 전 블록(주소 기준 · 메시지 칸 판별), `block` = splice 결과(제자리 + 끝에 이은 꼬리)."""
    patches = list(_orphan_patches().get(scene_id, []))
    spans = [(m.start, m.end) for m in M.parse(orig)]
    for i in range(len(orig) - 3):
        if orig[i] == 0x1F and orig[i + 3] == 0x04 and not any(a <= i < b for a, b in spans):
            try:
                nm = orig[i + 1 : i + 3].decode("cp932")
            except UnicodeDecodeError:
                continue
            if nm in ORPHAN_SPEAKERS and nm in speakers:
                patches.append((i, orig[i : i + 4], b"\x1f" + font.encode(speakers[nm], table) + b"\x04"))
    if not patches:
        return block
    out = bytearray(block)
    for off, old, new in patches:
        if bytes(orig[off : off + len(old)]) != old:
            raise TranslateError(
                f"scn {scene_id} +{off:#06x}: 조각 자리가 {old.hex()} 가 아니다({bytes(orig[off:off+len(old)]).hex()}) — 원문이 바뀌었나"
            )
        if len(new) <= len(old):
            out[off : off + len(new)] = new
            continue
        if len(old) < 3:
            raise TranslateError(f"scn {scene_id} +{off:#06x}: 자리 {len(old)}B 라 점프(3B)를 못 둔다")
        at = M.BASE + len(out)  # 끝에 이은 꼬리: 새 바이트 + 원래 자리 뒤로 되돌아가는 점프
        back = M.BASE + off + len(old)
        out += new + bytes([0x0F, back & 0xFF, back >> 8])
        out[off : off + 3] = bytes([0x0F, at & 0xFF, at >> 8])
    return bytes(out)
