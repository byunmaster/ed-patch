"""엔딩 스태프롤(rel 909) — 분야 라벨·배역·제목은 **한글**(마스터 10-16), 사람·회사 이름도 한글(영문 표기는 그대로, 10-16 규칙 3-7 · 옛 전각 영문판은 `ED_STAFF_EN=1`).

    python3 games/pce-ed1/tools/staffroll.py          # 새 스태프롤 미리보기 + 폭·바이트 검사

옛 판(2026-09-24): 「스태프 역할명은 전각영문으로 해도 충분할듯」 — 한글을 못 넣는 줄 알았다:
엔딩 모듈(rel 898)은 BIOS `EX_GETFNT` 로 직접 그리고 우리 글리프 훅이 거기엔 없다
(오프닝 성우 크레딧 표제를 `ＣＡＳＴ` 로 비켜 간 것과 같은 판단). **그러나 호출부 둘의 피연산자를 돌려 자체 후킹을 두면 된다**(아래 `hook_code`, 마스터 10-16).

구조(엔딩 모듈 +0x5A25~+0x62E5, 2,241B, `1A` 종단):
    줄 = … `0D 0A`, `09` = 탭(다음 32px 칸), `1B`/`1D` = 강조 여닫이, 그 밖 = **2바이트 SJIS**
    렌더러(모듈 +0x5688)는 `< 0x20` 만 제어로 보고 **나머지를 늘 2바이트로 읽는다** — 반각 영문은
    못 쓴다. 글자 폭은 강조 12px · 보통 16px, 줄 끝 256px.
🔴 **줄 수를 바꾸지 않는다** — 스크롤이 곡 길이에 맞춰져 있다. 제목을 두 줄로 늘린 대신
   바로 밑 빈 줄 하나를 쓴다.
⚠ 원문은 여기 없다 — 빌드 때 originals 에서 읽는다. 표의 JP 열쇠는 역할명·배역명 같은
   **단어 수준 라벨**이다(루트 「저작권」: 단어 라벨은 코드 유지 OK).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font

MODULE_REL = 898
OFF, SIZE = 0x5A25, 2241
TAB, ADV, ADV_PLAIN, LIMIT = 32, 12, 16, 256
FW = str.maketrans({chr(c): chr(c + 0xFEE0) for c in range(0x21, 0x7F)} | {" ": "　"})


def fw(s: str) -> str:
    return s.translate(FW)


# 배역(성우 표의 왼쪽 열) — 칸 CAST_COL 자 안에 들어가야 한다
CAST = {
    # 🔴 표기 순위(마스터 2026-09-25): ① 팔콤 공식(음반 『Symphonic Poem Dragon Slayer -The Legend
    #   of Heroes- Vol.2』 곡명 — Selios · Sonia · Rias · Akdam) ② PC-98 영문 팬 번역
    #   (nleseul/ds6_pc98_trans 화자 칸). 영문판(TGXCD1029)은 이름을 통째로 바꿔(Logan …) 못 쓴다.
    "ナレーション": "Narration",
    "セリオス": "Selios",  # 공식
    "リュナン": "Runan",  # 팬
    "ロー": "Ro",  # 팬
    "ゲイル": "Gail",  # 팬
    "ソニア": "Sonia",  # 공식
    "ディーナ姫": "Dina",  # 팬 「Princess Dina」 는 10자 칸을 넘어 이름만(마스터 2026-09-25)
    "ライアス": "Rias",  # 공식(팬은 Lyas)
    "ボアード": "Buald",  # 팬
    "大盗賊ゲイル": "Gail I",  # 게일의 할아버지(랄프가 2세) — 팬 「The Great Thief Gail」 은 10자 칸을 넘는다(마스터 2026-09-25)
    "アクダム": "Akdam",  # 공식(팬은 Achdam)
    "シルフィ": "Sylphie",  # 팬
    "バジール": "Beziel",  # 팬
    "アグニージャ": "Agnija",  # 팬
}
CAST_COL = 10  # 배역 칸 폭(자) — 이름 열 32+12×10 = 152px, 6자 이름(16px 글씨)이 248px 에 끝난다

# 역할·회사·제목 — 줄 안의 그 글자열을 통째로 바꾼다(사람 이름 줄은 안 건드린다)
ROLE = {
    # 🔴 영문판(TGXCD1029, originals/us/pce-ed1) 스태프롤과 **담당자 이름으로 짝지어** 그 표기를 따랐다
    #   (마스터 2026-09-24: 「영문판 참고」). 짝이 없는 역할만 우리가 옮겼다(# 자체).
    #   튜플 = 두 줄 — 영문판도 그렇게 나눈다. 바로 앞 빈 줄을 첫 줄로 쓴다(줄 수 보존).
    "制作・総指揮": "Executive Producer",
    "オリジナル・プログラム": "Original Program",
    "プログラム": "Program",
    "サウンド": "Sound",  # 자체(영문판엔 머리말이 없다)
    "作曲": "Original Score",
    "ファルコム": "Falcom",
    "サウンドチーム": "Sound Team",
    "編曲": "Arranger",
    "レコーディング": "Recording",
    "ＭＩＴスタジオ": "Studio MIT",
    "録音": "Engineer",  # 자체(영문판은 Recording 한 칸에 사람·스튜디오를 같이 둔다)
    "サウンドプロデューサー": "Sound Director",
    "ナレーション協力": "Voice Production",  # 자체(영문판은 성우가 달라 없다)
    "青二プロダクション": "Aoni Production",
    "スタジオタバック": "Studio Tavac",
    "グラフィック": "Graphics",  # 자체
    "グラフィック・チーフ": "Art Direction",
    "絵コンテ": "Sketching",
    "作画監督": "Graphic Direction",
    "（スタジオライブ）": "(Studio Live)",
    "原画": "Original Art",
    "ビジュアル・デモ": "Graphic Scrolling",
    "（ＡＤＳ）": "(ADS)",
    "ゲーム・グラフィック": "Game Graphics",  # 자체
    "オリジナル・デザイン": "Original Design",  # 영문판 「Original Graphic Design」 은 한 줄에 안 들고 앞에 빈 줄이 없다
    "日本ファルコム": "Nihon Falcom",
    "デザイン・スタッフ": "Graphic Design",
    "オリジナル・シナリオ": "Original Scenario",
    "シナリオ再構成": "Scenario Rewrite",
    "テンポラリー・アドバイザー": "Temporary Adviser",  # 자체
    "スペシャル・サンクス": "Special Thanks",
    "（ＲＥＤカンパニー）": "(RED Company)",
    "制作進行": ("Project", "Coordination"),
    "ディレクター": "Director",
    "プロデューサー": "Project Manager",
    "スーパーバイザー": "Supervisor",
    "エグゼクティブプロデューサー": ("Executive", "Production Manager"),
}
TITLE_JP = "ドラゴンスレイヤー英雄伝説"
TITLE = ("Dragon Slayer", "The Legend of Heroes")


def original() -> bytes:
    return common.track_data(MODULE_REL, 128)[OFF : OFF + SIZE]


def width(line: bytes) -> int:
    """줄 끝 x(px). 🔴 글자 폭이 **굵기마다 다르다**(2026-09-24 화면 실측) — 강조(`1B`~`1D`,
    역할명)는 12px, 보통(이름·회사)은 16px. 처음엔 12px 하나로 재서 「Nihon Falcom」 이 잘렸다."""
    x, i, bold = 0, 0, False
    while i < len(line):
        c = line[i]
        if c == 9:
            # 🔴 탭은 칸 정렬이 아니라 **늘 +32px**(2026-09-24 마스터 캡처: 「탭 탭 공백 탭」 줄의
            #   「MIT」 가 96 이 아니라 112 에서 시작했고, 넘친 「o」 가 BAT 를 돌아 왼쪽 끝에 나왔다)
            x += TAB
            i += 1
        elif c == 0x1B:
            bold = True
            i += 1
        elif c == 0x1D:
            bold = False
            i += 1
        elif c < 0x20:
            i += 1
        else:
            x += ADV if bold else ADV_PLAIN
            i += 2
    return x


def sj(s: str) -> bytes:
    return s.encode("cp932")


def fit(line: bytes) -> bytes:
    """폭을 넘으면 들여쓰기(앞 전각 공백 → 앞 탭)를 하나씩 덜어 낸다."""
    while width(line) > LIMIT:
        head = len(line) - len(line.lstrip(b"\t"))
        rest = line[head:]
        # 탭 뒤·강조 앞의 전각 공백부터
        k = rest.find(sj("　"))
        if k == 0 or (k > 0 and rest[:k].strip(b"\x1b\x1d\t") == b""):
            line = line[:head] + rest[:k] + rest[k + 2 :]
        elif head:
            line = line[1:]
        else:
            raise ValueError(f"들여쓰기를 다 덜어도 {width(line)}px: {line!r}")
    return line


# ── 한글판(제품 기본, 마스터 10-16 「스태프롤 한글 적용하자」 · ED_STAFF_EN=1 이면 옛 전각 영문) ─────────────────────────────────────────────────────────────────────────
# 마스터 10-15 「ed2 와 일관성: 분야 라벨 한글 · 성우 배역 이름은 정본 한글 · 사람·회사 이름은 원문」. pce-ed2 `ending.py` 와 같은 길 — 렌더러가 글자마다 부르는
# BIOS `EX_GETFNT`(`JSR $E060`, 모듈 +0x56B3·+0x57CC) 의 피연산자를 우리 루틴으로 돌린다: 리드 `F0` 이면 자체 표(24B/자)에서 `($FA)` 로 복사, 아니면 `JMP $E060`.
KR = not os.environ.get("ED_STAFF_EN")
NAME_TIGHT = not os.environ.get("ED_NAME_F1")  # 이름 줄도 12px 전진(굵게 경로, 마스터 10-16 「12px로 바꾸자」) — ED_NAME_F1=1 이면 옛 F1 꼴
LEAD, TRAIL0 = font.LEAD0, font.TRAIL0
SEAM_OFFS = (0x56B4, 0x57CD)  # `20 60 E0` 의 피연산자
SEAM_OLD = b"\x60\xe0"
BIOS_GETFNT = 0xE060
KO_ROLE = {  # 분야 라벨(굵은 줄) — 회사·팀·스튜디오 이름은 원문 그대로 둔다
    "制作・総指揮": "제작・총지휘",
    "オリジナル・プログラム": "오리지널 프로그램",
    "プログラム": "프로그램",
    "サウンド": "사운드",
    "作曲": "작곡",
    "編曲": "편곡",
    "レコーディング": "레코딩",
    "録音": "녹음",
    "サウンドプロデューサー": "사운드 프로듀서",
    "ナレーション協力": "내레이션 협력",
    "グラフィック": "그래픽",
    "グラフィック・チーフ": "그래픽 치프",
    "絵コンテ": "콘티",
    "作画監督": "작화 감독",
    "原画": "원화",
    "ビジュアル・デモ": "비주얼 데모",
    "ゲーム・グラフィック": "게임 그래픽",
    "オリジナル・デザイン": "오리지널 디자인",
    "デザイン・スタッフ": "디자인 스태프",
    "オリジナル・シナリオ": "오리지널 시나리오",
    "シナリオ再構成": "시나리오 재구성",
    "テンポラリー・アドバイザー": "템포러리 어드바이저",
    "スペシャル・サンクス": "스페셜 땡스",
    "制作進行": "제작 진행",
    "ディレクター": "디렉터",
    "プロデューサー": "프로듀서",
    "スーパーバイザー": "슈퍼바이저",
    "エグゼクティブプロデューサー": "이그제큐티브 프로듀서",
}
# 사람·회사 이름(마스터 10-16 「아예 일본어가 안 남게」, 외래어 표기법). 읽기가 불확실하던 여섯(에비나·고라이·모모타·오야마·사와구치·타박)은 마스터 지시로 웹 조사(북미판 영문 크레딧 등)로
# 정했다 — 근거 표는 관리자 `names-final-1016.tsv`. 열쇠 = 원문에서 전각 공백을 뺀 꼴. 영문(J.D.K. 등)은 그대로. 회사는 공식 로마자가 있으면 그 이름을 옮기고 없으면 가나를 옮긴다.
KO_NAME = {
    # 성우 13(오프닝 크레딧과 같은 표기)
    "銀河万丈": "긴가 반조",
    "大倉正章": "오쿠라 마사아키",
    "戸谷公次": "도야 고지",
    "田中亮一": "다나카 료이치",
    "掛川裕彦": "가케가와 히로히코",
    "原えりこ": "하라 에리코",
    "皆口裕子": "미나구치 유코",
    "宮内幸平": "미야우치 고헤이",
    "西村知道": "니시무라 도모미치",
    "永井一郎": "나가이 이치로",
    "野田圭一": "노다 게이이치",
    "寺瀬めぐみ": "데라세 메구미",
    "郷里大輔": "고리 다이스케",
    # 제작진
    "芳賀孝宏": "하가 다카히로",
    "米光亮": "요네미쓰 료",
    "鈴木誠": "스즈키 마코토",
    "斎藤晴夫": "사이토 하루오",
    "星恵太": "호시 게이타",
    "井上雅明": "이노우에 마사아키",
    "滝本利昭": "다키모토 도시아키",
    "古市利雄": "후루이치 도시오",
    "藤本佳代": "후지모토 가요",
    "松下浩美": "마쓰시타 히로미",
    "藤沢俊幸": "후지사와 도시유키",
    "竹内浩志": "다케우치 히로시",
    "山口美佳": "야마구치 미카",
    "佐々木伸": "사사키 신",
    "守山智幸": "모리야마 도모유키",
    "岡田寿夫": "오카다 도시오",
    "武田真理": "다케다 마리",
    "日高真一": "히다카 신이치",
    "大竹浩史": "오타케 히로시",
    "田中和恵": "다나카 가즈에",
    "長山豊": "나가야마 유타카",
    "進藤司": "신도 쓰카사",
    "小林正樹": "고바야시 마사키",
    "相田和彦": "아이다 가즈히코",
    "\x03口岳志": "사와구치 다카시",  # 첫 글자 「澤」 는 제어코드 03 의 외자 글리프(원판 화면 확인)
    "工藤裕司": "구도 유지",
    "杉本悟": "스기모토 사토루",
    "蝦名寿昌": "에비나 도시마사",
    "近永早苗": "지카나가 사나에",
    "牛来隆行": "고라이 다카유키",
    "百田亮海": "모모타 료미",
    "佐橋秀樹": "사하시 히데키",
    "宮本徳人": "미야모토 노리히토",
    "小山俊典": "오야마 도시노리",
    "松永智史": "마쓰나가 사토시",
    "木本旬": "기모토 준",
    "中本伸一": "나카모토 신이치",
    # 회사·팀·스튜디오
    "日本ファルコム": "니혼 팔콤",
    "ファルコム": "팔콤",
    "サウンドチーム": "사운드 팀",
    "ＭＩＴスタジオ": "ＭＩＴ 스튜디오",
    "青二プロダクション": "아오니 프로덕션",
    "スタジオタバック": "스튜디오 타박",  # 공식 영문 Studio Tavac 기준
    "（スタジオライブ）": "（스튜디오 라이브）",
    "（ＲＥＤカンパニー）": "（ＲＥＤ 컴퍼니）",
    "（ＡＤＳ）": "（ＡＤＳ）",  # 영문은 그대로 — 괄호만 안쪽 글리프
}
OPENING_CAST = [  # 오프닝 성우 크레딧 이름 13명(원문, 한글) — 오프닝 크레딧 모듈 안 순서($5C2B 부터 11B 간격, `credits_kr`)
    ("大倉正章", "오쿠라 마사아키"),
    ("戸谷公次", "도야 고지"),
    ("田中亮一", "다나카 료이치"),
    ("掛川祐彦", "가케가와 히로히코"),
    ("原　えりこ", "하라 에리코"),
    ("野田圭一", "노다 게이이치"),
    ("皆口裕子", "미나구치 유코"),
    ("銀河万丈", "긴가 반조"),
    ("宮内幸平", "미야우치 고헤이"),
    ("西村知道", "니시무라 도모미치"),
    ("寺瀬めぐみ", "데라세 메구미"),
    ("永井一郎", "나가이 이치로"),
    ("郷里大輔", "고리 다이스케"),
]
KO_TITLE = ("드래곤 슬레이어", "영웅전설")
KO_CAST_EXTRA = {"ナレーション": "내레이션", "大盗賊ゲイル": "대도 게일"}


def _cast_ko(jp: str) -> str:
    if jp in KO_CAST_EXTRA:
        return KO_CAST_EXTRA[jp]
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
    import canon

    for cat in ("person", "speaker", "ui"):
        r = canon.lookup(jp, cat, "ed2")  # ED1·ED2 공통 세계 — 사전 입구는 canon 하나
        if r:
            return r
    raise KeyError(jp)


BR_CHARS = "()"  # 전각 괄호는 자체 글리프로 — 보통/굵은 글씨 줄 모두 12px 칸 안에서 괄호 잉크를 **안쪽 가장자리**에 붙인다(반각처럼 글자에 붙는다, 마스터 10-16 「괄호는 반각」)
BR_MAP = str.maketrans({"（": "(", "）": ")"})


def _glyph(ch: str) -> bytes:
    """글리프 표 한 글자 24B — 괄호는 기본 글꼴의 3px 괄호를 칸의 안쪽(여는 괄호 = 오른쪽 끝, 닫는 괄호 = 왼쪽 끝)으로 민다."""
    g = font.glyph(ch)
    if ch not in BR_CHARS:
        return g
    shift = 8 if ch == "(" else 1
    rows = [int.from_bytes(g[2 * i : 2 * i + 2], "big") >> shift for i in range(12)]
    return b"".join((r & 0xFFF0).to_bytes(2, "big") for r in rows)


def _is_hangul(ch: str) -> bool:
    return "\uac00" <= ch <= "\ud7a3"


def _enc_ko(text: str, idx: dict) -> bytes:
    """한글 문안 → SJIS 2바이트열 — 한글은 리드 F0 + 트레일(0x24+번호), 공백은 전각, 가운뎃점은 `81 45`."""
    out = bytearray()
    for ch in text:
        if ch == " ":
            out += b"\x81\x40"
        elif ch == "・":
            out += b"\x81\x45"
        elif _is_hangul(ch) or ch.translate(BR_MAP) in BR_CHARS:
            out += bytes([LEAD, TRAIL0 + idx[ch.translate(BR_MAP)]])
        else:
            out += sj(ch)  # 전각 영문 — BIOS 글꼴
    return bytes(out)


def _enc_name(text: str, idx: dict) -> bytes:
    """사람·회사 이름(보통 글씨 줄) — 성/이름 사이 공백을 **칸으로 안 두고** 뒤 낱말의 한글을 리드 F1(오른쪽으로 4px 민 꼴)로 쓴다.
    글자 둘 사이 틈이 4px → 8px(반각 공백 폭)가 되고 한 칸이 줄어, 9칸 이름도 원판의 이름 열(128px)에 든다(마스터 10-16 정렬·반각)."""
    out = bytearray()
    for n, word in enumerate(text.split(" ")):
        for ch in word:
            if _is_hangul(ch) or ch.translate(BR_MAP) in BR_CHARS:
                out += bytes([LEAD + (1 if n else 0), TRAIL0 + idx[ch.translate(BR_MAP)]])
            else:
                out += sj(ch)
        if n == 0 and len(text.split(" ")) > 1 and not _is_hangul(word[-1]):
            out += b"\x81\x40"  # 영문 낱말 뒤는 전각 공백을 둔다(ＭＩＴ 스튜디오)
    return bytes(out)


def _ko_strings() -> list[str]:
    s = list(KO_ROLE.values()) + list(KO_TITLE) + [_cast_ko(k) for k in CAST] + list(KO_NAME.values())
    return s


def glyph_chars() -> list[str]:
    return sorted({ch for t in _ko_strings() for ch in t.translate(BR_MAP) if _is_hangul(ch) or ch in BR_CHARS})


KO_CAST_COL = max(len(_cast_ko(k)) for k in CAST) + 1  # 6 — 가장 긴 배역명(디나 공주·대도 게일) 뒤에도 한 칸 띄운다(시험 캡처에서 이름에 붙었다)


def _name_ko(jp: str, idx: dict) -> bytes:
    """원문 이름(전각 공백 포함 가능)을 KO_NAME 으로 — 표에 없으면(보통·낮음 확신) 원문 그대로."""
    key = jp.replace("　", "")
    if key not in KO_NAME:
        return sj(jp)
    ko = KO_NAME[key]
    if NAME_TIGHT and all(_is_hangul(c) or c == " " for c in ko):
        # 마스터 10-16 「글자 사이 여백이 커서 띄어쓰기가 안 느껴진다」 — 이름도 굵은 줄 경로(12px 전진)로 라벨처럼 촘촘히, 성/이름 사이는 12px 칸(보통 간격 4px + 12 = 16px 이상 틈)
        return b"\x1b" + _enc_ko(ko, idx) + b"\x1d"
    return _enc_name(ko, idx)


def build_kr() -> bytes:
    idx = {ch: i for i, ch in enumerate(glyph_chars())}
    src = original()
    body = src.split(b"\x1a", 1)[0]
    lines = body.split(b"\r\n")
    out: list[bytes] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        text = ln.decode("cp932")
        if TITLE_JP in text:
            assert lines[i + 1] == b"", "제목 밑 빈 줄이 없다"
            # 제목 두 줄은 둘 다 **보통 글씨(16px 전진)** 로 화면 가운데에 둔다 — 원판 일본어 제목(전각 한 줄, 앞 전각 공백 하나)과 같은 서체·간격이다.
            #   (처음엔 아랫줄을 굵은 12px 로 해 x=0 에 붙어 작고 잘려 보였다 — 마스터 10-16 캡처)
            for line in KO_TITLE:
                w_px = ADV_PLAIN * len(line.replace(" ", "")) + ADV_PLAIN * line.count(" ")  # 한글 하나·공백 하나 모두 16px
                lead = max(0, (LIMIT - w_px) // 2 // ADV_PLAIN)
                out.append(fit(sj("　") * lead + _enc_ko(line, idx)))
            i += 2
            continue
        if "\x1b" in text and "\x1d" in text:
            pre, rest = text.split("\x1b", 1)
            mid, post = rest.split("\x1d", 1)
            key = mid.rstrip("　")
            if key in CAST and post:
                ko = _cast_ko(key)
                assert len(ko) <= KO_CAST_COL, (key, ko)
                # 이름 열을 가장 긴 배역명 폭(+1칸)으로 앞당긴다 — 성/이름 사이를 칸으로 안 두니(`_enc_name`) 8칸(128px) 이름이 32+72+128=232px 안에 든다(배역 시작 x=32 는 원판 그대로)
                b = sj(pre) + b"\x1b" + _enc_ko(ko, idx) + sj("　") * (KO_CAST_COL - len(ko)) + b"\x1d" + _name_ko(post, idx)
                assert width(b) <= LIMIT, (ko, width(b))
                out.append(b)
                i += 1
                continue
            if key in KO_ROLE:
                b = sj(pre) + b"\x1b" + _enc_ko(KO_ROLE[key], idx) + sj(mid[len(key) :]) + b"\x1d" + sj(post)
                out.append(fit(b))
                i += 1
                continue
            if key in KO_NAME:  # 굵은 회사 줄(（스튜디오 라이브） 등)
                b = sj(pre) + b"\x1b" + _enc_ko(KO_NAME[key], idx) + sj(mid[len(key) :]) + b"\x1d" + sj(post)
                out.append(fit(b))
                i += 1
                continue
        else:
            core = text.lstrip("\t　")
            if core.replace("　", "") in KO_NAME:  # 보통 글씨 이름·회사 줄 — 들여쓰기는 두고 이름만 바꾼다
                head = text[: len(text) - len(core)]
                out.append(fit(sj(head) + _name_ko(core, idx)))
                i += 1
                continue
        out.append(ln)
        i += 1
    assert len(out) == len(lines), (len(out), len(lines))
    return b"\r\n".join(out) + b"\x1a"


def hook_code(base: int, seg_a: int, n_a: int, seg_b: int, n_b: int) -> bytes:
    """리드 F0 → 18B 묶음 표(앞 구역 `seg_a` n_a 자 · 뒤 구역 `seg_b`)에서 24B 로 풀어 `($FA)` 에 쓴다(BIOS 와 같은 규약: `$F9`=리드 · `$F8`=트레일), 나머지는 BIOS 로.
    풀이 루틴은 오프닝 크레딧과 같다(`credits_kr.routine`, 뱅크 걸기 없음) — 24B 표는 글자 140자에서 자막 런타임 자리를 모자라게 했다(18B 로 묶어 25% 줄임)."""
    import credits_kr

    segs = [(seg_a, n_a)] + ([(seg_b, n_b)] if n_b else [])
    return credits_kr.routine(base, segs, None, shift=True)


def kr_layout() -> dict:
    """글리프 표 앞부분은 **원래 스태프롤 자리**(포인터를 옮겨 비었다, +0x5A25~, 2,241B)에 두고, 뒤는 새 텍스트 뒤 훅 루틴 곁에 둔다(자막 런타임은 그 뒤). 글리프는 18B 묶음."""
    text = build_kr()
    chars = glyph_chars()
    n_low = min(len(chars), SIZE // font.PACKED_BYTES)
    t_end = NEW_OFF + len(text)
    hook_off = (t_end + 1 + 1) & ~1
    probe = hook_code(hook_off + 0x2000, 0, n_low, 0, len(chars) - n_low)
    hi_off = (hook_off + len(probe) + 1) & ~1
    end = hi_off + font.PACKED_BYTES * (len(chars) - n_low)
    return {
        "text": text,
        "hook_off": hook_off,
        "hi_off": hi_off,
        "chars": chars,
        "n_low": n_low,
        "end": end,
        "hook_len": len(probe),
    }


def end_off() -> int:
    """스태프롤이 쓰는 모듈 오프셋의 끝(자막 런타임 코드 자리의 시작 하한)."""
    if KR:
        return kr_layout()["end"]
    return NEW_OFF + len(build().split(b"\x1a", 1)[0]) + 1


def apply_kr(f, touched) -> str:
    from shared.disc import mode1

    lay = kr_layout()
    lba = common.T2_SECTOR + MODULE_REL
    size = 128 * common.USER
    text = lay["text"].split(b"\x1a", 1)[0] + b"\x1a"
    n_low = lay["n_low"]
    chars = lay["chars"]
    hook = hook_code(
        lay["hook_off"] + 0x2000,
        OFF + 0x2000,
        n_low,
        lay["hi_off"] + 0x2000,
        len(chars) - n_low,
    )
    table_lo = b"".join(font.pack(_glyph(ch)) for ch in chars[:n_low])
    table_hi = b"".join(font.pack(_glyph(ch)) for ch in chars[n_low:])
    assert lay["end"] <= 0x8000, (lay["end"], "스태프롤 한글이 모듈 창($8000) 을 넘는다")
    orig = original()
    spans = [
        (NEW_OFF, text, b"\0" * len(text), "staffroll ko text"),
        (lay["hook_off"], hook, b"\0" * len(hook), "staffroll ko hook"),
        (OFF, table_lo, orig[: len(table_lo)], "staffroll ko glyphs(앞, 원래 자리)"),
    ]
    if table_hi:
        spans.append((lay["hi_off"], table_hi, b"\0" * len(table_hi), "staffroll ko glyphs(뒤)"))
    for off, data, expect, label in spans:
        mode1.write_at(f, lba, size, off, data, label=label, expect=expect)
        first, last = off // common.USER, (off + len(data) - 1) // common.USER
        touched.append((lba + first, last - first + 1))
    addr = NEW_OFF + 0x2000
    old = bytes([0xA9, 0x25, 0x85, 0x10, 0xA9, 0x7A])
    new = bytes([0xA9, addr & 0xFF, 0x85, 0x10, 0xA9, addr >> 8])
    mode1.write_at(f, lba, size, PTR_OFF, new, label="staffroll pointer", expect=old)
    touched.append((lba + PTR_OFF // common.USER, 1))
    seam = (lay["hook_off"] + 0x2000).to_bytes(2, "little")
    for off in SEAM_OFFS:
        mode1.write_at(f, lba, size, off, seam, label="staffroll EX_GETFNT seam", expect=SEAM_OLD)
        touched.append((lba + off // common.USER, 1))
    return (
        f"스태프롤 한글 텍스트 {len(text)}B · 글자 {len(chars)}(앞 표 {n_low}자는 원래 자리) · 후킹 {len(hook)}B"
        f" → 모듈 +0x{NEW_OFF:X}~+0x{lay['end']:X}(남은 자리 {0x8000 - lay['end']}B)"
    )


def build() -> bytes:
    if KR:
        return build_kr()
    src = original()
    body = src.split(b"\x1a", 1)[0]
    lines = body.split(b"\r\n")
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        text = ln.decode("cp932")
        if TITLE_JP in text:
            # 제목 두 줄 — 밑의 빈 줄 하나를 쓴다(줄 수 보존)
            assert lines[i + 1] == b"", "제목 밑 빈 줄이 없다"
            out.append(fit(sj("　" + fw(TITLE[0]))))
            # 부제는 강조(12px) — 보통 글씨(16px)로는 20자가 320px 라 한 줄에 안 든다
            out.append(fit(sj("\x1b" + fw(TITLE[1]) + "\x1d")))
            i += 2
            continue
        if "\x1b" in text and "\x1d" in text:
            pre, rest = text.split("\x1b", 1)
            mid, post = rest.split("\x1d", 1)
            key = mid.rstrip("　")
            if key in CAST and post:  # 성우 표: 배역 칸 + 이름 — 🔴 fit() 로 덜면 열이 어긋난다
                role = fw(CAST[key])
                assert len(role) <= CAST_COL, (key, role)
                new = pre + "\x1b" + role + "　" * (CAST_COL - len(role)) + "\x1d" + post
            elif key in ROLE and isinstance(ROLE[key], tuple):
                first, second = ROLE[key]
                assert out and out[-1] == b"", ("두 줄 역할 앞에 빈 줄이 없다", key)
                out[-1] = fit(sj(pre + "\x1b" + fw(first) + "\x1d"))
                new = pre + "\x1b" + fw(second) + mid[len(key) :] + "\x1d" + post
            elif key in ROLE:
                new = pre + "\x1b" + fw(ROLE[key]) + mid[len(key) :] + "\x1d" + post
            else:
                new = text
        else:
            key = text.lstrip("\t　")
            new = text[: len(text) - len(key)] + fw(ROLE[key]) if key in ROLE else text
        b = sj(new)
        if "\x1b" in text and text.split("\x1b", 1)[1].split("\x1d", 1)[0].rstrip("　") in CAST:
            assert width(b) <= LIMIT, f"배역 줄이 넘친다(열을 못 맞춘다): {new!r} {width(b)}px"
        out.append(fit(b))
        i += 1
    assert len(out) == len(lines), (len(out), len(lines))
    data = b"\r\n".join(out) + b"\x1a"
    return data


# 🔴 자리를 옮긴다(2026-09-24) — 전각 영문이 원래 자리(2,241B)를 304B 넘는다(2,545B).
#   모듈 +0x64D9 부터 6,951B 가 0 이고, 쓰기 BP 로 엔딩 전 구간을 지켜보니 **곡이 끝난 뒤**
#   (오마케 적재, BIOS CD 전송 $EA9C)에야 덮인다 — 스태프롤이 도는 동안은 비어 있다.
#   시작 주소는 +0x50A6 `LDA #$25 / STA $10 / LDA #$7A / STA $11` 한 곳뿐이다(원문 $7A25 =
#   모듈 +0x5A25, 즉 이 시점 논리 = 모듈 오프셋 + $2000 — 원문이 $8000 창을 걸쳐 읽히므로
#   +0x6500 → $8500 도 같은 창이다).
NEW_OFF = 0x6500
NEW_ROOM = 0x64D9 + 6951 - NEW_OFF
PTR_OFF = 0x50A6


def apply(f, touched) -> str:
    if KR:
        return apply_kr(f, touched)
    from shared.disc import mode1

    data = build().split(b"\x1a", 1)[0] + b"\x1a"
    assert len(data) <= NEW_ROOM, (len(data), NEW_ROOM)
    lba = common.T2_SECTOR + MODULE_REL
    size = 128 * common.USER
    mode1.write_at(f, lba, size, NEW_OFF, data, label="staffroll text", expect=b"\0" * len(data))
    addr = NEW_OFF + 0x2000
    old = bytes([0xA9, 0x25, 0x85, 0x10, 0xA9, 0x7A])
    new = bytes([0xA9, addr & 0xFF, 0x85, 0x10, 0xA9, addr >> 8])
    mode1.write_at(f, lba, size, PTR_OFF, new, label="staffroll pointer", expect=old)
    for off, n in ((NEW_OFF, len(data)), (PTR_OFF, len(new))):
        first, last = off // common.USER, (off + n - 1) // common.USER
        touched.append((lba + first, last - first + 1))
    return f"스태프롤 전각 영문 {len(data)}B → 모듈 +0x{NEW_OFF:X} (포인터 ${addr:04X})"


def main() -> None:
    new = build()
    body = new.split(b"\x1a", 1)[0]
    for ln in body.split(b"\r\n"):
        w = width(ln)
        vis = ln.replace(b"\x1b", b"").replace(b"\x1d", b"").replace(b"\t", b">").decode("cp932")
        print(f"{w:3} {vis}")
    print(
        f"바이트 {len(body) + 1} / 새 자리 {NEW_ROOM} · 최대 폭 {max(map(width, body.split(b'\r\n')))}px"
    )


if __name__ == "__main__":
    main()
