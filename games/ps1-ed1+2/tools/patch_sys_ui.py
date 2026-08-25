"""ED1 UI 텍스트(메뉴·상태창·전투커맨드·전투설정) 정발 이식 — ED.EXE 제자리 재삽입.

시스템 텍스트 중 '고정 UI 라벨'만 대상(아이템·마법·몬스터는 별도 — 시퀀스 정렬 필요).
이름과 달리 UI는 고정 세트라 정발 공식 표기를 오프셋별로 직접 매핑, KR이 짧아 제자리 삽입.

전제: reinsert_kr_pilot.py로 만든 KR Pilot 이미지(폰트 탑재됨) 위에 얹는다
      (patch_gfx_cards.py와 동일 패턴). 없으면 먼저 reinsert 실행.
출력: work/Eiyuu Densetsu (KR UI).bin/.cue

PS1 오프셋은 ED.EXE(LBA 257) 내 오프셋. UI 영역 0xBE290~0xBE5C6 (scan_sys 참조).
"""

import os
import shutil

import hangul_map as H
from common import BUILD_DIR, OUT_DIR, extract, write_cue, write_user_data

ED_LBA, ED_SIZE = 257, 1021952
SRC = f"{BUILD_DIR}/Eiyuu Densetsu (KR Pilot).bin"
DST = f"{BUILD_DIR}/Eiyuu Densetsu (KR UI).bin"
DST_CUE = f"{BUILD_DIR}/Eiyuu Densetsu (KR UI).cue"

# ED.EXE 오프셋 → 정발 KR (만트라 ED1MAIN.EXE 공식 표기 기준). 슬롯에 맞춰 길이 조정.
# 인게임 QA로 확정 대상(대사 승격과 동일 — AI 1차, 사람 QA).
UI = {
    # ⚠ 파티 메뉴는 **PS1 원문 + ED2 정발** 표기다(유저 확정 2026-08-13).
    #   원문: 呪文 / 使う / 装備 / 捨てる / 強さ / その他 / リーダー
    #   ED1 정발(마법사용·도구사용·능력치·기타)은 의역이고, ED2 정발이 원문 1:1이다.
    #   ⚠ **ED2.EXE(LBA 756) 0x99C84 에 같은 문자열이 따로 한 벌 더 있다** — 공유가 아니라
    #   사본이라 ED2 트랙에서 같은 자리를 또 고쳐야 하고, 갈리면 한 디스크가 두 말을 한다.
    0xBE290: "주문",
    0xBE29A: "사용",
    0xBE2A4: "장비",
    0xBE2AE: "버린다",
    0xBE2B8: "상태",
    0xBE2C2: "그외",
    0xBE2CC: "리더",
    # ── 전투 커맨드 여덟 — **ED2 정발로 두 편 통일**(유저 확정 2026-08-17) ──────────
    # 원문은 `戦う·呪文·守る·使う·武器·オート·強さ·逃げる` 로 **ED1(ED.EXE 0xBE2D8)과
    # ED2(ED2.EXE 0x99CCC)가 여덟 다 바이트까지 같다**(실측). 정발만 갈렸다 —
    # ED1 정발 `전투/수비/능력치/도망감` · ED2 정발 `공격/방어/강함/도망`.
    # 유저 판정: ED2 쪽이 세련되고 원음에 가깝다 → **ED2 로 맞춘다.**
    # ⚠ ED2 는 `patch_ed2_sys.positional()` 이 이 표를 **자리로** 끌어가므로 여기만 고치면
    # 두 편이 같이 움직인다. ED2 쪽에 따로 적으면 지식이 두 곳에 갈린다.
    0xBE2D8: "공격",  # 戦う (ED1 정발 `전투`)
    0xBE2E2: "주문",
    0xBE2EC: "방어",  # 守る (ED1 정발 `수비`)
    0xBE2F6: "사용",
    0xBE300: "무기",
    0xBE30A: "자동",
    0xBE314: "강함",  # 強さ (ED1 정발 `능력치`) — 파티 메뉴 `상태`·능력치 창 `힘` 과 별개다
    0xBE31E: "도망",  # 逃げる (ED1 정발 `도망감`) — 슬롯 10B
    0xBE328: "마지막 들른 마을로",
    0xBE33C: "전투 직전으로",
    # 패배 메뉴 3선택지 — 슬롯 20B 고정(코드가 베이스+인덱스×20 으로 읽어 재배치 불가).
    # JP `冒険の続きをする`(모험의 계속을 한다)는 **세이브 불러오기**인데 직역으론 그게 안 보여
    # 정발도 `LOAD 를 합니다`로 풀어 썼다. 표기는 **'로드'** — 세이브/로드 메시지가 이미
    # 그렇게 쓴다(`%d 번을 로드합니다`). 메뉴 헤더의 전각 `ＬＯＡＤ` 는 원본 그대로 둔 것이라
    # 맞출 대상이 아니다(같은 화면에 `1 번을 로드합니다`가 뜬다 — 유저 확정 2026-08-01).
    # (`마지막에 들른 마을로` 는 21B 로 넘쳐 `에` 를 뺐다. 유저 확정 2026-08-01)
    0xBE350: "모험을 계속한다",
    0xBE378: "시스템",
    0xBE382: "전투설정",
    0xBE38C: "힘",
    0xBE396: "지혜",
    0xBE3A0: "민첩성",
    0xBE3AA: "행운",
    0xBE3B4: "공격력",
    0xBE3BE: "방어력",
    0xBE3C8: "자동 전투",  # オートバトル — 원문 1:1(유저 확정 2026-08-14). 아랫줄 `자동회복`(オート回復)과 대구가 맞는다. ED1 DOS 정발 `인공지능전투` 는 의역이고 ED2 정발이 `자동전투` 다
    0xBE3D7: "자동 회복",
    0xBE3E6: "전투의 주문",
    0xBE3F5: "회복의 주문",
    0xBE404: "회복 아이템",
    0xBE413: "전원의 설정을",
    0xBE444: "사용",
    0xBE44E: "미사용",
    0xBE458: "사용",
    0xBE462: "미사용",
    0xBE46C: "사용",
    0xBE476: "미사용",
    0xBE480: "같게",
    0xBE488: "따로",
    # ⚠ `자동` 은 명사라 뒤 명사와 **띄어 쓰는 게 원칙**이다(자동 이동·자동 전투·자동 회복).
    # 셋 중 둘만 붙여 써서 한 화면에서 어긋나 있었다(유저 지적 2026-08-14). 정발도 갈린다 —
    # ED2 정발이 `자동 전투`·`자동 회복` 은 띄우고 `자동이동` 은 붙였다. 맞춤법 쪽으로 통일한다.
    0xBE490: "자동 이동",
    0xBE49F: "레벨업",
    # 0xBE4BD ＢＧＭ = 영어라 원본 유지 (미터치)
    0xBE4CC: "이동",
    0xBE4DB: "메시지",
    0xBE4FC: "자동",
    0xBE504: "수동",  # ﾏﾆｭｱﾙ(반각 가나 5B — 반각이라 초기 스캔에서 누락됐던 값 문자열)
    0xBE514: "남다",  # あと — **HUD 라벨과 맞춘다**(유저 지적 2026-08-14). `patch_hud_names` 가 이미 그래픽 라벨을 `남다` 로 갈아 놨는데(정발 표기) 메뉴만 `앞으로` 라 한 빌드 안에서 어긋나 있었다
    0xBE52C: "보통",
    0xBE534: "빠르게",
    0xBE53C: "천천히",
    0xBE544: "보통",
    0xBE54C: "빠르게",
    0xBE554: "멈춤",  # 止まる — 직역이 「멈춘다」다(유저 확정 2026-08-14). `한번에` 는 원문과 거의 반대였다 — ED1 DOS 정발의 의역이고 ED2 정발이 `멈춤` 이다
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
    0xBE5C6: "도망간다",  # 정발 표기(유저 QA 2026-08-06) — 슬롯 10B 중 9B
    # 장비/메뉴 미착용 (何もない → 없음). 표준 슬롯 자동 계산.
    # 주의: 0x51CE의 何もない은 "%c何もない%c" 전투 포맷 문자열 중간이라 건드리면 안 됨.
    0xC30C: "없음",
}

