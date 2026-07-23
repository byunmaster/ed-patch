"""ED1 UI 텍스트(메뉴·상태창·전투커맨드·전투설정) 정발 이식 — ED.EXE 제자리 재삽입.

시스템 텍스트 중 '고정 UI 라벨'만 대상(아이템·마법·몬스터는 별도 — 시퀀스 정렬 필요).
이름과 달리 UI는 고정 세트라 정발 공식 표기를 오프셋별로 직접 매핑, KR이 짧아 제자리 삽입.

전제: reinsert_kr_pilot.py로 만든 KR Pilot 이미지(폰트 탑재됨) 위에 얹는다
      (patch_gfx_cards.py와 동일 패턴). 없으면 먼저 reinsert 실행.
출력: work/Eiyuu Densetsu (KR UI).bin/.cue

PS1 오프셋은 ED.EXE(LBA 257) 내 오프셋. UI 영역 0xBE290~0xBE5C6 (scan_sys 참조).
"""

import shutil

import hangul_map as H
from common import WORK_DIR, extract, write_cue, write_user_data

ED_LBA, ED_SIZE = 257, 1021952
SRC = f"{WORK_DIR}/Eiyuu Densetsu (KR Pilot).bin"
DST = f"{WORK_DIR}/Eiyuu Densetsu (KR UI).bin"
DST_CUE = f"{WORK_DIR}/Eiyuu Densetsu (KR UI).cue"

# ED.EXE 오프셋 → 정발 KR (만트라 ED1MAIN.EXE 공식 표기 기준). 슬롯에 맞춰 길이 조정.
# 인게임 QA로 확정 대상(대사 승격과 동일 — AI 1차, 사람 QA).
UI = {
    0xBE290: "마법사용",
    0xBE29A: "도구사용",
    0xBE2A4: "장비",
    0xBE2AE: "버린다",
    0xBE2B8: "능력치",
    0xBE2C2: "기타",
    0xBE2CC: "리더",
    0xBE2D8: "전투",
    0xBE2E2: "주문",
    0xBE2EC: "수비",
    0xBE2F6: "사용",
    0xBE300: "무기",
    0xBE30A: "자동",
    0xBE314: "능력치",
    0xBE31E: "도망",
    0xBE328: "마지막에 들른 마을",
    0xBE33C: "전투 직전으로",
    0xBE350: "모험을 계속한다",
    0xBE378: "시스템",
    0xBE382: "전투설정",
    0xBE38C: "힘",
    0xBE396: "지혜",
    0xBE3A0: "민첩성",
    0xBE3AA: "행운",
    0xBE3B4: "공격력",
    0xBE3BE: "방어력",
    0xBE3C8: "인공지능전투",
    0xBE3D7: "자동회복",
    0xBE3E6: "전투의 주문",
    0xBE3F5: "회복의 주문",
    0xBE404: "회복 아이템",
    0xBE413: "모두의 설정을",
    0xBE444: "사용",
    0xBE44E: "미사용",
    0xBE458: "사용",
    0xBE462: "미사용",
    0xBE46C: "사용",
    0xBE476: "미사용",
    0xBE480: "같게",
    0xBE488: "따로",
    0xBE490: "자동 이동",
    0xBE49F: "레벨 업",
    # 0xBE4BD ＢＧＭ = 영어라 원본 유지 (미터치)
    0xBE4CC: "이동",
    0xBE4DB: "메시지",
    0xBE4FC: "자동",
    0xBE504: "수동",  # ﾏﾆｭｱﾙ(반각 가나 5B — 반각이라 초기 스캔에서 누락됐던 값 문자열)
    0xBE514: "앞으로",
    0xBE52C: "보통",
    0xBE534: "빠르게",
    0xBE53C: "천천히",
    0xBE544: "보통",
    0xBE54C: "빠르게",
    0xBE554: "한번에",
    0xBE55C: "천천히",
    0xBE564: "예",
    0xBE56C: "아니오",
    0xBE574: "삽니다",
    0xBE57E: "팝니다",
    0xBE592: "공격력",
    0xBE59C: "방어력",
    0xBE5A6: "민첩성",
    0xBE5B0: "남은",
    0xBE5BC: "전투설정",
    0xBE5C6: "도망",
    # 장비/메뉴 미착용 (何もない → 없음). 표준 슬롯 자동 계산.
    # 주의: 0x51CE의 何もない은 "%c何もない%c" 전투 포맷 문자열 중간이라 건드리면 안 됨.
    0xC30C: "없음",
}

