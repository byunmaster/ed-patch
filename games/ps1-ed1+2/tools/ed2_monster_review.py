"""ED2 몬스터 이름 — PS1 원문과 정발 문안을 음차로 짝지어 검토표를 낸다.

`ED2MON<N>.BIN` 의 레코드는 **[이름들][대사들][능력치표]** 반복이고, 능력치표가
`64 00`(=100)의 긴 반복이라 **언어와 무관한 구분자**로 쓸 수 있다. 정발 `M_<N>xx.DLL` 은
**파일 하나 = 전투 조우 하나**라 이름 슬롯 4개에 서로 다른 종이 들어갈 수 있다
(`M_206` = 호보 / 독카즈라A / 독카즈라B). 자세한 근거는 `docs/ed2-status.md`.

⚠ **번호만으로는 기계적으로 안 짝지어진다** — 종 수가 다르고(147/143) 순서도 국지적으로
어긋난다. 그래서 음차 유사도로 **후보**를 내고 사람이 고른다. 화자 매핑에서 쓰는
`align_jp_kr.kana_to_hangul` · `name_sim` 을 그대로 재사용한다(규칙이 갈리면 안 된다).

⚠ 산출물은 **정발 문안을 담으므로 `work/review/` 에만** 쓴다 — 커밋 금지.

    python3 tools/ed2_monster_review.py            # 검토표 생성
    python3 tools/ed2_monster_review.py --group 2  # 한 그룹만 화면에
"""

import argparse
import glob
import itertools
import json
import os
import re

from align_jp_kr import kana_to_hangul, name_sim
from common import REVIEW_DIR, ROOT, extract

# ED2MON<N>.BIN — (LBA, 크기). `reinsert_kr_pilot.SCN_FILES` 와 같은 출처다.
MON = {
    0: (2408, 8584),
    1: (2413, 92356),
    2: (2459, 48000),
    3: (2483, 58536),
    4: (2512, 70944),
    5: (2547, 58008),
}

# ⚠ 레포 상대경로를 쓰면 cwd 를 탄다 — 어디서 부르든 같아야 한다
KR_MON_DIR = os.path.join(ROOT, "..", "..", "originals", "kr", "dos-ed2", "MON")
KR_NAME_OFF, KR_NAME_STRIDE, KR_NAME_SLOTS = 0x3430, 0x40, 4

# 능력치표 = `64 00` 의 긴 반복. 반복 수를 12 로 잡든 16 으로 잡든 같은 수가 나온다.
STAT = re.compile(rb"(?:\x64\x00){12,}")

JP = re.compile(r"[ぁ-んァ-ヴ一-鿿]")
CTL = re.compile(r"[\x00-\x1f]")
DIALOG = re.compile(r"[。！？…、」『%\n]")  # 하나라도 있으면 이름이 아니라 대사다
# 개체 구분 접미. ⚠ A~D 로 끊지 말 것 — `ニュートハニーE`~`J` 처럼 J 까지 간다
SUFFIX = re.compile(r"[Ａ-ＺA-Z][’′”]*$")
PLACE = re.compile(r"^[MＭ][0-9０-９]{3}[A-DＡ-Ｄ]?$")  # `M206D` 같은 빈 슬롯 자리표

NAME_MAX = 14  # 이름의 최대 글자 수. 넘으면 대사로 본다
SIM_OK = 0.6  # 화자 매핑과 같은 임계

