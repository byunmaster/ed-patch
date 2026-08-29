"""
PS1 일문 ↔ DOS 정발판 한국어 대사 정렬 테이블 초안 생성기.

입력: out/scn_jp/EDxSCNn.json (extract_scn.py) + out/dos_kr/<게임>/*.json (extract_dos_kr.py)

씬 대응 (실측, 2026-07-09): DLL 파일명 둘째 자리 숫자 N ↔ EDxSCN(N+1).
 (T1 폴스↔SCN2 フォルス, T4 대도 게일↔SCN5 大盗賊ゲイル, C3 아도스 국왕↔SCN4 アートス国王)
 접두사 = 역할: T=마을 대화, C=이벤트, D=던전, H=집, A/E/F=보조.
 ⚠ **이 1:1 규칙은 ED1 에서만 성립한다.** ED2 는 정발 그룹 9개 ↔ PS1 씬 13개라 다대다다
 (그룹0 = 씬1+2, 그룹2 = 씬4+5+13 …). 정본은 `ed2_scene_tables.json`, 근거는
 docs/ed2-scene-map.md — `scene_groups()` 참조.

매칭 전략 (초안 — PS1은 리메이크라 블록이 DOS의 2배 이상, 1:1 불가):
 1. 화자 매핑: 수동 사전(보통명사) + 가타카나→한글 음차 + 자모 편집거리 fuzzy
 2. DLL 단위 Smith-Waterman 국소 정렬 — 화자 일치·본문 길이·숫자·문장부호 점수
 3. 블록 수 많은 DLL부터 탐욕 배정 (JP 블록 중복 청구 방지)
 4. 실패분은 flags로 표시 (unmatched / low_confidence) — 수작업 검토 대상

출력: out/align/<게임>_SCN<n>.json + 화자 매핑표 out/align/<게임>_speakers.json
"""

import json
import math
import os
import re
import sys

from common import MARKUP, OUT_DIR, ROOT

SCN_JP_DIR = os.path.join(OUT_DIR, "scn_jp")
DOS_KR_DIR = os.path.join(OUT_DIR, "dos_kr")
ALIGN_DIR = os.path.join(OUT_DIR, "align")

# 게임별: (SCN 파일 접두사, SCN 수)
GAMES = {"ED1": ("ED1SCN", 6), "ED2": ("ED2SCN", 13)}