# 지명 테이블 (HUD 우하단) — 0xBE690부터 14B 고정슬롯 48개.
# 정발 ED1MAIN.EXE 0x273D6 블롭 표기 그대로. 예외 2건:
#  - 엘아스타: ED1 본체만 '엘아스터'(소수 표기) — JP 원음(エルアスタ)·ED2 정발·ED1 오프닝
#    모두 '엘아스타'라 통일(유저 확정 2026-07-13).
#  - ⚠ **지명 안은 붙여 쓴다**(`크루즈마을`·`네리아항구`). 정발은 대개 띄웠지만(`콜크스마을`만
#    붙임) 실내 HUD 경로가 **지명을 2바이트 단위로 종단**해서, 반각 공백이 낀 홀수 길이 지명은
#    널을 놓치고 앞 문자열의 꼬리가 비친다(`크루즈 마을 입구` 실측 2026-08-04). 원본 지명 48개가
#    전부 짝수라 원작에선 안 생기던 일이다. 접미 앞 공백은 **슬롯 꼬리**에 따로 붙이므로
#    `크루즈마을 입구` 로 나온다 — 원작의 `마을/항구` 를 살리는 쪽을 택했다(유저 확정).
PLACES_BASE, PLACES_STRIDE = 0xBE690, 14
# ⚠ HUD 접미(`입구`)를 실내에서만 없애는 건 **이 계층에서 안 된다**(2026-08-04 실패 기록).
# 조립 루틴(RAM 0x800856BC)은 **플레이어 월드 좌표**로만 접미를 고른다 —
#   맵 등록좌표와 정확히 일치 → `入口` · ±8 이내 → `付近` · 그 밖 → 방위(北南東西).
# 마을 **안**과 월드맵에서 **그 타일에 올라선 것**이 좌표상 똑같아서 루틴이 둘을 못 가른다.
# 실제로 `入口` 분기(0x80085A48 `slti $v1,$v0,4` → imm 0)를 죽여 봤더니 실내는 해결됐지만
# 월드맵에서 마을에 올라섰을 때의 `입구`까지 사라졌다(유저 스샷). 되돌렸다.
# 가르려면 "실내인가"를 아는 **런타임 플래그**가 필요하다 — 호출처 6곳(전부 `j 0x800856BC`,
# a0=0x80166650)이 화면별로 갈리므로 그 자리에서 갈라야 한다. 후보 전역: 0x80108B2C(2와 비교)
# ·0x80108AD5(6과 비교). 정적으로는 확정 못 했고 **에뮬 RAM 대조가 필요**하다.
# HUD 상태이상 라벨 — ED.EXE 0xF91D8부터 **4바이트 stride**(2바이트 글자 + 널 2).
# 한글 1음절이 2바이트라 슬롯에 그대로 맞는다. 원본이 한 글자 약어라 우리도 한 글자로.
# (전투 커맨드 `守る`는 0xBE2EC의 별도 문자열로 이미 '수비'로 한글화돼 있다.)
STATUS_BASE, STATUS_STRIDE = 0xF91D8, 4
# ⚠ **정발 표기를 따른다**(2026-08-16 유저 실기 대조). 우리가 한자를 음차해 `란`·`도` 로
# 두었는데, 정발 DOS 원본에 라벨이 그대로 박혀 있다 — `\x01독 \x08잠 \x10혼 \x02묵 @반  수`
# (ED1MAIN.EXE 0x268E5 · ED2MAIN.EXE 0x14B0D3, 앞 바이트가 상태 비트다).
#   乱 → **혼**(혼란). `란` 은 한자 음차라 정발과 어긋났다.
#   跳 → **반**(반사). `跳ね返す`(튕겨 되돌리다)가 리파크다 — 정발 화면의 「주문을
#        되돌려보냈다!!」와 `반` 라벨이 그 자리이고, 색도 노랑(버프)으로 일치한다.
#   守 → 수(방어) 그대로. ⚠ `呪`(저주)는 **정발에 대응 라벨이 없다** — 음차 `주` 를 유지하되
#        정발 화면에서 그 상태를 본 적이 없어 표기 미확정이다(편차 대장 대상).
STATUS_LABELS = [
    ("毒", "독"),  # 중독
    ("黙", "묵"),  # 침묵
    ("呪", "주"),  # 저주 — 정발 대응 없음(미확정)
    ("眠", "잠"),  # 수면
    ("乱", "혼"),  # 혼란 — 정발 표기
]
PLACES = [  # (PS1 일본어, 정발 한국어) — JP는 SCN 헤더 치환 키
    ("エルアスタ", "엘아스타"),
    ("ルディア", "루디아"),
    ("ルディア", "루디아"),  # (중복 슬롯)
    ("クルスの村", "크루즈마을"),
    ("ベルガの鉱山", "베르가광산"),
    ("ネリアの港", "네리아항"),
    ("ロンドの港", "론도항"),
    ("ラルファの砦", "랄파요새"),
    ("マスクーン", "마스쿤"),
    ("リーゼル", "리젤"),
    ("海賊島", "해적섬"),
    ("スエルの村", "스엘마을"),
    ("アムダの村", "암다마을"),
    ("ヨルドの港", "요르도항"),
    ("ナッシュの町", "낫슈마을"),
    ("セリス", "세리스"),
    ("バズヌーン", "바즈눈"),
    ("カウルの村", "카울마을"),
    ("エメの町", "에메마을"),
    ("ルドラの港", "루드라항"),
    ("リシェール", "리셸"),
    ("ナスールの町", "나슬마을"),
    ("ファエトの村", "파에토마을"),
    ("ファンガス", "판가스"),
    ("コルクスの町", "콜크스마을"),
    ("フィーンの砦", "핀요새"),
    ("ギルモアの里", "길모아마을"),
    ("ラスタバン", "라스타반"),
    ("老夫婦の家", "노부부의집"),
    ("オレアの家", "오레아의집"),
    ("森の一軒家", "숲의초가집"),
    ("ロエルの家", "로엘의집"),
    ("ミラルダの家", "미랄다의집"),
    ("バーバラの家", "바바라의집"),
    ("岬の洞窟", "곶의동굴"),
    ("岬の洞窟", "곶의동굴"),  # (중복 슬롯)
    ("流血の洞窟", "유혈의동굴"),
    ("グエンの塔", "구엔의탑"),
    ("試練の洞窟", "시련의동굴"),
    ("王家の墓", "왕가의묘"),
    ("国境の洞窟", "국경의동굴"),
    ("国境の洞窟", "국경의동굴"),  # (중복 슬롯)
    ("カザミの塔", "바람의탑"),  # (風見 — 정발 의역)
    ("風よけの穴", "방풍의동굴"),
    ("狼の口", "늑대입"),  # 정발 '늑대의 입' — 붙여도 8B+널=9 > 슬롯 8B 라 '의' 탈락 유지
    # 붙여쓰기로 1B 가 남아 정발 '수정의 탑' 복원(붙여서 8B+널=9 ≤ 슬롯 9B, 2026-08-04)
    ("水晶の塔", "수정의탑"),
    ("廃坑", "폐광"),
    ("ニルギド", "니르기드"),
]

