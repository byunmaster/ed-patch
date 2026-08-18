"""아이템·마법·몬스터명 정발 이식 — ED.EXE 이름 영역 재packing + lui/addiu 참조 전량 갱신.

ED1 이름 소스는 ED.EXE 안의 세 영역(2026-07-14 규명, 참조 구조 전부 동일):
  ① 메인 블롭 0x828~0xE73: 장비 100 + 마법 13, 널종단 가변길이(4바이트 정렬).
     인벤토리·장비·상점이 쓰는 본 테이블. u32 포인터 테이블 없음 — 초기화 루틴이
     이름마다 lui/addiu 쌍으로 주소를 만들어 strcpy(jal 0x800CC6B0)로 런타임
     테이블(0x8016xxxx, 32B stride)에 복사한다. 인덱스 접근은 사본 쪽에서만.
  ② 8B stride 테이블 0xF8DC4(아이템 17)·0xF8E48(마법 14): 전투/이벤트용.
     참조 방식은 ①과 동일(이름당 lui/addiu 1쌍, 공유 lui 0개 — 전수 스캔 확인).
  ③ 몬스터명 블롭 0x9D58~0xA8CF: 208개(색상 변형 Ａ~Ｄ 포함, 고유 베이스 92).
     뒤 0xA8DC~에 아이템 블롭과 같은 데이터 섬 — 영역 밖이라 안전.

따라서 각 영역을 KR로 통짜 재packing하고, 옛 주소를 계산하는 addiu의 lo만 갱신하면
끝난다. 두 영역 모두 재packing 후에도 RAM 상위 16비트(0x8001/0x8011)와 lo의 부호가
변하지 않아 lui는 손댈 필요가 없다(공유 lui 오염 위험 원천 차단 — assert로 강제).

예산(검증): 블롭 1612B ≥ KR 4정렬 합, 8B 테이블 영역 244B ≥ KR 합.
번역: 정발 DOS(ED1MAIN.EXE 0x2695B~ stride 20 / 마법 0x2727F~ stride 11) 의미 매핑.
편차는 docs/jeongbal-deviations.md에 기록(치유의 로브·번개의 지팡이 등).
실행: build.py 체인에서 FINAL 이미지 제자리 갱신.
"""

import os
import re
import struct

import battle_text as BT
import hangul_map as H
from common import BUILD_DIR, MIPS_ADDIU, MIPS_ORI, extract, iter_lui_pairs, write_user_data
from derive_text import jp_map

ED_LBA, ED_SIZE = 257, 1021952
TARGET = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")

# 0xDC8~0xDD7은 이름이 아닌 데이터 섬(u16 500/1000/2500/5000/10000 — 가격 단계 추정)
# 이라 보존해야 한다 → 블롭을 둘로 나눠 재packing.
BLOB_EQ = (0x828, 0xDC8)  # 장비·도구 100
BLOB_MAGIC = (0xDD8, 0xE74)  # 마법 13
SEC = (0xF8DC4, 0xF8EB8)  # 아이템 17 + 마법 14 (구 8B stride)
MONSTER = (0x9D58, 0xA8D0)  # 몬스터 208
# 전투 트랙(2026-07-14 스코핑): 전부 lui/addiu 참조(u32 데이터 포인터 0) — 같은 기법.
CHAPTER = (0xB9C0, 0xBCD4)  # 챕터 클리어 메시지 13 (해방 공지 + 第N章…完)
ARENA = (0xBD18, 0xBDCC)  # 격투장 상품 대사 4 (정발 T_204~207 어투)
BTL_MSG = (0xBDCC, 0xBE48)  # 공격/일격/데미지 6 (뒤 0xBE48~ 포인터 테이블 — 보존)
BTL_MSG2 = (0xBE60, 0xBEC8)  # 인벤 초과·포기·입수 3
FRAG_TACHI = (0xF8ED4, 0xF8EEC)  # 파티명 접미 たち — 정발은 '들'(세리오스들은 상자를…)
# は逃げ出した。 도주 메시지 오프셋 지정 — 조사 훅 이전엔 솔로 도주(세리오스)에 맞춰 '는'을
# 정적 고정했으나, **동적 조사 훅 활성화(2026-07-27)로 불필요**해졌다. 병기 '은(는)'를 방출하면
# 훅이 앞말에 맞게 축약한다(솔로=세리오스는, 파티=류난들은). textmap 기본값이 이미 병기라
# 오버라이드를 비워 기본 변환에 맡긴다.
BATTLE_OFF_KR = {}
FRAG = (0xF8EEC, 0xF9064)  # 전투 조각(조사·접속사·%포맷) 58
EVT = (0xF9074, 0xF910C)  # 이벤트 전투 이름(사령관·병사·가르고 등)·방위 21
RYUNAN = 0x80C  # リュナン 기본 이름(12B 슬롯) — 세리오스(0x800)는 patch_sys_ui가 처리