# ── 화자 매핑 ────────────────────────────────────────────────────────────────
# 보통명사·의역 이름 수동 사전 (음차로 못 잡는 것들 — 실데이터 기준 수집)
SPEAKER_DICT = {
    # 장음 `ー` 는 음차에서 사라져 1음절이 된다 — `ロー`→`로` 라 정발 `로우`와의 유사도가
    # 임계(0.6) 밑으로 떨어져 미해결로 빠졌다. 그러면 화자창에 음차 `로`가 그대로 나간다
    # (인게임 지적 2026-08-02). 장음 이름은 사전에 박는다.
    "ロー": "로우",
    # `フラート` 는 음차로 정발명이 안 나온다(→'플라트'류)라 사전에 박는다. ⚠ **ED1 정발은
    # `브라도`, ED2 정발은 `프라토`** 로 갈리는데 ED2 우선이 방침이라 `프라토` 다(유저 확정
    # 2026-08-12). ED2 는 네 파일에서 일관되고(`당시 국왕 프라토님은 유괴당하고` — ED1 3장의
    # 그 사건이다) 원음에도 가깝다. `all_kr_speakers()` 는 ED1+ED2 를 함께 보므로 통과한다.
    "フラート": "프라토",
    # 아래 둘은 **정발 화자 목록에 그대로 있다**(코퍼스 전수 확인 2026-08-04) — 음차가 아니라
    # 정발 표기다. 자동 매칭이 놓친 건 장음 `ー`·요음 `ャ` 가 음차에서 뭉개져 임계(0.6)를
    # 못 넘겨서다. ⚠ `アグニージャ`→'아그니자'로 고치지 말 것: 정발이 '아그니쟈'다.
    "アグニージャ": "아그니쟈",
    "ギュリゲス": "규리게스",
    # ⚠ **주인공 넷이 사전에 없었다**(2026-08-17). 음차가 `ゲイル`→`게이루` 라 정발 `게일` 과
    # 안 붙어, 후보 좁히기에서 **게일 대사 247건이 「정발에 대응 없음」으로 떨어졌다.**
    # 나머지 셋은 음차가 우연히 맞아 티가 안 났다 — 그래서 더 늦게 발견됐다.
    #
    # ⚠ **`ゲイル` 과 `大盗賊 ゲイル` 은 딴사람이다**(유저 확정 2026-08-17) — 파티에 드는
    # 쪽이 `게일` 이고 `대도 게일` 은 그 **할아버지**다. 이름이 겹치므로 후보 좁히기에서
    # 뭉개지면 손자 대사에 할아버지 문장이 들어온다. 지금은 `name_sim('게일','대도 게일')`
    # 이 0.50 이라 문턱(0.6) 아래로 갈리는데 **그건 우연이다** — 문턱을 낮추거나 부분일치를
    # 허용하는 쪽으로 고칠 때 이 쌍을 먼저 확인할 것.
    "ゲイル": "게일",
    "大盗賊 ゲイル": "대도 게일",
    "リュナン": "류난",
    "セリオス": "세리오스",
    "ソニア": "소니아",
    "兵士": "병사",
    "侍女": "시녀",
    "男": "남자",
    "女": "여자",
    "老人": "노인",
    "道具屋": "도구점",
    # ⚠ `ラルファの道具屋` 는 접미(`の道具屋`)가 있어 부분일치로 `ラルフ`(랄프)에 끌려갔다 —
    # 마스쿤 이벤트에서 화자가 `랄프` 로 나왔다(유저 QA 2026-08-08). 정발은 `랄파의 도구점`.
    "ラルファの道具屋": "랄파의 도구점",
    "武器屋": "무기점",
    "防具屋": "방어구점",
    "神父": "신부",
    # 遊び人 = **건달**(유저 확정 2026-08-26). 정발은 `여행자` 였는데 `遊び人` 은 한량·건달이지
    # 미해결로 빠졌고, 그러면 화자창이 비거나 임의 표기가 나간다(유저 QA 2026-08-03 — 내가
    # `건달`로 잘못 넣었던 자리다). 정발이 쓴 말이 정본이다.
    "遊び人": "건달",
    "海賊": "해적",
    # ⚠ 유저 확정 2026-08-19 — 원문 `盗賊` 의 정확한 대응. 정발·옛 정본은 「도둑」이었다.
    # `大盗賊 ゲイル` 는 **칭호**라 「대도 게일」로 따로 간다(大盗 는 우리말에 있는 낱말).
    "盗賊": "도적",
    "隊長": "대장",
    "子供": "아이",
    "母親": "아이 어머니",
    "パン屋": "빵집",
    "学者": "학자",
    "役人": "공무원",
    "商人": "상인",
    "漁師": "어부",
    "少女": "소녀",
    "少年": "소년",
    "おばあさん": "할머니",
    "賢者": "현자",
    "側近": "측근",
    "怪物": "괴물",
    "ハリー": "해리",
    "ゴードン": "고든",
    "ファーガソン": "퍼거슨",
    "アートス国王": "아토스 국왕",  # ⚠ ED1 정발 `아도스`, ED2 `아토스` — ED2 우선(유저 확정 2026-08-12)
    "クレア王妃": "크레아 왕비",
    # 실데이터 대조로 확정한 추가분 (KR 인벤토리 131명 기준)
    "おじいさん": "할아버지",
    "にわとり": "닭",
    "やぎ": "염소",
    "修道士": "수도사",
    "船長": "선장",
    "村長": "촌장",
    "町長": "시장",
    "長老": "장로",
    "門番": "문지기",
    "宿屋の主人": "여관주인",
    "宿の主人": "여관주인",
    "酒場の主人": "술집 주인",
    "占い師": "점술사",
    "砂漠の商人": "사막의 상인",
    "奴隷商人": "노예상인",
    # 정발 엔트리마다 `밀매상`/`밀매상인`이 갈리는데 화자창 표기는 `밀매상`이 정본이다
    # (유저 QA 2026-08-03 — 정발 화면 대조). JP 화자는 `やみの商人` 하나뿐이라 여기서 통일한다.
    "やみの商人": "밀매상",
    "やみ屋": "밀매상",
    "何でも屋": "뭐든지 가게",
    "農夫": "농부",
    "補佐官": "보좌관",
    "司令官": "사령관",
    "兵士の隊長": "병사의 대장",
    "兵士たち": "병사들",
    "入口の兵士": "입구의 병사",
    "門の兵士": "문의 병사",
    "家の中の男": "집안의 남자",
    "レジスタンスの男": "레지스탕스의 남자",
    "石像": "석상",
    "光の剣": "빛의 검",
    "情報屋 トミー": "정보상 토미",  # 정발 실측(ED2 화자 헤더·대사 모두 `정보상`)
    "流血の洞窟の主 ガルゴ": "유혈 동굴의 주인 가르고",
    "海賊の親分": "해적선장",
    "ディーナ姫": "디나 공주",
    "ラヌーラの娘": "라누라의 소녀",  # 정발 `라누라의 아가씨`. ⚠ 정발은 `라느라` 지만 지명 표기 정본은 `라누라` 다
    "頑固そうな老人": "완고해 보이는 노인",
    "やさしそうな おばあさん": "착해 보이는 할머니",
    "気の強そうな女": "당차 보이는 여자",
    "ねあかの娘": "밝은 소녀",
    # ⚠ **원문이 갈라 쓰면 우리도 가른다**(유저 확정 2026-08-17). 원작은 `モンスター`(382곳)와
    # `バケモノ`·`怪物`·`魔物`(97곳)를 따로 쓴다 — 한쪽으로 통일하면 원문의 결을 지운다.
    # ED1 이 76곳에서 `モンスター` 를 `괴물` 로 받아 ED2(`몬스터`)와 갈려 있던 것을 맞췄다.
    "バケモノ": "괴물",
    "モンスター": "몬스터",
    "老婆": "노파",
    "囚人": "갇힌 사람",
    "もと囚人": "갇혀있었던 사람",
    "ギルモアの星": "길모아의 별",
    "宝くじ屋": "복권집",
    "娘": "소녀",
}
# 접미사 규칙: 부하·동료류는 본체 이름 매핑 + 접미사 번역
SUFFIX_RULES = [("の手下", "의 부하"), ("の仲間", "의 동료")]