# 음차로도 순서로도 안 잡히는 자리 — 사람이 정한다. 표기는 **ED1 `patch_items.MONSTERS` 선례**를
# 따른다: 붙여쓰기(`슬라임버브`·`썬더하운드`), 뜻이 서는 말은 의미역(`猛毒ガメ`→`맹독거북`·
# `オオバサミ`→`큰가위`), 단 `~の~` 는 띄운다(`アクダムの手下`→`아크담의 부하`).
# ⚠ 표시는 **정발과 갈리는 자리**다 — 정발이 음차인데 ED1 통일을 택했다.
MANUAL = {
    # 정발이 원문을 잘못 읽은 자리 — 방침대로 자체 번역으로 간다
    "デスバード": "데스버드",  # 정발 `데쓰 뱃트` — バード(bird)를 バット(bat)로 봤다
    "ゴドウィン２世": "고드윈 2세",  # 정발은 `２世` 를 통째로 흘렸다
    "パワーアングル": "파워앵글",
    "羽竜": "익룡",
    # ⚠ 아래 셋은 **슬롯이 좁다**. 이름 시작은 4바이트 정렬이어야 하고 그 안에서만 쓸 수 있다.
    # 넘치면 패처가 건너뛰고 **화면엔 일본어가 그대로 남는다**.
    "炎の騎士": "불꽃의기사",  # 정발 그대로. 띄어쓰기만 뺐다(12B 슬롯에 딱 12B)
    "木人": "목인",  # ⚠ 정발 `나무인간` 은 10B 인데 슬롯이 8B — 재배치해도 48B/32B 라 안 된다
    "杖使い": "봉술사",  # ⚠ 정발 `지팡이 술사` 는 12B, 슬롯 8B — 대사까지 손볼 때 되찾는다
    "邪心の仮面": "사심의 가면",
    "砂もぐら": "모래두더지",  # 정발 `모래 두더쥐` — 표준어는 두더지
    "スプラッシャー": "스플래셔",
    "レミングプラス": "레밍플러스",
    "冷血ガメ": "냉혈거북",  # ED1 `猛毒ガメ`→`맹독거북` 선례
    "猛毒ナメクジ": "맹독민달팽이",  # ⚠ 정발은 음차 `맹독 나메쿠지`
    "ひげくじら": "수염고래",
    "鋼鉄アリ": "강철개미",
    "毒カヅラ": "독덩굴",  # ⚠ 정발은 음차 `독카즈라`. カヅラ = 덩굴
    "ハンタークロー": "헌터크로우",
    "レッドラット": "레드랫",  # 정발 `레드 랫드`
    "陸クラゲ": "육지해파리",
    "ロングアージ": "롱구아지",
    "モーンガー": "몽거",
    "ホーボ": "호보",  # 정발과 순서가 뒤바뀐 자리라 앵커에서 탈락한다
    "音操り": "음악가",
    "ウｲーバー": "와이바",
    "甲殻亜人": "갑각아인",
    "ニュート": "뉴트",
    "ニュートハニー": "뉴트하니",  # 정발에 짝이 없다
    "暗黒ガス": "암흑가스",
    "護衛": "호위",
    "くぐつ戦士": "꼭두각시전사",
    "レイシア": "레이시아",
    "ダダルカ": "다다르카",  # 정발에 짝이 없다
    "アクトス": "아크토스",  # 정발에 짝이 없다
    "装甲スライム": "장갑슬라임",
    "紅牙戦士": "홍아전사",
    "海王騎士": "해왕기사",
    # ⚠ 아래 일곱은 **레코드 머리 밖에 있는 이름**이라 행 추출이 못 잡았다(대사 패처의
    # 전 파일 훑기에서 드러났다). 손으로 정한 것은 행이 없어도 정본에 실어야 한다 —
    # 안 실으면 그 이름만 화면에 일본어로 남는다.
    "デ・オクト": "디오쿠토",
    "ストライプツ": "스트라이프츠",
    "プルダーム": "풀담",
    "ブランナ": "브란나",
    "雷娘": "뇌랑",
    "ブラムナクイーン": "브람나퀸",
    "サイレント・ロード": "사일런트로드",
}