# JP → 정발 KR. DOS는 이름 필드가 14B(마법 8B)라 긴 이름을 압착했는데(성스러운지팡이
# 등) PS1은 제약이 없어 띄어쓰기를 복원했다. 유저 확정 편차(2026-07-15):
#   いやしのローブ 치유의 로브(정발 '천민의 옷'은 卑しい 오독) · いかづちの杖 번개의
#   지팡이(정발 ED2 표기, '위엄의 지팡이'는 오독) · 大根 무(정발 부재 신규).
NAMES = {
    # ── 무기 (블롭) ──
    "幅広のつるぎ": "대형검",
    "小型のつるぎ": "소형검",
    "青銅のつるぎ": "청동검",
    "鉄のやり": "철창",
    "鉄のつるぎ": "철검",
    "はがねのやり": "강철창",
    "はがねのつるぎ": "강철검",
    "ムラサメの刀": "소나기의 검",
    "銀のつるぎ": "은검",
    "水晶の杖": "수정의 지팡이",
    "水晶のやり": "수정창",
    "水晶のつるぎ": "수정검",
    "プラチナのやり": "백금창",
    "プラチナの剣": "백금검",
    "セラミックの剣": "세라믹검",
    "聖なる杖": "성스러운 지팡이",
    "いかづちの杖": "번개의 지팡이",
    "黄金のつるぎ": "황금의 검",
    "死者のつるぎ": "사자의 검",
    "王家のつるぎ": "왕가의 검",
    "戦士のつるぎ": "전사의 검",
    "聖なるつるぎ": "성스러운 검",
    "首刈りガマ": "목자르는 낫",
    "ダイヤの杖": "다이아의 지팡이",
    "ダイヤのつるぎ": "다이아의 검",
    "古代の武器の本": "고대의 검의 책",
    "光のつるぎ": "빛의 검",
    # ── 갑옷 (블롭) ──
    "冒険者の服": "탐험자의 옷",
    "プラチナの鎧": "백금 갑옷",
    "絹のローブ": "비단 옷",
    "革のヨロイ": "가죽 갑옷",
    "青銅のヨロイ": "청동 갑옷",
    "くさりかたびら": "미늘 갑옷",
    "鉄のヨロイ": "철 갑옷",
    "はがねのヨロイ": "강철 갑옷",
    "銀のヨロイ": "은 갑옷",
    "水晶のヨロイ": "수정 갑옷",
    "いやしのローブ": "치유의 로브",
    "黄金のヨロイ": "황금 갑옷",
    "死者のヨロイ": "사자의 갑옷",
    "王家のヨロイ": "왕가의 갑옷",
    "聖なるヨロイ": "성스러운 갑옷",
    "ダイヤのヨロイ": "다이아 갑옷",
    "バトル・スーツ": "배틀 슈츠",
    "幸運の指輪": "행운의 반지",
    # ── 방패 (블롭) ──
    "革のたて": "가죽 방패",
    "青銅のたて": "청동 방패",
    "鉄のたて": "철 방패",
    "はがねのたて": "강철 방패",
    "銀のたて": "은 방패",
    "水晶のたて": "수정 방패",
    "プラチナのたて": "백금 방패",
    "黄金のたて": "황금 방패",
    "死者のたて": "사자의 방패",
    "王家のたて": "왕가의 방패",
    "聖なるたて": "성스러운 방패",
    "ダイヤのたて": "다이아 방패",
    "いにしえのたて": "고대의 방패",
    # ── 도구 (블롭) ──
    "レスの葉": "레스의 잎",
    "ビスの実": "비스의 열매",
    "毒消し草": "해독초",
    "たいまつ": "횃불",
    "ジャグリの地図": "쟈그리의 지도",
    "ヨシュアの目": "요슈아의 눈",
    "黄金のカード": "황금의 카드",
    "気付けぐすり": "약",
    "テュトの指輪": "튜트의 반지",
    "オプナの指輪": "오프나의 반지",  # ⚠ ED2 표기(ED2MAIN.EXE) — ED1 은 `오프너` 였다
    "ギルモアの涙": "길모아의 눈물",
    "ワプの羽": "워프의 깃털",
    "クイクの指輪": "퀵의 반지",
    "ワプの翼": "워프의 날개",
    "ドラゴンの布": "드래곤의 천",  # ⚠ ED1 정발은 `옷`, ED2 는 `천`(布) — ED2 우선(2026-08-12)
    "あらわしの鈴": "발견의 방울",
    "必ず当る宝くじ": "당첨 복권",
    "レスの根": "레스의 뿌리",
    "ヨシュアの鏡": "요슈아의 거울",
    "エリクサー": "에릭서",
    "黄金のカギ": "황금의 열쇠",
    "太陽の石": "태양의 돌",
    "ギルモアの星": "길모아의 별",
    "ギルモアの虹": "길모아의 무지개",
    "風のローブ": "바람의 로브",
    "不幸のタロット": "불행의 타로트",
    "幸運のタロット": "행운의 타로트",
    "あらわしの笛": "발견의 피리",
    "ビックリ箱": "깜짝 상자",
    "ルメンのランプ": "루멘의 램프",
    "レスの杖": "레스의 지팡이",
    "ピコハンマー": "피코 해머",
    "タイソンパンチ": "타이슨 펀치",
    "ハイパー2000": "하이퍼 2000",
    "ハイパー660": "하이퍼 660",
    "呼びよせの指輪": "호출의 반지",
    "不思議な壷": "이상한 물병",
    "グラディウス": "그라디우스",
    "バスタードの剣": "파멸의 검",
    "究極のローブ": "궁극의 로브",
    "究極の杖": "궁극의 지팡이",
    "目玉の付いた靴": "눈 달린 신발",
    # ── 마법 (블롭 13) ──
    "ヒュール": "휼",
    "ハイパー": "하이퍼",
    "ビックリ": "깜짝",
    "サクタス": "사크타스",
    "ヘベタル": "헤베달",
    "シレント": "시렌트",
    "パペピア": "파페피아",
    "サイレス": "사이레스",  # ⚠ ED1 정발 `사일레스`, ED2 `사이레스` — ED2 우선(2026-08-12)
    "インパス": "인파스",  # 원음 in-pa-su · ED2 정발 표기(유저 확정 2026-08-14). ED1 정발 `인퍼스` 는 원음과 어긋난다 — 한 디스크 한 표기라 ED1 화면도 같이 바뀐다
    "テュート": "튜트",
    "リパーク": "리파크",
    "イサイト": "이사이트",
    "ヨシュア": "요슈아",
    # ── 8B 테이블: 아이템 17 ──
    "ナイフ": "나이프",
    "銀の杖": "은의 지팡이",
    "炎の杖": "불의 지팡이",
    "氷の杖": "얼음의 지팡이",
    "布の服": "헝겊 옷",
    "粘土": "점토",
    "ラム酒": "럼주",
    "眠り草": "수면초",
    "銀の笛": "은의 피리",
    "爆薬": "폭약",
    "竜の笛": "용의 피리",
    "毒針": "독침",
    "大根": "무",
    "金塊": "금괴",
    "フラム": "프람",
    "イグナ": "이그나",
    "笛": "피리",
    # ── 8B 테이블: 마법 14 ──
    "オビス": "오비스",
    "サクト": "사쿠토",
    "カース": "커스",
    "ダナム": "다남",
    "ラック": "랙",
    "ホー": "호",
    "プアゾ": "푸아조",
    "セラ": "세라",
    "レス": "레스",
    "リーフ": "리프",
    "レジナ": "레지나",
    "ヴィス": "비스",
    "ルクス": "룩스",
    "ワプ": "워프",
}