# 지명 테이블 (HUD 우하단) — 0xBE690부터 14B 고정슬롯 48개.
# 정발 ED1MAIN.EXE 0x273D6 블롭 표기 그대로. 예외 2건:
#  - 엘아스타: ED1 본체만 '엘아스터'(소수 표기) — JP 원음(エルアスタ)·ED2 정발·ED1 오프닝
#    모두 '엘아스타'라 통일(유저 확정 2026-07-13).
#  - 콜크스 마을: 정발은 '콜크스마을'(12B 컬럼 제약 추정) — 타 'X 마을'과 일관되게 띄움.
PLACES_BASE, PLACES_STRIDE = 0xBE690, 14
# HUD 상태이상 라벨 — ED.EXE 0xF91D8부터 **4바이트 stride**(2바이트 글자 + 널 2).
# 한글 1음절이 2바이트라 슬롯에 그대로 맞는다. 원본이 한 글자 약어라 우리도 한 글자로.
# (전투 커맨드 `守る`는 0xBE2EC의 별도 문자열로 이미 '수비'로 한글화돼 있다.)
STATUS_BASE, STATUS_STRIDE = 0xF91D8, 4
STATUS_LABELS = [
    ("毒", "독"),  # 중독
    ("黙", "묵"),  # 침묵
    ("呪", "주"),  # 저주
    ("眠", "잠"),  # 수면
    ("乱", "란"),  # 혼란
]
PLACES = [  # (PS1 일본어, 정발 한국어) — JP는 SCN 헤더 치환 키
    ("エルアスタ", "엘아스타"),
    ("ルディア", "루디아"),
    ("ルディア", "루디아"),  # (중복 슬롯)
    ("クルスの村", "크루즈 마을"),
    ("ベルガの鉱山", "베르가 광산"),
    ("ネリアの港", "네리아 항구"),
    ("ロンドの港", "론도 항구"),
    ("ラルファの砦", "랄파 요새"),
    ("マスクーン", "마스쿤"),
    ("リーゼル", "리젤"),
    ("海賊島", "해적섬"),
    ("スエルの村", "스엘 마을"),
    ("アムダの村", "암다 마을"),
    ("ヨルドの港", "요르도항구"),  # SCN3 헤더 슬롯 11B라 공백 제거(전 지점 통일) — 검수 대상
    ("ナッシュの町", "낫슈 마을"),
    ("セリス", "세리스"),
    ("バズヌーン", "바즈눈"),
    ("カウルの村", "카울 마을"),
    ("エメの町", "에메 마을"),
    ("ルドラの港", "루드라 항구"),
    ("リシェール", "리셸"),
    ("ナスールの町", "나슬 마을"),
    ("ファエトの村", "파에토 마을"),
    ("ファンガス", "판가스"),
    ("コルクスの町", "콜크스 마을"),
    ("フィーンの砦", "핀 요새"),
    ("ギルモアの里", "길모아 마을"),
    ("ラスタバン", "라스타반"),
    ("老夫婦の家", "노부부의 집"),
    ("オレアの家", "오레아의 집"),
    ("森の一軒家", "숲의 초가집"),
    ("ロエルの家", "로엘의 집"),
    ("ミラルダの家", "미랄다의 집"),
    ("バーバラの家", "바바라의 집"),
    ("岬の洞窟", "곶의 동굴"),
    ("岬の洞窟", "곶의 동굴"),  # (중복 슬롯)
    ("流血の洞窟", "유혈의 동굴"),
    ("グエンの塔", "구엔의 탑"),
    ("試練の洞窟", "시련의 동굴"),
    ("王家の墓", "왕가의 묘"),
    ("国境の洞窟", "국경의 동굴"),
    ("国境の洞窟", "국경의 동굴"),  # (중복 슬롯)
    ("カザミの塔", "바람의 탑"),  # (風見 — 정발 의역)
    ("風よけの穴", "방풍의 동굴"),
    ("狼の口", "늑대 입"),  # 정발 '늑대의 입'(10B)이 SCN5 헤더 슬롯(8B) 초과 — '의' 탈락(유저 확정)
    (
        "水晶の塔",
        "수정 탑",
    ),  # 정발 '수정의 탑'(10B)이 SCN5 헤더 슬롯(9B) 초과 — '의' 탈락(유저 확정)
    ("廃坑", "폐광"),
    ("ニルギド", "니르기드"),
]

