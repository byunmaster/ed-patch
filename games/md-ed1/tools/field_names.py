"""대본 블록 91 안의 지명 표 — 입장 배너가 읽는다. `collect_chars()` 가 안 보는 자리.

    python3 tools/field_names.py --check   # 표 자리가 원본과 같은 값인지 검산

## 왜 빈 칸이 됐나 (마스터 지시 2026-09-27 밤, devlog 09-27 참조)

입장 배너(마을 경계에서 뜨는 큰 틀)는 `place_a`/`place_b`(코너 표시가 읽는 표)와 **무관**하게,
**대본 블록 91**(`archives.ARCHIVES["script"][91]`, 씬 로더가 RAM `$FF6650`에 푸는 자리)의
압축 해제 오프셋 `0x296C`에 박힌 **자체 지명 사전**을 읽는다. 「지명+の町/の村/…」 46개를
1바이트 구분자(`0x07`)로 나열한 **고정 14바이트 칸** 표다(가운데 정렬, 반각 공백 패딩).

이 표는 `scene.py` 가 뽑는 「문안 스트림」 경계 밖(이벤트 자료 취급 구간)이라
`build.py:collect_chars()` 가 이 글자를 한 번도 안 본다 — `hangul.py` 방침 (b)("가나·한자는
버린다")가 번역 코퍼스에 없는 코드를 통째로 빈 칸으로 만드는 바람에 배너가 완전히 빈 칸으로
떴다. field_hud 절의 近/口 버그(낱자 둘만 빈 칸)와 같은 메커니즘의 확대판(표 전체 46개가 걸림).

## 고치는 법 (마스터 확정 2026-09-27 밤 — (a) 번역, 이번 라운드)

46개 항목 전부 **이미 있는 정본**을 재사용해 조합했다(`엘아스타`+`마을`→`엘아스타마을` 류) —
새 표기를 짓지 않고 기존 코드를 재사용하므로 글꼴 칸이 늘지 않는다. 🔴 **정본 조회는
`shared/canon/nouns/eiyuu.json`(place 105항목)까지 봐야 한다** — 처음엔 `textmap/names.json`
(place_a/b, 50항목)만 보고 39번을 "글로서리에 없는 새 이름"이라 음역했는데, **글로서리엔
이미 있었다**(`ジャグリ`→`쟈그리`, place 820행 부근). names.json 은 place_a/b 두 표가 이미
뽑아 쓴 **부분집합**이라 이걸 "정본"으로 착각하면 놓친다(관리자 지적 2026-09-27 밤). 예외 하나:

- **34번 「竜の卵ι」** — 끝의 `0x83C7`("ι"로 디코드되지만 이 게임 고유 글꼴에서 실제로 뭘
  그리는지 모른다)은 **의미를 모르니 건드리지 않고 그대로 보존**한다. 한글 「용의알」 뒤에
  원본 바이트를 그대로 이어 붙인다.

**칸을 넘지 않는다** — 46개 전부 계산해 최대 사용량이 12/14바이트(엘아스타마을), 나머지는
6~10바이트라 **항상 여유가 있다**(대칭 패딩으로 반각 공백을 좌우 균등하게 채운다, 홀수 나머지는
안 나온다 — 한글도 2바이트 고정이라 남는 폭이 항상 짝수). **칸 길이를 원본과 완전히 같게
유지한다**(마스터 지시) — 표 뒤의 코드·서술문·그래픽 바이트가 한 바이트도 안 밀리게 하기 위해서다.

## 갈무리14로 확대 (마스터 확정 2026-09-28 — "입장배너 폰트크기 키울 수 있나")

배너 글자가 대사창·HUD(표0, 갈무리11)보다 작아 보인다는 지적에, **배너를 그리는 루틴을 찾아
다른 리소스를 읽게 라우팅을 바꾸는 안**(ASM 조사, devlog 09-28)을 먼저 봤지만 한 번에 못
잡았다. **관리자가 더 쉬운 길을 냈다** — 표0에 빈 칸이 716개 있으니, **배너가 쓰는 89음절만
갈무리14로 그린 사본 글리프**를 표0의 **새 코드**에 굽고, 블록91 문자열만 그 코드로
인코딩한다. 대사창·HUD 는 원래(갈무리11) 코드를 그대로 쓰므로 **ASM 도 렌더러도 안
건드린다** — 순수 데이터 추가다. `field_hud.py` 의 콘덴스드 뒷말과 같은 `hangul.CUSTOM_GLYPHS`
경로(PUA 자리표시로 `hangul.py` 기존 코드 배정·표0 굽기 파이프라인을 그대로 탄다)를 재사용한다.

⚠ **갈무리14 는 14×14 칸을 잉크로 꽉 채운다**(원본 JP 글리프엔 있던 1px 여백이 없다,
`hangul.py` 리소스5/자막 주석에 이미 문서화됨) — 그래서 8방향 팽창 테두리(ring)가 칸 가장자리에서
못 나간다(89음절 전수 확인: 전부 칸 가장자리에 잉크가 닿는다). **새 문제가 아니라 이미 쓰는
자막(리소스5)과 같은 특성**이다 — 잉크 자체(글자 획)는 안 잘리고, 테두리만 한쪽이 살짝
얇아질 뿐이다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import dict_names
import hangul

BLOCK = 91
TABLE_OFF = 10604  # 압축 해제 오프셋 0x296C
ENTRY_LEN = 14
STRIDE = ENTRY_LEN + 1  # +구분자(0x07)
ORIG_ANCHOR = bytes.fromhex("8347838b83418358835e82cc92ac")  # エルアスタの町 — 표 0번 항목 원문

# (색인, 원본에서 그대로 보존하는 꼬리 바이트, 원문) — 한글은 사전·접미 규칙에서 읽는다(`banner_kr`).
# 게임 폴더에 이름 표를 두지 않는다(사전 적용 2단계, 마스터 2026-10-08).
ENTRY_JP = [
    (0, b"", "エルアスタの町"),
    (1, b"", "ルディアの町"),
    (2, b"", "クルスの村"),
    (3, b"", "ベルガの鉱山"),
    (4, b"", "ネリアの港"),
    (5, b"", "ロンドの港"),
    (6, b"", "ラルファの砦"),
    (7, b"", "マスクーンの町"),
    (8, b"", "リーゼルの町"),
    (9, b"", "スエルの村"),
    (10, b"", "アムダの村"),
    (11, b"", "ヨルドの港"),
    (12, b"", "ナッシュの町"),
    (13, b"", "セリスの町"),
    (14, b"", "バズヌーンの町"),
    (15, b"", "エメの町"),
    (16, b"", "ルドラの港"),
    (17, b"", "カウルの村"),
    (18, b"", "リシェールの港"),
    (19, b"", "ナスールの町"),
    (20, b"", "ファンガスの町"),
    (21, b"", "コルクスの町"),
    (22, b"", "ファエトの村"),
    (23, b"", "フィーンの砦"),
    (24, b"", "ギルモアの里"),
    (25, b"", "ニルギドの城"),
    (26, b"", "ラスタバン"),
    (27, b"", "ルディアの城"),
    (28, b"", "岬の洞窟"),
    (29, b"", "流血の洞窟"),
    (30, b"", "グエンの塔"),
    (31, b"", "試練の洞窟"),
    (32, b"", "王家の墓"),
    (33, b"", "国境の洞窟"),
    (34, b"\x83\xc7", "竜の卵<83c7>"),
    (35, b"", "カザミの塔"),
    (36, b"", "風よけの穴"),
    (37, b"", "狼の口"),
    (38, b"", "水晶の塔"),
    (39, b"", "ジャグリの廃坑"),
    (40, b"", "老夫婦の家"),
    (41, b"", "オレアの家"),
    (42, b"", "森の一軒家"),
    (43, b"", "ロエルの家"),
    (44, b"", "ミラルダの家"),
    (45, b"", "バーバラの家"),
]
# 원문 접미 → 한국어 접미 — 칸은 **원문대로**(마스터 10-07): 원문에 の町·の城 가 있으면 붙이고 없으면 맨이름.
# 지명 접미 규칙 — 정본 ui 의 `원문@지명칸` 열쇠(마스터 10-08). 게임 폴더에 표를 두지 않는다.
SUFFIX_KR = {k.split("@")[0]: v for k, v in dict_names.canon.table("ui", "ed1").items() if k.endswith("@지명칸")}
_SUFFIX = re.compile("^(.+?)(" + "|".join(SUFFIX_KR) + ")$")


def banner_kr(jp: str) -> str:
    """배너 칸 원문 → 한글. 사전 place 에 통째로 있으면 그 값, 없으면 「사전 이름 + 원문 접미」(붙여쓰기)."""
    jp = re.sub(r"<[^>]*>", "", jp)
    v = dict_names.from_dict(jp, ("place",))
    if v:
        return v
    m = _SUFFIX.match(jp)
    base = dict_names.from_dict(m.group(1), ("place",)) if m else None
    if not base:
        raise SystemExit(f"블록 91 배너 {jp!r}: 사전 place 에 없다 — 사전 후보로 올린다")
    return base + SUFFIX_KR[m.group(2)]


ENTRIES = [(i, banner_kr(jp), extra, jp) for i, extra, jp in ENTRY_JP]


# ── 갈무리14 전용 합성 글리프 (마스터 확정 2026-09-28 — "입장배너 폰트크기 키울 수 있나") ──
# 표0은 대사창(피치12)과 공유라 통째로 바꿀 수 없다 — 배너 89음절만 PUA(U+E100~) 자리표시로
# hangul.py 기존 파이프라인(코드 배정·표0 굽기)을 태워 **별도 코드**로 굽는다(field_hud.py 의
# 콘덴스드 뒷말과 같은 `hangul.CUSTOM_GLYPHS` 경로). 대사창·HUD 는 원래 코드를 그대로 쓰므로
# 영향이 없다. ASM 은 안 건드린다 — 블록91 레코드에 들어가는 **코드값만** 바뀐다(바이트 길이는
# 음절당 2B 로 그대로라 `_pad`·칸 계산도 안 바뀐다).
GALMURI14 = common.ROOT / "shared" / "fonts" / "Galmuri14.bdf"
_PUA_BASE = 0xE100
_pua_for: dict[str, str] | None = None


def _pua_map() -> dict[str, str]:
    global _pua_for
    if _pua_for is None:
        uniq = sorted(
            set("".join(kr for _, kr, _extra, _jp in ENTRIES))
            | {ch for tbl in DEST.values() for _jp, kr in tbl for ch in kr}
        )
        _pua_for = {ch: chr(_PUA_BASE + i) for i, ch in enumerate(uniq)}
    return _pua_for


def _ensure_custom_glyphs() -> None:
    # top=0(대사창/HUD 은 top=1) — 갈무리14 는 이미 14행을 꽉 채우는 디자인이라 top=1 을 얹으면
    # 89자 중 74자가 바닥 행이 칸 밖(15번째 행)으로 밀려 조용히 잘렸다(마스터 실기 지적
    # 2026-09-28, `m-0928-banner-g14-bottomcut.png`). 배너 사본에만 적용 — 대사창·HUD(Galmuri11,
    # top=1)는 안 건드린다.
    bdf = hangul._load_bdf(GALMURI14, hangul.CELL, top=0, left=0)
    for ch, pua in _pua_map().items():
        if pua in hangul.CUSTOM_GLYPHS:
            continue
        g = bdf.get(ch)
        if g is None:
            raise SystemExit(f"갈무리14 에 없는 글자: {ch!r}")
        hangul.CUSTOM_GLYPHS[pua] = hangul.extend_jamo_arms(g)


def chars() -> set[str]:
    """이 표가 쓰는 글자 — `collect_chars()` 가 다른 문안과 상관없이 늘 굽는다.
    실제로 굽는 건 갈무리14 합성 글리프(PUA)뿐이다(마스터 확정 2026-09-28)."""
    _ensure_custom_glyphs()
    return set(_pua_map().values())


def _pad(body: bytes, total: int = ENTRY_LEN) -> bytes:
    pad = total - len(body)
    if pad < 0 or pad % 2:
        raise SystemExit(f"칸 초과 또는 홀수 나머지: body={len(body)}B, 칸={total}B")
    left = pad // 2
    return b" " * left + body + b" " * (pad - left)


def new_block(orig_data: bytes, cs) -> bytes:
    """블록 91 의 디컴프레스 결과에서 표 구간만 한글로 갈아 끼운다. 나머지(코드·서술문·그래픽)는
    원본 그대로 — 칸 길이(46×14B)가 완전히 같아 뒤 오프셋이 안 흔들린다.

    `cs` 는 `hangul.Charset` — 각 음절을 PUA 코드(갈무리14 합성 글리프)로 인코딩한다."""
    if orig_data[TABLE_OFF : TABLE_OFF + len(ORIG_ANCHOR)] != ORIG_ANCHOR:
        raise SystemExit("블록 91: 지명 표 자리가 원본과 다르다 — 원본이 바뀌었나 확인")
    pua = _pua_map()
    out = bytearray(orig_data)
    pos = TABLE_OFF
    for _i, kr, extra, _jp in ENTRIES:
        body = b"".join(cs.encode_char(pua[ch]) for ch in kr)
        rec = _pad(body + extra)
        out[pos : pos + ENTRY_LEN] = rec
        pos += STRIDE
    return bytes(out)


# ── 블록 92·93 — 같은 14B 칸 꼴의 목적지 목록 (커버리지 점검 2026-10-08) ────────────────────────
# 블록 91(입장 배너)과 같은 **가운데 정렬 14B 칸 + 0x07 구분자** 표가 블록 93(항구·요새 목적지 아홉)·블록 92(마을 하나)에도
# 있다. 문안 스트림 밖이라 이름 검사·원문 잔존 게이트가 못 봤다 — 일본어로 남아 있었다(`names_corpus` 에 안 들어 있었다).
# 한글은 배너와 같은 규칙(`banner_kr`, 사전 place + 원문 접미)이고, **칸 길이는 원본과 같다**(뒤 오프셋 불변).
# 같은 갈무리14 합성 글리프(PUA)로 굽는다 — 블록 91 이 필드 지도(입장 배너), 92·93 은 같은 꼴 표를 가진 다른 지도 구역(바다·항구)이라
# 같은 배너 루틴이 읽는다고 본다(표 꼴·구분자가 같다). 인게임 확인은 바다 구역(배 필요, 후반)에 닿을 때.
DEST_JP = {
    92: ["ルディアの町"],
    93: [
        "ネリアの港",
        "ロンドの港",
        "ラルファの砦",
        "海賊島",
        "スエルの村",
        "ヨルドの港",
        "ルドラの港",
        "リシェールの港",
        "フィーンの砦",
    ],
}
DEST = {blk: [(jp, banner_kr(jp)) for jp in jps] for blk, jps in DEST_JP.items()}


def _orig_cell(jp: str) -> bytes:
    return _pad(jp.encode("cp932"))


def _dest_start(data: bytes, blk: int) -> int:
    """표 첫 칸의 시작 — 원본 첫 칸(가운데 정렬 14B)을 앵커로 찾고, 나머지 칸이 15B 간격으로 이어지는지 검산한다."""
    jps = DEST_JP[blk]
    first = _orig_cell(jps[0])
    at = data.find(first + b"\x07")
    if at < 0 or data.find(first + b"\x07", at + 1) >= 0:
        raise SystemExit(f"블록 {blk}: 목적지 표 첫 칸이 유일하게 안 잡힌다 — 원본이 바뀌었나 확인")
    for i, jp in enumerate(jps):
        if data[at + i * STRIDE : at + i * STRIDE + ENTRY_LEN] != _orig_cell(jp):
            raise SystemExit(f"블록 {blk}: 목적지 표 {i}번 칸({jp})이 원본과 다르다")
    return at


def new_dest_block(blk: int, orig_data: bytes, cs) -> bytes:
    """블록 92·93 의 목적지 표를 한글로 — 칸 길이 불변, 배너와 같은 갈무리14 합성 코드."""
    at = _dest_start(orig_data, blk)
    out = bytearray(orig_data)
    pua = _pua_map()
    for i, (_jp, kr) in enumerate(DEST[blk]):
        body = b"".join(cs.encode_char(pua[ch]) for ch in kr)
        out[at + i * STRIDE : at + i * STRIDE + ENTRY_LEN] = _pad(body)
    return bytes(out)


def check() -> None:
    import archives as _archives

    rom = common.rom()
    bl = _archives.blocks(rom, _archives.ARCHIVES["script"][0])
    _s, data, _e = bl[BLOCK]
    if data[TABLE_OFF : TABLE_OFF + len(ORIG_ANCHOR)] != ORIG_ANCHOR:
        raise SystemExit(f"블록 {BLOCK}: 지명 표 앵커가 원본과 다르다")
    print(f"  대본 블록 {BLOCK} 지명 표 — 앵커 일치, 항목 {len(ENTRIES)}개")
    for blk in DEST_JP:
        _dest_start(bl[blk][1], blk)
    print(f"  대본 블록 {'·'.join(map(str, DEST_JP))} 목적지 표 — 앵커 일치, 항목 {sum(len(v) for v in DEST_JP.values())}개")


if __name__ == "__main__":
    check()