# 몬스터 베이스명(색상 변형 접미 Ａ~Ｄ 제외 92종) — 정발 MONDLL/M###.DLL 이름 레코드
# (오프셋 0x280E, stride 56) 대응. 유저 확정(2026-07-14): 송리그모·데스코브라·데쓰 가디안·
# 브랏드 나이트는 정발 유지, ﾌﾗﾜｰﾘｻﾞｰﾄﾞ는 정발 내부 불일치(솔로=꽃도마뱀/무리=플라워리자드)
# → 플라워리자드 단일화. 접미는 반각 A~D(정발식)로 통일, ♀♂는 SJIS 기호 유지.
MONSTERS = {
    "スライム": "슬라임",
    "アクダム": "아크담",
    "ヘルニルド": "헤르닐드",
    "スライムバブ": "슬라임버브",
    "ｷｬﾘｵﾝ ｸﾛｰﾗｰ": "캬리온",
    "フクロウ": "부엉이",
    "ヤマネコ": "산고양이",
    "ハサミムシ": "집게벌레",
    "カブトガエル": "투구개구리",
    "カザス": "카자스",
    "サソリグモ": "송리그모",
    "スリーパー": "슬리퍼",
    "アジン": "아진",
    "カメルン": "카메룬",
    "エラビ": "에라비",
    "カース": "카스",
    "アクダムの手下": "아크담의 부하",
    "ヂガバチ": "지가바치",
    "ブロウコング": "브로우콩",
    "オオバサミ": "큰가위",
    "山賊鳥": "산적새",
    "猛毒ガメ": "맹독거북",
    "眼力魔": "안력마",
    "バラム": "바람",
    "スライムさん": "슬라임씨",
    "ｻﾝﾀﾞｰﾊｳﾝﾄﾞ": "썬더하운드",
    "ギュリゲス": "규리게스",
    "シルフィ": "실피",
    "ベラミス": "베라미스",
    "毒大ガエル": "큰독개구리",
    "デスクラブ": "데스코브라",
    "タルコス": "타루코스",
    "ﾄｰﾀｽ ﾅｲﾄ": "토타스나이트",
    "マドマン": "매드맨",
    "兵隊ムカデ": "군대지네",
    "ツノコブラ": "뿔코브라",
    "ヨロイグモ": "갑옷거미",
    "ワーラット": "전투쥐",
    "フォジー": "포지",
    "キラーベア": "키라베어",
    "ボイルガード": "보일가드",
    "カミナリグイ": "천둥말뚝",
    "イーグ": "이그",
    "オークホーン": "오크혼",
    "ﾌﾗﾜｰﾘｻﾞｰﾄﾞ": "플라워리자드",
    "インプ": "인프",
    "ｼﾞｬｲｱﾝﾄ ｴｲﾌﾟ": "큰고릴라",
    "ファイアーモス": "불나방",
    "サラマンダー": "사라만다",
    "ﾃﾞﾓﾝｺﾞｰｽﾄ": "데몬고스트",
    "ダークリッチ": "다크리치",
    "ｻﾝﾄﾞｲｰﾀｰ": "샌드이터",
    "サンドイーター": "샌드이터",
    "アジイ": "아지이",
    "オディノン": "오디논",
    "キバイノシシ": "송곳니 멧돼지",
    "アックスビーク": "액스비크",
    "ｱｯｸｽﾋﾞｰｸ": "액스비크",
    "バルガー": "바루가",
    "ﾊｲ=ｱｷﾞｰﾙ": "하이 아길",
    "ハイ＝アギール": "하이 아길",
    "ﾀﾞｰｸｿﾙｼﾞｬｰ": "다크 솔져",
    "ガリュバス": "가류바스",
    "バジール実体": "바질 실체",
    "バジール幻体": "바질 환체",
    "アギール": "아길",
    "ﾊﾞｰｽﾄﾊｳﾝﾄﾞ": "버스트 하운드",
    "ファントム": "팬텀",
    "スカルファング": "스컬팽",
    "岩石魔人": "암석마인",
    "ラドアス": "라도아스",
    "デスガーディアン": "데쓰 가디안",
    "モルゴス": "모르고스",
    "ブラカマン": "브라카맨",
    "スティングビートル♀": "스팅 비틀♀",
    "スティングビートル♂": "스팅 비틀♂",
    "バルバス": "발바스",
    "ブラッドナイト": "브랏드 나이트",
    "ザール": "잘",
    "ｻﾝﾀﾞｰｽﾈｰｶｰ": "썬더 스네이커",
    "ジャーバ": "쟈바",
    "グルム": "구룸",
    "暗黒の戦士": "암흑의 전사",
    "アージバル": "아지발",
    "殺人魚": "살인어",
    "ダルディア": "다루디아",
    "ガーバイン": "가바인",
    "ジャーデイン": "쟈딘",
    "ザグリス": "자그리스",
    "妖魔道士": "요마도사",
    "火炎ガニ": "화염게",
    "アグニージャ": "아그니쟈",
}
_FW = {"Ａ": "A", "Ｂ": "B", "Ｃ": "C", "Ｄ": "D"}

