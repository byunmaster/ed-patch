"""엔딩 스태프롤(rel 909) — **사람 이름만 원문**, 나머지(역할·배역·회사·제목)는 전각 영문.

    python3 games/pce-ed1/tools/staffroll.py          # 새 스태프롤 미리보기 + 폭·바이트 검사

마스터 확정 2026-09-24: 「스태프 역할명은 전각영문으로 해도 충분할듯」. 한글이 아닌 이유 —
엔딩 모듈(rel 898)은 BIOS `EX_GETFNT` 로 직접 그리고 우리 글리프 훅이 거기엔 없다
(오프닝 성우 크레딧 표제를 `ＣＡＳＴ` 로 비켜 간 것과 같은 판단).

구조(엔딩 모듈 +0x5A25~+0x62E5, 2,241B, `1A` 종단):
    줄 = … `0D 0A`, `09` = 탭(다음 32px 칸), `1B`/`1D` = 강조 여닫이, 그 밖 = **2바이트 SJIS**
    렌더러(모듈 +0x5688)는 `< 0x20` 만 제어로 보고 **나머지를 늘 2바이트로 읽는다** — 반각 영문은
    못 쓴다. 글자 폭은 강조 12px · 보통 16px, 줄 끝 256px.
🔴 **줄 수를 바꾸지 않는다** — 스크롤이 곡 길이에 맞춰져 있다. 제목을 두 줄로 늘린 대신
   바로 밑 빈 줄 하나를 쓴다.
⚠ 원문은 여기 없다 — 빌드 때 originals 에서 읽는다. 표의 JP 열쇠는 역할명·배역명 같은
   **단어 수준 라벨**이다(루트 「저작권」: 단어 라벨은 코드 유지 OK).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common

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


def build() -> bytes:
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