KANA = {
    "ア": "아",
    "イ": "이",
    "ウ": "우",
    "エ": "에",
    "オ": "오",
    "カ": "카",
    "キ": "키",
    "ク": "쿠",
    "ケ": "케",
    "コ": "코",
    "ガ": "가",
    "ギ": "기",
    "グ": "구",
    "ゲ": "게",
    "ゴ": "고",
    "サ": "사",
    "シ": "시",
    "ス": "스",
    "セ": "세",
    "ソ": "소",
    "ザ": "자",
    "ジ": "지",
    "ズ": "즈",
    "ゼ": "제",
    "ゾ": "조",
    "タ": "타",
    "チ": "치",
    "ツ": "츠",
    "テ": "테",
    "ト": "토",
    "ダ": "다",
    "デ": "데",
    "ド": "도",
    "ナ": "나",
    "ニ": "니",
    "ヌ": "누",
    "ネ": "네",
    "ノ": "노",
    "ハ": "하",
    "ヒ": "히",
    "フ": "후",
    "ヘ": "헤",
    "ホ": "호",
    "バ": "바",
    "ビ": "비",
    "ブ": "부",
    "ベ": "베",
    "ボ": "보",
    "パ": "파",
    "ピ": "피",
    "プ": "푸",
    "ペ": "페",
    "ポ": "포",
    "マ": "마",
    "ミ": "미",
    "ム": "무",
    "メ": "메",
    "モ": "모",
    "ヤ": "야",
    "ユ": "유",
    "ヨ": "요",
    "ラ": "라",
    "リ": "리",
    "ル": "루",
    "レ": "레",
    "ロ": "로",
    "ワ": "와",
    "ヲ": "오",
}
KANA2 = {  # 요음·외래어 조합 (2글자 우선 매칭)
    "リュ": "류",
    "シャ": "샤",
    "シュ": "슈",
    "ショ": "쇼",
    "ジャ": "쟈",
    "ジュ": "주",
    "ジョ": "조",
    "チャ": "차",
    "チュ": "추",
    "チョ": "초",
    "キャ": "캬",
    "キュ": "큐",
    "ギャ": "갸",
    "ギュ": "규",
    "ニャ": "냐",
    "ファ": "파",
    "フィ": "피",
    "フェ": "페",
    "フォ": "포",
    "ティ": "티",
    "ディ": "디",
    "ヴァ": "바",
    "ヴィ": "비",
    "ヴェ": "베",
    "ヴォ": "보",
    "ジェ": "제",
    "チェ": "체",
    "シェ": "셰",
    "ウィ": "위",
    "ウェ": "웨",
    "ウォ": "워",
    "ミュ": "뮤",
    "ビュ": "뷰",
    "ピュ": "퓨",
    "ニュ": "뉴",
    "ヒュ": "휴",
    "テュ": "튜",
    "デュ": "듀",
}
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def add_jong(syl, jong):
    """한글 음절에 받침 추가 (없을 때만)."""
    code = ord(syl) - 0xAC00
    if not 0 <= code < 11172 or code % 28:
        return syl
    return chr(ord(syl) + JONG.index(jong))


