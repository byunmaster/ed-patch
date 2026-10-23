"""실게임 흐름 촬영 — 새 게임을 정식으로 진행해 필드 NPC 말걸기 직전까지 가고, 그 NPC 의 대사 문자열을
RAM 에서 목표 문안으로 갈아 끼운 채 실제로 말을 걸어 찍는다.

왜 이렇게 하나. 엔진의 메시지 표시 함수(0x800B1D24)를 필드 VSync 훅에서 직접 부르던 옛 방식은 실제 필드 흐름과
달라 창이 5행으로 그려지고(「이름 + 본문 5줄」에서 이름이 밀림), 쪽 끝에 대기 커서(▽) 대신 점무늬가 찍혔다.
실제 말걸기 흐름을 타면 창 행 수·글자 렌더·타자 애니메이션·▽ 커서가 실게임과 같다(자연 대사와 픽셀 차이 0 — README).

한계: 창 위치는 이 NPC 에서 고정(화면 아래 왼쪽)이고, 인자 값(이름 주입 등)은 `pages.evaluate` 가 흉내 낸다.
게임마다 진행 경로·말걸기 대상 NPC 가 다르다 — `PROFILES`(ED1 · ED2)가 정본이다.
"""

import os

import numpy as np

from .libretro import Machine

CROP = (136, 232, 0, 200)  # 대사창이 들어 있는 화면 영역(y0, y1, x0, x1) — 테두리 바깥까지
TEXT_BOX = (14, 80, 10, 190)  # 크롭 안의 글자 영역(위의 맵 애니메이션·아래 ▽ 커서를 뺀다)
CURSOR_BOX = (80, 96, 90, 115)  # 크롭 기준 ▽ 커서 자리(y0, y1, x0, x1)

_BOOT = [("run", 2600), ("press", "start", 10, 180)]  # 타이틀 → 메뉴

# 게임별 진행 경로·말걸기 대상. (버튼, 누름 프레임, 뗀 뒤 프레임) / ("run", 프레임) — 말걸기 직전까지.
PROFILES = {
    # ED1: 새 게임 → 1장 오프닝 → 엘아스타 성 → NPC(대장간 쪽)에게 말 걸기 직전.
    "ED1": {
        "slot": ("ED1SCN1", 21),
        "talk": ("circle", 4, 0),  # 말걸기 입력
        "presses": 10,  # 말걸기 앞 대사 쪽 수 — 씬 문안의 쪽 수가 바뀌면 맞춘다(--presses)
        "route": (
            _BOOT
            + [("press", "circle", 4, 600), ("press", "start", 4, 900)]
            + [("press", "circle", 4, 300)] * 3
            + [("press", "circle", 4, 200)] * 3
            + [("press", "circle", 4, 150)] * 24
            + [("press", "down", 120, 10)] * 4
            + [("press", "down", 60, 10), ("press", "circle", 4, 60)]
            + [("press", "up", 8, 10), ("press", "left", 8, 10), ("press", "circle", 4, 80), ("run", 400)]
        ),
    },
    # ED2: 타이틀에서 오른쪽(= ED2) → 서장 「평화로운 나날」 → 엘아스타 성 → 교육계 라우엘 쪽으로 걸어가면
    #      위로 한 걸음 더 닿는 순간 대사가 **자동으로 시작**한다(말걸기 버튼이 아니라 걸음이 방아쇠) — 그 직전까지 간다.
    "ED2": {
        "slot": ("ED2SCN1", 1),
        "talk": ("up", 10, 0),
        "presses": 0,
        "route": (
            _BOOT
            + [("press", "right", 4, 20), ("press", "circle", 4, 600), ("press", "start", 4, 900)]
            + [("press", "circle", 4, 300)] * 3
            + [("press", "circle", 4, 100)] * 12
            + [("press", "circle", 4, 150)] * 10
            + [("press", "down", 30, 30)]
            + [("press", "right", 60, 10), ("press", "right", 40, 10), ("press", "up", 30, 10)]
        ),
    },
}  # fmt: skip
SLOT_SCN, SLOT_EID = PROFILES["ED1"]["slot"]  # (호환) ED1 말걸기 대상
ROUTE = PROFILES["ED1"]["route"]
TALK_PRESSES = PROFILES["ED1"]["presses"]


def _step(m: Machine, s: tuple):
    if s[0] == "run":
        m.run(s[1])
    else:
        m.press(s[1], s[2], s[3])


class RealFlow:
    def __init__(
        self,
        m: Machine,
        cache_dir: str,
        slot_bytes: bytes,
        presses: int | None = None,
        game: str = "ED1",
    ):
        self.m = m
        self.game = game
        self.pre = os.path.join(
            cache_dir, "pre_talk.state" if game == "ED1" else f"pre_talk_{game.lower()}.state"
        )
        self.slot_bytes = slot_bytes
        self.presses = PROFILES[game]["presses"] if presses is None else presses
        self.slot = 0
        self.hero_ram = b""

    def prepare(self):
        """말걸기 직전 상태를 만들거나(첫 실행) 캐시에서 읽는다. 상태엔 이 이미지의 코드가 들어 있다."""
        m = self.m
        m.run(1)
        if os.path.exists(self.pre):
            m.load(self.pre)
        else:
            for s in PROFILES[self.game]["route"]:
                _step(m, s)
            for _ in range(self.presses):
                m.press("circle", 4, 150)
                m.run(150)
            os.makedirs(os.path.dirname(self.pre), exist_ok=True)
            m.save(self.pre)
        ram = m.dump()
        at = ram.find(self.slot_bytes, 0x00060000)
        if at < 0:
            raise RuntimeError("대상 NPC 의 대사 문자열을 RAM 에서 못 찾았다 — 경로·이미지 확인")
        self.slot = 0x80000000 + at

    def _window(self) -> np.ndarray:
        y0, y1, x0, x1 = CROP
        return self.m.frame()[y0:y1, x0:x1]

    def _cursor_visible(self, win: np.ndarray) -> bool:
        y0, y1, x0, x1 = CURSOR_BOX
        p = win[y0:y1, x0:x1].astype(int)
        return bool(((p[..., 1] > 90) & (p[..., 0] < 60) & (p[..., 2] > 90)).any())

    def shoot(self, text: bytes | None, max_frames: int = 1500):
        """text 를 그 NPC 대사로 갈아 끼우고 말을 건다(None 이면 자연 대사). → (창 크롭, 타자 끝남, ▽ 보임)"""
        m = self.m
        m.load(self.pre)
        if text is not None:
            m.poke(self.slot, text + b"\0")
        m.press(*PROFILES[self.game]["talk"])
        last, stable, spent = None, 0, 0
        while spent < max_frames:
            m.run(6)
            spent += 6
            y0, y1, x0, x1 = TEXT_BOX
            cur = self._window()[y0:y1, x0:x1].copy()
            stable = stable + 1 if last is not None and (cur == last).all() else 0
            last = cur
            if stable >= 10:
                break
        done = stable >= 10
        for _ in range(40):  # ▽ 가 깜박이므로 보이는 프레임을 기다린다
            if self._cursor_visible(self._window()):
                break
            m.run(2)
        win = self._window().copy()
        return win, done, self._cursor_visible(win)