# SCN 플레이트에만 나오는 지명 — **ED.EXE 표에는 없다**(슬롯이 47번 `ニルギド` 에서 끝난다,
# 실측 2026-08-10). 위 `PLACES` 는 **위치가 곧 슬롯 번호**라 여기 덧붙이면 표 뒤 데이터를
# 덮는다. 그래서 `patch_scn_headers` 만 쓰는 표로 따로 둔다.
# ⚠ 정발에 대응 표기가 없다(ED1 대사 코퍼스·ED2 정발 둘 다 0건) — 우리 음역이다.
# 편차 대장(docs/jeongbal-deviations.md)에 기록한다.
# ⚠ **붙여쓴다** — 위 `PLACES` 가 전부 붙여쓰기(`늑대입`·`요르도항구`)인데 여기만 띄어 써서
# 같은 HUD 안에서 규칙이 갈려 있었다(유저 방침: HUD 는 붙여쓰기). 띄어쓰기 1바이트가
# 슬롯을 넘기는 자리이기도 하다 — `용의 알` 이 화면에서 뒤 자료까지 그려졌다(유저 QA).
SCN_PLACES = [
    ("ギーラの道", "기라의길"),
    ("バゼルの塔", "바젤의탑"),
    ("バーニス城", "바니스성"),
    # ⚠ ED.EXE 슬롯은 `リシェール`(리셸)뿐인데 **SCN 플레이트는 `リシェールの港`** 이다.
    # 짧은 쪽으로 잡으면 뒤에 `の港` 가 이어져 `data[e] == 0` 에서 걸러진다 — 일본어로
    # 남아 있었다(2026-08-10, SCN5 2곳). JP 도 슬롯/플레이트를 이렇게 갈라 쓴다.
    ("リシェールの港", "리셸항"),
    # 라누라의 성역 — ED.EXE 슬롯엔 없고 SCN 플레이트에만 나온다. 정발 대사가 `용의 알` 이다
    # (`용의 알에 들어가는 방법…`). 포인터 테이블 꼬리에 붙어 있어 ① 조건으로 잡힌다.
    ("竜の卵", "용의알"),
]