def decode_sjis(raw):
    """SJIS 로 읽되 **앞의 잡음 바이트를 떼며 재시도**한다.

    ⚠ 앞 레코드의 꼬리 바이트 하나가 붙으면 2바이트 짝이 통째로 밀려 **다른 글자**가 된다
    (실측: `ff`+`ギュード` → `сMュード`, ED2MON3 0x276). 증상이 「이상한 접두가 붙었다」로
    보여서 접두를 잘라내는 쪽으로 가면 **첫 글자를 같이 잃는다**(`ギ` 를 잃었다).
    고칠 자리는 절삭이 아니라 여기, 디코드다.

    ⚠ **첫 성공을 받으면 안 된다.** 잡음 바이트가 한자로 읽히는 자리가 있어(`潼1音操り`)
    그대로 통과한다. 후보를 다 만들어 **ASCII 가 안 섞인 쪽**을 고른다 — 이름은 순수
    일본어라 영숫자가 끼면 그건 잡음이 남았다는 뜻이다.
    """
    c = decode_candidates(raw)
    return c[0] if c else None


def decode_candidates(raw):
    """정렬 후보를 **점수 순으로 전부** 돌려준다 — `decode_sjis` 는 그 첫째다.

    ⚠ 점수만으로는 정렬이 안 갈리는 자리가 있다. 이진 바이트 둘이 우연히 **깨끗한 한자**로
    조립되면 진짜 시작점과 점수가 같아지고, 그때 동점을 가르는 `-skip` 이 **덜 건너뛴 쪽**
    (= 유령 접두가 붙은 쪽)을 고른다. 실측: ED2MON3 0x648 `ff 82 8f 50` + `モーンガーＡ`
    → `8f 50` 이 `襲` 로 읽혀 `襲モーンガーＡ` 가 이기고 정답 `モーンガーＡ` 가 진다.

    바이트만 봐서는 어느 쪽이 맞는지 알 수 없다 — **정본과 대조해야** 갈린다. 그래서 한
    후보를 고르지 않고 목록을 내주고, 부르는 쪽이 표를 걸어 고르게 한다(`resolve_name`).
    """
    out = []
    for skip in range(5):
        try:
            s = raw[skip:].decode("cp932")
        except UnicodeDecodeError:
            continue
        if not s or not JP.match(s):
            continue
        out.append(((not re.search(r"[0-9A-Za-z]", s[:-1]), -skip), s))
    out.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in out]


def resolve_name(raw, names):
    """이 바이트열이 **이름**이면 정본 키를, 아니면 None.

    정렬 후보를 전부 대조한다 — 점수가 뽑은 첫 후보가 유령 접두를 달고 있어도(위 참조)
    올바른 정렬이 후보 안에 있으면 여기서 잡힌다. 이게 없으면 그 자리는 이름인데도
    대사 취급이 되어 「문안 없음」으로 보고된다(실측 1건, ED2MON3 `モーンガーＡ`).
    """
    for s in decode_candidates(raw):
        base = SUFFIX.sub("", s)
        if base in names:
            return base
    return None


def strings(buf, start, end):
    """[start, end) 의 널 종단 문자열 — (오프셋, 문자열)."""
    out = []
    i = start
    while i < end - 1:
        if buf[i] == 0:
            i += 1
            continue
        j = buf.find(b"\x00", i)
        if j < 0 or j > end:
            break
        if 2 <= j - i <= 80:
            s = decode_sjis(buf[i:j])
            if s and JP.search(s):
                out.append((i, s))
        i = j + 1
    return out


def stem(s):
    return SUFFIX.sub("", s).strip()


def normalize(name):
    """표기를 ED1 선례에 맞춘다 — **HUD 이름표는 붙여쓴다**(`그록 가드`→`그록가드`).

    몬스터 이름은 전투 HUD 의 이름표가 주 용도라 유저 방침의 「HUD 는 붙여쓰기」가 적용된다
    (ED1 `patch_items.MONSTERS` 도 `슬라임버브`·`썬더하운드` 로 붙여 놨다). 정발은 스무 자리
    남짓을 띄어 쓰는데 그대로 두면 ED1 과 갈린다.

    ⚠ 예외 둘 — `~의 ~` 는 띄운다(`아크담의 부하` 선례), 숫자 뒤도 띄운다(`고드윈 2세`).
    """
    if "의 " in name or re.search(r" [0-9]", name):
        return name
    return name.replace(" ", "")


