"""타이틀 로고 「영웅전설」 정본.

원화(유저 제작)는 자간이 24 / 3 / -8px 이고 배경이 검게 구워져 있었다(알파 없음). 글자를
넷으로 갈라 다시 늘어놓고 알파를 만든 결과가 `shared/assets/title_logo.png` — **그 정본을
커밋하고 빌드는 읽기만 한다.** 분할은 휴리스틱(연결 성분·밝기 임계)이라 빌드 경로에 두면
원화를 손댈 때 조용히 흔들린다. 이 레포 관용대로 판단은 정본에 박는다.

⚠ **자간을 다시 만지려면 원화가 필요하다.** 지금은 레포에 없다(유저 확정 2026-08-23 —
  정본이 있으니 원화는 뺀다). 만든 절차와 값은 `shared/assets/README.md` 와 이 커밋 이전
  히스토리에 있다.

PS1·새턴이 같은 로고를 쓴다(둘 다 320x240, 원본 한자 상자도 같다).
"""

import os

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, find_objects, label

INK_LUM = 60  # 이 위가 글자 본체(금색·크림)

# 🔴 확정 자간(유저 QA 2026-08-23) — 원화 척도의 기하 간격 셋.
#   경위: 균등 62 로 놓으니 「영웅은 좁고 전설은 넓다」였고(마주보는 거리 117 / 162 / 138),
#   넓이를 맞춘 광학 해(79 / 48 / 59)는 이번엔 「영웅·전설이 넓고 웅전이 좁다」였다.
#   둘 사이에서 눈으로 골랐다. ⚠ 계산으로 안 닫힌다 — **사람이 보고 정한 값**이다.
GAPS = (68, 62, 56)

CANON = os.path.join(os.path.dirname(__file__), "..", "assets", "title_logo.png")


def title_logo():
    """타이틀 로고 정본 RGBA. 게임 도구는 이것만 부른다."""
    return Image.open(CANON).convert("RGBA")


def split(rgb):
    """(4개 성분의 주인 맵, 각 성분의 잉크 상자)."""
    lum = rgb.sum(2)
    ink = lum > INK_LUM
    lab, n = label(ink, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())
    keep = [i for i in range(1, n + 1) if sizes[i] > 800]
    boxes = find_objects(lab)
    keep.sort(key=lambda i: boxes[i - 1][1].start)
    if len(keep) != 4:
        raise SystemExit(f"글자를 넷으로 못 갈랐다 — 덩어리 {len(keep)}개")
    # 잉크가 아닌 화소(그림자·안티에일리어스)는 **가장 가까운 잉크의 주인**에게 준다
    _, idx = distance_transform_edt(~ink, return_indices=True)
    near = lab[idx[0], idx[1]]
    owner = np.zeros(lab.shape, np.int8)
    for k, i in enumerate(keep):
        owner[near == i] = k + 1
    return owner, [(boxes[i - 1][1].start, boxes[i - 1][1].stop - 1) for i in keep]


def facing(owner, ink, i, y0, y1):
    """i 번째와 i+1 번째 글자가 **마주보는 거리**를 행별로."""
    L = (owner == i + 1) & ink
    R = (owner == i + 2) & ink
    out = []
    for y in range(y0, y1 + 1):
        a = np.nonzero(L[y])[0]
        b = np.nonzero(R[y])[0]
        if len(a) and len(b):
            out.append(b.min() - a.max() - 1)
    return np.array(out, float)