def _ed2_scn_places():
    """ED2 씬 플레이트 — 표기 정본은 `patch_ed2_sys.PLACES_ED2` 하나다.

    ⚠ **여기에 한글을 다시 적으면 안 된다.** 같은 지명을 두 표에 적으면 한쪽만 고쳤을 때
    한 디스크가 두 말을 한다(이 파일이 계속 경계하는 그 사고). 원문 문자열로 끌어온다.

    ED2 씬을 체인에 올리자 **플레이트 200곳이 일본어로 남았다**(2026-08-16). 지명 34개가
    전부 정본에 있었는데 **SCN 플레이트 표가 ED2 를 안 보고 있었을 뿐**이다.
    """
    import re

    from patch_ed2_sys import PLACES_ED2

    # ⚠ 그 표엔 지명 아닌 것도 섞여 있다(`スロット１` → `슬롯1`). 플레이트 인코더는
    # 완성형만 받으므로(`hangul_map.encode_kr`) **한글·공백뿐인 값만** 쓴다.
    return [(jp, kr) for jp, kr in PLACES_ED2.items() if not re.search(r"[^가-힣 ]", kr)]

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
    """한글=한자슬롯 인코딩. ASCII·기호(B.G.M. 등)·전각 라틴은 SJIS 그대로 폴백.

    ⚠ **글자 단위**로 갈라야 한다. 예전엔 문자열 통째로 시도하고 실패하면 통째로 SJIS 로
    폴백했는데, 그러면 한글과 라틴이 **섞인 문자열이 아예 인코딩 불가**였다(`ＬＯＡＤ해서
    계속한다` 실측 2026-08-01). 순수 한글·순수 ASCII 문자열의 결과는 전과 동일하다.
    """
    out = b""
    for ch in s:
        try:
            out += H.encode_kr(ch)
        except ValueError:
            out += ch.encode("shift_jis")
    return out