# 주인공 기본 이름 (새 게임 시 세이브로 복사, HUD·상태창 표기) — 12B 슬롯.
# 0x80C リュナン(ED2 주인공)은 ED2 작업 시 결정(DOS 정발 ED2 주인공은 '아트라스') — 미터치.
HERO = {0x800: "세리오스"}  # セリオス


def avail_bytes(ed, off):
    """off 슬롯 가용 바이트 = 다음 문자열 시작까지(널종단+패딩 포함). 임의 오프셋 대응."""
    e = off
    while e < len(ed) and ed[e] != 0:
        e += 1
    n = e + 1
    while n < len(ed) and ed[n] == 0:
        n += 1
    return n - off


def enc(s):
    """한글=한자슬롯 인코딩. ASCII·기호(B.G.M. 등)는 SJIS 그대로 폴백."""
    try:
        return H.encode_kr(s)
    except ValueError:
        return s.encode("shift_jis")


# 필드 커맨드 메뉴(파티 메뉴) — 정발처럼 박스 폭(마법사용=8B)에 맞춰 글자 스프레드.
# 값 메뉴(시스템/전투설정 창 안 라벨)는 게임이 값을 고정 컬럼 정렬하므로 스프레드 안 함.
FIELD_MENU = {
    0xBE290, 0xBE29A, 0xBE2A4, 0xBE2AE, 0xBE2B8, 0xBE2C2,
    0xBE2CC,  # 리더(동료 합류 후 메뉴에 추가) → "리    더"
    0xBE378, 0xBE382,  # 기타 서브메뉴 항목(시스템→"시 스 템"·전투설정) — SAVE/LOAD 4전각 칸 맞춤
}
FIELD_WIDTH = 8  # 마법사용/도구사용 = 4전각 = 8B

# 값 메뉴 정렬 — RAM 라이브 실험으로 규명(2026-07-13, 픽셀 측정 검증):
#   값 X = 라벨 렌더폭 + [행별 고정 갭].  갭은 JP 라벨 폭 기준으로 하드코딩돼 있어
#   (JP에서 컬럼이 맞도록), KR 라벨을 "그룹 내 동일 폭"이 아니라 **JP 원본 라벨의
#   렌더폭**에 맞춰야 값이 정렬된다. 렌더폭 단위=반각(전각=2): 한글슬롯/0x8140=2,
#   0x20/ASCII=1. 패딩은 전각공백 0x8140(원본 폰트 빈 글리프) + 반각 0x20 조합.
#   전투설정 그룹은 '전투의 주문'(5.5전각)이 JP(5.0)보다 넓어 전 행을 +0.5 일괄 시프트
#   (행간 상대만 맞으면 컬럼 정렬 — 절대 위치는 반각 하나 우측일 뿐).
# BGM/EP/HP 등 영어 라벨은 원본 유지(JP가 이미 패딩 포함).
VALUE_PAD = {  # off: 목표 렌더폭(반각 단위)
    # 전투설정 (JP: オートバトル12·オート回復10·戦いの呪文10·回復の呪文10·回復アイテム12, +1 시프트)
    0xBE3C8: 13,  # 인공지능전투(12)
    0xBE3D7: 11,  # 자동회복(8)
    0xBE3E6: 11,  # 전투의 주문(11)
    0xBE3F5: 11,  # 회복의 주문(11)
    0xBE404: 13,  # 회복 아이템(11)
    # 시스템 (JP: オート移動10·レベルアップ12·移動4·メッセージ10)
    0xBE490: 10,  # 자동 이동(9)
    0xBE49F: 12,  # 레벨 업(7)
    0xBE4CC: 4,  # 이동(4)
    0xBE4DB: 10,  # 메시지(6)
    # 능력치 팝업 (JP: 強さ4·かしこさ8·すばやさ8·運の良さ8·攻撃力6·防御力6)
    0xBE38C: 4,  # 힘(2)
    0xBE396: 8,  # 지혜(4)
    0xBE3A0: 8,  # 민첩성(6)
    0xBE3AA: 8,  # 행운(4)
    0xBE3B4: 6,  # 공격력(6)
    0xBE3BE: 6,  # 방어력(6)
    # 상태창 (JP 전부 8: 攻撃力␣␣·防御力␣␣·すばやさ·残り␣␣␣␣)
    0xBE592: 8,  # 공격력(6)
    0xBE59C: 8,  # 방어력(6)
    0xBE5A6: 8,  # 민첩성(6)
    0xBE5B0: 8,  # 남은(4)
}