def translit(name):
    """음차. ⚠ `kana_to_hangul` 은 가타카나만 안다 — 히라가나를 먼저 올린다.

    몬스터 이름엔 히라가나가 섞인다(`ひげくじら`·`気功うさぎ`). 안 올리면 그 글자가 통째로
    사라져 음차가 빈 문자열이 되고, 짝이 있는데도 못 잡는다.
    """
    kata = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in name)
    return kana_to_hangul(kata)


def records(buf):
    """[(시작, 끝)] — 능력치표 **끝**부터 다음 표 시작까지가 한 레코드다.

    ⚠ 표의 시작에서 자르면 레코드 머리에 표가 들어와 이름을 못 찾는다.
    """
    marks = list(STAT.finditer(buf))
    if not marks:
        return []
    return [(0, marks[0].start())] + [
        (marks[i].end(), marks[i + 1].start()) for i in range(len(marks) - 1)
    ]


def ps1_names(group):
    """[(레코드 번호, [(오프셋, 이름)])] — 레코드 머리에 붙어 있는 이름들."""
    lba, size = MON[group]
    buf = bytes(extract(lba, size))
    out = []
    for idx, (s, e) in enumerate(records(buf)):
        names, seen = [], None
        for off, text in strings(buf, s, e):
            # 이름 구간은 대사가 나오면 끝난다 — 뒤쪽 이름은 분열체 등 파생이라 안 센다
            if len(text) > NAME_MAX or DIALOG.search(text) or CTL.search(text):
                break
            st = stem(text)
            if st and st != seen:
                names.append((off, st))
            seen = st
        out.append((idx, _drop_noise_prefix(names)))
    return out


def _drop_noise_prefix(names):
    """같은 레코드의 **깨끗한 형제**로 잡음 접두를 걷어낸다.

    앞이 문자열이 아니라 이진 덩어리면(`ff 82 8f 50`) 널 기준으로는 시작을 못 찾고, 잡음이
    한자로 읽혀(`襲モーンガーＡ`) 디코드 재시도도 통과한다. 그런데 개체는 Ａ/Ｂ 쌍이라
    **뒤쪽 형제는 대개 깨끗**하다(`モーンガーＢ`). 그걸 정답으로 삼는다.

    ⚠ 오프셋도 같이 민다 — 나중에 이 자리에 한글을 써야 하므로 이름만 고쳐선 안 된다.
    """
    out = []
    for off, st in names:
        short = min(
            (o for _x, o in names if o != st and st.endswith(o)),
            key=len,
            default=None,
        )
        if short:
            off += len(st[: -len(short)].encode("cp932", "replace"))
            st = short
        out.append((off, st))
    return out


def kr_names(group):
    """[(파일명, [이름])] — 정발 조우 파일의 이름 슬롯. ⚠ 종단자가 NUL 이 아니라 `\\x06`."""
    out = []
    for path in sorted(glob.glob(os.path.join(KR_MON_DIR, f"M_{group}*.DLL"))):
        with open(path, "rb") as f:
            data = f.read()
        names, seen = [], None
        for i in range(KR_NAME_SLOTS):
            off = KR_NAME_OFF + i * KR_NAME_STRIDE
            raw = re.split(rb"[\x00-\x08]", data[off : off + 30])[0]
            s = raw.decode("cp949", "replace").strip()
            if not s or PLACE.match(s):
                continue
            st = stem(s)
            if st and st != seen:
                names.append(st)
            seen = st
        out.append((os.path.basename(path), names))
    return out