# 전투·챕터·격투장 메시지. %s에 들어갈 이름의 받침을 정적으로 알 수 없어 조사는
# 병기(은(는)·을(를))·정발 고정형(으로는 — DOS도 고정) 채택. 동적 조사 훅(음절→종성
# 비트테이블 + 결합 루틴 훅)은 status.md 개선 항목. 챕터 제목은 카드와 동일 정발명.
# ＢＣＤＥＦＧＨ 등 전각 라틴은 한자 블록 밖이라 원본 유지.
# {JP → KR} 82종(챕터 클리어 13·격투장 4·전투 알림 등) — textmap/items_battle.json 파생.
BATTLE = jp_map("items_battle")


def monster_kr(jp):
    """몬스터명 번역: 베이스 매핑 + 색상 접미(전각→반각 정규화)."""
    if jp in MONSTERS:
        return MONSTERS[jp]
    base, sfx = jp[:-1].rstrip(), _FW.get(jp[-1], jp[-1])
    assert sfx in "ABCD" and base in MONSTERS, f"몬스터 매핑 없음: {jp!r}"
    return MONSTERS[base] + sfx


def ram_of(fo):
    return fo - 0x800 + 0x80010000


def enc(kr):
    """한글=한자슬롯, 숫자/공백=SJIS 반각."""
    out = b""
    for ch in kr:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return out