def render_width(s):
    """KR 라벨의 렌더폭(반각 단위): 한글=2, 공백/ASCII=1."""
    return sum(2 if "가" <= c <= "힣" else 1 for c in s)


# SAVE/LOAD·메모리카드 메시지 — ED.EXE 전체에서 JP 원문 전 사본을 스캔·치환(사본 다수).
# PS1 고유 기능이라 정발 원문 없음 — 시스템 문구 존댓말로 신규 번역. 용어: 로드/저장(실패
# 메시지 20B 슬롯에 '불러오기에…'가 안 들어가 '로드' 채택), 메모리카드(붙임).
# JP의 전각공백 들여쓰기는 KR에선 제거(유저 QA 07-19 — 어색). 긴 줄은 창 폭(~14슬롯)에
# 맞춰 개행 분할('확인하고 있습니다' 15슬롯이 단어 중간에서 꺾이던 것). 원문에 한자가 있는 문구는 우리
# 폰트가 한자 슬롯을 차지해 현재 한글 글자가 임의로 표시되는 상태라 번역이 필수.
MSGS = [
    ("スロット１", "슬롯１"),
    ("スロット２", "슬롯２"),
    ("    新しくセーブする", "   새로 저장하기"),
    (
        "メモリーカードを 調べています\nメモリーカードを\n　　　抜かないでください",
        "메모리카드를 확인하고\n있습니다\n메모리카드를 빼지 마세요",
    ),
    ("このカードには\n　　　データが ありません", "이 카드에는\n데이터가 없습니다"),
    (
        "メモリーカードが\n　フォーマット されていません\nフォーマット しますか？",
        "메모리카드가\n포맷되어 있지 않습니다\n포맷하시겠습니까?",
    ),
    ("メモリーカードが\n　　　差さっていません", "메모리카드가\n꽂혀있지 않습니다"),
    ("  メモリーカードが", "메모리카드가"),  # 0xC33C/0xC350 두 슬롯 분할형
    ("　　　差さっていません", "꽂혀있지 않습니다"),
    ("データが壊れています", "데이터가 깨졌습니다"),
    ("%d 番にセーブします\nよろしいですか？", "%d 번에 저장합니다\n계속하시겠습니까?"),
    ("%d 番をロードします\nよろしいですか？", "%d 번을 로드합니다\n계속하시겠습니까?"),
    (
        "ロード中 ... \n\nメモリーカードを\n　　　抜かないでください",
        "로드 중 ...\n\n메모리카드를 빼지 마세요",
    ),
    (
        "セーブ中 ... \n\nメモリーカードを\n　　　抜かないでください",
        "저장 중 ...\n\n메모리카드를 빼지 마세요",
    ),
    ("ロードに失敗しました", "로드에 실패했습니다"),
    ("セーブに失敗しました", "저장에 실패했습니다"),
    (
        "このメモリーカードは\n  フォーマットされています",
        "이 메모리카드는\n포맷되어 있습니다",
    ),
    (
        "メモリーカードの\n  フォーマットに失敗しました",
        "메모리카드의\n포맷에 실패했습니다",
    ),
    ("空きブロックが 足りないので\nセーブできません", "빈 블록이 부족해서\n저장할 수 없습니다"),
    (
        "メモリーカードを\n　フォーマットしています\n\nメモリーカードを\n　　　抜かないでください",
        "메모리카드를\n포맷하고 있습니다\n\n메모리카드를 빼지 마세요",
    ),
    # 세이브/복귀 확인창 (1차 이식에서 누락 — 유저 QA 발견)
    ("新しくセーブします\nよろしいですか？", "새로 저장합니다\n계속하시겠습니까?"),
    ("これでよろしいですか？", "이대로 하시겠습니까?"),
    ("%sの入口に戻ります。\nよろしいですか？", "%s 입구로 돌아갑니다.\n계속하시겠습니까?"),
    # 레벨업 화면(0x982C~) 문구는 patch_items 전투 코퍼스로 이관(2026-07-14) —
    # 여기의 부분 문자열 전역 치환이 긴 변형('強さが%c%d%cﾎﾟｲﾝﾄあがった。')의
    # 접두만 바꾸고 꼬리를 널로 밀어 문장을 자르는 버그가 있었다.
]


