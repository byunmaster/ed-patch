"""스팀덱 QA 앱 — 게임을 고르면 빌드를 고르고(없으면 받고) mednafen 으로 띄운다. 끄면 이번 캡처에
메모를 붙여 작업 머신의 QA 수신함으로 올린다.

    ~/.local/share/edqa-venv/bin/python scripts/deck/edqa.py            # 전체 화면(게임 모드)
    ~/.local/share/edqa-venv/bin/python scripts/deck/edqa.py --window   # 창으로(데스크톱 모드)
설치는 `sh scripts/deck/install.sh` — SteamOS 시스템 파이썬엔 깔 수 없어 앱 전용 가상환경에 pygame-ce 를 둔다.

🔴 **왜**(마스터 2026-10-30). 인텔 맥에선 새턴이 버벅인다. 브라우저 실행기(`scripts/publish/run.html`)를
넓히는 안은 접었다 — 브라우저 에뮬은 네이티브보다 무겁고, 새턴 웹 코어는 mednafen 계열이 아니라 화면
판정 기준이 흔들리고, CD 이미지(300~700MB)를 열 때마다 받아야 한다. 덱에선 mednafen 이 그대로 돈다.

마스터 요청 그대로:
  · 게임 선택 → 빌드 선택 → 실행. 덱에 없으면 받는다. 빌드 삭제.
  · 게임별·빌드별 캡처 목록 / 상세 · 메모 · 삭제.
  · 정렬은 기종별.

── 서버 ─────────────────────────────────────────────────────────────────────
작업 머신의 파일서버(`scripts/publish/serve.py`, :8800)의 `/api/*` 를 쓴다(그 파일 머리말). 서버 주소는
첫 실행에 묻고 `~/.config/edqa/config.json` 에 둔다. 집 망이면 `http://<작업 머신 IP>:8800`.

── 지키는 것(이 레포의 1급 사고가 「낡거나 엉뚱한 이미지를 정상으로 오해하는 것」이라) ────────
  · 받은 파일은 **서버 sha1 과 대조**한다. 서버가 큰 파일 sha1 을 아직 못 셌으면 셀 때까지 기다린다.
    대조를 못 한 칸은 실행하지 않는다 — 못 본 걸 봤다고 하지 않는다(`pull-build.sh` 와 같은 원칙).
  · 받는 중엔 `.part` 로 두고 다 받은 뒤에만 이름을 바꾼다. 그래서 받다 만 파일이 롬으로 안 뜬다.
  · 서버 sha1 이 덱 것과 다르면 목록에 「새 빌드」로 띄운다.
  · 세이브는 `emu.sh` 와 같은 규칙: 띄우기 전에 서버 정본을 당기고(덱이 더 새것이면 안 덮는다),
    해시 없는 이름으로 모으고(`ss_gameid.fit` · `save_unhash.fit`), 끈 뒤 바뀐 것만 올린다(서버가
    `.bak` 한 세대를 남긴다). 이번 실행에서 만든 스테이트는 `state/` 에 쌓는다(덮지 않는다).
  · 캡처 삭제는 서버가 `.trash/` 로 옮기기만 한다. 덱 빌드 삭제는 그 칸 하나만, 묻고 지운다.
  · 올리기 전 캡처는 `<root>/pending/` 에 남는다 — 망이 끊겨도 다음 실행에 다시 올린다.

── 조작 ─────────────────────────────────────────────────────────────────────
  A 고르기 · B 뒤로 · X 받기/메모 · Y 지우기 · 십자키 이동(상세에선 ←→ 앞뒤 캡처)
  키보드: 화살표 · Enter · Esc · x · y. 메모는 Steam+X 로 화면 키보드를 띄운다.
  게임 안 캡처: mednafen 의 스크린샷 키(F9) — 스팀 입력에서 뒤 버튼 하나를 F9 에 걸어 둔다.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "emu"))

CONFIG = os.path.expanduser("~/.config/edqa/config.json")
DEFAULTS = {
    "server": "",
    "root": "~/edqa",
    "mednafen": "mednafen",  # flatpak 이면 "flatpak run --command=mednafen com.github.AmatCoder.mednaffe"
    "mednafen_home": "~/.mednafen",
}
PLATFORM_LABEL = {
    "ps1": "PS1",
    "ss": "새턴",
    "pce": "PC엔진",
    "sfc": "슈퍼패미컴",
    "md": "메가드라이브",
}
MODULE = {"ps1": "psx", "ss": "ss", "pce": "pce", "sfc": "snes", "md": "md"}
ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
# 띄울 이미지 — 앞에 있을수록 먼저(새턴 두 장짜리는 m3u, CD 는 cue, 롬은 그 자체)
IMAGE_EXTS = (".m3u", ".cue", ".sfc", ".smc", ".md", ".gen", ".bin", ".iso")
MANIFEST = ".edqa.json"


def game_label(game):
    plat, _, ed = game.partition("-ed")
    nums = "·".join(ROMAN.get(x, x) for x in ed.split("+"))
    return (
        f"{PLATFORM_LABEL.get(plat, plat)} 영웅전설 {nums}"  # 「기종 영웅전설 넘버」(마스터 10-30)
    )


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


# ── 덱 패드 → mednafen 버튼(실물 패드 위치 그대로) ──────────────────────────────
# 스팀이 만드는 가상 패드는 mednafen 에 「Microsoft X-Box 360 pad」로 잡힌다(마스터 덱 실측 10-30, 장치 번호
# 아래 DECK_PAD). 리눅스 joydev 번호: 버튼 A0 B1 X2 Y3 LB4 RB5 View6 Start7 · 축 LX0 LY1 LT2 RX3 RY4 RT5
# 십자키 6(좌우)·7(상하). 「-」「+」는 반축(mednafen `drivers/Joystick.cpp:BNToString`).
# 면 버튼은 자리로 맞춘다 — 아래 A · 오른쪽 B · 왼쪽 X · 위 Y.
DECK_PAD = "0x000328de11ff00010008000b00000000"
_DPAD = {
    "up": ("abs_7-", "abs_1-"),
    "down": ("abs_7+", "abs_1+"),
    "left": ("abs_6-", "abs_0-"),
    "right": ("abs_6+", "abs_0+"),
}
PAD_LAYOUT = {
    # PS1 다이아몬드 그대로 — ✕ 아래 · ○ 오른쪽 · □ 왼쪽 · △ 위
    "psx.input.port1.gamepad": {
        **_DPAD,
        "cross": ("button_0",),
        "circle": ("button_1",),
        "square": ("button_2",),
        "triangle": ("button_3",),
        "l1": ("button_4",),
        "r1": ("button_5",),
        "l2": ("abs_2+",),
        "r2": ("abs_5+",),
        "select": ("button_6",),
        "start": ("button_7",),
    },
    # SFC — B 아래 · A 오른쪽 · Y 왼쪽 · X 위(실물과 같은 자리)
    "snes.input.port1.gamepad": {
        **_DPAD,
        "b": ("button_0",),
        "a": ("button_1",),
        "y": ("button_2",),
        "x": ("button_3",),
        "l": ("button_4",),
        "r": ("button_5",),
        "select": ("button_6",),
        "start": ("button_7",),
    },
    # 새턴·MD 6버튼 — 아랫줄 A B C 를 A·B·RB, 윗줄 X Y Z 를 X·Y·LB 에(덱엔 두 줄이 없다)
    "ss.input.port1.gamepad": {
        **_DPAD,
        "a": ("button_0",),
        "b": ("button_1",),
        "c": ("button_5",),
        "x": ("button_2",),
        "y": ("button_3",),
        "z": ("button_4",),
        "ls": ("abs_2+",),
        "rs": ("abs_5+",),
        "start": ("button_7",),
    },
    "md.input.port1.gamepad6": {
        **_DPAD,
        "a": ("button_0",),
        "b": ("button_1",),
        "c": ("button_5",),
        "x": ("button_2",),
        "y": ("button_3",),
        "z": ("button_4",),
        "start": ("button_7",),
        "mode": ("button_6",),
    },
    "md.input.port1.gamepad": {
        **_DPAD,
        "a": ("button_0",),
        "b": ("button_1",),
        "c": ("button_5",),
        "start": ("button_7",),
    },
    # PCE — II 아래 · I 오른쪽(2버튼 패드의 두 버튼 자리), 6버튼 나머지는 X·Y·LB·RB
    "pce.input.port1.gamepad": {
        **_DPAD,
        "ii": ("button_0",),
        "i": ("button_1",),
        "iii": ("button_2",),
        "iv": ("button_3",),
        "v": ("button_4",),
        "vi": ("button_5",),
        "select": ("button_6",),
        "run": ("button_7",),
    },
}


def add_pad(text, pad_id):
    """cfg 의 패드 버튼 줄마다 덱 패드 바인딩을 대안(`||`)으로 더한다 — 키보드 몫과 사람이 물린 것은 그대로.

    ⚠ 줄을 새로 만들지 않는다(mednafen_cfg 와 같은 원칙) — 없는 이름이면 이 mednafen 이 모르는 것이다.
    """
    import re

    for prefix, buttons in PAD_LAYOUT.items():
        for btn, binds in buttons.items():
            name = f"{prefix}.{btn}"
            m = re.search(rf"^{re.escape(name)} (.*)$", text, re.MULTILINE)
            if not m:
                continue
            alts = [x.strip() for x in m.group(1).split("||") if x.strip()]
            for b in binds:
                want = f"joystick {pad_id} {b}"
                if want not in alts:
                    alts.append(want)
            text = text[: m.start()] + f"{name} {' || '.join(alts)}" + text[m.end() :]
    return text


FLATPAK_MEDNAFEN = "flatpak run --command=mednafen com.github.AmatCoder.mednaffe"


def mednafen_cmd(cfg):
    """설정 값 → 실행 명령. 기본값(`mednafen`)이 PATH 에 없으면 Mednaffe 플랫팩 안의 mednafen 을 쓴다
    (덱엔 mednafen 패키지가 없어 Discover 의 Mednaffe 로 깐다 — 마스터 10-30)."""
    cmd = cfg["mednafen"]
    if cmd == "mednafen" and not shutil.which("mednafen") and shutil.which("flatpak"):
        r = subprocess.run(
            ["flatpak", "info", "com.github.AmatCoder.mednaffe"], capture_output=True, check=False
        )
        if r.returncode == 0:
            return FLATPAK_MEDNAFEN
    return cmd


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(CONFIG + ".tmp", CONFIG)


# ── 서버 ────────────────────────────────────────────────────────────────────
class Server:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def url(self, *parts):
        return self.base + "/" + "/".join(urllib.parse.quote(p) for p in parts)

    def get_json(self, *parts):
        with urllib.request.urlopen(self.url(*parts), timeout=30) as r:
            return json.load(r)

    def put(self, data, *parts):
        req = urllib.request.Request(self.url(*parts), data=data, method="PUT")
        with urllib.request.urlopen(req, timeout=60) as r:
            return urllib.parse.unquote(r.headers.get("X-Saved-As") or "")

    def delete(self, *parts):
        req = urllib.request.Request(self.url(*parts), method="DELETE")
        with urllib.request.urlopen(req, timeout=10):
            pass

    def fetch(self, dest, parts, progress=None, mtime=None):
        """`.part` 로 받고 다 받은 뒤에만 이름을 바꾼다. sha1 을 돌려준다."""
        h = hashlib.sha1()
        tmp = dest + ".part"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with urllib.request.urlopen(self.url(*parts), timeout=30) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        os.replace(tmp, dest)
        if mtime:
            os.utime(dest, (mtime, mtime))
        return h.hexdigest()


def sha1_file(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 덱 쪽 빌드 칸 ───────────────────────────────────────────────────────────
class Local:
    def __init__(self, cfg):
        self.root = os.path.expanduser(cfg["root"])
        self.med_home = os.path.expanduser(cfg["mednafen_home"])

    def build_dir(self, game, tag):
        return os.path.join(self.root, "builds", game, tag)

    def manifest(self, game, tag):
        try:
            with open(os.path.join(self.build_dir(game, tag), MANIFEST), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def write_manifest(self, game, tag, files):
        p = os.path.join(self.build_dir(game, tag), MANIFEST)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"files": files, "at": time.time()}, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)

    def tags(self, game):
        d = os.path.join(self.root, "builds", game)
        if not os.path.isdir(d):
            return []
        return sorted(t for t in os.listdir(d) if self.manifest(game, t))

    def images(self, game, tag):
        d = self.build_dir(game, tag)
        names = [f for f in os.listdir(d) if f.lower().endswith(IMAGE_EXTS)]
        for ext in IMAGE_EXTS:
            got = sorted(f for f in names if f.lower().endswith(ext) and "(track" not in f.lower())
            if got:
                return [os.path.join(d, f) for f in got]
        return []

    def pending_dir(self, game, tag):
        return os.path.join(self.root, "pending", game, tag)

    def snap_dir(self, game, tag):
        return os.path.join(self.root, "snaps", game, tag)

    def qa_cache(self, game, tag, n):
        return os.path.join(self.root, "qa-cache", game, tag, n + ".png")

    def sav_dir(self, game):
        return os.path.join(self.med_home, "sav", game)


def build_state(server_build, manifest):
    """목록에 띄우는 상태 — (글, 실행 가능)."""
    if server_build is None:
        return ("덱에만 있음(서버에서 지워짐)", True)
    if manifest is None:
        return ("받기 전", False)
    remote = {f["name"]: f["sha1"] for f in server_build["files"]}
    if any(remote.get(k) and remote[k] != v for k, v in manifest["files"].items()) or any(
        k not in manifest["files"] for k in remote
    ):
        return ("새 빌드 있음", True)
    return ("받음 · 서버와 같음", True)


# ── 화면 ────────────────────────────────────────────────────────────────────
import pygame

W, H = 1280, 800
C_BG = (22, 24, 33)
C_PANEL = (34, 37, 50)
C_TEXT = (230, 232, 240)
C_DIM = (140, 146, 165)
C_ACCENT = (240, 196, 92)
C_SEL = (58, 66, 98)
C_OK = (120, 205, 140)
C_WARN = (240, 140, 110)


def find_font():
    for name in ("notosanscjkkr", "notosanscjk", "notosanscjkkrregular", "nanumgothic"):
        p = pygame.font.match_font(name)
        if p:
            return p
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ko"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        if out and os.path.isfile(out):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return None


class UI:
    def __init__(self, window):
        self.window = window
        self.open()
        path = find_font()
        self.f_big = pygame.font.Font(path, 34)
        self.f = pygame.font.Font(path, 26)
        self.f_small = pygame.font.Font(path, 20)
        self.toast_text, self.toast_until = "", 0

    def open(self):
        pygame.display.init()
        pygame.joystick.init()
        flags = 0 if self.window else pygame.FULLSCREEN
        self.screen = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption("영웅전설 QA")
        self.pads = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]

    def close(self):
        """에뮬을 띄우는 동안은 창과 패드를 놓는다 — 게임 모드가 새 창으로 초점을 넘기게."""
        pygame.joystick.quit()
        pygame.display.quit()

    def toast(self, text, sec=3.0):
        self.toast_text, self.toast_until = text, time.time() + sec

    def text(self, s, pos, font=None, color=C_TEXT):
        img = (font or self.f).render(s, True, color)
        self.screen.blit(img, pos)
        return img.get_width()

    def wrap(self, s, width, font=None):
        font = font or self.f
        lines = []
        for para in s.split("\n"):
            cur = ""
            for ch in para:
                if font.size(cur + ch)[0] > width:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            lines.append(cur)
        return lines

    def frame(self, title, hint):
        self.screen.fill(C_BG)
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, 64))
        self.text(title, (28, 12), self.f_big, C_ACCENT)
        pygame.draw.rect(self.screen, C_PANEL, (0, H - 44, W, 44))
        self.text(hint, (28, H - 38), self.f_small, C_DIM)

    def finish(self):
        if self.toast_text and time.time() < self.toast_until:
            img = self.f.render(self.toast_text, True, C_TEXT)
            r = img.get_rect(center=(W // 2, H - 90))
            pygame.draw.rect(self.screen, (60, 60, 80), r.inflate(40, 20), border_radius=10)
            self.screen.blit(img, r)
        pygame.display.flip()


def actions(events, text_mode=False):
    """패드·키보드 → 동작 이름. 글 입력 중엔 글자 키를 동작으로 안 읽는다."""
    out = []
    for e in events:
        if e.type == pygame.JOYBUTTONDOWN:
            out.append({0: "a", 1: "b", 2: "x", 3: "y", 7: "start"}.get(e.button))
        elif e.type == pygame.JOYHATMOTION:
            x, y = e.value
            out.append(
                {(0, 1): "up", (0, -1): "down", (-1, 0): "left", (1, 0): "right"}.get((x, y))
            )
        elif e.type == pygame.JOYAXISMOTION and e.axis in (0, 1) and abs(e.value) > 0.7:
            if e.axis == 1:
                out.append("down" if e.value > 0 else "up")
            else:
                out.append("right" if e.value > 0 else "left")
        elif e.type == pygame.KEYDOWN:
            k = e.key
            m = {
                pygame.K_UP: "up",
                pygame.K_DOWN: "down",
                pygame.K_LEFT: "left",
                pygame.K_RIGHT: "right",
                pygame.K_RETURN: "a",
                pygame.K_KP_ENTER: "a",
                pygame.K_ESCAPE: "b",
            }
            if not text_mode:
                m.update({pygame.K_BACKSPACE: "b", pygame.K_x: "x", pygame.K_y: "y"})
                m.update({pygame.K_DELETE: "y", pygame.K_q: "quit"})
            out.append(m.get(k))
    return [a for a in out if a]


class ListView:
    """줄 목록 — 머리줄(고를 수 없음)과 항목. rows = [(글, 곁글, 값 | None)]."""

    def __init__(self, rows, top=84, row_h=52):
        self.rows, self.top, self.row_h = rows, top, row_h
        self.sel = next((i for i, r in enumerate(rows) if r[2] is not None), 0)
        self.scroll = 0

    def value(self):
        return self.rows[self.sel][2] if self.rows else None

    def update(self, rows):
        """줄을 갈아도 고른 항목·스크롤을 지킨다(목록은 매 화면 다시 센다)."""
        cur = self.value()
        self.rows = rows
        for i, r in enumerate(rows):
            if r[2] is not None and r[2] == cur:
                self.sel = i
                return
        self.sel = next((i for i, r in enumerate(rows) if r[2] is not None), 0)

    def move(self, d):
        i = self.sel
        while 0 <= i + d < len(self.rows):
            i += d
            if self.rows[i][2] is not None:
                self.sel = i
                return

    def draw(self, ui):
        visible = (H - 44 - self.top) // self.row_h
        self.scroll = min(self.scroll, self.sel)
        if self.sel >= self.scroll + visible:
            self.scroll = self.sel - visible + 1
        if self.scroll > 0 and self.rows[self.scroll - 1][2] is None:
            self.scroll -= 1  # 머리줄을 같이 보인다
        for i, (label, side, val) in enumerate(self.rows[self.scroll : self.scroll + visible]):
            y = self.top + i * self.row_h
            idx = self.scroll + i
            if val is None:
                ui.text(label, (28, y + 14), ui.f_small, C_ACCENT)
                continue
            if idx == self.sel:
                pygame.draw.rect(
                    ui.screen, C_SEL, (16, y + 2, W - 32, self.row_h - 4), border_radius=8
                )
            ui.text(label, (40, y + 9))
            if side:
                color = C_WARN if "새 빌드" in side or "실패" in side else C_DIM
                img = ui.f_small.render(side, True, color)
                ui.screen.blit(img, (W - 40 - img.get_width(), y + 14))


# ── 앱 ──────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, cfg, window):
        self.cfg = cfg
        self.ui = UI(window)
        self.local = Local(cfg)
        self.stack = []
        self.server = Server(cfg["server"]) if cfg["server"] else None
        self.builds = None  # /api/builds
        self.busy = None  # (글, 진행 0~1 | None) — 뒤 일이 도는 동안 화면을 막는다
        self.after = []  # 일 끝나고 주 루프에서 부를 것

    # 뒤 일 — 받기·올리기는 오래 걸려 화면이 멈추지 않게 실로 돌린다
    def run_bg(self, label, work, done=None):
        self.busy = (label, None)

        def go():
            try:
                res, err = work(lambda d, t: self._progress(label, d, t)), None
            except Exception as e:  # noqa: BLE001 — 망·디스크 무엇이든 화면에 알린다
                res, err = None, e
            self.after.append(lambda: self._bg_done(res, err, done))

        threading.Thread(target=go, daemon=True).start()

    def _progress(self, label, d, t):
        self.busy = (label, d / t if t else None)

    def _bg_done(self, res, err, done):
        self.busy = None
        if err:
            self.ui.toast(f"실패: {err}", 6)
        elif done:
            done(res)

    def refresh(self, then=None):
        def work(_p):
            return self.server.get_json("api", "builds")

        def done(res):
            self.builds = res
            if then:
                then()

        self.run_bg("서버 목록 읽는 중", work, done)

    def server_build(self, game, tag):
        for g in (self.builds or {}).get("games", []):
            if g["game"] == game:
                return next((b for b in g["builds"] if b["tag"] == tag), None)
        return None

    def push(self, scr):
        self.stack.append(scr)

    def pop(self):
        self.stack.pop()
        if not self.stack:
            raise SystemExit

    def start(self):
        if not self.server:
            self.push(TextInput(self, "서버 주소", "http://192.168.45.104:8800", self._set_server))
        else:
            self.push(Games(self))
            self.refresh()

    def step(self, events):
        """한 프레임 — 끝내야 하면 False."""
        if any(e.type == pygame.QUIT for e in events):
            return False
        while self.after:
            self.after.pop(0)()
        scr = self.stack[-1]
        if not self.busy and hasattr(scr, "feed"):
            scr.feed(events)
        if self.busy:
            self.draw_busy()
        else:
            for a in actions(events, getattr(scr, "text_mode", False)):
                if a == "quit":
                    return False
                scr.handle(a, events)
                if self.stack and self.stack[-1] is not scr:
                    break
            if self.stack:
                self.stack[-1].draw()
        self.ui.finish()
        return True

    def loop(self):
        clock = pygame.time.Clock()
        self.start()
        while self.step(pygame.event.get()):
            clock.tick(30)

    def _set_server(self, url):
        self.cfg["server"] = url.strip()
        save_config(self.cfg)
        self.server = Server(self.cfg["server"])
        self.stack = [Games(self)]
        self.refresh()

    def draw_busy(self):
        label, frac = self.busy
        self.ui.screen.fill(C_BG)
        self.ui.text(label, (80, H // 2 - 60), self.ui.f_big)
        pygame.draw.rect(self.ui.screen, C_PANEL, (80, H // 2, W - 160, 28), border_radius=8)
        if frac is not None:
            pygame.draw.rect(
                self.ui.screen, C_ACCENT, (80, H // 2, int((W - 160) * frac), 28), border_radius=8
            )
            self.ui.text(f"{frac * 100:.0f}%", (80, H // 2 + 40), self.ui.f_small, C_DIM)

    # ── 받기 ────────────────────────────────────────────────────────────────
    def download(self, game, tag, then=None):
        """빌드 칸을 통째로 받는다 — sha1 이 같은 파일은 건너뛴다. 대조를 못 하면 실패."""

        def work(progress):
            files = {}
            deadline = time.time() + 300
            while True:  # 큰 파일 sha1 은 서버가 뒤에서 센다 — 다 셀 때까지 기다린다
                sb = self.server.get_json("api", "builds")
                b = next(
                    (
                        x
                        for g in sb["games"]
                        if g["game"] == game
                        for x in g["builds"]
                        if x["tag"] == tag
                    ),
                    None,
                )
                if b is None:
                    raise RuntimeError("서버에 그 빌드가 없다")
                if all(f["sha1"] for f in b["files"]) or time.time() > deadline:
                    break
                self.busy = ("서버가 지문을 세는 중", None)
                time.sleep(3)
            self.builds = sb
            d = self.local.build_dir(game, tag)
            old = (self.local.manifest(game, tag) or {}).get("files", {})
            total = sum(f["size"] for f in b["files"]) or 1
            base = 0
            for f in b["files"]:
                dest = os.path.join(d, f["name"])
                if not f["sha1"]:
                    raise RuntimeError(
                        f"서버 sha1 을 못 받았다: {f['name']} — 대조 없이 쓰지 않는다"
                    )
                if old.get(f["name"]) == f["sha1"] and os.path.isfile(dest):
                    files[f["name"]] = f["sha1"]
                    base += f["size"]
                    continue
                label = f"받는 중 — {f['name']}"
                got = self.server.fetch(
                    dest,
                    (game, tag, f["name"]),
                    lambda dn, _t, label=label, base=base: self._progress(label, base + dn, total),
                    f["mtime"],
                )
                if got != f["sha1"]:
                    os.remove(dest)
                    raise RuntimeError(f"전송 중 손상: {f['name']} — 다시 받으세요")
                files[f["name"]] = got
                base += f["size"]
            for n in os.listdir(d):  # 서버에서 빠진 파일은 덱에서도 뺀다(낡은 변종 오해 방지)
                if n not in files and n != MANIFEST and not n.startswith("."):
                    os.remove(os.path.join(d, n))
            self.local.write_manifest(game, tag, files)
            return True

        self.run_bg("받는 중", work, lambda _r: then() if then else self.ui.toast("받았습니다"))

    # ── 실행 ────────────────────────────────────────────────────────────────
    def launch(self, game, tag, image):
        plat = game.split("-", 1)[0]
        sav = self.local.sav_dir(game)
        os.makedirs(sav, exist_ok=True)
        snaps = self.local.snap_dir(game, tag)
        os.makedirs(snaps, exist_ok=True)
        try:
            self._pull_saves(game, sav)
        except (OSError, urllib.error.URLError) as e:
            self.ui.toast(f"세이브를 못 당겼다 — 덱 세이브로 갑니다 ({e})", 6)
        try:
            if plat == "ss":
                import ss_gameid

                ss_gameid.fit(sav, image)
            else:
                import save_unhash

                save_unhash.fit(sav, image)
        except Exception as e:  # noqa: BLE001
            self.ui.toast(f"세이브 이름 맞추기 실패: {e}", 6)
        self._apply_keys()
        mark = time.time() - 1
        cmd = mednafen_cmd(self.cfg).split() + [
            "-force_module",
            MODULE[plat],
            "-filesys.path_sav",
            f"sav/{game}",
            "-filesys.path_snap",
            snaps,
            image,
        ]
        self.ui.close()
        try:
            subprocess.run(cmd, check=False)
        except OSError as e:
            self.ui.open()
            self.ui.toast(f"mednafen 을 못 띄웠다: {e}", 8)
            return
        self.ui.open()
        self._after_play(game, tag, image, sav, snaps, mark)

    def _apply_keys(self):
        """맥 emu.sh 와 같은 키 정본(`mednafen_keys`)을 띄우기 직전에 맞춘다 — 빨리감기·퀵세이브·캡처 등.

        패드 바인딩(joystick)은 지킨다(`mednafen_cfg.keep_pads`) — 게임 안(Alt+Shift+1)에서 기종마다
        한 번 물린 패드가 다음 실행에 안 지워진다. 패치 빌드에만 있는 명령(창 크기·소리 끄기·연타)은
        이 mednafen 이 모르는 이름이라 cfg 에 없어 건너뛴다(만들지 않는다).
        """
        try:
            import mednafen_cfg
            import mednafen_keys

            os.environ["MEDNAFEN_HOME"] = self.local.med_home
            p = mednafen_cfg.cfg_path()
            if p.exists():
                # 스톡 mednafen 이 모르는 패치 명령(창 크기 등)마다 경고를 찍어 시끄럽다 — 덱에선 삼킨다
                with contextlib.redirect_stdout(io.StringIO()):
                    text, changed, _same, _missing = mednafen_cfg.apply(
                        p.read_text(), mednafen_keys.settings(), pads=True
                    )
                text2 = add_pad(text, self.cfg.get("pad_id") or DECK_PAD)
                # 플랫팩 mednafen 은 기본 출력(ALSA)을 못 잡아 소리가 안 났다(마스터 덱 실측 10-30:
                # sound 1 · driver default 인데 무음) — SDL 출력으로 맞춘다. 설정에 적어 두면 cfg 값을 따른다.
                drv = self.cfg.get("sound_driver", "sdl")
                text2 = re.sub(
                    r"^sound\.driver .*$", f"sound.driver {drv}", text2, flags=re.MULTILINE
                )
                if changed or text2 != text:
                    p.write_text(text2)
        except Exception as e:  # noqa: BLE001 — 키를 못 맞춰도 게임은 띄운다
            self.ui.toast(f"키 배치를 못 맞췄다: {e}", 6)

    def _pull_saves(self, game, sav):
        """서버 정본 → 덱. 덱 것이 더 새것이면 안 덮는다(안 올린 진행분 보호 — sync-saves.sh 와 같다)."""
        for f in self.server.get_json("api", "saves", game)["files"]:
            p = os.path.join(sav, f["name"])
            if os.path.isfile(p) and os.path.getmtime(p) >= f["mtime"]:
                continue
            if os.path.isfile(p):
                shutil.copy2(p, p + ".bak")
            self.server.fetch(p, (game, "saves", f["name"]), mtime=f["mtime"])

    def _after_play(self, game, tag, image, sav, snaps, mark):
        stem = os.path.splitext(os.path.basename(image))[0]
        pend = self.local.pending_dir(game, tag)
        os.makedirs(pend, exist_ok=True)
        for n in sorted(os.listdir(snaps)):  # 캡처는 먼저 덱 안에서 「올릴 칸」으로 옮긴다
            if n.lower().endswith(".png"):
                shutil.move(os.path.join(snaps, n), os.path.join(pend, n))

        def work(progress):
            saves = [
                n
                for n in os.listdir(sav)
                if os.path.isfile(os.path.join(sav, n))
                and os.path.getmtime(os.path.join(sav, n)) > mark
                and not n.endswith((".bak", ".tmp"))
            ]
            for n in saves:
                with open(os.path.join(sav, n), "rb") as f:
                    data = f.read()
                if len(set(data)) > 1:
                    self.server.put(data, "api", "save", game, n)
            mcs = os.path.join(self.local.med_home, "mcs")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            if os.path.isdir(mcs):
                for n in os.listdir(mcs):
                    p = os.path.join(mcs, n)
                    if (
                        n.startswith(stem + ".")
                        and n[-4:-1] == ".mc"
                        and os.path.getmtime(p) > mark
                    ):
                        with open(p, "rb") as f:
                            self.server.put(
                                f.read(), "api", "save", game, "state", f"{n}.{stamp}.mednafen"
                            )
            return self.upload_pending(game, tag, progress)

        def done(new):
            if new:
                self.push(
                    Detail(
                        self, game, [(tag, n, "") for n in new], 0, "이번 캡처 — 메모를 붙이세요"
                    )
                )
            else:
                self.ui.toast("세이브를 올렸습니다(새 캡처 없음)")

        self.run_bg("세이브·캡처 올리는 중", work, done)

    def upload_pending(self, game, tag, progress=None):
        pend = self.local.pending_dir(game, tag)
        names = (
            sorted(n for n in os.listdir(pend) if n.lower().endswith(".png"))
            if os.path.isdir(pend)
            else []
        )
        new = []
        for i, n in enumerate(names):
            p = os.path.join(pend, n)
            with open(p, "rb") as f:
                data = f.read()
            num = self.server.put(data, "api", "qa", game, tag, "new.png")
            cache = self.local.qa_cache(game, tag, num)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            shutil.move(p, cache)
            new.append(num)
            if progress:
                progress(i + 1, len(names))
        return new

    def pending_games(self):
        base = os.path.join(self.local.root, "pending")
        out = []
        if os.path.isdir(base):
            for g in os.listdir(base):
                for t in os.listdir(os.path.join(base, g)):
                    if any(
                        n.lower().endswith(".png") for n in os.listdir(os.path.join(base, g, t))
                    ):
                        out.append((g, t))
        return out


class Screen:
    text_mode = False

    def __init__(self, app):
        self.app, self.ui = app, app.ui

    def handle(self, a, events):
        pass

    def draw(self):
        pass


class Covers:
    """카드 표지 — 서버 `/api/cover/<게임>` 을 `<root>/covers/` 에 한 번 받아 둔다(화면을 막지 않게 실로)."""

    def __init__(self, app):
        self.app, self.img, self.busy, self.fails = app, {}, set(), {}

    def get(self, game):
        if game in self.img:
            return self.img[game]
        p = os.path.join(self.app.local.root, "covers", game + ".png")
        if os.path.isfile(p):
            try:
                self.img[game] = pygame.image.load(p)
            except pygame.error:
                self.img[game] = None
            return self.img[game]
        if game not in self.busy and self.app.server:
            self.busy.add(game)

            def go():
                try:
                    self.app.server.fetch(p, ("api", "cover", game))
                except urllib.error.HTTPError:
                    self.img[game] = None  # 표지가 없는 게임(404) — 글자 카드로 둔다
                except OSError:
                    # 망이 잠깐 끊긴 것 — 세 번까지 다시 받는다(한 번 실패로 세션 내내 빈 카드가 됐다)
                    self.fails[game] = self.fails.get(game, 0) + 1
                    if self.fails[game] >= 3:
                        self.img[game] = None
                finally:
                    self.busy.discard(game)

            threading.Thread(target=go, daemon=True).start()
        return None


class Games(Screen):
    """게임 카드 격자 — 기종 순(마스터 10-30 「그리드 카드 · 썸네일은 커버아트」)."""

    COLS, CARD_W, CARD_H, GAP, TOP = 4, 296, 300, 16, 80

    def games(self):
        games = (self.app.builds or {}).get("games", [])
        names = {g["game"] for g in games}
        root = os.path.join(self.app.local.root, "builds")
        if os.path.isdir(root):
            names |= {g for g in os.listdir(root) if self.app.local.tags(g)}
        plats = (self.app.builds or {}).get("platforms", list(PLATFORM_LABEL))

        def key(g):
            p = g.split("-", 1)[0]
            return (plats.index(p) if p in plats else len(plats), g)

        out = []
        for g in sorted(names, key=key):
            srv = next((len(x["builds"]) for x in games if x["game"] == g), 0)
            out.append((g, f"서버 {srv} · 덱 {len(self.app.local.tags(g))}"))
        return out

    def __init__(self, app):
        super().__init__(app)
        self.sel, self.scroll, self.cur = 0, 0, None
        self.covers = Covers(app)
        self.scaled = {}

    def handle(self, a, events):
        items = self.games()
        n = len(items)
        if a in ("left", "right", "up", "down") and n:
            d = {"left": -1, "right": 1, "up": -self.COLS, "down": self.COLS}[a]
            self.sel = max(0, min(n - 1, self.sel + d))
            self.cur = items[self.sel][0]
        elif a == "a" and n:
            self.app.push(GameMenu(self.app, items[self.sel][0]))
        elif a == "x":
            self.app.refresh()
        elif a == "y":
            pend = self.app.pending_games()
            if pend:

                def work(p):
                    return sum(len(self.app.upload_pending(g, t, p)) for g, t in pend)

                self.app.run_bg(
                    "못 올린 캡처 올리는 중", work, lambda n: self.ui.toast(f"{n}장 올렸습니다")
                )
        elif a == "b":
            self.app.pop()

    def thumb(self, game, box):
        img = self.covers.get(game)
        if img is None:
            return None
        key = (game, box)
        if key not in self.scaled:
            iw, ih = img.get_size()
            k = min(box[0] / iw, box[1] / ih)
            self.scaled[key] = pygame.transform.smoothscale(img, (int(iw * k), int(ih * k)))
        return self.scaled[key]

    def draw(self):
        items = self.games()
        if self.cur is not None and items:  # 목록이 바뀌어도 고른 게임을 지킨다
            names = [g for g, _ in items]
            if self.cur in names:
                self.sel = names.index(self.cur)
        self.sel = min(self.sel, max(0, len(items) - 1))
        self.cur = items[self.sel][0] if items else None
        pend = len(self.app.pending_games())
        hint = "A 고르기 · 십자키 이동 · X 새로 고침 · B 끝내기"
        if pend:
            hint += f" · Y 못 올린 캡처 올리기({pend}칸)"
        self.ui.frame("영웅전설 QA", hint)
        if not items:
            self.ui.text("서버 목록이 없습니다 — X 로 새로 고침", (40, 120), color=C_DIM)
            return
        rows_vis = max(1, (H - 44 - self.TOP) // (self.CARD_H + self.GAP))
        row = self.sel // self.COLS
        self.scroll = min(self.scroll, row)
        if row >= self.scroll + rows_vis:
            self.scroll = row - rows_vis + 1
        left = (W - (self.COLS * self.CARD_W + (self.COLS - 1) * self.GAP)) // 2
        for i, (g, side) in enumerate(items):
            r, c = divmod(i, self.COLS)
            if not self.scroll <= r < self.scroll + rows_vis:
                continue
            x = left + c * (self.CARD_W + self.GAP)
            y = self.TOP + (r - self.scroll) * (self.CARD_H + self.GAP)
            card = pygame.Rect(x, y, self.CARD_W, self.CARD_H)
            pygame.draw.rect(self.ui.screen, C_PANEL, card, border_radius=12)
            if i == self.sel:
                pygame.draw.rect(self.ui.screen, C_ACCENT, card, width=4, border_radius=12)
            box = (self.CARD_W - 24, self.CARD_H - 84)
            t = self.thumb(g, box)
            if t:
                self.ui.screen.blit(
                    t, t.get_rect(center=(x + self.CARD_W // 2, y + 12 + box[1] // 2))
                )
            else:
                plat = PLATFORM_LABEL.get(g.split("-", 1)[0], g)
                img = self.ui.f_small.render(plat, True, C_DIM)
                self.ui.screen.blit(
                    img, img.get_rect(center=(x + self.CARD_W // 2, y + 12 + box[1] // 2))
                )
            title = game_label(g)
            while self.ui.f_small.size(title)[0] > self.CARD_W - 20 and len(title) > 4:
                title = title[:-2] + "…"
            self.ui.text(title, (x + 12, y + self.CARD_H - 66), self.ui.f_small, C_TEXT)
            self.ui.text(side, (x + 12, y + self.CARD_H - 38), self.ui.f_small, C_DIM)
        more = (len(items) - 1) // self.COLS + 1 - (self.scroll + rows_vis)
        if more > 0:
            self.ui.text(f"▼ {more}줄 더", (W - 140, H - 74), self.ui.f_small, C_DIM)


class GameMenu(Screen):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.view = ListView(
            [("빌드 — 고르고 실행", "", "builds"), ("캡처 목록 — 메모·삭제", "", "qa")]
        )

    def handle(self, a, events):
        if a in ("up", "down"):
            self.view.move(-1 if a == "up" else 1)
        elif a == "a":
            scr = (
                Builds(self.app, self.game)
                if self.view.value() == "builds"
                else QAList(self.app, self.game)
            )
            self.app.push(scr)
        elif a == "b":
            self.app.pop()

    def draw(self):
        self.ui.frame(game_label(self.game), "A 고르기 · B 뒤로")
        self.view.draw(self.ui)


class Builds(Screen):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.view = ListView(self.rows())

    def rows(self):
        tags = set(self.app.local.tags(self.game))
        g = next(
            (x for x in (self.app.builds or {}).get("games", []) if x["game"] == self.game), None
        )
        if g:
            tags |= {b["tag"] for b in g["builds"]}
        rows = []
        for t in sorted(tags):
            sb = self.app.server_build(self.game, t)
            state, _ = build_state(sb, self.app.local.manifest(self.game, t))
            when = ""
            if sb and sb["files"]:
                when = time.strftime(
                    "%m-%d %H:%M", time.localtime(max(f["mtime"] for f in sb["files"]))
                )
            rows.append((t, f"{when}  {state}", t))
        return rows

    def handle(self, a, events):
        tag = self.view.value()
        if a in ("up", "down"):
            self.view.move(-1 if a == "up" else 1)
        elif a == "b":
            self.app.pop()
        elif not tag:
            return
        elif a == "a":
            sb = self.app.server_build(self.game, tag)
            state, ok = build_state(sb, self.app.local.manifest(self.game, tag))
            if not ok:
                self.app.download(self.game, tag, lambda: self.run(tag))
            elif "새 빌드" in state:
                self.app.push(
                    Confirm(
                        self.app,
                        "서버에 새 빌드가 있습니다. 받고 실행할까요?",
                        lambda: self.app.download(self.game, tag, lambda: self.run(tag)),
                        "X 는 덱에 있는 옛 빌드로 실행 · B 는 취소",
                        on_x=lambda: self.run(tag),
                    )
                )
            else:
                self.run(tag)
        elif a == "x" and self.app.server_build(self.game, tag):
            self.app.download(self.game, tag)
        elif a == "y" and self.app.local.manifest(self.game, tag):
            d = self.app.local.build_dir(self.game, tag)

            def rm():
                shutil.rmtree(d)
                self.ui.toast("덱에서 지웠습니다(세이브·캡처는 그대로)")

            self.app.push(
                Confirm(
                    self.app,
                    f"덱에서 이 빌드를 지울까요?  {tag}",
                    rm,
                    "세이브와 캡처는 지우지 않습니다.",
                )
            )

    def run(self, tag):
        imgs = self.app.local.images(self.game, tag)
        if not imgs:
            self.ui.toast("띄울 이미지를 못 찾았습니다", 6)
        elif len(imgs) == 1:
            self.app.launch(self.game, tag, imgs[0])
        else:
            self.app.push(PickImage(self.app, self.game, tag, imgs))

    def draw(self):
        self.view.update(self.rows())
        self.ui.frame(
            f"{game_label(self.game)} — 빌드",
            "A 실행(없으면 받기) · X 다시 받기 · Y 덱에서 지우기 · B 뒤로",
        )
        if not self.view.rows:
            self.ui.text("빌드가 없습니다", (40, 120), color=C_DIM)
        self.view.draw(self.ui)


class PickImage(Screen):
    def __init__(self, app, game, tag, imgs):
        super().__init__(app)
        self.game, self.tag = game, tag
        self.view = ListView([(os.path.basename(p), "", p) for p in imgs])

    def handle(self, a, events):
        if a in ("up", "down"):
            self.view.move(-1 if a == "up" else 1)
        elif a == "a":
            self.app.pop()
            self.app.launch(self.game, self.tag, self.view.value())
        elif a == "b":
            self.app.pop()

    def draw(self):
        self.ui.frame("이미지 고르기", "A 실행 · B 뒤로")
        self.view.draw(self.ui)


class QAList(Screen):
    def __init__(self, app, game):
        super().__init__(app)
        self.game = game
        self.data = None
        self.view = ListView([])
        self.load()

    def load(self):
        def done(res):
            self.data = res
            rows = []
            for t in res["tags"]:
                rows.append((t["tag"], f"{len(t['items'])}장", None))
                for it in t["items"]:
                    memo = it["memo"].strip().split("\n")[0] or "(메모 없음)"
                    rows.append((f"{it['n']}  {memo}", "", (t["tag"], it["n"], it["memo"])))
            self.view = ListView(rows)

        self.app.run_bg(
            "캡처 목록 읽는 중", lambda _p: self.app.server.get_json("api", "qa", self.game), done
        )

    def items(self):
        return [r[2] for r in self.view.rows if r[2] is not None]

    def handle(self, a, events):
        if a in ("up", "down"):
            self.view.move(-1 if a == "up" else 1)
        elif a == "a" and self.view.value():
            items = self.items()
            self.app.push(
                Detail(
                    self.app, self.game, items, items.index(self.view.value()), on_close=self.load
                )
            )
        elif a == "x":
            self.load()
        elif a == "b":
            self.app.pop()

    def draw(self):
        self.ui.frame(f"{game_label(self.game)} — 캡처", "A 상세 · X 새로 고침 · B 뒤로")
        if self.data is not None and not self.items():
            self.ui.text("캡처가 없습니다", (40, 120), color=C_DIM)
        self.view.draw(self.ui)


class Detail(Screen):
    """캡처 하나 — 그림 + 메모. ←→ 앞뒤, X 메모, Y 지우기."""

    def __init__(self, app, game, items, i, title=None, on_close=None):
        super().__init__(app)
        self.game, self.items, self.i = game, list(items), i
        self.title, self.on_close = title, on_close
        self.img = None
        self.load_img()

    def cur(self):
        return self.items[self.i]

    def load_img(self):
        tag, n, _m = self.cur()
        p = self.app.local.qa_cache(self.game, tag, n)
        self.img = None
        if os.path.isfile(p):
            self.img = pygame.image.load(p)
            return

        def done(_r):
            if self.items and self.cur()[:2] == (tag, n):
                self.img = pygame.image.load(p)

        self.app.run_bg(
            "그림 받는 중",
            lambda _p: self.app.server.fetch(p, (self.game, "qa", tag, n + ".png")),
            done,
        )

    def close(self):
        self.app.pop()
        if self.on_close:
            self.on_close()

    def handle(self, a, events):
        if not self.items:
            if a == "b":
                self.close()
            return
        tag, n, memo = self.cur()
        if a in ("left", "right", "up", "down"):
            d = -1 if a in ("left", "up") else 1
            if 0 <= self.i + d < len(self.items):
                self.i += d
                self.load_img()
        elif a in ("x", "a"):

            def save(text):
                self.app.run_bg(
                    "메모 올리는 중",
                    lambda _p: self.app.server.put(
                        text.encode("utf-8"), "api", "qa", self.game, tag, n + ".txt"
                    ),
                    lambda _r: self._set_memo(text),
                )

            self.app.push(TextInput(self.app, f"메모 — {tag} {n}", memo.strip(), save))
        elif a == "y":

            def rm():
                def done(_r):
                    del self.items[self.i]
                    self.i = max(0, min(self.i, len(self.items) - 1))
                    self.ui.toast("지웠습니다(서버 휴지통으로)")
                    if self.items:
                        self.load_img()

                self.app.run_bg(
                    "지우는 중",
                    lambda _p: self.app.server.delete("api", "qa", self.game, tag, n),
                    done,
                )

            self.app.push(
                Confirm(
                    self.app, f"이 캡처를 지울까요?  {tag} {n}", rm, "서버 휴지통으로 옮깁니다."
                )
            )
        elif a == "b":
            self.close()

    def _set_memo(self, text):
        tag, n, _m = self.cur()
        self.items[self.i] = (tag, n, text)
        self.ui.toast("메모를 저장했습니다")

    def draw(self):
        title = self.title or f"{game_label(self.game)} — 캡처 상세"
        self.ui.frame(title, "A/X 메모 · Y 지우기 · ←→ 앞뒤 · B 뒤로")
        if not self.items:
            self.ui.text("남은 캡처가 없습니다", (40, 120), color=C_DIM)
            return
        tag, n, memo = self.cur()
        self.ui.text(
            f"{tag}  #{n}   ({self.i + 1}/{len(self.items)})", (28, 76), self.ui.f_small, C_DIM
        )
        box = pygame.Rect(28, 108, W - 56, 480)
        if self.img:
            iw, ih = self.img.get_size()
            s = min(box.w / iw, box.h / ih)
            img = pygame.transform.smoothscale(self.img, (int(iw * s), int(ih * s)))
            self.ui.screen.blit(img, img.get_rect(center=box.center))
        y = 600
        for line in self.ui.wrap(memo.strip() or "(메모 없음 — A 로 쓰기)", W - 80)[:4]:
            self.ui.text(line, (40, y), color=C_TEXT if memo.strip() else C_DIM)
            y += 34


class Confirm(Screen):
    def __init__(self, app, msg, on_yes, note="", on_x=None):
        super().__init__(app)
        self.msg, self.on_yes, self.note, self.on_x = msg, on_yes, note, on_x

    def handle(self, a, events):
        if a == "a":
            self.app.pop()
            self.on_yes()
        elif a == "x" and self.on_x:
            self.app.pop()
            self.on_x()
        elif a == "b":
            self.app.pop()

    def draw(self):
        self.ui.frame("확인", "A 예 · B 아니요" + (" · X 다른 길" if self.on_x else ""))
        self.ui.text(self.msg, (60, H // 2 - 60), self.ui.f_big)
        if self.note:
            self.ui.text(self.note, (60, H // 2 + 4), color=C_DIM)


class TextInput(Screen):
    """글 입력 — 스팀 화면 키보드(Steam+X)든 실제 키보드든 SDL 글 입력으로 받는다."""

    text_mode = True

    def __init__(self, app, title, initial, on_done):
        super().__init__(app)
        self.title, self.value, self.on_done = title, initial, on_done
        self.compose = ""
        pygame.key.start_text_input()

    def handle(self, a, events):
        if a == "a":
            pygame.key.stop_text_input()
            # 🔴 pop() 이 아니라 직접 뺀다 — 첫 실행의 서버 주소 칸은 스택에 혼자라 pop() 이 「빈 스택 =
            #   끝내기」로 앱을 닫았고, 저장(on_done)이 불리지도 않았다(마스터 덱 실측 10-30).
            self.app.stack.pop()
            self.on_done(self.value)
            if not self.app.stack:
                raise SystemExit
        elif a == "b":
            pygame.key.stop_text_input()
            self.app.pop()

    def feed(self, events):
        for e in events:
            if e.type == pygame.TEXTINPUT:
                self.value += e.text
                self.compose = ""
            elif e.type == pygame.TEXTEDITING:
                self.compose = e.text
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_BACKSPACE and not self.compose:
                self.value = self.value[:-1]

    def draw(self):
        self.ui.frame(self.title, "Steam+X 화면 키보드 · Enter/A 저장 · Esc/B 취소")
        pygame.draw.rect(self.ui.screen, C_PANEL, (28, 100, W - 56, 400), border_radius=10)
        y = 120
        for line in self.ui.wrap(self.value + self.compose + "▏", W - 100)[-10:]:
            self.ui.text(line, (48, y))
            y += 36


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", action="store_true", help="전체 화면 대신 창으로")
    ap.add_argument("--server", help="서버 주소를 이번에만 바꾼다(설정에도 적는다)")
    a = ap.parse_args()
    cfg = load_config()
    if a.server:
        cfg["server"] = a.server
        save_config(cfg)
    pygame.init()
    App(cfg, a.window).loop()
    pygame.quit()


if __name__ == "__main__":
    main()