# 값 메뉴(시스템/전투설정 창 안 라벨)는 게임이 값을 고정 컬럼 정렬하므로 스프레드 안 함.
# ⚠ **파티 메뉴는 스프레드를 안 한다**(유저 확정 2026-08-13, B안). 원문(`呪文`·`使う`)도
# ED2 정발 화면도 왼쪽 정렬이다. 벌려 쓰던 건 ED1 DOS 정발이 4전각 라벨(`마법사용`)을
# 쓰느라 생긴 모양이라, 라벨을 원문대로 짧게 되돌리면 벌릴 이유가 없어진다.
# 🔴 **기타 서브메뉴도 안 벌린다**(유저 확정 2026-08-24). `시 스 템` 처럼 글자 사이를
#   벌려 SAVE/LOAD 4전각 칸에 맞추던 자리인데, **1뎁스 메뉴가 이미 안 벌리므로** 서브메뉴만
#   벌리면 한 게임 안에서 규칙이 갈린다. 새턴도 안 벌린다 — 두 이식판을 맞춘다.
FIELD_MENU = set()  # 비워 둔다 — 되살리려면 여기에 오프셋을 넣으면 된다
FIELD_WIDTH = 8  # (FIELD_MENU 가 비어 있으면 안 쓰인다)

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
    0xBE3C8: 13,  # 자동 전투(9)
    0xBE3D7: 11,  # 자동 회복(9)
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
        "메모리카드를 확인하고\n있습니다.\n메모리카드를 빼지 마세요.",
    ),
    ("このカードには\n　　　データが ありません", "이 카드에는\n데이터가 없습니다."),
    (
        "メモリーカードが\n　フォーマット されていません\nフォーマット しますか？",
        "메모리카드가\n포맷되어 있지 않습니다.\n포맷하시겠습니까?",
    ),
    ("メモリーカードが\n　　　差さっていません", "메모리카드가\n꽂혀있지 않습니다."),
    ("  メモリーカードが", "메모리카드가"),  # 0xC33C/0xC350 두 슬롯 분할형
    ("　　　差さっていません", "꽂혀있지 않습니다."),
    ("データが壊れています", "데이터가 깨졌습니다."),
    ("%d 番にセーブします\nよろしいですか？", "%d 번에 저장합니다.\n계속하시겠습니까?"),
    ("%d 番をロードします\nよろしいですか？", "%d 번을 로드합니다.\n계속하시겠습니까?"),
    (
        "ロード中 ... \n\nメモリーカードを\n　　　抜かないでください",
        "로드 중 ...\n\n메모리카드를 빼지 마세요.",
    ),
    (
        "セーブ中 ... \n\nメモリーカードを\n　　　抜かないでください",
        "저장 중 ...\n\n메모리카드를 빼지 마세요.",
    ),
    ("ロードに失敗しました", "로드에 실패했습니다."),
    ("セーブに失敗しました", "저장에 실패했습니다."),
    (
        "このメモリーカードは\n  フォーマットされています",
        "이 메모리카드는\n포맷되어 있습니다.",
    ),
    (
        "メモリーカードの\n  フォーマットに失敗しました",
        "메모리카드의\n포맷에 실패했습니다.",
    ),
    ("空きブロックが 足りないので\nセーブできません", "빈 블록이 부족해서\n저장할 수 없습니다."),
    (
        "メモリーカードを\n　フォーマットしています\n\nメモリーカードを\n　　　抜かないでください",
        "메모리카드를\n포맷하고 있습니다.\n\n메모리카드를 빼지 마세요.",
    ),
    # 세이브/복귀 확인창 (1차 이식에서 누락 — 유저 QA 발견)
    ("新しくセーブします\nよろしいですか？", "새로 저장합니다.\n계속하시겠습니까?"),
    ("これでよろしいですか？", "이대로 하시겠습니까?"),
    # ⚠ `%s` 는 지명 테이블에서 오는데 그 슬롯이 **전각 공백으로 끝난다**(HUD 접미 붙임용) —
    # 여기서 또 띄우면 두 칸이 된다. 공백은 지명 쪽이 들고 있으니 서식에는 안 넣는다.
    ("%sの入口に戻ります。\nよろしいですか？", "%s입구로 돌아갑니다.\n계속하시겠습니까?"),
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
# ⚠ 정발은 `아무 것도`(띄어씀)인데 **`아무것`은 사전에 한 단어(대명사)로 올라 있다** —
# `textmap/battle.json` 은 이미 `fix` 로 교정하고 있었는데 이 라벨만 정발 원문 그대로여서
# ED1 안에서 표기가 갈려 있었다(2026-08-16 유저 QA). ED2 쪽(`何もない`)도 같은 문안이다.
NOTHING_KR = "없음"
NOTHING_DONOR = (
    "メモリーカードを\n　フォーマットしています\n\nメモリーカードを\n　　　抜かないでください"
)
NOTHING_REFS = [  # 何もない(RAM 0x8001BB0C)를 lui/addiu로 로드하는 lui 명령 RAM 주소
    0x800A5E74,
    0x800A5F0C,
    0x800A5FA4,
    0x800A603C,
    0x800A8ACC,
    0x800A8B64,
    0x800A8BFC,
    0x800A8C94,
]


def relocate_nothing(ed):
    """'없음' 문자열을 도너 꼬리의 '아무것도 없다'로 교체(참조 리다이렉트)."""
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
    print(
        f"'없음' → {NOTHING_KR!r} 리다이렉트 (새 문자열 RAM 0x{ram:X}, 참조 {len(NOTHING_REFS)}곳)"
    )


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


# ── ED.EXE 이벤트 대사 (월드맵 내레이션 등) ─────────────────────────────────
# 씬 오버레이가 아니라 ED.EXE에 박힌 이벤트 문장들 — 탈출 직후 월드맵 내레이션 클러스터
# (유저 QA 2026-07-24 발견). 번역은 textmap/event.json에서 파생(신규=ours, 정발 인용=src).
# JP 원문은 리포에 없음 — 빌드 시 ED.EXE에서 읽어 sha1 키로 조회한다. 슬롯은 다음
# 문자열 전 0런까지, KR이 넘치면 assert(확장 필요 시 relocate_nothing식 도너로 전환).
EVENT_OFFS = [0xC058, 0xC090, 0xC0C0, 0xC118, 0xC170]