def enc_msg(s):
    """메시지 인코딩: 한글=슬롯, 개행/공백/ASCII/전각기호=SJIS 그대로."""
    out = b""
    for ch in s:
        out += H.encode_kr(ch) if "가" <= ch <= "힣" else ch.encode("shift_jis")
    return out


# 장비/도구 빈칸 라벨: JP 何もない(0xC30C, 슬롯 12B) → 정발 "아무 것도 없다"(14B+널)가
# 제자리에 안 들어감 → **메시지 풀 도너 꼬리로 리다이렉트**. 도너 = 포맷중 메시지
# (JP 86B → KR 60B, 꼬리 ~25B 0패딩). 정적 문자열 풀이라 런타임 안전. 참조는 코드
# lui/addiu 8곳뿐(u32 데이터 참조 0, 2026-07-14 전수 스캔).
NOTHING_KR = "아무 것도 없다"
NOTHING_DONOR = (
    "メモリーカードを\n　フォーマットしています\n\nメモリーカードを\n　　　抜かないでください"
)
NOTHING_REFS = [  # 何もない(RAM 0x8001BB0C)를 lui/addiu로 로드하는 lui 명령 RAM 주소
    0x800A5E74, 0x800A5F0C, 0x800A5FA4, 0x800A603C,
    0x800A8ACC, 0x800A8B64, 0x800A8BFC, 0x800A8C94,
]


def relocate_nothing(ed):
    """'없음' 문자열을 도너 꼬리의 '아무 것도 없다'로 교체(참조 리다이렉트)."""
    import struct

    donor_kr = dict(MSGS)[NOTHING_DONOR]
    kb = enc_msg(donor_kr)  # patch_msgs가 이미 치환한 KR 본문
    jb = NOTHING_DONOR.encode("shift_jis")
    i = bytes(ed).find(kb)
    assert i > 0, "없음 리다이렉트: 도너 메시지 못 찾음 (patch_msgs 후 호출해야 함)"
    dst = i + len(kb) + 1
    nb = enc_msg(NOTHING_KR)
    assert dst + len(nb) + 1 <= i + len(jb), "없음 리다이렉트: 도너 꼬리 부족"
    ed[dst : dst + len(nb)] = nb
    ed[dst + len(nb)] = 0
    ram = 0x80010000 + (dst - 0x800)
    hi, lo = ram >> 16, ram & 0xFFFF
    if lo & 0x8000:  # addiu 부호확장 보정
        hi += 1
    for pc in NOTHING_REFS:
        fo = pc - 0x80010000 + 0x800
        lui = struct.unpack_from("<I", ed, fo)[0]
        assert (lui >> 26) == 0x0F, f"0x{pc:X}: lui 아님 (0x{lui:08X})"
        rt = (lui >> 16) & 0x1F
        struct.pack_into("<I", ed, fo, (lui & 0xFFFF0000) | hi)
        for d in range(4, 28, 4):
            y = struct.unpack_from("<I", ed, fo + d)[0]
            if (y >> 26) == 0x09 and ((y >> 21) & 0x1F) == rt:
                struct.pack_into("<I", ed, fo + d, (y & 0xFFFF0000) | lo)
                break
        else:
            raise SystemExit(f"0x{pc:X}: 짝 addiu 못 찾음")
    print(f"'없음' → {NOTHING_KR!r} 리다이렉트 (새 문자열 RAM 0x{ram:X}, 참조 {len(NOTHING_REFS)}곳)")