def scan_names(ed, lo, hi):
    """영역의 (file_off, jp) 널종단 문자열 나열. 비-SJIS 조각은 오류."""
    out, i = [], lo
    while i < hi:
        if ed[i] == 0:
            i += 1
            continue
        j = i
        while ed[j] != 0:
            j += 1
        out.append((i, ed[i:j].decode("shift_jis")))
        i = j + 1
    return out


def repack(ed, lo, hi, label, align=4, tr=None, pools=None):
    """영역을 KR로 재packing(tr: JP→KR 변환, 기본 NAMES). 반환: {옛 RAM: 새 RAM}.

    pools를 주면 재packing 후 남는 꼬리 (free_lo, hi)를 추가한다(전투 코퍼스
    재배치용 여유 공간)."""
    tr = tr or NAMES.__getitem__
    names = scan_names(ed, lo, hi)
    # ⚠ **구획 안에 「빈 문자열」을 가리키는 참조가 숨어 있다**(2026-08-16 실측).
    # 이름이 아니라 그 바이트가 `0x00` 이라 코드가 「아무것도 안 나오는 자리」로 쓴다
    # (`lui $a1,0x8011; addiu $a1,$a1,-0x7844; jal …`). 재packing 이 그 위를 덮으면
    # **없어야 할 글자가 화면에 뜬다** — 실패하지 않고 조용히 틀린다. ED1 에 1곳
    # (`0x0F8FBC` 에 `왼쪽 ` 이 얹혀 있었다), ED2 에 2곳 있었다.
    # 널이 **한 바이트** 남아 있기만 하면 되므로 그 자리를 건너뛴다.
    starts = {off for off, _jp in names}
    reserved = sorted(
        {
            addr - 0x80010000 + 0x800
            for _i, _l, _o, addr in iter_lui_pairs(bytes(ed), {MIPS_ADDIU, MIPS_ORI})
            if lo <= addr - 0x80010000 + 0x800 < hi
            and addr - 0x80010000 + 0x800 not in starts
        }
    )
    moved, cur = {}, lo
    packed = bytearray()
    for off, jp in names:
        kb = enc(tr(jp)) + b"\x00"
        kb += b"\x00" * (-len(kb) % align)  # 정렬은 관례(코드는 바이트 접근)
        while any(cur <= r < cur + len(kb) for r in reserved):
            r = next(r for r in reserved if cur <= r < cur + len(kb))
            packed += b"\x00" * (r + 1 - cur)
            cur = r + 1
        assert cur + len(kb) <= hi, f"{label}: 예산 초과 @{jp}"
        moved[ram_of(off)] = ram_of(cur)
        packed += kb
        cur += len(kb)
    ed[lo:hi] = packed.ljust(hi - lo, b"\x00")
    if pools is not None and hi - cur >= 8:
        pools.append([cur, hi])
    print(f"{label}: {len(names)}개 재packing ({len(packed)}/{hi - lo}B)")
    return moved


def redirect(ed, moved):
    """옛 이름 주소를 만드는 lui/addiu 쌍의 addiu lo를 새 주소로 갱신.

    재packing이 영역 안에서만 움직이므로 상위 16비트(부호확장 포함)는 불변 —
    lui는 건드리지 않는다(다른 addiu와 lui를 공유해도 안전). 이름당 참조 1개
    이상을 assert(누락 참조 = 인게임에서 일본어 잔존)."""
    hits = {}
    for imm_off, _lui_off, op, addr in iter_lui_pairs(bytes(ed), {MIPS_ADDIU, MIPS_ORI}):
        if addr in moved:
            hits.setdefault(addr, []).append((imm_off, op))
    unref = {a for a in moved if a not in hits}
    assert not unref, f"참조 0건 이름 주소: {[hex(a) for a in unref]}"
    n = 0
    for old, sites in hits.items():
        lo = moved[old] & 0xFFFF
        for imm_off, op in sites:
            w = struct.unpack_from("<I", ed, imm_off)[0]
            # 부호확장 클래스(±)가 같아야 lui 불변 (ori는 무부호라 항상 안전)
            if op != MIPS_ORI:
                assert (w ^ lo) & 0x8000 == 0, f"0x{imm_off:X}: lo 부호 변화 — lui 갱신 필요"
            struct.pack_into("<I", ed, imm_off, (w & 0xFFFF0000) | lo)
            n += 1
    print(f"참조 갱신 {n}곳 ({len(hits)}개 주소)")