def patch_event_msgs(ed):
    import os
    import re
    import sys

    from derive_text import jp_map

    _repo = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    sys.path.insert(0, os.path.join(_repo, "shared"))
    from text.krwrap import wrap_pages

    ev = jp_map("event")
    n = 0
    for off in EVENT_OFFS:
        j = ed.index(0, off)
        jp = ed[off:j].decode("shift_jis")
        if jp not in ev:
            continue  # 번역 없으면 JP 유지
        e = j
        while ed[e] == 0:
            e += 1
        val = ev[jp].replace("엘아스터", "엘아스타")  # 표기 통일(대사 트랙과 동일 판정)
        head = b""
        if val.startswith("\x1e"):  # 정발 화자 헤더(\x1e이름\x04) → %c이름%c
            nm, _, val = val[1:].partition("\x04")
            head = b"%c" + enc_msg(nm) + b"%c\n"
        if "\x01" in val:  # 정발 src 파생 — DOS {n}은 표시 artifact, 우리 폭(14슬롯) 재조판
            body = re.sub(r"\s+", " ", val.replace("\x01", " ")).strip()
            body = re.sub(r" +(?=[!?])", "", body)  # 종결부호 앞 공백(대사 규약)
            pages = wrap_pages(
                body,
                14.0,
                5,
                break_char="\n",
                cell_width=lambda ch: 0.5 if ch == " " or ch in ".,!?" else 1.0,
                strip_before=".,!?",
                strip_after="",
            )
            assert len(pages) == 1, f"이벤트 메시지 페이지 초과 @0x{off:X}"
            val = "\n".join(pages[0])
        if jp.endswith("%c") and not val.endswith("%c"):
            val += "%c"  # 종단 제어(%c=인자 소비)는 구조 — src 파생분에 자동 부여
        b = head + enc_msg(val)
        assert len(b) < e - off, f"이벤트 메시지 초과 @0x{off:X}: {len(b)}B ≥ {e - off}B"
        ed[off:e] = b.ljust(e - off, b"\x00")
        n += 1
    print(f"이벤트 대사 재삽입 {n}/{len(EVENT_OFFS)}건")


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
    # ⚠ 꼬리에 **반각 공백**을 붙인다 — HUD 는 `[지명][접미]` 를 한 버퍼에 이어 붙이는데
    # (RAM 0x800856C0: 지명을 널까지 바이트 복사 → 접미를 이어 붙임) 사이에 공백이 없어
    # `베르가 광산남서` 로 붙어 나왔다. 접미 쪽은 못 고친다 — 스택 사본의 **복사 바이트 수가
    # ASM 에 박혀** 있어(入口/付近 4B·방위 2B) 글자를 늘리려면 코드를 고쳐야 한다.
    # 지명 쪽은 슬롯이 널종단이라 데이터만으로 된다. 접미가 없는 자리에선 꼬리 공백이라 무해.
    # ⚠ 처음엔 전각(0x8140)으로 넣었다 — "반각은 홀수 바이트가 되어 경계가 깨진다"는 기록
    # 때문인데, **지명 내부 구분자가 이미 반각이라 그 전제가 틀렸다**(`크루즈 마을` = 11B 홀수인데
    # 정상 렌더 + 뒤 접미도 정상, 유저 스샷 2026-08-04). 전각은 지명 내부 간격과 안 맞아
    # 벌어져 보여 반각으로 통일했다(유저 확정).
    # 진단: HUD_DIAG=noplaces 면 ED.EXE 지명표를 **일본어 그대로** 둔다. 실내 HUD 가 이 표에서
    # 오는지(→ 일본어로 뜬다) SCN 헤더에서 오는지(→ 한글 유지)를 한 판에 가르는 스위치다.
    diag_noplaces = os.environ.get("HUD_DIAG") == "noplaces"
    for i, (_jp, kr) in enumerate(PLACES):
        if diag_noplaces:
            continue
        off = PLACES_BASE + i * PLACES_STRIDE
        b = H.encode_kr(kr) + b"\x20"
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
    patch_event_msgs(ed)

    shutil.copyfile(SRC, DST)
    with open(DST, "r+b") as f:
        print(f"ED.EXE: 섹터 {write_user_data(f, ED_LBA, ed, label='시스템 UI (ED.EXE)')}개 수정")
        patch_scn_headers(f)
    write_cue(DST_CUE, os.path.basename(DST))
    print(f"완료: {DST}")


# HUD 지명의 실제 소스는 ED.EXE가 아니라 씬 오버레이(ED1SCN*.BIN) 맵 세그먼트 헤더다:
# [RAM 포인터 테이블(0x8017xxxx)] + [지명 SJIS 널종단] + [%c 대사 블록…] 구조로,
# 세그먼트마다 지명이 박혀 있다(ED1 6파일 계 168곳). 헤더 판별: 앞 바이트가 포인터
# 꼬리(0x80)/널/파일시작이고 뒤가 널. 치환은 동일 길이 유지(KR+널 패딩)라 대사 내
# 오탐이 있어도 같은 자리 한글화일 뿐 구조 훼손 없음.
# ⚠ **정본은 `reinsert_kr_pilot.SCN_FILES` 하나다**(2026-08-16 통합). 여기 같은 표를 또
# 두었더니 **ED2SCN1 이 한쪽에만 올라가** 재삽입은 되는데 지명 플레이트·이름 사본 치환은
# 안 도는 상태가 됐다 — 두 표가 어긋나도 빌드는 성공한다(조용히 틀리는 부류).
def _scn_files():
    from reinsert_kr_pilot import SCN_FILES as _S

    return _S


class _LazySCN:
    """`SCN_FILES` 를 정본에서 늦게 끌어온다(순환 import 회피 — reinsert 가 이 모듈을 쓴다)."""

    def __iter__(self):
        return iter(_scn_files())

    def __len__(self):
        return len(_scn_files())

    def __getitem__(self, i):
        return _scn_files()[i]


SCN_FILES = _LazySCN()