def patch_msgs(ed):
    """ED.EXE 전역에서 MSGS의 JP 원문 전 사본을 슬롯 실측 내로 치환."""
    import re

    n = skipped = 0
    for jp, kr in MSGS:
        jb = jp.encode("shift_jis")
        kb = enc_msg(kr)
        # MSGS는 '긴 문자열 → 그 부분 문자열' 순서라, 부분형이 스캔될 땐 긴 사본이 이미
        # 치환돼 잔여(독립 슬롯)만 매칭된다.
        hits = [m.start() for m in re.finditer(re.escape(jb), bytes(ed))]
        for i in hits:
            e = i + len(jb)
            a = e
            while a < len(ed) and ed[a] == 0:
                a += 1
            avail = a - i
            if len(kb) + 1 > avail:
                skipped += 1
                print(f"  메시지 슬롯 부족 0x{i:X} {kr[:12]!r}… {len(kb) + 1}>{avail}")
                continue
            ed[i:a] = kb.ljust(avail, b"\x00")
            n += 1
    print(f"메모리카드/세이브 메시지 치환 {n}곳" + (f" (부족 {skipped})" if skipped else ""))


def justify(kr, target, avail):
    """KR을 target 바이트 폭에 맞춰 글자 사이 공백 분배(정발식). 슬롯(avail) 한도."""
    base = H.encode_kr(kr)
    goal = min(target, avail - 1)
    extra = goal - len(base)  # 채워야 할 공백 바이트 수 (공백=1B)
    if extra <= 0:
        return base
    chars = list(kr)
    gaps = len(chars) - 1
    if gaps <= 0:  # 한 글자뿐이면 뒤에 패딩
        return H.encode_kr(kr + " " * extra)
    per, rem = divmod(extra, gaps)
    out = chars[0]
    for i in range(1, len(chars)):
        out += " " * (per + (1 if i <= rem else 0)) + chars[i]
    return H.encode_kr(out)


def main():
    import os

    if not os.path.exists(SRC):
        raise SystemExit(f"KR Pilot 이미지 없음 — reinsert_kr_pilot.py 먼저 실행\n  기대: {SRC}")
    ed = bytearray(extract(ED_LBA, ED_SIZE, path=SRC))
    avails = {off: avail_bytes(ed, off) for off in UI}  # 패치 전 계산

    ok, over = 0, []
    for off, kr in UI.items():
        avail = avails[off]
        if off in FIELD_MENU:
            b = justify(kr, FIELD_WIDTH, avail)
        else:
            b = enc(kr)
            tgt = VALUE_PAD.get(off)
            if tgt is not None:  # 값 메뉴 라벨 → JP 원본 렌더폭으로 패딩
                pad_h = tgt - render_width(kr)
                assert pad_h >= 0, f"0x{off:X} {kr!r} 폭 {render_width(kr)} > JP {tgt} — 축약 필요"
                b += b"\x81\x40" * (pad_h // 2) + b" " * (pad_h % 2)
        if len(b) + 1 > avail:
            over.append((off, kr, len(b), avail))
            continue
        ed[off : off + len(b)] = b
        ed[off + len(b)] = 0
        ok += 1

    print(f"UI 재삽입 {ok}/{len(UI)}개")
    for off, kr, n, av in over:
        print(f"  슬롯 초과 0x{off:05X} {kr!r} {n}B>{av}B — 단축 필요")

    # 지명 테이블 — 14B 고정슬롯이라 avail 계산 불필요(원본 JP도 같은 슬롯).
    for i, (_jp, kr) in enumerate(PLACES):
        off = PLACES_BASE + i * PLACES_STRIDE
        b = H.encode_kr(kr)
        assert len(b) < PLACES_STRIDE, f"지명 초과 {kr!r} {len(b)}B"
        ed[off : off + PLACES_STRIDE] = b.ljust(PLACES_STRIDE, b"\x00")
    print(f"지명 재삽입 {len(PLACES)}개 (0x{PLACES_BASE:X}~)")

    # HUD 상태이상 라벨
    for i, (jp, kr) in enumerate(STATUS_LABELS):
        off = STATUS_BASE + i * STATUS_STRIDE
        assert ed[off : off + 2] == jp.encode("cp932"), (
            f"상태 라벨 슬롯 불일치 @0x{off:X}: {ed[off : off + 2].hex()} != {jp!r}"
        )
        b = H.encode_kr(kr)
        assert len(b) < STATUS_STRIDE, f"상태 라벨 초과 {kr!r} {len(b)}B"
        ed[off : off + STATUS_STRIDE] = b.ljust(STATUS_STRIDE, b"\x00")
    print(f"상태이상 라벨 {len(STATUS_LABELS)}개 (0x{STATUS_BASE:X}~)")

    # 주인공 기본 이름 (12B 슬롯)
    for off, kr in HERO.items():
        b = H.encode_kr(kr)
        assert len(b) < 12, f"이름 초과 {kr!r}"
        ed[off : off + 12] = b.ljust(12, b"\x00")
    print(f"주인공명 재삽입 {len(HERO)}개")

    patch_msgs(ed)
    relocate_nothing(ed)

    shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        print(f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed)}개 수정")
        patch_scn_headers(f)
    write_cue(DST_CUE, os.path.basename(DST))
    print(f"완료: {DST}")