# ── 전투 코퍼스: 몬스터 행동·조우·상태이상·보스 대사 ~530종 ──
# 번역은 battle_text.py. **코드 참조가 정본**: 텍스트 휴리스틱은 포인터 테이블 직후
# (널 구분 없이 붙은) 문자열을 데이터로 오인해 놓치므로(→ 일본어 잔존·재배치 충돌),
# 대신 lui/addiu가 가리키는 주소 중 실제 텍스트인 것을 전투 문자열로 삼는다.
# 구조상 데이터 조각(포인터)이 문자열 사이에 섞여 통짜 재packing 불가 → 문자열별
# 제자리 치환, 슬롯 초과분만 풀 재배치 + 참조 완전 갱신(lui 포함).
CORPUS = (0x4954, 0x9938)
CORPUS_SKIP = {0x4E64, 0x4EAC, 0x4ED8, 0x4F00}  # 메모리카드 문구 — patch_sys_ui가 처리
# 코퍼스 영역 밖 산재 전투 문자열(참조는 있으나 영역 스캔이 못 잡음) — 명시 편입.
# 골드획득·레벨업, 전투 문맥 캐릭터명 사본(ロー/ゲイル/ソニア/海賊), 레벨업 확인.
CORPUS_EXTRA = (0x10F4, 0x493C, 0xF8DB4, 0xF8DBC, 0xF9140, 0xF9194, 0xF91A0, 0x9938)


def is_battle_string(orig, fo):
    """참조 대상이 실제 전투 텍스트인가 — 엄격 SJIS + 출력가능 문자.

    포인터 테이블 베이스(제어바이트 포함)와 값 테이블 첫 바이트('d'=100 등 순수
    ASCII 단일문자)를 걸러낸다."""
    if fo >= len(orig) or orig[fo] == 0:
        return False
    j = orig.find(b"\x00", fo)
    if j < 0 or j == fo or j - fo > 120:
        return False
    try:
        s = orig[fo:j].decode("shift_jis")
    except UnicodeDecodeError:
        return False
    if all(c < "\x80" for c in s) and "%" not in s:
        return False  # 값 테이블 조각(예: 'd')
    return all(c >= " " or c in "\n　" for c in s)


def corpus_strings(orig):
    """전투 문자열 (off, slot_end, jp) 나열 — 코드 참조 정본 + EXTRA."""
    refd = set()
    for _imm, _lui, _op, addr in iter_lui_pairs(orig, {MIPS_ADDIU, MIPS_ORI}):
        fo = addr - 0x80010000 + 0x800
        if CORPUS[0] <= fo < CORPUS[1] and fo not in CORPUS_SKIP:
            refd.add(fo)
    refd.update(CORPUS_EXTRA)
    out = []
    for fo in sorted(refd):
        if not is_battle_string(orig, fo):
            continue
        j = orig.index(0, fo)
        e = j
        while orig[e] == 0:
            e += 1
        out.append((fo, e, orig[fo:j].decode("shift_jis")))
    return out


# 진단 스위치: `BATTLE_JP=1` 이면 **자체 번역분을 JP 원문 그대로** 되돌린다.
# 인게임에서 일본어로 보이는 전투 메시지 = 아직 정발 대응이 없는 자리다(유저 제안 2026-08-09).
# 길이가 원본과 같아 제자리 치환이라 구조에 영향이 없다. 배포 빌드에는 쓰지 않는다.
_BATTLE_JP = os.environ.get("BATTLE_JP") == "1"
if _BATTLE_JP:
    print("⚠ BATTLE_JP=1 — **진단 빌드**다(자체 번역분이 일본어로 나온다). 배포·QA 금지.")


def _ellipsis(t):
    """말줄임표를 3점으로 — 대사와 같은 표기로 맞춘다(유저 확정 2026-08-13).

    ⚠ **대사의 규칙을 그대로 가져오지 않는다.** 대사는 2점을 1점으로 줄이지만
    (`fix_spacing`), 전투 보스 대사의 2점은 원문이 `･ ･ ･`(3점)이거나 말더듬(`き、きさまら`)
    이라 성격이 다르다 — 우연히 닮은 코드를 묶으면 한쪽이 틀어진다. 여기서는 **늘어난 점만**
    3점으로 줄인다(슬롯이 짧아지는 방향이라 재배치도 안 는다).
    """
    return re.sub(r"(?<!\.)\.{4,9}(?!\.)", "...", t) if t else t


def battle_kr(jp):
    """전투 문자열 번역 — B 우선, 표시명은 monster_kr 폴백."""
    if _BATTLE_JP:
        from derive_text import jkey, ours_keys

        if jkey(jp) in ours_keys("battle"):
            return jp
    if jp in BT.B:
        return _ellipsis(BT.B[jp])
    try:
        return monster_kr(jp)
    except AssertionError:
        return None