def kana_to_hangul(name):
    """가타카나 이름 → 한글 음차 (관용 규칙: ー 생략, ン=ㄴ받침, 자음 앞 ル=ㄹ받침)."""
    out = []
    i = 0
    while i < len(name):
        pair = name[i : i + 2]
        if pair in KANA2:
            out.append(KANA2[pair])
            i += 2
            continue
        ch = name[i]
        if ch == "ン" and out:
            out[-1] = add_jong(out[-1], "ㄴ")
        elif ch == "ル" and out and i + 1 < len(name):  # 자음 앞 ル → ㄹ받침
            out[-1] = add_jong(out[-1], "ㄹ")
        elif ch == "フ" and i == len(name) - 1:
            out.append("프")  # 어말 フ 관용
        elif ch in KANA:
            out.append(KANA[ch])
        # ー·ッ·미지 문자는 생략
        i += 1
    return "".join(out)


def jamo(s):
    """한글 문자열 → 자모 시퀀스 (fuzzy 비교용)."""
    out = []
    for ch in s:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [CHO[code // 588], JUNG[code % 588 // 28]]
            if code % 28:
                out.append(JONG[code % 28])
        else:
            out.append(ch)
    return out


def edit_dist(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def name_sim(a, b):
    ja, jb = jamo(a), jamo(b)
    if not ja or not jb:
        return 0.0
    return 1 - edit_dist(ja, jb) / max(len(ja), len(jb))


_ALL_KR_SPK = None


# **정발 코퍼스에 없어도 이 표기를 쓴다** — 정발이 같은 이름을 갈라 쓸 때의 판정이다.
# 근거는 편차 대장(docs/jeongbal-deviations.md)에 함께 적는다.
SPEAKER_FORCE = {
    # ⚠ **두 번 뒤집혔다가 제자리로 왔다.** 08-12: 정발 자체가 갈려 있어(대사 화자
    # `오크 혼` vs 몬스터 도감 `오크혼`) 원음 판정으로 **붙여** 썼다. 08-27: 몬스터 정본이
    # `오크 혼` 이 되면서 전투와 이름창이 갈려 **띄어** 쓰기로 통일했다(유저 확정).
    # 08-29: 공용 정본이 **「외래어 몬스터명은 공백을 뗀다」**로 정해져 다시 **붙인다**
    # (유저 확정 — `아크담의 부하` 같은 한국어 문법 공백만 남긴다). 20종을 함께 맞췄다.
    # 💡 표기가 왔다 갔다 한 까닭은 **규칙이 아니라 개별 판정으로 다뤘기 때문**이다.
    # 이제 규칙이 있으니 개별 자리에서 다시 뒤집지 않는다 — 정본이 판정한다.
    "オークホーン": "오크혼",
    # ⚠ 정발에 짝이 없어 퍼지 매칭이 `당차 보이는 여자` 를 물어 왔는데, 그건 `気の強そうな女`
    # (SCN1 크루즈)의 짝이다. `ねあか` 는 「천성이 밝음」이라 뜻이 다르다(2026-08-12).
    "ねあかの娘": "밝은 소녀",
}


def all_kr_speakers():
    """정발 ED1+ED2 코퍼스 전체의 `{spk}` 이름 집합 — 사전 항목 검증용(씬 범위 밖 포함)."""
    global _ALL_KR_SPK
    if _ALL_KR_SPK is None:
        import glob

        _ALL_KR_SPK = set()
        for p in glob.glob(os.path.join(OUT_DIR, "dos_kr", "*", "*.json")):
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            for e in doc["entries"] if isinstance(doc, dict) else doc:
                _ALL_KR_SPK.update(re.findall(r"\{spk\}(.*?)\{/spk\}", e.get("text", "")))
    return _ALL_KR_SPK


def build_speaker_map(jp_speakers, kr_speakers):
    """JP 화자 → KR 화자 매핑: 사전 → 접미사 규칙 → 음차 fuzzy (임계 0.6)."""
    mapping, unresolved = {}, []
    kr_list = sorted(kr_speakers)

    def resolve(jp):
        # ⚠ 사전은 **정발 코퍼스 전체**를 상대로 검증한다. `kr_speakers` 는 그 씬에 매핑된
        # 테이블의 화자만 담는데, 정발이 다른 테이블에서만 쓰는 이름이 있다(아그니쟈·규리게스는
        # ED1 코퍼스에 실재하는데 씬 집합엔 없어 사전이 통째로 무시됐다 — 2026-08-04 실측).
        # 퍼지 매칭 후보는 기존대로 씬 범위를 유지한다(후보 풀을 넓히면 기존 짝이 흔들린다).
        # ⚠ **정발 내부가 갈리면 사전이 이긴다.** 검증(`all_kr_speakers`)은 사전 오타를
        # 막는 장치인데, 정발이 같은 이름을 두 가지로 쓰면 그 검증이 우리 판정을 막는다 —
        # `オークホーン` 이 그랬다 — 대사 화자로는 `오크혼`, 몬스터 도감으로는 `오크혼`
        # 이라 이름창과 도감이 갈렸다(2026-08-12 실측). 그래서 `SPEAKER_FORCE` 에 적어
        # 검증을 건너뛴다. ⚠ 값 자체는 2026-08-27 에 `오크혼` 으로 통일했다 — 갈림을
        # 없앤 것이지 이 우회가 필요 없어진 건 아니다(정발 검증은 여전히 막는다).
        if jp in SPEAKER_FORCE:
            return SPEAKER_FORCE[jp]
        if jp in SPEAKER_DICT and SPEAKER_DICT[jp] in all_kr_speakers():
            return SPEAKER_DICT[jp]
        for suf_jp, suf_kr in SUFFIX_RULES:
            if jp.endswith(suf_jp):
                base = resolve(jp[: -len(suf_jp)])
                if base and base + suf_kr in kr_speakers:
                    return base + suf_kr
        translit = kana_to_hangul(jp)
        best, best_s = None, 0.6
        for kr in kr_list:
            s = name_sim(translit, kr)
            if s > best_s:
                best, best_s = kr, s
        return best

    for jp in sorted(jp_speakers):
        kr = resolve(jp)
        if kr:
            mapping[jp] = kr
        else:
            unresolved.append(jp)
    return mapping, unresolved


# ── 블록 로드·시그니처 ──────────────────────────────────────────────────────
# 마크업 한 벌은 **`common.MARKUP` 이 정본**이다 — 사본을 두면 조용히 갈린다
# (2026-08-29 통합: 여섯 파일 중 둘이 대문자 헥스만 봤다).
TAG = MARKUP
JP_SPK = re.compile(r"^\{c\}(.*?)\{c\}")
DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def norm_body(text):
    """태그·이스케이프·공백 제거 + 전각 숫자 정규화 → 시그니처용 본문."""
    t = TAG.sub("", text).translate(DIGITS)
    return re.sub(r"[\s　]", "", t)


def sig(body):
    return {
        "len": len(body),
        "digits": "".join(re.findall(r"\d", body)),
        "q": min(body.count("?") + body.count("？"), 3),
        "x": min(body.count("!") + body.count("！"), 3),
    }


def valid_jp_speaker(s):
    """첫 {c} 구간이 화자인지 판별 — 긴 문장·나레이션(개행·구두점 포함)은 화자가 아님."""
    return s and len(s) <= 12 and "\\x" not in s and "{n}" not in s and "。" not in s


def load_jp_scene(game, n):
    """SCN JSON → [{id, speaker, sig}]. 화자 아닌 첫 구간은 본문으로 되돌림."""
    path = os.path.join(SCN_JP_DIR, f"{game}SCN{n}.json")
    doc = json.load(open(path, encoding="utf-8"))
    blocks = []
    for e in doc["entries"]:
        if e["kind"] != "block":
            continue
        m = JP_SPK.match(e["text"])
        spk = m.group(1) if m and valid_jp_speaker(m.group(1)) else None
        body = norm_body(e["text"][m.end() :] if spk else e["text"])
        blocks.append({"id": e["entry_id"], "speaker": spk, "sig": sig(body), "body": body})
    return blocks


_ED2_SCENE_TABLES = None


def scene_groups(game, n):
    """씬 n 이 후보로 삼을 정발 파일명 그룹(셋째 글자) 집합.

    ED1 은 **그룹 = 씬번호 − 1** 이 실측 규칙이라 코드로 충분하다(모듈 독스트링).
    ED2 는 전제가 깨진다 — 정발 그룹은 9개인데 PS1 씬은 13개다. 정발은 ED1 과 **같은
    지역 묶음**을 물려받았고(그룹0 = ED1SCN1 지역 …) PS1 은 그것을 **진행 순서로 다시
    갈랐다**(그룹0 → 씬1+2, 그룹2 → 씬4+5+13). 그래서 ED2 만 정본 파일을 읽는다.
    근거는 `ed2_scene_tables.json` 의 maps(맵 세그먼트 지명 헤더 전수 스캔)와
    docs/ed2-scene-map.md.

    ⚠ 옛 규칙은 한 자리 전제라 **씬 10~13 이 항상 0건**이었고(빌드가 계속 경고를 찍었다),
    씬 1~9 도 한 칸씩 어긋난 그룹을 보고 있었다 — 그 상태로 만든 배정 568건은 폐기했다.
    ⚠ 이 집합은 **후보를 좁히는 용도**지 배정 정본이 아니다(정본은 align_map.json).
    넉넉히 잡으면 회수가 늦어질 뿐이지만, 좁게 잡으면 정답이 후보에 없어 영영 안 나온다.
    """
    if game != "ED2":
        return {str(n - 1)}
    global _ED2_SCENE_TABLES
    if _ED2_SCENE_TABLES is None:
        with open(os.path.join(ROOT, "ed2_scene_tables.json"), encoding="utf-8") as f:
            _ED2_SCENE_TABLES = json.load(f)
    return set(_ED2_SCENE_TABLES["groups"].get(str(n), ()))


def load_kr_scene(game, n):
    """씬 그룹의 DLL들 → {table_id: [{id, speaker, sig}]} (no_speaker는 직전 화자 승계)."""
    dir_ = os.path.join(DOS_KR_DIR, game)
    tables = {}
    if not os.path.isdir(dir_):
        return tables
    groups = scene_groups(game, n)
    for fname in sorted(os.listdir(dir_)):
        if not fname.endswith(".json") or fname.startswith(("_", "._")):
            continue
        stem = fname[:-5]
        if len(stem) < 3 or stem[2] not in groups:
            continue
        doc = json.load(open(os.path.join(dir_, fname), encoding="utf-8"))
        blocks, cur_spk = [], None
        for e in doc["entries"]:
            if e["kind"] != "block":
                continue
            carried = not e["speaker"]
            if e["speaker"]:
                cur_spk = e["speaker"]
            if "no_body" in e["flags"]:
                continue
            body = norm_body(e["text"])
            blocks.append(
                {
                    "id": e["entry_id"],
                    "speaker": cur_spk,
                    "carried": carried,  # 승계 화자 — 나레이션 오귀속 가능, 감쇠 가중치
                    "sig": sig(body),
                    "body": body,
                }
            )
        if blocks:
            tables[doc["table_id"]] = blocks
    if not tables:
        print(f"경고: {game} 씬{n} — 대응 KR 테이블 0건 (씬 규칙 미대응 또는 덤프 누락 확인)")
    return tables


# ── 매칭 ────────────────────────────────────────────────────────────────────
KR_PER_JP = 0.55  # 본문 길이 비율 기준값 (KR자수/JP자수, 조사·압축 감안한 근사)
GAP_JP, GAP_KR = -0.35, -0.9  # JP 쪽은 리메이크 추가분이 많아 갭 패널티를 낮게


def annotate_names(jp_blocks, kr_tables, spk_map):
    """본문 속 등장인물 이름 앵커 (가타카나 고유명만 — 보통명사는 노이즈)."""
    kana_names = {k: v for k, v in spk_map.items() if re.fullmatch(r"[ァ-ヴー]{3,}", k)}
    for b in jp_blocks:
        b["names"] = {v for k, v in kana_names.items() if k in b["body"]}
    kr_values = set(kana_names.values())
    for blocks in kr_tables.values():
        for b in blocks:
            b["names"] = {v for v in kr_values if v in b["body"]}


def pair_score(jp, kr, spk_map):
    s = 0.0
    mj = spk_map.get(jp["speaker"]) if jp["speaker"] else None
    if mj and kr["speaker"]:
        # KR 승계 화자는 나레이션 오귀속 가능성이 있어 감쇠
        w_hit, w_miss = (1.5, -1.0) if kr["carried"] else (3.0, -2.5)
        s += w_hit if mj == kr["speaker"] else w_miss
    inter = jp["names"] & kr["names"]
    sym = jp["names"] ^ kr["names"]
    s += min(2.4, 1.2 * len(inter)) - min(1.5, 0.6 * len(sym))
    a, b = jp["sig"], kr["sig"]
    if a["len"] and b["len"]:
        r = b["len"] / (a["len"] * KR_PER_JP)
        s += max(-1.0, 1.5 - 2.0 * abs(math.log(r)))
    if a["digits"] or b["digits"]:
        s += 1.5 if a["digits"] == b["digits"] else -1.0
    s += 0.5 if a["q"] == b["q"] else -0.25
    s += 0.5 if a["x"] == b["x"] else -0.25
    return s


def smith_waterman(jp_blocks, kr_blocks, spk_map, claimed):
    """국소 정렬: KR 블록열(한 DLL)이 JP 씬 열 안에서 가장 잘 맞는 경로. 반환: [(ji, ki, score)]."""
    nj, nk = len(jp_blocks), len(kr_blocks)
    H = [[0.0] * (nk + 1) for _ in range(nj + 1)]
    best, best_pos = 0.0, (0, 0)
    for i in range(1, nj + 1):
        for j in range(1, nk + 1):
            m = pair_score(jp_blocks[i - 1], kr_blocks[j - 1], spk_map)
            if jp_blocks[i - 1]["id"] in claimed:
                m = -4.0  # 이미 다른 DLL이 청구한 JP 블록
            H[i][j] = max(0.0, H[i - 1][j - 1] + m, H[i - 1][j] + GAP_JP, H[i][j - 1] + GAP_KR)
            if H[i][j] > best:
                best, best_pos = H[i][j], (i, j)
    # traceback
    pairs = []
    i, j = best_pos
    while i and j and H[i][j] > 0:
        m = pair_score(jp_blocks[i - 1], kr_blocks[j - 1], spk_map)
        if jp_blocks[i - 1]["id"] in claimed:
            m = -4.0
        if abs(H[i][j] - (H[i - 1][j - 1] + m)) < 1e-9:
            pairs.append((i - 1, j - 1, m))
            i, j = i - 1, j - 1
        elif abs(H[i][j] - (H[i - 1][j] + GAP_JP)) < 1e-9:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def refine(pairs, jp_blocks, kr_blocks, spk_map, claimed_pos):
    """국소 재배정: 같은 NPC의 상태별 변형 대사는 판본 간 파일 내 순서가 달라
    순차 정렬이 ±N 어긋난다. ① 인접 쌍 스왑 힐클라이밍 ② 미청구 JP 재할당."""
    pairs = [list(p) for p in pairs]

    def sc(ji, ki):
        return pair_score(jp_blocks[ji], kr_blocks[ki], spk_map)

    for _ in range(4):  # 수렴까지 반복 (보통 2회면 고정)
        improved = False
        # ① 쌍끼리 JP 교환
        for i in range(len(pairs)):
            for j in range(i + 1, min(i + 5, len(pairs))):
                a, b = pairs[i], pairs[j]
                cur = sc(a[0], a[1]) + sc(b[0], b[1])
                alt = sc(a[0], b[1]) + sc(b[0], a[1])
                if alt > cur + 0.2:
                    a[0], b[0] = b[0], a[0]
                    improved = True
        # ② 근방의 미청구 JP로 갈아타기
        used = {p[0] for p in pairs}
        for p in pairs:
            best_ji, best_s = p[0], sc(p[0], p[1]) + 0.3
            for cand in range(max(0, p[0] - 6), min(len(jp_blocks), p[0] + 7)):
                if cand in used or cand in claimed_pos:
                    continue
                s = sc(cand, p[1])
                if s > best_s:
                    best_ji, best_s = cand, s
            if best_ji != p[0]:
                used.discard(p[0])
                used.add(best_ji)
                p[0] = best_ji
                improved = True
        if not improved:
            break
    return [(ji, ki, sc(ji, ki)) for ji, ki, _ in pairs]


def align_scene(game, n, spk_map):
    jp_blocks = load_jp_scene(game, n)
    kr_tables = load_kr_scene(game, n)
    annotate_names(jp_blocks, kr_tables, spk_map)
    claimed = {}  # jp_id → (table, kr_id)
    claimed_pos = set()  # jp 리스트 인덱스 (refine용)
    results = []
    # 블록 수 많은 DLL부터 (긴 시퀀스가 위치 확정에 유리)
    for table in sorted(kr_tables, key=lambda t: -len(kr_tables[t])):
        kr_blocks = kr_tables[table]
        pairs = smith_waterman(jp_blocks, kr_blocks, spk_map, claimed)
        pairs = refine(pairs, jp_blocks, kr_blocks, spk_map, claimed_pos)
        matched_k = set()
        for ji, ki, m in pairs:
            if m <= 0:
                continue  # 갭 대용으로 억지 매칭된 저점수 쌍은 버림
            jp, kr = jp_blocks[ji], kr_blocks[ki]
            claimed[jp["id"]] = (table, kr["id"])
            claimed_pos.add(ji)
            matched_k.add(kr["id"])
            flags = [] if m >= 2.0 else ["low_confidence"]
            results.append(
                {
                    "jp": {"entry_id": jp["id"], "speaker": jp["speaker"]},
                    "kr": {"table": table, "entry_id": kr["id"], "speaker": kr["speaker"]},
                    "score": round(m, 2),
                    "flags": flags,
                }
            )
        for kr in kr_blocks:
            if kr["id"] not in matched_k:
                results.append(
                    {
                        "jp": None,
                        "kr": {"table": table, "entry_id": kr["id"], "speaker": kr["speaker"]},
                        "score": 0,
                        "flags": ["unmatched_kr"],
                    }
                )
    jp_unmatched = [b["id"] for b in jp_blocks if b["id"] not in claimed]
    return {
        "scene": f"{game}SCN{n}",
        "jp_blocks": len(jp_blocks),
        "kr_blocks": sum(len(v) for v in kr_tables.values()),
        "kr_tables": sorted(kr_tables),
        "matched": len(claimed),
        "pairs": results,
        "jp_unmatched": jp_unmatched,
    }


def main():
    # ⚠ 인자 없이 돌리면 **의미정렬(align_semantic, LaBSE) 결과인 `*_SCN*.json` 을 덮어쓴다**.
    # 화자맵만 필요하면 `--speakers-only` 를 쓸 것 — 빌드 체인이 쓰는 경로가 이쪽이다.
    speakers_only = "--speakers-only" in sys.argv
    os.makedirs(ALIGN_DIR, exist_ok=True)
    for game, (_, n_scn) in GAMES.items():
        if not os.path.isdir(os.path.join(DOS_KR_DIR, game)):
            print(f"{game}: dos_kr 덤프 없음 — 건너뜀")
            continue
        # 화자 인벤토리 (게임 전체) → 매핑표
        jp_spk, kr_spk = set(), set()
        for n in range(1, n_scn + 1):
            jp_spk |= {b["speaker"] for b in load_jp_scene(game, n) if b["speaker"]}
            for blocks in load_kr_scene(game, n).values():
                kr_spk |= {b["speaker"] for b in blocks if b["speaker"]}
        spk_map, unresolved = build_speaker_map(jp_spk, kr_spk)
        with open(os.path.join(ALIGN_DIR, f"{game}_speakers.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"map": spk_map, "unresolved_jp": unresolved}, f, ensure_ascii=False, indent=1
            )
        print(f"{game}: 화자 매핑 {len(spk_map)}건, 미해결 {len(unresolved)}건")
        if speakers_only:
            continue

        for n in range(1, n_scn + 1):
            # ⚠ 의미정렬(align_semantic) 결과를 **구조 신호 초안으로 덮어쓰지 않는다.**
            # 이 파일은 두 도구가 공유하는데, 여기(화자·길이·순서)는 같은 화자의 변형 대사를
            # swap 한다 — 정본을 날리면 인게임에서 "잘 나오던 대사가 딴 대사로" 바뀐다
            # (2026-08-03 실측: 머신 이동 후 work/derived 복구 중 실제로 밟았다. work/ 는
            # gitignore 라 정렬이 머신을 안 따라가고, 재생성하면 초안이 된다).
            out = os.path.join(ALIGN_DIR, f"{game}_SCN{n}.json")
            if "--force" not in sys.argv and os.path.exists(out):
                try:
                    gen = json.load(open(out, encoding="utf-8")).get("generator")
                except (json.JSONDecodeError, OSError):
                    gen = None
                if gen == "align_semantic":
                    print(
                        f"  건너뜀 {game}_SCN{n}: 의미정렬(align_semantic) 정본이다 — "
                        f"덮어쓰려면 --force (권장: `python3 tools/align_semantic.py` 로 재생성)"
                    )
                    continue
            doc = align_scene(game, n, spk_map)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
            pct = 100 * doc["matched"] / doc["kr_blocks"] if doc["kr_blocks"] else 0
            low = sum(1 for p in doc["pairs"] if "low_confidence" in p["flags"])
            print(
                f"  SCN{n}: JP {doc['jp_blocks']} / KR {doc['kr_blocks']} "
                f"→ 매칭 {doc['matched']} (KR 대비 {pct:.0f}%, low_conf {low}), "
                f"JP 미매칭 {len(doc['jp_unmatched'])}"
            )


if __name__ == "__main__":
    main()