# 캐릭터명 사본 — SCN 오버레이가 들고 있는 **널종단 단독 이름 문자열**. 필드 대사의 %s
# (인라인 화자 헤더 %c%s%c 등)가 주입하는 소스가 **ED.EXE 0x800이 아니라 이 사본**이다
# (2026-07-23 실증: 0x800은 '세리오스'로 정상 패치됐는데도 대사창 이름만 일본어로 떴다).
# 지명과 동일하게 길이 보존 치환 — 슬롯 여유 확인됨(セリオス 8B/슬롯12B, ソニア 6B/슬롯8B).
#
# ⚠ 이 사본은 **블록으로 안 잡히는 자리에도 있다**(2026-08-09 emucap 추적). 사본이 포인터
# 테이블 **바로 뒤**에 붙으면 블록 분할이 테이블 blob 에 통째로 삼켜서 대사 재삽입이 아예
# 못 본다 — 구엔의 탑 사일레스 이벤트의 `ゲイル`(ED1SCN2 @0x10D84)이 그랬다. 인게임에서
# 「%s의 주문서에…」의 %s 만 일본어로 떴고, ED.EXE 0xF8DBC·메모리카드·상태창은 전부
# 한글이라 정적 증거만으로는 못 잡았다. 쓰기 브레이크포인트로 %s 소스가 이 사본임을
# 확인하고 나서야 자리가 나왔다(전 씬 재스캔: SCN2 @0x3088·@0xFAA0 `ロー` 도 같은 꼴).
# → 표를 **5인 전원**으로 채운다. 표에 없으면 그 이름은 조용히 일본어로 남는다.
# 오탐 0 확인: ED1 6오버레이 전수에서 헤더 판별을 통과하는 자리는 아래 주석의 6곳뿐.
#
# 셋째 칸 `plate` = **정렬 금지 목록에도 넣을지**(`is_name_plate`). 치환 대상과 정렬 금지
# 대상은 같지 않다 — `ゲイル`·`ロー` 는 **본문이 그대로 이름인 대사**가 실재한다
# (`{c}セリオス{c}{n}ゲイル !?{c}` = 리더별 변형). 이걸 금지 목록에 넣으면 멀쩡한 대사가
# 통째로 빠진다(SCN5 jp485·jp1063 — 5인 전원을 겸용으로 넣었더니 실제로 1블록이 사라졌다,
# 2026-08-09 관측 대장이 잡았다). 단독 이름 블록이 실재하는 이름만 True.
CHAR_NAMES = [
    ("セリオス", "세리오스", True),  # ED1SCN1 @0x8C8 (참조O)
    ("リュナン", "류난", False),  # 단독 사본 없음(표 완결용 — 생기면 자동으로 잡힌다)
    ("ロー", "로우", False),  # ED1SCN2 @0x3088 · @0xFAA0 (테이블 blob 꼬리)
    ("ゲイル", "게일", False),  # ED1SCN2 @0x10D84 (테이블 blob 꼬리 — 사일레스 %s)
    ("ソニア", "소니아", True),  # ED1SCN2 @0x3090 (참조O) · @0x613C (테이블 blob 꼬리)
]


def is_name_plate(body):
    """이 본문이 `patch_scn_headers` 관할의 **이름·지명 단독 블록**인가.

    ⚠ 이 표(PLACES·CHAR_NAMES)와 LaBSE 정렬은 같은 플레이트 블록을 서로 모른 채 노린다.
    reinsert가 먼저 돌아 한국어를 써버리면 JP 바이트가 사라져 여기서 못 고친다 —
    **먼저 쓰는 쪽이 이기는 경합**이다. 실측 8건이 전부 정렬 쪽 오배정이었다(2026-07-31):
    セリス→'세리오스'(다른 인물) · ラルファの砦→'랄파의 도구점'(요새가 상점으로) ·
    海賊島→'해적'(섬 탈락) · ルディア→'루디아 마을\\x07'. 이름만 있는 블록은 문맥이 없어
    LaBSE가 표면 유사도로 끌려간다 — 애초에 정렬이 손댈 자리가 아니다.

    그래서 이 표를 **정렬 금지 목록으로 겸용**해 관할을 가른다. 하드코딩을 새로 늘리지 않고
    단일 출처를 유지하는 게 요점 — 표에 이름을 추가하면 치환과 배제가 함께 따라온다.
    ⚠ 단 CHAR_NAMES 는 `plate=True` 인 것만 본다(그 표의 주석 참조 — 겸용이 항상 옳진 않다).

    앞 ≤2글자 여유는 포인터 배열 꼬리가 SJIS로 잘못 풀려 붙는 몫이다(`責勒セリス` 실측).
    """
    body = (body or "").strip()
    if not body:
        return False
    allp = PLACES + SCN_PLACES + _ed2_scn_places()
    for nm in {j for j, _ in allp} | {j for j, _, plate in CHAR_NAMES if plate}:
        if body == nm or (body.endswith(nm) and len(body) - len(nm) <= 2):
            return True
    return False


def _scn_layout():
    """reinsert가 쓴 재배치 매니페스트(OUT_DIR/scn_layout.json) 반영 — 확장 씬은 LBA·크기가 바뀐다.

    ⚠ 경로를 하드코딩하지 말 것. 예전엔 `../out/`을 직접 조립했는데, 산출물 디렉터리를
    `work/derived/`로 옮겼을 때 그대로 남아 **조용히 SCN_FILES(재배치 전 LBA)로 폴백**했다.
    엉뚱한 섹터에 치환하니 지명·화자 이름이 통째로 일본어로 남았다(2026-07-31 실측).
    그래서 없으면 경고를 찍는다 — 침묵 폴백이 버그를 숨겼다.
    """
    import json

    p = os.path.join(OUT_DIR, "scn_layout.json")
    if not os.path.exists(p):
        print(
            f"  ⚠ 재배치 매니페스트 없음({p}) — 원본 LBA로 진행. reinsert 뒤라면 치환이 빗나간다."
        )
        return SCN_FILES
    m = json.load(open(p, encoding="utf-8"))
    return [
        (name, m[name]["lba"], m[name]["size"]) if name in m else (name, lba, size)
        for name, lba, size in SCN_FILES
    ]