def apply_battle(ed, orig, pools):
    """코퍼스 치환: 제자리 우선, 초과분은 풀 재배치 + 참조 완전 갱신(lui 포함).

    재배치는 상위 16비트/부호가 바뀔 수 있어 lui까지 갱신한다 — lui를 다른
    대상과 공유하면 오염되므로 공유 여부를 전수 검사(assert)한다."""
    strs = corpus_strings(orig)
    missing = sorted({jp for _, _, jp in strs if battle_kr(jp) is None})
    assert not missing, f"번역 누락 {len(missing)}건: {missing[:8]}"

    # 참조 인덱스 (ORIG 기준 — 코퍼스 참조 코드는 앞 단계에서 불변)
    targets = {ram_of(off) for off, _, _ in strs}
    refs, lui_use = {}, {}
    for imm_off, lui_off, op, addr in iter_lui_pairs(bytes(ed), {MIPS_ADDIU, MIPS_ORI}):
        if addr in targets:
            refs.setdefault(addr, []).append((imm_off, lui_off, op))
        lui_use.setdefault(lui_off, set()).add(addr)

    # 1패스: 제자리/재배치 분류. 재배치분의 옛 슬롯은 즉시 비우고 풀에 편입
    # (인접 슬롯은 병합 — 보스 대사처럼 연속 재배치 구간이 큰 연속 풀이 된다).
    inplace, moves = 0, []
    for off, slot_end, jp in strs:
        kb = enc(BATTLE_OFF_KR.get(off) or battle_kr(jp)) + b"\x00"
        old = ram_of(off)
        assert refs.get(old), f"0x{off:X} {jp[:12]!r}: 참조 0건"
        if len(kb) <= slot_end - off:
            ed[off:slot_end] = kb.ljust(slot_end - off, b"\x00")
            inplace += 1
        else:
            ed[off:slot_end] = b"\x00" * (slot_end - off)
            pools.append([off, slot_end])
            moves.append((old, kb, jp))
    pools.sort()
    merged = []
    for lo, hi in pools:
        if merged and merged[-1][1] == lo:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    pools[:] = merged

    # 2패스: 큰 것부터 최적적합(best-fit) 할당 — 파편화 최소화
    for old, kb, jp in sorted(moves, key=lambda m: -len(m[1])):
        cand = [p for p in pools if p[1] - p[0] >= len(kb)]
        if not cand:
            raise SystemExit(f"풀 부족: {jp[:14]!r} ({len(kb)}B)")
        pool = min(cand, key=lambda p: p[1] - p[0])
        dst = pool[0]
        pool[0] += len(kb)
        ed[dst : dst + len(kb)] = kb
        new = ram_of(dst)
        hi = (new >> 16) + (1 if new & 0x8000 else 0)  # addiu 부호확장 보정
        for imm_off, lui_off, op in refs[old]:
            others = lui_use[lui_off] - {old}
            assert not others, f"0x{imm_off:X}: lui 공유({[hex(a) for a in others]}) — 재배치 불가"
            if op == MIPS_ORI:
                hi_w, lo_w = new >> 16, new & 0xFFFF
            else:
                hi_w, lo_w = hi, new & 0xFFFF
            w = struct.unpack_from("<I", ed, lui_off)[0]
            struct.pack_into("<I", ed, lui_off, (w & 0xFFFF0000) | hi_w)
            w = struct.unpack_from("<I", ed, imm_off)[0]
            struct.pack_into("<I", ed, imm_off, (w & 0xFFFF0000) | lo_w)
    left = sum(p[1] - p[0] for p in pools)
    print(f"전투 코퍼스 {len(strs)}개: 제자리 {inplace} + 재배치 {len(moves)} (풀 잔여 {left}B)")


# 전투 데미지 메시지의 조사 교정 — "세리오스을(를) N의 데미지" → "…에 N의 데미지"
# 조합: sprintf(buf, "%c%s%c을(를) ", 2, 이름, 1) + sprintf(t, "%d의 데미지!!\n", dmg) + strcat
# 그 포맷 문자열(%c%s%c을(를) )은 **참조 9곳으로 공유**돼(…목을 뻗어 ○○을(를) 쪼았다 등)
# 제자리 변경이 불가하다. → 새 문자열을 코퍼스 여유(0런)에 심고 **데미지 경로 1곳만** 리다이렉트.
# 데미지 경로는 라이브 디스어셈블로 확정(2026-07-23): lui@0x80069838 + addiu@0x8006983C.
# 조사는 "에"(정발: 슬라임B에 N의 데미지 — 유저 레퍼런스 07-28. 대상이 몬스터/아군 공통 로케이브).
DMG_LUI, DMG_ADDIU = 0x80069838, 0x8006983C
CORPUS_LO, CORPUS_HI = 0x4954, 0x9938  # 전투 코퍼스 영역(여유 0런 탐색 범위)