def _monotone(anchors):
    """등장 순서가 어긋나지 않는 앵커만 남긴다(최장 증가 부분열).

    한쪽이 순서를 어기면 그 앵커를 믿고 사이를 메울 수 없다 — 어긋난 자리를 버리는 편이
    억지로 끼워 맞춰 **뒤를 통째로 밀어 놓는 것**보다 낫다.
    """
    best = []
    for k in range(len(anchors)):
        cur = max((best[m] for m in range(k) if anchors[m][1] < anchors[k][1]), key=len, default=[])
        best.append([*cur, anchors[k]])
    return max(best, key=len, default=[])


def _fill_by_order(pair, n_ps, n_kr):
    """음차로 못 잡은 자리를 **순서**로 메운다 — 앵커 사이에 하나씩만 남으면 서로의 짝이다.

    한자가 섞인 이름은 음차가 원리상 안 나온다(`赤スライム`→`스라이무`, 정발 `붉은슬라임`).
    그런 자리도 **앞뒤가 확정되어 있으면** 사이에 남은 것끼리 짝이 정해진다.

    ⚠ 사이에 남은 수가 서로 다르면 **건드리지 않는다.** 종 수가 애초에 다르므로
    (PS1 147 / 정발 143) 억지로 채우면 한 칸씩 밀린 짝이 조용히 생긴다 — 그게 가장 나쁜
    결과다. 화면에서만 드러나고 빌드는 통과한다.
    """
    anchors = _monotone(sorted((i, j) for i, (j, _s) in pair.items()))
    taken_p = {i for i, _ in anchors}
    taken_k = {j for _, j in anchors}
    for i in list(pair):
        if i not in taken_p:
            del pair[i]

    bounds = [(-1, -1), *anchors, (n_ps, n_kr)]
    for (p0, k0), (p1, k1) in itertools.pairwise(bounds):
        gap_p = [i for i in range(p0 + 1, p1) if i not in taken_p]
        gap_k = [j for j in range(k0 + 1, k1) if j not in taken_k]
        if gap_p and len(gap_p) == len(gap_k):
            for i, j in zip(gap_p, gap_k, strict=True):
                pair[i] = (j, None)  # 유사도 없음 = 순서로 메운 자리


def match(group):
    """음차 유사도로 짝을 낸다 — [(PS1 이름, 음차, 정발 이름 또는 None, 점수, 출처)].

    ⚠ **결정적이어야 한다.** 같은 점수가 여럿이면 등장 순서가 이긴다(`-score` 다음 인덱스).
    부동소수 잡음이 승자를 정하면 머신마다 결과가 갈린다 — 실제로 겪은 사고다.
    """
    ps = [(idx, off, nm) for idx, names in ps1_names(group) for off, nm in names]
    kr = [(f, nm) for f, names in kr_names(group) for nm in names]

    cand = []
    for i, (_idx, _off, jp) in enumerate(ps):
        tr = translit(jp)
        for j, (_f, ko) in enumerate(kr):
            sc = name_sim(tr, ko)
            if sc >= SIM_OK:
                cand.append((-sc, i, j))
    cand.sort()

    took_p, took_k, pair = set(), set(), {}
    for negsc, i, j in cand:
        if i in took_p or j in took_k:
            continue
        took_p.add(i)
        took_k.add(j)
        pair[i] = (j, -negsc)

    _fill_by_order(pair, len(ps), len(kr))

    rows = []
    for i, (idx, off, jp) in enumerate(ps):
        j, sc = pair.get(i, (None, None))
        name = kr[j][1] if j is not None else None
        src = kr[j][0] if j is not None else None
        if jp in MANUAL:  # 손으로 정한 자리가 자동 결과를 이긴다
            name, src, sc = MANUAL[jp], "손", None
        if name:
            name = normalize(name)
        rows.append(
            {
                "rec": idx,
                "off": off,
                "jp": jp,
                "translit": translit(jp),
                "kr": name,
                "src": src,
                "sim": sc,
            }
        )
    # ⚠ `took_k` 가 아니라 **최종 짝**으로 센다 — 순서로 메운 자리가 빠져 「짝 없음」으로 나온다
    used = {j for j, _s in pair.values()}
    unmatched_kr = [kr[j] for j in range(len(kr)) if j not in used]
    return rows, unmatched_kr