def patch_scn_headers(f):
    import re

    jp2kr = {}
    for jp, kr in PLACES + SCN_PLACES + _ed2_scn_places():
        jp2kr.setdefault(jp, kr)
    for jp, kr, _ in CHAR_NAMES:  # 대사 %s가 주입하는 이름 사본
        jp2kr.setdefault(jp, kr)
    total = 0
    for name, lba, size in _scn_layout():
        data = bytearray(extract(lba, size, path=DST))
        n = 0
        for jp, kr in jp2kr.items():
            jb = jp.encode("shift_jis")
            kb = H.encode_kr(kr)
            for m in list(re.finditer(re.escape(jb), bytes(data))):
                i, e = m.start(), m.end()
                # 헤더 판별 ①앞=포인터 꼬리(0x80)/널 ②또는 뒤 널 패딩 ≥4B(단독 널종단 이름).
                # ②는 블록 종단(%c 00) 뒤 잡바이트가 낀 내부 맵 사본용(여관 ルディア 실측
                # 2026-07-26, 전 씬 +11곳: 리젤·왕가의 묘·파에트·수정탑 등 전부 내부 맵).
                # 대사 내 지명은 항상 뒤에 텍스트/%c가 이어져 ②에 안 걸린다.
                # ③앞=0xFF 종단 마커(`\xFF\xFF` + 지명, 뒤 널 패딩이 2B뿐이라 ②에도 안 걸린다 —
                # 크루즈 마을 HUD 1곳이 이것 때문에 일본어로 남아 있었다, 유저 QA 2026-08-03).
                # 대사 속 지명 언급은 뒤에 본문이 이어져 `data[e] == 0` 에서 배제된다
                # (`ネリアの港には…` 실측 — 그건 대사 번역 경로 관할).
                # ④뒤=`00 00 %c` — 이름이 널종단이고 **바로 다음이 블록 시작(`%c`)** 인 꼴.
                # 앞바이트가 포인터 꼬리(0x80)가 아니고 널 패딩도 2B뿐이라 ①②③ 어디에도
                # 안 걸려 **일본어로 남아 있었다**(숲의초가집·오레아의집·로엘의집 — 실내 HUD 가
                # 그 바이트를 한글 폰트로 그려 `예の겟리꽃` 같은 깨짐이 났다. 유저 QA 2026-08-07).
                # 대사 속 지명은 뒤에 본문이 이어져 `data[e] == 0` 에서 이미 배제된다.
                # ⑤앞=`00 <코드>` — **같은 이름이 줄줄이 늘어선 표**의 중간 레코드다
                # (`グエンの塔\x00\x04 グエンの塔\x00\x2c グエンの塔\x00\x02 …`). 앞 레코드의
                # 널종단 뒤에 1바이트 코드가 끼어 ①(앞=널/0x80)에 안 걸리고, 뒤 패딩도
                # 1B뿐이라 ②④에도 안 걸린다 — 네 슬롯 중 둘만 바뀌고 둘이 일본어로
                # 남아 있었다(SCN2 구엔의 탑, **포인터가 직접 가리키는 살아있는 자료**다.
                # 빌드 이미지를 세어 찾았다 — 스크래치패드 `plateleft.py`, 2026-08-10).
                # ⑥길이가 **정확히 같으면** 앞 조건을 안 본다. 뒤가 널이라 대사가 아닌 게
                # 이미 보장되고(대사면 본문이 이어진다), 같은 길이면 **바이트가 한 칸도 안
                # 밀려** 구조를 못 깨뜨린다. ED2 를 올리자 `グロストス城` 4곳이 ①~⑤ 어디에도
                # 안 걸려 일본어로 남았다(2026-08-16) — 앞이 `40 10`·`35 37` 처럼 자원 표
                # 한복판이라 「경계」로 볼 바이트가 없다. 앞 조건은 **길이가 바뀔 때만**
                # 필요한 안전장치였다.
                same_len = len(kb) == len(jb)
                if (
                    i == 0
                    or data[i - 1] in (0x80, 0x00, 0xFF)
                    or (i >= 2 and data[i - 2] == 0)
                    or data[e : e + 4] == b"\x00" * 4
                    or data[e : e + 4] == b"\x00\x00\x25\x63"
                    or same_len
                ) and (e < len(data) and data[e] == 0):
                    a = e  # 가용 = 이름 + 뒤따르는 널 패딩(다음 데이터 전까지)
                    while a < len(data) and data[a] == 0:
                        a += 1
                    avail = a - i
                    assert len(kb) + 1 <= avail, f"{kr!r} {len(kb) + 1}B > 슬롯 {avail}B @0x{i:X}"
                    data[i:a] = kb.ljust(avail, b"\x00")
                    n += 1
        secs = write_user_data(f, lba, data, label="시스템 UI (씬)")
        print(f"  {name}: 지명 헤더 {n}곳 (섹터 {secs}개)")
        total += n
    print(f"SCN 지명·캐릭터명 치환 {total}곳")


if __name__ == "__main__":
    main()