# HUD 지명의 실제 소스는 ED.EXE가 아니라 씬 오버레이(ED1SCN*.BIN) 맵 세그먼트 헤더다:
# [RAM 포인터 테이블(0x8017xxxx)] + [지명 SJIS 널종단] + [%c 대사 블록…] 구조로,
# 세그먼트마다 지명이 박혀 있다(ED1 6파일 계 168곳). 헤더 판별: 앞 바이트가 포인터
# 꼬리(0x80)/널/파일시작이고 뒤가 널. 치환은 동일 길이 유지(KR+널 패딩)라 대사 내
# 오탐이 있어도 같은 자리 한글화일 뿐 구조 훼손 없음.
SCN_FILES = [
    ("ED1SCN1", 1183, 206260),
    ("ED1SCN2", 1284, 217940),
    ("ED1SCN3", 1391, 199084),
    ("ED1SCN4", 1489, 134184),
    ("ED1SCN5", 1555, 171392),
    ("ED1SCN6", 1639, 100270),
]


# 캐릭터명 사본 — SCN 오버레이가 들고 있는 **널종단 단독 이름 문자열**. 필드 대사의 %s
# (인라인 화자 헤더 %c%s%c 등)가 주입하는 소스가 **ED.EXE 0x800이 아니라 이 사본**이다
# (2026-07-23 실증: 0x800은 '세리오스'로 정상 패치됐는데도 대사창 이름만 일본어로 떴다).
# 지명과 동일하게 길이 보존 치환 — 슬롯 여유 확인됨(セリオス 8B/슬롯12B, ソニア 6B/슬롯8B).
CHAR_NAMES = [
    ("セリオス", "세리오스"),  # ED1SCN1 @0x8C8 (참조O)
    ("ソニア", "소니아"),  # ED1SCN2 @0x3090 (참조O)
]


def patch_scn_headers(f):
    import re

    jp2kr = {}
    for jp, kr in PLACES:
        jp2kr.setdefault(jp, kr)
    for jp, kr in CHAR_NAMES:  # 대사 %s가 주입하는 이름 사본
        jp2kr.setdefault(jp, kr)
    total = 0
    for name, lba, size in SCN_FILES:
        data = bytearray(extract(lba, size, path=DST))
        n = 0
        for jp, kr in jp2kr.items():
            jb = jp.encode("shift_jis")
            kb = H.encode_kr(kr)
            for m in list(re.finditer(re.escape(jb), bytes(data))):
                i, e = m.start(), m.end()
                if (i == 0 or data[i - 1] in (0x80, 0x00)) and e < len(data) and data[e] == 0:
                    a = e  # 가용 = 이름 + 뒤따르는 널 패딩(다음 데이터 전까지)
                    while a < len(data) and data[a] == 0:
                        a += 1
                    avail = a - i
                    assert len(kb) + 1 <= avail, f"{kr!r} {len(kb) + 1}B > 슬롯 {avail}B @0x{i:X}"
                    data[i:a] = kb.ljust(avail, b"\x00")
                    n += 1
        secs = write_user_data(f, lba, data)
        print(f"  {name}: 지명 헤더 {n}곳 (섹터 {secs}개)")
        total += n
    print(f"SCN 지명·캐릭터명 치환 {total}곳")


if __name__ == "__main__":
    main()