def fix_damage_particle(ed):
    import struct

    nb = b"\x25\x63\x25\x73\x25\x63" + enc("에") + b"\x20\x00"  # '%c%s%c에 \0'
    # 코퍼스 여유(0런)에서 자리 확보 — 4바이트 정렬
    need = len(nb)
    dst = None
    run = 0
    # ⚠ 런의 **앞**에서 정렬해 잡는다. 예전엔 끝(`i-need+1`)에서 잡고 4B 정렬을 올림했는데,
    # 그러면 dst+need 가 런을 최대 3B 넘어설 수 있었다(런이 넉넉할 땐 안 드러남). 2026-07-31
    # 시스템 메시지에 온점을 넣어 런이 2B 짧아지자 `목적지가 비어있지 않음`으로 터졌다.
    for i in range(CORPUS_LO, CORPUS_HI):
        run = run + 1 if ed[i] == 0 else 0
        if run < need:
            continue
        cand = (i - run + 1 + 3) & ~3  # 런 시작을 4B 정렬로 올림
        if cand + need <= i + 1:  # 정렬 뒤에도 런 **안**에 들어가야 한다
            dst = cand
            break
    assert dst is not None, f"데미지 조사: 코퍼스에 {need}B 여유 없음"
    assert all(ed[dst + k] == 0 for k in range(need)), "데미지 조사: 목적지가 비어있지 않음"
    ed[dst : dst + need] = nb

    ram = ram_of(dst)
    hi, lo = ram >> 16, ram & 0xFFFF
    if lo & 0x8000:  # addiu 부호확장 보정
        hi += 1
    for pc, opc in ((DMG_LUI, 0x0F), (DMG_ADDIU, 0x09)):
        fo = pc - 0x80010000 + 0x800
        w = struct.unpack_from("<I", ed, fo)[0]
        assert (w >> 26) == opc, f"0x{pc:X}: 예상 opcode {opc:#x} 아님 ({w:#010x})"
        struct.pack_into("<I", ed, fo, (w & 0xFFFF0000) | (hi if opc == 0x0F else lo))
    print(f"데미지 조사 '을(를)'→'에' (새 문자열 0x{ram:08X}, 참조 1곳만 리다이렉트)")


def main():
    if not os.path.exists(TARGET):
        raise SystemExit(f"대상 이미지 없음: {TARGET} — build.py 먼저")
    ed = bytearray(extract(ED_LBA, ED_SIZE, path=TARGET))
    orig = extract(ED_LBA, ED_SIZE)  # 원본(JP) — 코퍼스 스캔·검증 기준
    if ed[BLOB_EQ[0]] != orig[BLOB_EQ[0]]:
        raise SystemExit("이미 패치된 이미지 — build.py로 처음부터 다시 빌드하세요")

    pools = []
    moved = repack(ed, *BLOB_EQ, "이름 블롭(장비·도구100)", pools=pools)
    moved.update(repack(ed, *BLOB_MAGIC, "이름 블롭(마법13)", pools=pools))
    moved.update(repack(ed, *SEC, "전투 테이블(아이템17+마법14)", align=1, pools=pools))
    moved.update(repack(ed, *MONSTER, "몬스터명(208)", tr=monster_kr, pools=pools))
    b = BATTLE.__getitem__
    moved.update(repack(ed, *CHAPTER, "챕터 클리어(13)", align=1, tr=b, pools=pools))
    moved.update(repack(ed, *ARENA, "격투장(4)", align=1, tr=b, pools=pools))
    moved.update(repack(ed, *BTL_MSG, "전투 메시지(6)", align=1, tr=b, pools=pools))
    moved.update(repack(ed, *BTL_MSG2, "전투 메시지(입수3)", align=1, tr=b, pools=pools))
    # ⚠ 앞에 **본문색(3)** 을 붙인다 — `들` 은 이름 버퍼(`%s`)에 딸려 들어가 **이름색으로
    # 물든다**(`류난들`이 통째로 주황, 유저 QA 2026-08-15). 이름과 조각이 한 버퍼라 블록
    # 텍스트로는 가를 수 없어서, 조각 자신이 색을 되돌리게 한다. 이 조각을 쓰는 자리는
    # 파티명 해설뿐이고(참조 1곳 — lui/addiu 전수 확인) 그 블록들은 전부 본문이 초록이다.
    moved.update(repack(ed, *FRAG_TACHI, "たち(파티)", align=1, tr=lambda _: "\x03들", pools=pools))
    moved.update(repack(ed, *FRAG, "전투 조각(58)", align=1, tr=b, pools=pools))
    moved.update(repack(ed, *EVT, "이벤트 이름·방위(21)", align=1, tr=b, pools=pools))
    redirect(ed, moved)
    apply_battle(ed, orig, pools)
    fix_damage_particle(ed)

    # 동료 기본 이름 リュナン(12B 슬롯) — 이름판 그래픽과 동일 표기
    b = enc("류난")
    ed[RYUNAN : RYUNAN + 12] = b.ljust(12, b"\x00")
    print("동료명 리유난→류난 (0x80C)")

    with open(TARGET, "r+b") as f:
        print(
            f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed, label='아이템·몬스터명 (ED.EXE)')}개 수정"
        )
    print(f"완료: {os.path.basename(TARGET)}")


if __name__ == "__main__":
    main()