def report(groups):
    lines = ["# ED2 몬스터 이름 검토표", ""]
    lines.append("⚠ 정발 문안이 들어 있다 — **커밋 금지**(`work/review/`).")
    lines.append("")
    lines.append("`정발` 이 비었으면 음차로 짝이 안 잡힌 것이다(자체 번역 대상).")
    lines.append("유사도가 낮으면 **음차가 우연히 닿은 남의 이름**일 수 있으니 눈으로 본다.")
    lines.append("")
    tot = hit = 0
    for g in groups:
        rows, left = match(g)
        got = sum(1 for r in rows if r["kr"])
        tot += len(rows)
        hit += got
        lines.append(f"## ED2MON{g} — {len(rows)}종 중 {got}종 짝 잡힘")
        lines.append("")
        lines.append("| 레코드 | 오프셋 | 원문 | 음차 | 정발 | 유사도 | 출처 |")
        lines.append("| ---: | ---: | --- | --- | --- | ---: | --- |")
        for r in rows:
            sim = (
                f"{r['sim']:.2f}"
                if r["sim"] is not None
                else ("" if r["src"] == "손" else "순서" if r["kr"] else "")
            )
            lines.append(
                f"| {r['rec']} | `{r['off']:#07x}` | {r['jp']} | {r['translit']} "
                f"| {r['kr'] or ''} | {sim} | {r['src'] or ''} |"
            )
        lines.append("")
        if left:
            lines.append(f"짝이 안 붙은 정발 이름 {len(left)}: " + ", ".join(n for _f, n in left))
            lines.append("")
    lines.insert(2, f"전체 {tot}종 중 **{hit}종**({hit / tot:.0%}) 이 음차로 짝이 잡혔다.")
    return "\n".join(lines) + "\n", tot, hit


def emit():
    """짝지은 결과를 **커밋되는 정본**(`textmap/monsters_ed2.json`)으로 박는다.

    ⚠ 빌드가 이 스크립트를 부르면 안 된다 — 음차 유사도는 **제안**이고, 제안이 빌드 경로에
    있으면 결과가 환경을 탄다(레포 제1원칙). 여기서 한 번 굳히고 패처는 JSON 만 읽는다.

    단어 수준 명칭이라 리포에 남겨도 된다(`CLAUDE.md` 저작권 절) — 문장급 문안과 다르다.
    """
    # ⚠ 손으로 정한 것을 **먼저** 깐다 — 행 추출이 못 잡은 이름도 정본에 있어야 한다.
    out = dict(MANUAL)
    for g in sorted(MON):
        rows, _left = match(g)
        for r in rows:
            if not r["kr"]:
                continue
            if out.get(r["jp"], r["kr"]) != r["kr"]:
                raise SystemExit(f"⚠ `{r['jp']}` 이 두 값으로 갈린다 — {out[r['jp']]} / {r['kr']}")
            out[r["jp"]] = r["kr"]
    path = os.path.join(ROOT, "textmap", "monsters_ed2.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"몬스터 이름 {len(out)}종 → {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", type=int, help="한 그룹만 화면에 낸다")
    ap.add_argument("--emit", action="store_true", help="정본 JSON 을 갱신한다")
    a = ap.parse_args()

    if a.emit:
        emit()
        return

    groups = [a.group] if a.group is not None else sorted(MON)
    text, tot, hit = report(groups)
    if a.group is not None:
        print(text)
        return
    os.makedirs(REVIEW_DIR, exist_ok=True)
    out = os.path.join(REVIEW_DIR, "ed2_monsters.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{tot}종 중 {hit}종 짝 잡힘 → {out}")


if __name__ == "__main__":
    main()
