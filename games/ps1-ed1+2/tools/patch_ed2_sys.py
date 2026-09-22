#!/usr/bin/env python3
"""ED2 시스템 텍스트(ED2.EXE) 한글화 — 파티 이름 · 메뉴 · 전투 커맨드 · 지명 두 표.

**왜 따로인가.** 디스크에 실행파일이 둘이고(`ED.EXE` LBA 257 · `ED2.EXE` LBA 756)
**같은 UI 문자열을 각자 한 벌씩** 들고 있다. 공유가 아니라 **사본**이라 ED1 쪽만 고치면
ED2 화면은 일본어로 남고, 따로 번역하면 **한 디스크가 두 말을 한다.**

그래서 새로 번역하지 않는다 — **ED1 정본(`patch_sys_ui.UI`·`PLACES`)을 원문으로 대조해
옮긴다.** 오프셋이 아니라 **원본 SJIS 문자열**로 짝을 짓기 때문에 두 EXE 의 배치가 달라도
어긋나지 않고, 한쪽을 고치면 다른 쪽이 따라온다(실측: 메뉴 52건 중 51건이 ED1 정본으로
덮인다 — `呪文能力` 하나만 ED2 에 새로 있다).

지명은 표가 둘이다. **HUD 판(14B)** 은 화면 우하단에 뜨는 것이고, **워프 메뉴(16B)** 는
목적지 목록이라 접미(`の町`·`の港`)가 붙는다. 정발 ED2 의 워프 목적지 표
(`dos_kr/ED2/F_000` 30곳)가 후자의 정본이다.

⚠ **둘 다 붙여 쓴다** — 슬롯이 좁은 층이라 그렇다(`늑대입`). 대사에서는 띄운다
(`늑대의 입`) — [policy.md](../docs/policy.md) 「표기 방침」.

⚠ **폰트가 먼저다.** ED2.EXE 에 한글 글리프를 굽는 건 `reinsert_kr_pilot` 이 한다
(`font_map.FONT_BASE`). 이 스크립트만 돌리면 글자가 안 나온다.

전제: `build.py` 체인 안에서 재삽입 뒤에 돈다 — 이미지 제자리 갱신.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hangul_map as H
import patch_sys_ui as P
from common import BUILD_DIR, extract, write_user_data

ED2_LBA, ED2_SIZE = 756, 872448

# HUD 상태이상 라벨 사본 — ED.EXE `0xF91D8`(patch_sys_ui.STATUS_BASE)와 값·스트라이드는
# 같고 오프셋만 다르다(034 RE, 위 apply() 참조).
STATUS_BASE_ED2 = 0xD4B10
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"

# 파티 이름 (0x800, 12B 슬롯) — 정발 ED2 코퍼스 실측(아트라스 188회 · 플로라 101 ·
# 신디 66 · 란도 56). ED1 party 가 ED.EXE 0x800 에 있는 것과 같은 자리다.
PARTY = {
    "アトラス": "아트라스",
    "ランドー": "란도",
    "フローラ": "플로라",
    "シンディ": "신디",
}

# ED1 에 없는 메뉴 라벨 — 나머지는 `patch_sys_ui.UI` 에서 원문으로 끌어온다.
# ⚠ `呪文` 은 「주문」이다(유저 개념 정정 2026-08-13, policy). 마법이 아니다.
MENU_EXTRA = {"呪文能力": "주문능력"}

# ⚠ **전투 커맨드를 여기 적지 말 것.** ED1↔ED2 정발이 갈리는 자리(`戦う`·`守る`·`強さ`·
# `逃げる`)라 한때 여기에 자리 override 를 뒀는데, 유저 판정으로 **ED2 정발로 두 편을
# 통일**했다(2026-08-17). 통일된 뒤엔 `patch_sys_ui.UI` 한 곳만 고치면 `positional()` 이
# 자리로 끌어가 ED2 도 따라온다 — 여기 다시 적으면 같은 지식이 두 곳에 갈린다.

# 지명 — **고유명은 ED1 과 한 표기**여야 한다(policy 「표기 방침」). ED1 에 있는 것은
# `patch_sys_ui.PLACES` 에서 원문으로 끌어오고, ED2 에만 나오는 것만 여기 적는다.
# 근거는 정발 ED2 코퍼스 실측 — 이슈타(29회) · 이즈(28) · 프로스(25) · 큐베라(15) ·
# 아훌(9) · 유이시스(8) · 베른(5) · 네사(4) · 사피아(3) · 그로스토스(3) · 테크니카(13) ·
# 모건(17) · 보아드(55) · 아네스(2). `ウイル` 은 대사에 「윌」로 나온다.
PLACES_ED2 = {
    # ⚠ **다섯 나라는 ED2.EXE 안의 표(0x9778~)에 따로 있다**(2026-08-16 실측). 씬 헤더에는
    # 0곳이라 `patch_sys_ui.PLACES`(ED.EXE 0xBE690 고정 슬롯표)와도 무관하다 — 상태 문서가
    # 「PLACES 에 넣는다」로 적혀 있었는데 그 표는 다른 자리였다. 널종단이라 제자리 치환이면
    # 바이트가 안 밀린다. 표기는 편차 대장의 나라 표가 정본이다.
    "ファーレーン": "파렌",
    "ウォンリーク": "온리크",
    "ラヌーラ": "라누라",
    "ソルディス": "솔디스",
    "モレストン": "모레스톤",
    "クルス": "크루즈",
    "ベルガ": "베르가",
    "ネリア": "네리아",
    "ロンド": "론도",
    "ラルファ": "랄파",
    "シリカ": "시리카",
    "ヨルド": "요르도",
    "ナッシュ": "낫슈",
    "セレ": "세레",
    "スエル": "스엘",
    "アムダ": "암다",
    "セダル": "세달",
    "ルドラ": "루드라",
    "カウル": "카울",
    "ナスール": "나슬",
    "ファエト": "파에토",
    "コルクス": "콜크스",
    "ボアード海運": "보아드해운",
    "イシュタ": "이슈타",
    "アフル": "아훌",
    "イズー": "이즈",
    "キュベラ": "큐베라",
    "プロス": "프로스",
    "ウイル": "윌",
    "ベルン": "베른",
    "ユイシス": "유이시스",
    "奈落の口": "나락의입",
    "アネスの塔": "아네스의탑",
    # qa2 021(마스터 QA, 2026-09-21) — の 를 살려 "사피아의호수"로 맞추려 했으나 제자리
    # 슬롯이 정확히 12B(=원문 サピアの湖 6음절 분)라 13B("사피아의호수")가 1B 초과로
    # 안 들어간다(`patch_scn_headers` 의 슬롯 assert 실측). 이 표는 REPACK 구획 밖(0x1880,
    # REPACK 은 0x800~0xF44)이라 늘릴 여유가 없다 — 대사 쪽만 반영하고 HUD 는 보류.
    "サピアの湖": "사피아호수",
    "モーガンの家": "모건의집",
    "ネサの辺土": "네사의변토",
    "グロストス城": "그로스토스성",
    "テクニカ": "테크니카",
    "溶岩炉": "용암로",
    "玉座の間": "옥좌의방",
    "中庭": "안뜰",
    "スロット１": "슬롯1",
    "スロット２": "슬롯2",
}

# qa2 021 후속(마스터 QA, 2026-09-22) — サピアの湖 는 이 파일 안에서도 **자리마다 여유가
# 다르다**. ED2SCN10 필드 HUD(씬 헤더, `patch_sys_ui.patch_scn_headers`)는 실측 12B 고정
# (원본 10B+널, `사피아의호수` 13B 는 1B 초과 — 실제로 `사피아의호수`로 바꿔 빌드해
# `AssertionError: '사피아의호수' 13B > 슬롯 12B @0x1880` 로 확인했다)이라 PLACES_ED2 는
# 여전히 `사피아호수`로 둔다. 반면 **이 파일이 관할하는 ED2.EXE 지명목록(0x9A280 대)은
# 14B 여유**(실측: `plan()`의 세 구획 스캔)라 の가 들어간다 — HUD 전역 값을 바꾸면
# 위 12B 슬롯이 깨지니, `plan()` 안에서만(=이 파일이 쓰는 표에만) 덮어쓴다.
PLACES_ED2_ROOMY = {
    "サピアの湖": "사피아의호수",
}

# ── ED2 아이템·주문 이름 ────────────────────────────────────────────────────
# ED1 정본(`patch_items.NAMES`·`MONSTERS`)이 153건 중 55건을 덮는다 — 두 편이 무기·방어구·
# 도구를 공유해서다. 여기엔 **ED2 에만 있는 것**만 적는다.
#
# 정발 소재: `originals/kr/dos-ed2/ED2MAIN.EXE 0x14A775` 에 27개짜리 14B stride 표가 있다
# (은의 플레이트 · 지팡이의 파편 · 투시 안경 · 철 아령 · 변환로의 열쇠 …).
#
# ⚠ **보통명사 아이템 둘은 ED2 정발을 따른다**(유저 확정 2026-08-14) — `幅広のつるぎ` 와
# `くさりかたびら` 는 고유명사가 아니라 원음 판정이 안 서는 자리다. ED1 은 `대형검`·
# `미늘 갑옷` 을 유지하므로 **두 편이 갈린다** — 의도한 결정이다.
NAMES_ED2 = {
    # 주문 (ED1 에 없는 것만)
    "ストール": "스톨",
    # ⚠ 정발 대조로 고쳤다(2026-08-15, 유저 지적) — 음차로 정하면 안 되는 자리다.
    # `ブラムナ` 는 원문이 `ブ`(bu)지만 **정발은 `프람나`**(5건)다 — `フラム`(프람)의
    # 광역 주문이라 계열을 살린 것이다. `ヒュドナ` 도 정발이 `휴드나`(3건)라 맞췄다.
    # ⚠ 몬스터 `ブラムナドッグ` 은 정발이 `브람나 독` 이라 **그쪽은 브람나로 둔다** —
    # 주문과 몬스터는 다른 것이고, 정발이 각각 그렇게 부른다.
    "ブラムナ": "프람나",
    "ヒュドナ": "휴드나",
    "エント": "엔트",
    "ビス": "비스",
    "ビスナ": "비스나",
    "レストナ": "레스토나",
    # 도구·시나리오 아이템
    "大笑い袋": "웃음보따리",
    "透視メガネ": "투시 안경",
    "鉄アレイ": "철 아령",
    "フレイアの微笑": "프레이아의 미소",
    "変換炉のカギ": "변환로의 열쇠",
    "光の杖": "빛의 지팡이",
    "切符": "표",
    "密造酒": "밀조주",
    "ランプ": "램프",
    "竜の涙": "용의 눈물",
    "ビキニ": "비키니",
    "布の服": "천 옷",
    # ⚠ ED1 과 갈리는 둘 (위 주석)
    "幅広のつるぎ": "대형검",
    "くさりかたびら": "사슬 갑옷",
    # ── ED2 전용 장비·도구 53건 (2026-08-16) ──────────────────────────────────
    # ⚠ **선례가 없다.** ED1 원본(`ED.EXE`)에 `理力`·`不死身`·`バトルスーツ`·`こんぼう`·
    # `聖剣` 이 하나도 없고, 정발 ED1·ED2 대사에도 「이력·곤봉·성검·불사」가 0건이다
    # (실측). 그래서 **정발 표기를 옮기는 게 아니라 새로 짓는 자리**다 — 편차 대장 기록.
    #
    # 지은 기준은 **ED1 정본의 계열**이다(`patch_items.NAMES`): 재질 수식은 붙이고
    # (`청동검`·`철창`), 개념·인물 수식은 「~의」를 살린다(`파멸의 검`). 방패·갑옷은
    # 정본이 이미 띄어 쓴다(`청동 방패`·`철 갑옷`).
    # ⚠ **우리 SCN 대사에 이미 확정된 것은 그걸 따른다** — 아래 ✅ 표시. 이름 표와 대사가
    # 갈리면 같은 물건이 화면에서 두 이름을 갖는다(정발이 안에서 갈릴 때와 같은 사고).
    "鉄球こんぼう": "철구 곤봉",
    "強者のやり": "강자의 창",
    "必殺のつるぎ": "필살의 검",
    "大地のおの": "대지의 도끼",
    "勇者のつるぎ": "용사의 검",
    "騎士のやり": "기사의 창",
    "撃破のつるぎ": "격파의 검",  # ✅ SCN3 대사
    "理力のつるぎ": "이력의 검",
    "正義のつるぎ": "정의의 검",
    "ドラゴンの剣": "드래곤의 검",
    "太陽の聖剣": "태양의 성검",
    "炎のやり": "불꽃의 창",
    "不死身のヨロイ": "불사의 갑옷",
    "バトルスーツ": "배틀슈트",
    "理力のヨロイ": "이력의 갑옷",
    "自由のヨロイ": "자유의 갑옷",
    "ドラゴンの鎧": "드래곤의 갑옷",
    "回復のヨロイ": "회복의 갑옷",
    "無敵のたて": "무적의 방패",
    "理力のたて": "이력의 방패",
    "希望のたて": "희망의 방패",
    "ドラゴンのたて": "드래곤의 방패",
    # ⚠ `マホウ`(마법)와 `スペル`(주문)은 **원문이 갈라 놓은 두 낱말**이라 우리도 가른다.
    # `呪文` = 「주문」 방침(policy)과도 맞는다 — 한쪽으로 뭉치면 반지 둘이 같은 이름이 된다.
    "マホウのゆびわ": "마법의 반지",
    "スペルのゆびわ": "주문의 반지",
    "賢者のゆびわ": "현자의 반지",
    # ⚠ **같은 물건인데 두 EXE 의 표기가 갈린다** — ED1 은 `オプナの指輪`(한자), ED2 는
    # `オプナのゆびわ`(가나)다. 정본은 원문 문자열로 짝을 짓기 때문에(`ed1_canon`) 이
    # 넷이 조용히 안 물려 일본어로 남아 있었다. 표기가 갈리는 자리는 **양쪽 다 적는다.**
    "オプナのゆびわ": "오프나의 반지",
    "テュトのゆびわ": "튜트의 반지",
    "クイクのゆびわ": "퀵의 반지",
    "幸運のゆびわ": "행운의 반지",
    "ビスのキノコ": "비스의 버섯",
    "回復キノコ": "회복 버섯",
    "レストナキノコ": "레스토나 버섯",
    "ビスナの実": "비스나의 열매",
    "眠りタケ": "수면 버섯",  # ✅ SCN 대사 — "레스토나 버섯"·"회복 버섯"과 같은 띄어쓰기(naming.md)
    "災害のお守り": "재해 방지 부적",  # ✅ SCN1 대사
    "戦士の笛": "전사의 피리",  # ✅ SCN 대사
    "キノコの王様": "버섯의 왕",  # ✅ SCN 대사
    "バクヤク": "폭약",  # ✅ SCN 대사
    "杖のかけら": "지팡이 조각",  # ✅ SCN3 대사
    "カノンの親書": "카논의 친서",  # ✅ SCN 대사
    "ランケアの親書": "랑케아의 친서",  # ✅
    "ハルパの親書": "하르파의 친서",  # ✅
    "マリスカの親書": "마리스카의 친서",  # ✅
    "アフル通行証": "아훌 통행증",  # ✅
    "イズー通行証": "이즈 통행증",  # ✅
    "キュベラ通行証": "큐베라 통행증",  # ✅
    "ウイル通行証": "윌 통행증",  # ✅
    "銀のプレート": "은 플레이트",  # ✅ SCN 대사
    "金のプレート": "금 플레이트",
    "銅のプレート": "동 플레이트",
    "不思議なマント": "신비한 망토",  # `不思議な` = 「신비한」(보물상자 변형과 한 표기)
    "不思議な箱": "신비한 상자",
    "シナリオ専用": "시나리오 전용",  # 내부 표식 — 화면에 뜨는지 미확인이나 남기면 일본어다
}

# 이름 구획은 **통째로 다시 채운다**(`repack_names`) — 칸 하나하나에 맞추지 않는다.
# ⚠ 처음엔 제자리 치환만 해서 칸이 좁은 다섯을 줄여 썼는데(`성지팡이`·`빛의 봉` …),
# ED2 정발은 `성스러운 지팡이`·`빛의 지팡이`·`얼음의 지팡이`·`용의 눈물` 이다(유저 지적
# 2026-08-14). 이름을 줄일 게 아니라 **자리를 옮기는 게 맞다** — ED1 도 그렇게 한다.
# 안전 근거: 이 구획의 이름 **153건이 전부 `lui`/`addiu` 로 참조된다**(참조 0건 0, 실측).
# 그래서 옮긴 뒤 `patch_items.redirect` 가 참조를 전부 갱신할 수 있다.
REPACK = ((0x800, 0xF44, "ED2 이름"),)

# ── 옮기면 안 되는 표 — 제자리에서만 채운다 ─────────────────────────────────
# 🔴 **시나리오 아이템 칸(`0xD4870~0xD4950`)은 재packing 하면 안 된다**(2026-08-16 실측).
# 한동안 `REPACK` 두 번째 구획으로 넣어 뒀는데, 그러면 **ED2 맵 배경이 통째로 검게** 나갔다
# (첫 맵부터. 캐릭터·HUD·창은 멀쩡하고 배경만 사라진다). 이 224B 만 원본으로 되돌리고
# 참조 19곳을 원복하니 그 자리에서 정상으로 돌아왔다 — differential 빌드로 확정.
#
# 왜 통과했나: **가진 게이트가 전부 초록이었다.** 이름 25개가 `lui`/`addiu` 로 **하나도
# 빠짐없이 참조**되고(참조 0건 0), `redirect` 의 부호확장 assert 도, `repack_names` 의
# 예산 assert 도 걸리지 않는다. 「참조가 있으니 옮겨도 된다」가 여기서 깨진다.
#
# 진짜 계약은 **간격**이다 — 원본에서 앞 20개(`ナイフ`…`リーフ`)가 정확히 8B 간격으로
# 놓여 있다. 코드가 포인터로도 부르고 `base + i*8` 로도 읽는 배열이라, 촘촘히 밀어 담으면
# 포인터 쪽만 맞고 인덱싱 쪽이 어긋난다. 루트 CLAUDE.md 「구조 계약」의 **위치** 항목이다.
FIXED_SLOTS = ((0xD4870, 0xD4950, "ED2 시나리오 아이템"),)

# 058(2026-09-14, 마스터 판정) — 光の杖·氷の杖·竜の涙·笛 넷은 FIXED_SLOTS 안에서도
# **8B 고정칸에 갇힌 시나리오 이벤트 전용 참조**다(정적 확인: 각 이름이 lui/addiu
# 참조 정확히 1곳뿐이고, 셋은 같은 이벤트큐 등록 함수(0x80021b3c)를, 笛는 그 자매
# 함수(0x80021d7c)를 부른다 — fp 카운터를 증가시키며 아이템을 순서대로 지급하는
# 연출). ⚠ **인벤토리는 이 표를 안 읽는다** — 같은 이름 넷이 전부 `NAMES_ED2`
# (REPACK 대상, 길이 제약 없음)에도 이미 있고 그쪽이 인벤토리 정본이다(비키니·
# 램프도 마찬가지 — 두 표에 값이 겹치는 건 034·051 처럼 새는 사고의 씨앗이 될 수도
# 있었지만, 이번엔 **인벤토리가 이미 옳아서** 대사 쪽 참조만 바꾸면 끝나는 쪽으로
# 뒤집혔다).
# ⇒ **FIXED_SLOTS 안 원래 칸(8B)은 손대지 않는다**(옆 슬롯 20개가 `base+i*8` 로도
# 읽히는 배열이라 스트라이드를 조금이라도 어긋나게 하면 위 "ED2 맵 배경이 검게
# 나간 사고"가 재현된다 — 이 넷도 그 배열 안에 있다). 대신 **참조(대사가 읽는
# 포인터)만** REPACK 구획(`0x800~0xF44`, `repack_names` 가 이미 매 빌드 다시
# 채우는 안전한 자리)의 재packing 뒤 남는 꼬리로 돌린다 — 새 0런을 찾지 않는다
# (052 교훈: 빈 공간이 VAB 일 수 있다).
FIXED_ITEM_REFS = {
    # (원본 lui 파일오프셋, 원본 addiu 파일오프셋, 원본 명령 워드 — 034 식 byte-assert)
    "光の杖": (0xF728, 0xF72C, 0x3C05800E, 0x24A54080),
    "氷の杖": (0x102D8, 0x102DC, 0x3C05800E, 0x24A540A0),
    "竜の涙": (0x10780, 0x10784, 0x3C05800E, 0x24A540A8),
    "笛": (0x12118, 0x1211C, 0x3C05800E, 0x24A54110),
}


def relocate_fixed_items(buf, canon):
    """`FIXED_ITEM_REFS` 의 대사 참조를 REPACK 꼬리의 완전한 KR 문자열로 돌린다.

    반환: 옮긴 수. 옮긴 항목은 `canon`에서 지운다 — `fill_fixed()`가 원래 칸을
    다시 건드리지 않게(원래 칸은 그대로 두는 게 계약이다, 위 주석).
    """
    import struct

    import patch_items as PI

    lo, hi, _label = REPACK[0]
    used = max((k for k in range(lo, hi) if buf[k]), default=lo - 1) + 1
    used = (used + 3) & ~3
    n = 0
    for jp, (lui_fo, imm_fo, want_lui, want_imm) in FIXED_ITEM_REFS.items():
        kr = canon.get(jp)
        if not kr:
            continue
        got_lui = struct.unpack_from("<I", buf, lui_fo)[0]
        got_imm = struct.unpack_from("<I", buf, imm_fo)[0]
        assert (got_lui, got_imm) == (want_lui, want_imm), (
            f"058 {jp!r} 참조 명령 불일치 @0x{lui_fo:X}/0x{imm_fo:X}: "
            f"{got_lui:08x}/{got_imm:08x} != {want_lui:08x}/{want_imm:08x}"
        )
        kb = _enc(kr) + b"\x00"
        new_fo = used
        assert new_fo + len(kb) <= hi, f"058 {jp!r} REPACK 꼬리 여유 부족 ({new_fo}+{len(kb)}>{hi})"
        buf[new_fo : new_fo + len(kb)] = kb
        used = (new_fo + len(kb) + 3) & ~3
        new_ram = PI.ram_of(new_fo)
        new_lo = new_ram & 0xFFFF
        new_hi = (new_ram >> 16) + (1 if new_lo & 0x8000 else 0)
        struct.pack_into("<I", buf, lui_fo, (want_lui & 0xFFFF0000) | new_hi)
        struct.pack_into("<I", buf, imm_fo, (want_imm & 0xFFFF0000) | new_lo)
        canon.pop(jp, None)
        n += 1
    if n:
        print(f"  058 시나리오 아이템 대사 참조 재배치 {n}건 (REPACK 꼬리, 정본 칸은 안 건드림)")
    return n


# 주문책 — `Xの書` 는 **주문 이름 + 「의 책」**이다(`呪文` 은 「주문」, policy 「표기 방침」).
# 이름은 ED1 정본에서 끌어오므로 여기 다시 적지 않는다 — 주문 표기를 고치면 책도 따라온다.
BOOK_SUFFIX = "의 책"

# 워프 메뉴(16B) 접미 — 정발 `F_000` 30곳의 표기를 따른다. 핵심어는 위 표를 쓰고
# 접미만 여기서 붙인다(같은 지명이 두 표에서 다른 말을 하지 않게).
# ⚠ `の港`→`항구` — ED1 정본(`patch_sys_ui.PLACES`: `네리아항구`·`론도항구`·`요르도항구`·
# `루드라항구`·`리셸항구`)과 맞춘다. 그 다섯은 `positional()`(ED1 표와의 자리 정렬)이
# 먼저 채워 이 표를 안 거치지만, **랄파는 ED1 표에 `ラルファの港` 가 없어**(ED1 은
# `ラルファの砦`=요새) 정렬이 안 잡히고 이 기본값으로 떨어진다 — `항` 이던 시절엔
# 그 자리만 `랄파항` 으로 남아 ED1↔ED2 표기가 갈렸다(마스터 QA 014, 2026-09-13).
SUFFIX = {"の町": "", "の村": "마을", "の港": "항구", "の鉱山": "광산", "の城": "성"}


def _enc(kr):
    """한글은 슬롯 SJIS 로, 나머지(숫자·부호)는 원래 SJIS 로 — `patch_sys_ui.enc_msg` 관용.

    ⚠ `H.encode_kr` 은 완성형 밖 글자에 죽는다. `슬롯1` 의 `1` 이 그 자리였다.
    """
    out = bytearray()
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return bytes(out)


def _jp_at(buf, off):
    end = buf.find(b"\x00", off)
    try:
        return buf[off:end].decode("cp932")
    except Exception:  # noqa: BLE001 — 바이너리 구간
        return None


def positional():
    """{ED2 오프셋: ED1 우리표기} — 두 UI 블록을 **자리로** 짝짓는다.

    ⚠ **문자열로 짝지으면 안 된다.** ED1 은 같은 원문을 문맥마다 다르게 옮겼다 —
    `強さ` 가 셋(파티 메뉴 `상태` · 전투 커맨드 `능력치` · 능력치 창 `힘`)이고
    `逃げる` 가 둘(`도망감`/`도망간다`)이다. 첫 값이 전부에 붙어 **능력치 창에
    「상태 6」이 떴다**(유저 QA 2026-08-14).

    ED2 블록은 ED1 과 같은 순서인데 `ＳＡＶＥ`·`ＬＯＡＤ` 처럼 **더 있는 항목**이 있어
    단순 zip 이 뒤부터 통째로 밀린다. 그래서 삽입을 견디는 시퀀스 정렬로 맞춘다.
    """
    from difflib import SequenceMatcher

    ed = extract(P.ED_LBA, P.ED_SIZE)
    a = [(o, _jp_at(ed, o), P.UI[o]) for o in sorted(P.UI) if 0xBE290 <= o <= 0xBE5C6]
    b = _walk(extract(ED2_LBA, ED2_SIZE), 0x99C84, 0x9A030)
    out, pad = {}, {}
    sm = SequenceMatcher(None, [x[1] for x in a], [x[1] for x in b], autojunk=False)
    for i, j, n in sm.get_matching_blocks():
        for d in range(n):
            o1, _jp, kr = a[i + d]
            o2 = b[j + d][0]
            out[o2] = kr
            if o1 in P.VALUE_PAD:  # 값 메뉴 — JP 렌더폭에 맞춰야 값 컬럼이 선다
                pad[o2] = P.VALUE_PAD[o1]
            if o1 in P.FIELD_MENU:  # SAVE/LOAD 칸에 맞춰 벌려 쓴다
                pad[o2] = -P.FIELD_WIDTH
    return out, pad


def _walk(buf, lo, hi):
    out, i = [], lo
    while i < hi:
        if buf[i] == 0:
            i += 1
            continue
        e = buf.find(b"\x00", i)
        s = _jp_at(buf, i)
        if s:
            out.append((i, s))
        i = e + 1
    return out


def ed1_canon():
    """{원본 JP: 우리 표기} — ED1 정본을 **원문으로** 뒤집어 만든다.

    ⚠ 오프셋으로 옮기면 안 된다. 두 EXE 는 배치가 다르고, ED1 표를 고쳤을 때 ED2 가
    안 따라오면 그때부터 한 디스크가 두 말을 한다.
    """
    ed = extract(P.ED_LBA, P.ED_SIZE)
    out = {}
    for off, kr in P.UI.items():
        jp = _jp_at(ed, off)
        if jp:
            out.setdefault(jp, kr)
    for jp, kr in list(P.PLACES) + list(P.SCN_PLACES):
        out.setdefault(jp, kr)
    return out


def plan():
    """[(오프셋, JP, KR, 슬롯B)] — 쓸 것 전부. 슬롯 초과는 여기서 걸러 보고한다."""
    import re

    buf = extract(ED2_LBA, ED2_SIZE)
    canon = ed1_canon()
    canon.update(PARTY)
    canon.update(MENU_EXTRA)
    canon.update(PLACES_ED2)
    canon.update(NAMES_ED2)
    import patch_items as PI

    canon.update({k: v for k, v in PI.NAMES.items() if k not in canon})
    canon.update({k: v for k, v in PI.MONSTERS.items() if k not in canon})
    # `Xの書` 는 주문 이름에서 파생한다 — 한 번 적으면 이름 표기를 고칠 때 같이 움직인다.
    for jp, kr in list(canon.items()):
        canon.setdefault(jp + "の書", kr + BOOK_SUFFIX)
    canon.update(PLACES_ED2_ROOMY)  # 이 표(ED2.EXE)만 여유 있는 자리 — HUD 슬롯엔 안 번진다

    by_off, pad = positional()
    rows, over = [], []
    for lo, hi in ((0x99C84, 0x9A030), (0x9A030, 0x9A280), (0x9A280, 0x9A550)):
        i = lo
        while i < hi:
            if buf[i] == 0:
                i += 1
                continue
            end = buf.find(b"\x00", i)
            jp = _jp_at(buf, i)
            if not jp:
                i = end + 1
                continue
            kr = by_off.get(i) or canon.get(jp)
            if kr is None and lo == 0x9A030:  # 워프 메뉴 — 접미를 떼고 다시 본다
                m = re.match(r"(.+?)(の町|の村|の港|の鉱山|の城)$", jp)
                if m and m.group(1) in canon:
                    kr = canon[m.group(1)] + SUFFIX[m.group(2)]
            if kr:
                # 쓸 수 있는 공간 = **다음 문자열 시작까지**(널 패딩 포함).
                # ⚠ 널 종단 다음부터 세야 한다. 처음에 `i + 1` 에서 시작했더니 문자열
                # 한복판이라 while 이 한 발도 안 나가고 **슬롯 = 문자열 길이**가 됐다 —
                # 16B 칸에 든 `竜の卵`(7B)이 「8B 라 안 들어간다」로 잘못 걸렸다.
                nxt = end
                while nxt < hi and buf[nxt] == 0:
                    nxt += 1
                slot = nxt - i
                enc = _enc(kr)
                t = pad.get(i)
                if t is not None and t < 0:  # 칸 채움(벌려 쓰기)
                    enc = P.justify(kr, -t, slot)
                elif t is not None:  # 값 메뉴 — JP 렌더폭까지 패딩
                    h = t - P.render_width(kr)
                    if h > 0:
                        enc += b"\x81\x40" * (h // 2) + b" " * (h % 2)
                (rows if len(enc) + 1 <= slot else over).append((i, jp, kr, slot, enc))
            i = end + 1
    return rows, over


def _reserved_in(buf, lo, hi, names):
    """구획 안에서 **이름이 아닌데 코드가 가리키는** 오프셋 — 덮으면 안 되는 자리.

    ⚠ 실측(2026-08-16): `0xD4938`·`0xD493B` 가 그랬다. 원본에서 그 바이트는 `0x00`,
    즉 **빈 문자열**이고 코드는 그걸 「아무것도 안 나오는 자리」로 쓴다
    (`lui $a0,0x800e; addiu $a0,$a0,0x4138; jal …`). 재packing 이 그 위를 이름으로
    덮으면 **없어야 할 글자가 화면에 뜬다** — 실패하지 않고 조용히 틀린다.
    """
    import patch_items as PI

    starts = {off for off, _jp in names}
    out = set()
    for _i, _l, _o, addr in PI.iter_lui_pairs(bytes(buf), {PI.MIPS_ADDIU, PI.MIPS_ORI}):
        fo = addr - 0x80010000 + 0x800
        if lo <= fo < hi and fo not in starts:
            out.add(fo)
    return sorted(out)


STRIDE_MIN = 8  # 이보다 짧은 연속은 우연으로 본다
STRIDE_SHARE = 0.6  # 구획의 이 비율 이상을 한 줄이 덮으면 배열이다


def assert_not_strided(names, label):
    """**균일 간격이 구획을 지배하면 재packing 금지** — 배열은 `base + i*간격` 으로도 읽힌다.

    참조가 100% 있어도 안전하다는 뜻이 아니다(`FIXED_SLOTS` 주석의 실측 사고). 포인터는
    갱신되지만 인덱싱이 어긋나고, **빌드는 성공한다.** 그래서 여기서 죽인다.

    ⚠ 절대 길이로 재면 못 쓴다 — `ED2 이름`(132개)에도 12B 간격이 16개 이어지는 자리가
    있는데 그건 **이름 길이가 우연히 같아서**고, 그 구획은 재packing 해도 멀쩡하다(실측).
    가르는 건 **비율**이다: 시나리오 아이템 표는 25개 중 20개(80%)가 한 줄이었다.
    """
    offs = [off for off, _jp in names]
    best = run = 1
    at = step = 0
    for i in range(1, len(offs) - 1):
        run = run + 1 if offs[i + 1] - offs[i] == offs[i] - offs[i - 1] else 1
        if run > best:
            best, at, step = run, offs[i - run + 1], offs[i] - offs[i - 1]
    if best >= STRIDE_MIN and best >= STRIDE_SHARE * len(offs):
        raise SystemExit(
            f"⚠ {label}: 0x{at:X} 부터 {best}개(전체 {len(offs)})가 {step}B 균일 간격이다"
            " — 고정 스트라이드 배열이라 재packing 하면 조용히 깨진다."
            " `FIXED_SLOTS` 로 옮겨 제자리에서만 채울 것."
        )


def repack_names(buf, canon):
    """이름 구획을 KR 로 다시 채우고 참조를 갱신한다. 반환: 옮긴 이름 수."""
    import patch_items as PI

    n = 0
    for lo, hi, label in REPACK:
        names = _walk(buf, lo, hi)
        assert_not_strided(names, label)
        reserved = _reserved_in(buf, lo, hi, names)
        moved, cur, packed = {}, lo, bytearray()
        for off, jp in names:
            kr = canon.get(jp)
            kb = (_enc(kr) if kr else jp.encode("shift_jis")) + b"\x00"
            kb += b"\x00" * (-len(kb) % 4)  # 정렬은 관례(코드는 바이트 접근)
            # 예약 바이트를 밟으면 그 자리를 널로 남기고 뒤로 건너뛴다(위 주석).
            while any(cur <= r < cur + len(kb) for r in reserved):
                r = next(r for r in reserved if cur <= r < cur + len(kb))
                packed += b"\x00" * (r + 1 - cur)
                cur = r + 1
            assert cur + len(kb) <= hi, f"{label}: 예산 초과 @{jp} ({cur - lo}/{hi - lo}B)"
            moved[PI.ram_of(off)] = PI.ram_of(cur)
            packed += kb
            cur += len(kb)
        buf[lo:hi] = packed.ljust(hi - lo, b"\x00")
        PI.redirect(buf, moved)
        print(f"  {label}: {len(names)}개 재packing ({len(packed)}/{hi - lo}B)")
        n += len(names)
    return n


def fill_fixed(buf, canon):
    """`FIXED_SLOTS` 를 **제자리에서만** 채운다 — 배치를 한 바이트도 안 바꾼다.

    슬롯은 「이 이름 시작 ~ 다음 이름 시작」이다(원본 간격을 그대로 존중한다).
    안 들어가는 이름은 **원문을 남기고 보고**한다 — 줄여 쓰거나 옮기지 않는다.
    옮기면 왜 안 되는지는 `FIXED_SLOTS` 주석.
    """
    n = over = 0
    for lo, hi, label in FIXED_SLOTS:
        names = _walk(buf, lo, hi)
        edges = [off for off, _jp in names] + [hi]
        for i, (off, jp) in enumerate(names):
            kr = canon.get(jp)
            if not kr:
                continue
            slot = edges[i + 1] - off
            kb = _enc(kr) + b"\x00"
            if len(kb) > slot:
                over += 1
                print(f"  ⚠ {label} 칸 부족 {off:#07x} {jp!r} → {kr!r} ({len(kb)}>{slot}B)")
                continue
            buf[off : off + slot] = kb.ljust(slot, b"\x00")
            n += 1
        print(f"  {label}: 제자리 {n}개" + (f" (칸 부족 {over})" if over else ""))
    return n


# HUD 이동 경로 라벨(승합마차·배 노선 안내) — **같은 지명이 반각 가타카나로 또 있다**
# (2026-09-14, 마스터 QA 051 — 「이슈타~이즈」 HUD 가 일본어로 보였다). 전각 SJIS
# 지명(`PLACES_ED2`)은 이미 다 옮겨져 있는데, 이 표는 **반각**(0xA1~0xDF)으로 같은
# 지명을 또 담고 있어 `_jp_at()`(전각 판정)가 원리상 못 봤다 — 034(ED2.EXE 사본
# 하나 더)와 같은 집안이다. 슬롯은 12B 로 고정, 이미 옆에 전각 번역이 있어 새로
# 옮길 것 없이 **그대로 복사**한다.
HALFWIDTH_ROUTE_LABELS = (
    # (오프셋, 반각 원본 바이트(꼬리 널 제외), KR)
    # 🔴 구분자는 물결표(~)에서 줄표(-)로 전환(마스터 확정 2026-09-15) — ASCII 0x7E 가
    # 이 폰트에서 물결이 아니라 **맨 윗줄 오버라인**으로 그려져(RE 실측: 잉크 행0)
    # "이슈타 ̄이즈"처럼 보였다. ASCII 0x2D('-')는 **행5 — 11행 중 정확히 세로 중앙**
    # (RE 실측)이라 하이픈답게 나온다. 반각 6px 전진폭 안에서 폭도 5px로 안 겹친다.
    (0xAAAC, bytes.fromhex("b2bcadc08160b2bddeb0"), "이슈타-이즈"),
    (0xAACC, bytes.fromhex("b2bcadc08160b1ccd9"), "이슈타-아훌"),
    (0xAAF8, bytes.fromhex("b2bddeb081608fe9"), "이즈-성"),
    (0xAB30, bytes.fromhex("b7adcdded781608fe9"), "큐베라-성"),
    (0xAB4C, bytes.fromhex("b7adcdded78160b3b2d9"), "큐베라-윌"),
    (0xAB78, bytes.fromhex("b3b2d98160cdded9dd"), "윌-베른"),
)
# 058ⓑ ④ → 062 로 정정(2026-09-14). 처음엔 음절 코드(0xC5~0xCA)+구분자('~')로 옮겼는데
# 그 음절 글리프가 7px 인데 반각 전진폭이 6px 라 화면에서 다음 글자를 먹었다(062 — 정확히
# 같은 원인이 HUD "늑대의입"에도 있었다). **고치는 법도 같다** — 큐베라프로스 여섯 글자를
# 66px 가상 캔버스에 그리고 6px씩 잘라 11칸(`patch_hangul_glyph_table.ROUTE_CODES`)에
# 나눠 굽는다. ⚠ **이 슬롯은 11코드+널=12B 로 꽉 차 구분자('~') 넣을 자리가 없다** —
# 66px 안에 여섯 글자(65px, 여유 1px)를 넣는 것도 빠듯해 물결표까지는 못 넣는다.
# "큐베라"·"프로스"로 갈라 보이던 걸 "큐베라프로스" 한 덩이로 붙여 보이는 트레이드오프다
# (마스터 062 비교 캡처로 검토·승인됨 — `.local/inbox/ps1-ed1+2/062-master-comparison.png`).
HALFWIDTH_ROUTE_LABEL_HALF_JP = bytes.fromhex("b7adcdded78160ccdfdbbd")  # ｷｭﾍﾞﾗ～ﾌﾟﾛｽ
ROUTE_LABEL_SLOT = 12

# 🔴 새로 찾은 사본(2026-09-14, 063 조사 중 발견 — 마스터가 「이슈타 이즈 아훌 큐베라 윌
# 프로스」 반각 필요를 짚어서 경로 라벨 표를 다시 훑다가 나왔다) — `0xD4B5C`
# 부근에 위 표와 **별개인 반각 지명 표**가 있고, 원본 그대로("ｱﾌﾙ～城"·"ｳｲﾙ～城") 번역이
# 안 돼 있었다. 슬롯은 8B 씩(위 HUD 지명 슬롯과 같은 크기지만 다른 좌표·다른 문맥) —
# 여기는 전각이 그대로 들어간다("아훌~성"=8B 딱 맞음, "윌~성"=6B, 여유 있음). 이 표의
# 실제 용도(성 함락류 이벤트 경고?)는 아직 안 밝혔다 — 화면에서 언제 뜨는지 확인 필요.
ROUTE_LABELS_2 = (
    (0xD4B5C, bytes.fromhex("b1ccd981608fe900"), "아훌-성"),
    (0xD4B64, bytes.fromhex("b3b2d981608fe900"), "윌-성"),
)


def fix_halfwidth_route_labels(buf):
    """`HALFWIDTH_ROUTE_LABELS` 자리를 반각 원문에서 한글로 — 고친 수 반환.

    0xAB10(큐베라프로스)은 전각으론 칸이 모자라 못 옮겼던 자리라 **062 조각 코드**
    (`patch_hangul_glyph_table.ROUTE_CODES`)로 옮긴다 — 정본은 그 파일.
    """
    import patch_hangul_glyph_table as G

    n = 0
    for off, jp_bytes, kr in HALFWIDTH_ROUTE_LABELS:
        assert buf[off : off + len(jp_bytes)] == jp_bytes, (
            f"HUD 경로 라벨 슬롯 불일치 @0x{off:X}: {bytes(buf[off : off + len(jp_bytes)]).hex()} != {jp_bytes.hex()}"
        )
        kb = _enc(kr) + b"\x00"
        assert len(kb) <= ROUTE_LABEL_SLOT, (
            f"HUD 경로 라벨 초과 {kr!r} {len(kb)}B > {ROUTE_LABEL_SLOT}B"
        )
        buf[off : off + ROUTE_LABEL_SLOT] = kb.ljust(ROUTE_LABEL_SLOT, b"\x00")
        n += 1
    off, jp_bytes = 0xAB10, HALFWIDTH_ROUTE_LABEL_HALF_JP
    assert buf[off : off + len(jp_bytes)] == jp_bytes, (
        f"HUD 경로 라벨(반각) 슬롯 불일치 @0x{off:X}: {bytes(buf[off : off + len(jp_bytes)]).hex()} != {jp_bytes.hex()}"
    )
    kb = bytes(G.ROUTE_CODES) + b"\x00"
    assert len(kb) <= ROUTE_LABEL_SLOT, f"HUD 경로 라벨(반각) 초과 {len(kb)}B > {ROUTE_LABEL_SLOT}B"
    buf[off : off + ROUTE_LABEL_SLOT] = kb.ljust(ROUTE_LABEL_SLOT, b"\x00")
    n += 1
    for off, jp_bytes, kr in ROUTE_LABELS_2:
        assert buf[off : off + len(jp_bytes)] == jp_bytes, (
            f"경로 라벨(사본2) 슬롯 불일치 @0x{off:X}: {bytes(buf[off : off + len(jp_bytes)]).hex()} != {jp_bytes.hex()}"
        )
        kb = _enc(kr) + b"\x00"
        assert len(kb) <= len(jp_bytes), (
            f"경로 라벨(사본2) 초과 {kr!r} {len(kb)}B > {len(jp_bytes)}B"
        )
        buf[off : off + len(jp_bytes)] = kb.ljust(len(jp_bytes), b"\x00")
        n += 1
    return n


def apply():
    rows, over = plan()
    for off, jp, kr, slot, enc in over:
        print(f"  ⚠ 슬롯 초과 — {off:#07x} {jp!r} → {kr!r} ({len(enc) + 1}B > {slot}B)")
    buf = bytearray(extract(ED2_LBA, ED2_SIZE, path=IMG))
    canon = ed1_canon()
    canon.update(PARTY)
    canon.update(MENU_EXTRA)
    canon.update(PLACES_ED2)
    canon.update(NAMES_ED2)
    import patch_items as PI

    canon.update({k: v for k, v in PI.NAMES.items() if k not in canon})
    canon.update({k: v for k, v in PI.MONSTERS.items() if k not in canon})
    for jp, kr in list(canon.items()):
        canon.setdefault(jp + "の書", kr + BOOK_SUFFIX)
    repack_names(buf, canon)
    relocate_fixed_items(buf, canon)
    fill_fixed(buf, canon)
    # ⚠ **메모리카드·세이브 문구는 ED2.EXE 에도 한 벌 더 있다**(2026-08-16 실측, 13곳).
    # ED1 쪽만 고쳐 뒀더니 ED2 화면엔 `メモリーカードを 캑べています` 처럼 **가나 + 깨진
    # 한글**로 나갔다 — 한자 슬롯을 한글로 덮어썼으니 원문 한자가 엉뚱한 한글이 된다.
    # `patch_sys_ui.MSGS` 는 **원문 문자열로 짝을 짓고 전 사본을 훑는** 표라 버퍼만 바꿔
    # 그대로 태우면 된다(오프셋을 다시 적으면 두 표가 갈린다 — 이 파일의 제1 관용).
    P.patch_msgs(buf)
    # ⚠ **HUD 상태이상 라벨도 ED2.EXE 에 사본이 따로 있다**(2026-09-13, 마스터 QA `034`
    # RE — ED1MON은 「묵」인데 ED2 전투 몬스터 창만 「黙」로 남아 있었다. `patch_sys_ui`
    # 가 `extract(ED_LBA=257)` 로 **ED.EXE 한 벌만** 열어 사본을 놓쳤다). 정본은
    # `patch_sys_ui.STATUS_LABELS` 하나 — 오프셋만 이쪽 사본 것(`0xD4B10`)을 쓴다.
    for i, (jp, kr) in enumerate(P.STATUS_LABELS):
        off = STATUS_BASE_ED2 + i * P.STATUS_STRIDE
        assert buf[off : off + 2] == jp.encode("cp932"), (
            f"ED2 상태 라벨 슬롯 불일치 @0x{off:X}: {buf[off : off + 2].hex()} != {jp!r}"
        )
        b = H.encode_kr(kr)
        assert len(b) < P.STATUS_STRIDE, f"ED2 상태 라벨 초과 {kr!r} {len(b)}B"
        buf[off : off + P.STATUS_STRIDE] = b.ljust(P.STATUS_STRIDE, b"\x00")
    print(f"ED2 상태이상 라벨 {len(P.STATUS_LABELS)}개 (0x{STATUS_BASE_ED2:X}~)")
    n_route = fix_halfwidth_route_labels(buf)
    print(f"HUD 경로 라벨(반각) {n_route}개")
    for off, _jp, _kr, slot, enc in rows:
        b = enc + b"\x00"
        buf[off : off + slot] = b + b"\x00" * (slot - len(b))
    with open(IMG, "r+b") as f:
        n = write_user_data(f, ED2_LBA, bytes(buf), label="ED2 시스템 UI (ED2.EXE)")
    print(
        f"ED2.EXE: 섹터 {n}개 수정 — 시스템 문자열 {len(rows)}건"
        + (f" (초과 {len(over)})" if over else "")
    )
    return len(over)


if __name__ == "__main__":
    if "--plan" in sys.argv:
        rows, over = plan()
        for off, jp, kr, slot, _e in rows:
            print(f"  {off:#07x} [{slot:>3}B] {jp:<12} → {kr}")
        print(f"\n쓸 것 {len(rows)}건 · 슬롯 초과 {len(over)}건")
        sys.exit(0)
    sys.exit(1 if apply() else 0)
