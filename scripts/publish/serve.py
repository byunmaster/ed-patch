"""파일서버 — 빌드 칸을 **올리지 않고 그 자리에서** 보여 준다(폰 QA 용).

    python3 scripts/publish/serve.py              # 0.0.0.0:8800
    python3 scripts/publish/serve.py --port 8801

🔴 **왜 새로 짰나**(마스터 2026-09-27). 종전엔 `python3 -m http.server` 가 `.local/cache/publish/`
를 내보내고, 세션이 빌드마다 그 칸으로 **손으로 사본을 떠 올렸다.** 한 번만 빠져도 폰에서 옛
롬이 뜬다 — 실제로 md 는 하루에 롬을 네 번 굽는 사이 게시를 안 돌려 세이브·롬이 옛것에 멈춰
있었다. `pull-build.sh` 처럼 **빌드 칸을 직접 찾아** 보여 주면 올리는 일 자체가 없어진다.
사본을 만들지 않으니 「사본이 낡은 채로 정상으로 오해되는」 이 레포의 단골 사고도 없다.

가상 배치(index.html · run.html 은 그대로 쓴다 — 목록 HTML 꼴이 http.server 와 같다):

    /                      scripts/publish/index.html
    /run.html              scripts/publish/run.html
    /<게임>/<꼬리표>/       games/<게임>/work/build/<꼬리표>/   ← 워크트리가 메인 트리를 이긴다
                           + 브라우저 실행용 `<롬이름>.srm` (세이브 정본을 가리킨다, 아래)
    /<게임>/saves/         ~/save/<게임>/  (세이브 정본 — emu.sh 와 같은 자리 · `state/` = 보낸 스테이트)
    /<게임>/original/      originals/*/<게임>/  (원본 대조용, 읽기만)
    /<게임>/<그 밖>/        .local/cache/publish/<게임>/<그 밖>/  (확인 페이지 같은 손으로 만든 것)

⚠ **꼬리표가 겹치면 워크트리가 이긴다** — `pull-build.sh` 와 같은 규칙(지금 굴리는 쪽이 그것).
⚠ **`*.failed` 가 든 칸은 안 보인다** — 실패한 빌드는 산출물을 무효화한다(루트 CLAUDE.md).
⚠ **세이브 짝**: 롬 칸 목록에 `<롬이름>.srm` 을 가상으로 끼운다. 가리키는 곳은 `~/save/<게임>/`
   의 해시 없는 `<롬이름>.sav|.srm` 이 있으면 그것, 없으면 해시 붙은 것 중 비어 있지 않은 제일
   새것이다 — `scripts/emu/save_unhash.py` 와 같은 규칙이라 맥의 emu.sh 와 폰이 같은 세이브를 본다.

── 스팀덱 QA 앱용 API(`scripts/deck/edqa.py`, 마스터 2026-10-30) ─────────────────────────
    GET    /api/builds                     게임별 빌드 칸과 파일(크기·시각·sha1) — 기종 순으로
    GET    /api/saves/<게임>               세이브 정본 칸의 파일(이름·크기·시각)
    PUT    /api/save/<게임>/<파일>         세이브 정본에 쓴다(`.bak` 한 세대 · 빈 세이브 거절)
    PUT    /api/save/<게임>/state/<파일>   스테이트를 쌓는다(덮지 않는다)
    GET    /api/qa/<게임>                  빌드별 QA 캡처와 메모
    GET    /api/cover/<게임>               카드 표지 — 배포 페이지와 같은 상자 그림(site.json `art`)
    PUT    /api/qa/<게임>/<꼬리표>/new.png  캡처를 다음 번호로 받는다(X-Saved-As: NNN)
    PUT    /api/qa/<게임>/<꼬리표>/NNN.txt  메모를 쓴다(빈 메모 = 지움)
    DELETE /api/qa/<게임>/<꼬리표>/NNN      캡처·메모를 `.trash/` 로 옮긴다(지우지 않는다)
    /<게임>/qa/<꼬리표>/NNN.png             캡처 그림
캡처 자리는 `.local/work/inbox/<게임>/deck/<꼬리표>/` — 워커가 마스터 캡처를 읽는 그 수신함이다.
"""

import argparse
import email.utils
import hashlib
import html
import io
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PAGES = os.path.join(REPO, "scripts", "publish")
EXTRA = os.path.join(REPO, ".local", "cache", "publish")
SAVES = os.path.expanduser(os.environ.get("DEV_SAVES_DIR", "~/save"))
HASHED = re.compile(r"^(?P<stem>.+)\.[0-9a-f]{32}\.(?P<ext>sav|srm)$")
# 🔴 꼬리표가 `test-` 로 시작하는 칸은 시험용 — 파일서버·pull-build 목록에 안 나온다(마스터 10-15
#    「내가 볼 빌드와 시험용빌드를 나눠서 관리」). 시험 빌드는 `ED_BUILD_TAG=test-<무엇>` 으로 굽는다.
TEST_PREFIX = "test-"
PLAYABLE = re.compile(r"\.(sfc|smc|md|gen|smd|bin)$", re.IGNORECASE)
INBOX = os.path.join(REPO, ".local", "work", "inbox")
# 목록 정렬 — 기종별(마스터 10-30 「정렬은 기종별로」). 여기 없는 기종은 뒤에 이름순.
PLATFORMS = ("ps1", "ss", "pce", "sfc", "md", "dos", "pc98")
GAME_RE = re.compile(r"^[a-z0-9]+-ed[0-9+]+$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
NUM_RE = re.compile(r"^[0-9]{3,}$")
SAVE_RE = re.compile(r"^[^/\\]+$")
_QA_LOCK = threading.Lock()


def platform_of(game):
    return game.split("-", 1)[0]


def platform_key(game):
    p = platform_of(game)
    return (PLATFORMS.index(p) if p in PLATFORMS else len(PLATFORMS), game)


def known_game(game):
    return bool(GAME_RE.match(game)) and (
        os.path.isdir(os.path.join(REPO, "games", game)) or game in build_dirs()
    )


def qa_dir(game, tag=None):
    d = os.path.join(INBOX, game, "deck")
    return os.path.join(d, tag) if tag else d


def qa_items(game):
    """{꼬리표: [{n, memo, size, mtime}]} — 번호순."""
    out = []
    base = qa_dir(game)
    if not os.path.isdir(base):
        return out
    for tag in sorted(os.listdir(base)):
        d = os.path.join(base, tag)
        if tag.startswith(".") or not os.path.isdir(d):
            continue
        items = []
        for f in sorted(os.listdir(d)):
            n, ext = os.path.splitext(f)
            if ext != ".png" or not NUM_RE.match(n):
                continue
            st = os.stat(os.path.join(d, f))
            memo_p = os.path.join(d, n + ".txt")
            memo = open(memo_p, encoding="utf-8").read() if os.path.isfile(memo_p) else ""  # noqa: SIM115
            items.append({"n": n, "memo": memo, "size": st.st_size, "mtime": st.st_mtime})
        if items:
            out.append({"tag": tag, "items": items})
    return out


def qa_next(d):
    """다음 캡처 번호 — 휴지통에 간 번호도 다시 쓰지 않는다(워커가 번호로 부른다)."""
    nums = [0]
    for sub in (d, os.path.join(os.path.dirname(d), ".trash")):
        if os.path.isdir(sub):
            for f in os.listdir(sub):
                m = re.match(r"^(?:.*?-)?([0-9]{3,})\.", f)
                if m and (sub == d or f.startswith(os.path.basename(d) + "-")):
                    nums.append(int(m[1]))
    return f"{max(nums) + 1:03d}"


SITE_JSON = os.path.join(REPO, "patcher", "site", "site.json")
ART_DIR = os.environ.get("SITE_ART") or "/mnt/originals/_cover"


def cover_of(game):
    """카드 표지 — 배포 페이지(`patcher/site/build_site.py`)와 같은 순서로 찾는다: 소장 상자 그림(site.json
    `art`) → 릴리스에서 받은 `.local/ship/site-covers/<게임>.png` → 저장소 게임 화면 `shots/<게임>--00.png`."""
    try:
        with open(SITE_JSON, encoding="utf-8") as f:
            art = next((g.get("art") for g in json.load(f)["games"] if g.get("id") == game), None)
    except (OSError, ValueError, KeyError):
        art = None
    for p in (
        os.path.join(ART_DIR, art) if art else None,
        os.path.join(REPO, ".local", "ship", "site-covers", f"{game}.png"),
        os.path.join(REPO, "patcher", "site", "shots", f"{game}--00.png"),
    ):
        if p and os.path.isfile(p):
            return p
    return None


def builds_listing():
    """/api/builds — 기종 순 · 게임 이름 순 · 꼬리표 순. sha1 은 큰 파일이면 계산 중(None)일 수 있다."""
    games = []
    for g, tags in sorted(build_dirs().items(), key=lambda kv: platform_key(kv[0])):
        builds = []
        for t, d in sorted(tags.items()):
            files = []
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if f.startswith(".") or not os.path.isfile(p):
                    continue
                st = os.stat(p)
                files.append(
                    {
                        "name": f,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "sha1": sha1_of(p, wait=False),
                    }
                )
            builds.append({"tag": t, "files": files})
        games.append({"game": g, "platform": platform_of(g), "builds": builds})
    return {"platforms": list(PLATFORMS), "games": games}


def saves_listing(game):
    d = os.path.join(SAVES, game)
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if f.startswith(".") or f.endswith((".bak", ".tmp")) or not os.path.isfile(p):
                continue
            st = os.stat(p)
            out.append({"name": f, "size": st.st_size, "mtime": st.st_mtime})
    return out


def build_dirs():
    """{게임: {꼬리표: 실제 경로}} — 메인 트리 먼저, 워크트리가 덮는다."""
    out = {}
    roots = (
        [REPO]
        + sorted(
            os.path.join(REPO, ".claude", "worktrees", w)
            for w in os.listdir(os.path.join(REPO, ".claude", "worktrees"))
            if os.path.isdir(os.path.join(REPO, ".claude", "worktrees", w))
        )
        if os.path.isdir(os.path.join(REPO, ".claude", "worktrees"))
        else [REPO]
    )
    for root in roots:
        games = os.path.join(root, "games")
        if not os.path.isdir(games):
            continue
        for g in os.listdir(games):
            b = os.path.join(games, g, "work", "build")
            if not os.path.isdir(b):
                continue
            for tag in os.listdir(b):
                if tag.startswith(TEST_PREFIX):
                    continue  # 시험용 칸은 마스터 목록에 안 보인다
                d = os.path.realpath(os.path.join(b, tag))
                if not os.path.isdir(d) or any(f.endswith(".failed") for f in os.listdir(d)):
                    continue
                out.setdefault(g, {})[tag] = d
    return out


def _blank(p):
    try:
        with open(p, "rb") as f:
            return len(set(f.read())) <= 1
    except OSError:
        return True


def save_for(game, stem):
    """롬 `stem` 의 세이브 정본 — 해시 없는 것 → 비어 있지 않은 해시 붙은 제일 새것."""
    d = os.path.join(SAVES, game)
    if not os.path.isdir(d):
        return None
    for ext in ("srm", "sav"):
        p = os.path.join(d, f"{stem}.{ext}")
        if os.path.isfile(p) and not _blank(p):
            return p
    cands = []
    for f in os.listdir(d):
        m = HASHED.match(f)
        if m and m["stem"] == stem:
            p = os.path.join(d, f)
            if not _blank(p):
                cands.append(p)
    return max(cands, key=os.path.getmtime) if cands else None


_SHA = {}
_SHA_LOCK = threading.Lock()
_SHA_BIG = 64 << 20


def _sha1_now(p, key):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with _SHA_LOCK:
        _SHA[key] = h.hexdigest()


def sha1_of(p, wait=True):
    """파일 sha1 — (경로·크기·시각)으로 캐시. 큰 파일(64MB+)은 뒤에서 계산하고 그동안은 None.

    `wait=False` 면 작은 파일도 뒤에서 센다 — 목록 API 가 빌드 칸 전부를 한 요청 안에서 세다
    덱 앱의 10초 제한을 넘겼다(10-30 실측: 워커들이 다시 얹고 재빌드해 시각이 다 바뀐 직후).
    """
    st = os.stat(p)
    key = (p, st.st_size, st.st_mtime)
    with _SHA_LOCK:
        if key in _SHA:
            return _SHA[key]
        if _SHA.get(("busy",) + key):
            return None
        _SHA[("busy",) + key] = True
    if wait and st.st_size < _SHA_BIG:
        _sha1_now(p, key)
        return _SHA[key]
    threading.Thread(target=_sha1_now, args=(p, key), daemon=True).start()
    return None


def save_target(game, stem):
    """웹 실행기가 올린 세이브를 둘 **정본 자리** — emu.sh 가 쓰는 해시 없는 한 벌과 같은 파일.

    해시 없는 `<stem>.sav|.srm` 이 있으면 그것, 없으면 해시 붙은 제일 새것의 확장자를 따르고,
    그것도 없으면 기종 관례(md = .sav · 그 밖 = .srm)로 새로 만든다.
    """
    d = os.path.join(SAVES, game)
    for ext in ("sav", "srm"):
        p = os.path.join(d, f"{stem}.{ext}")
        if os.path.isfile(p):
            return p
    hashed = []
    if os.path.isdir(d):
        for f in os.listdir(d):
            m = HASHED.match(f)
            if m and m["stem"] == stem:
                hashed.append((os.path.getmtime(os.path.join(d, f)), m["ext"]))
    ext = max(hashed)[1] if hashed else ("sav" if game.startswith("md-") else "srm")
    return os.path.join(d, f"{stem}.{ext}")


def originals_of(game):
    root = os.path.join(REPO, "originals")
    if not os.path.isdir(root):
        return None
    for region in sorted(os.listdir(root)):
        p = os.path.join(root, region, game)
        if os.path.isdir(p):
            return p
    return None


def resolve(parts):
    """URL 조각 → ('dir', 실제경로 | None, 가상항목 dict) 또는 ('file', 실제경로)."""
    if not parts:
        return ("file", os.path.join(PAGES, "index.html"))
    if len(parts) == 1 and parts[0] in ("index.html", "run.html"):
        return ("file", os.path.join(PAGES, parts[0]))
    game, rest = parts[0], parts[1:]
    builds = build_dirs().get(game, {})
    extra = os.path.join(EXTRA, game)
    if not rest:  # 게임 칸 — 가상 목록
        items = {t + "/": None for t in builds}
        if os.path.isdir(os.path.join(SAVES, game)):
            items["saves/"] = None
        if originals_of(game):
            items["original/"] = None
        if os.path.isdir(extra):
            for n in os.listdir(extra):
                if os.path.isdir(os.path.join(extra, n)) and n + "/" not in items:
                    items[n + "/"] = None
        return ("dir", None, items) if items else None
    head, tail = rest[0], rest[1:]
    if head in builds:
        base = builds[head]
        virt = {}
        if not tail:
            for f in os.listdir(base):
                if PLAYABLE.search(f):
                    stem = os.path.splitext(f)[0]
                    # md 빌드는 `.bin` 이라 index.html 이 실행 버튼을 안 단다 — `.md` 이름을 곁에 끼운다
                    if game.startswith("md-") and f.lower().endswith(".bin"):
                        virt[stem + ".md"] = os.path.join(base, f)
                    s = save_for(game, stem)
                    if s:
                        virt[stem + ".srm"] = s
        elif len(tail) == 1 and game.startswith("md-") and tail[0].endswith(".md"):
            p = os.path.join(base, tail[0][:-3] + ".bin")
            if os.path.isfile(p):
                return ("file", p)
        elif len(tail) == 1 and tail[0].endswith(".srm"):
            s = save_for(game, tail[0][:-4])
            if s and not os.path.exists(os.path.join(base, tail[0])):
                return ("file", s)
    elif head == "saves":
        base = os.path.join(SAVES, game)
        virt = {}
    elif head == "original" and originals_of(game):
        base = originals_of(game)
        virt = {}
    elif head == "qa" and known_game(game):
        base = qa_dir(game)
        virt = {}
    else:
        base = os.path.join(extra, head)
        virt = {}
    p = os.path.realpath(os.path.join(base, *tail))
    if os.path.isdir(p):
        return ("dir", p, virt)
    if os.path.isfile(p):
        return ("file", p)
    return None


class Handler(SimpleHTTPRequestHandler):
    def _parts(self):
        path = urllib.parse.urlsplit(self.path).path
        parts = [urllib.parse.unquote(x) for x in path.split("/") if x]
        if any(x in ("..", ".") for x in parts):
            return None
        return parts

    def _json(self, obj, code=HTTPStatus.OK):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return io.BytesIO(data)

    def _api_get(self, parts):
        if parts == ["api", "builds"]:
            return self._json(builds_listing())
        if len(parts) == 3 and parts[1] == "cover" and known_game(parts[2]):
            p = cover_of(parts[2])
            if p:
                return self._file(p)
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        if len(parts) == 3 and parts[1] in ("saves", "qa") and known_game(parts[2]):
            if parts[1] == "saves":
                return self._json({"game": parts[2], "files": saves_listing(parts[2])})
            return self._json({"game": parts[2], "tags": qa_items(parts[2])})
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def send_head(self):
        parts = self._parts()
        if parts and parts[0] == "api":
            return self._api_get(parts)
        r = resolve(parts) if parts is not None else None
        if r is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        if r[0] == "dir":
            if not self.path.split("?")[0].endswith("/"):
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header("Location", self.path.split("?")[0] + "/")
                self.end_headers()
                return None
            return self._listing(r[1], r[2])
        return self._file(r[1])

    def _listing(self, real, virt):
        names = []
        if real:
            for n in sorted(os.listdir(real)):
                if n.startswith("."):
                    continue
                names.append(n + "/" if os.path.isdir(os.path.join(real, n)) else n)
        names += [n for n in sorted(virt) if n not in names]
        body = (
            "<!DOCTYPE HTML><html><body><ul>\n"
            + "".join(
                f'<li><a href="{urllib.parse.quote(n)}">{html.escape(n)}</a></li>\n' for n in names
            )
            + "</ul></body></html>\n"
        )
        data = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return io.BytesIO(data)

    def _file(self, p):
        try:
            f = open(p, "rb")  # noqa: SIM115 — 닫는 건 http.server 가 한다
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        st = os.fstat(f.fileno())
        self.send_response(HTTPStatus.OK)
        ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        # 빌드·원본 대조용 — 실행기와 목록이 sha1 앞자리를 보여 준다(마스터 2026-09-27)
        digest = sha1_of(p)
        if digest:
            self.send_header("X-Sha1", digest)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return f

    def _put_state(self, game, tag, fname, n):
        """웹 실행기의 스테이트 보내기 — `/<게임>/<꼬리표>/<롬이름>.state?core=<코어>`.

        🔴 **세이브가 안 되는 자리(전투 등)에서 재현한 순간을 세션에 넘긴다**(마스터 2026-09-27).
        `~/save/<게임>/state/<롬이름>.<롬 sha1 앞 8>.<시각>.<코어>.state` 로 쌓는다(덮지 않는다).
        ⚠ 웹 코어(Genesis Plus GX · Snes9x) 스테이트는 emucap(mednafen·Mesen2)이 **못 불러온다** —
        세션은 풀어서 RAM·VRAM 을 읽는 데 쓴다. 이름의 sha1 로 어느 빌드였는지 가린다.
        """
        if not 0 < n <= 32 << 20:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        rom = next(
            (
                os.path.join(build_dirs()[game][tag], f)
                for f in os.listdir(build_dirs()[game][tag])
                if PLAYABLE.search(f) and os.path.splitext(f)[0] == fname[:-6]
            ),
            None,
        )
        if not rom:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        core = re.sub(r"[^A-Za-z0-9_-]", "", (q.get("core") or ["web"])[0])[:32] or "web"
        data = self.rfile.read(n)
        d = os.path.join(SAVES, game, "state")
        os.makedirs(d, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = os.path.join(d, f"{fname[:-6]}.{(sha1_of(rom) or 'nosha')[:8]}.{stamp}.{core}.state")
        with open(out + ".tmp", "wb") as f:
            f.write(data)
        os.replace(out + ".tmp", out)
        print(
            f"스테이트 받음: {game} → state/{os.path.basename(out)} ({len(data)}B)", file=sys.stderr
        )
        self.send_response(HTTPStatus.CREATED)
        self.send_header("X-Saved-As", urllib.parse.quote(os.path.basename(out)))
        self.end_headers()

    def do_PUT(self):
        """웹 실행기의 세이브 올리기 — `/<게임>/<꼬리표>/<롬이름>.srm` 만 받는다.

        🔴 **폰·맥이 같은 세이브를 보게 한다**(마스터 2026-09-27). 받은 SRAM 을 `~/save/<게임>/` 의
        해시 없는 정본에 쓴다 — 맥 emu.sh 가 당기고 올리는 바로 그 파일이다.
        · 덮기 전에 `.bak` 한 세대를 남긴다 · 빈 SRAM(바이트가 전부 같은 값)은 거절한다
        · 정본보다 짧으면 0xFF 로 채운다(MD 코어는 SRAM 을 마지막 비-FF 바이트까지만 내준다)
        """
        parts = self._parts()
        n = int(self.headers.get("Content-Length") or 0)
        if parts and parts[0] == "api":
            self._api_put(parts, n)
            return
        if (
            parts
            and len(parts) == 3
            and parts[2].endswith(".state")
            and parts[1] in build_dirs().get(parts[0], {})
        ):
            self._put_state(*parts, n)
            return
        if not parts or len(parts) != 3 or not parts[2].endswith(".srm") or not 0 < n <= 1 << 20:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        game, tag, fname = parts
        if tag not in build_dirs().get(game, {}):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = self.rfile.read(n)
        if len(set(data)) <= 1:
            self.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "blank save")
            return
        target = save_target(game, fname[:-4])
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # 크기 기준은 지금 정본(없으면 폰이 받아 간 세이브) — 짧으면 0xFF 로 채워 크기를 지킨다
        ref = target if os.path.isfile(target) else save_for(game, fname[:-4])
        if ref and os.path.getsize(ref) > len(data):
            data += b"\xff" * (os.path.getsize(ref) - len(data))
        if os.path.isfile(target):
            old = open(target, "rb").read()  # noqa: SIM115
            if data == old:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            shutil.copy2(target, target + ".bak")
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        print(f"세이브 받음: {game} → {os.path.basename(target)} ({len(data)}B)", file=sys.stderr)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _done(self, code=HTTPStatus.NO_CONTENT, saved_as=None):
        self.send_response(code)
        if saved_as:
            self.send_header("X-Saved-As", urllib.parse.quote(saved_as))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _api_put(self, parts, n):
        """덱 앱의 올리기 — 세이브 정본 · 스테이트 · QA 캡처 · 메모."""
        if len(parts) < 4 or not known_game(parts[2]):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        kind, game, rest = parts[1], parts[2], parts[3:]
        if kind == "save":
            if not 0 < n <= 64 << 20:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            data = self.rfile.read(n)
            if len(rest) == 2 and rest[0] == "state" and SAVE_RE.match(rest[1]):
                # 스테이트는 쌓기만 한다 — 같은 이름이 있으면 거절(앱이 시각을 붙여 보낸다)
                d = os.path.join(SAVES, game, "state")
                os.makedirs(d, exist_ok=True)
                out = os.path.join(d, rest[1])
                if os.path.exists(out):
                    self.send_error(HTTPStatus.CONFLICT)
                    return
                with open(out + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(out + ".tmp", out)
                print(f"스테이트 받음(덱): {game} → state/{rest[1]}", file=sys.stderr)
                self._done(HTTPStatus.CREATED, rest[1])
                return
            if len(rest) != 1 or not SAVE_RE.match(rest[0]) or rest[0].endswith((".bak", ".tmp")):
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            if len(set(data)) <= 1:
                self.send_error(HTTPStatus.UNPROCESSABLE_ENTITY, "blank save")
                return
            target = os.path.join(SAVES, game, rest[0])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.isfile(target):
                if open(target, "rb").read() == data:  # noqa: SIM115
                    self._done()
                    return
                shutil.copy2(target, target + ".bak")
            with open(target + ".tmp", "wb") as f:
                f.write(data)
            os.replace(target + ".tmp", target)
            print(f"세이브 받음(덱): {game} → {rest[0]} ({len(data)}B)", file=sys.stderr)
            self._done()
            return
        if kind == "qa" and len(rest) == 2 and TAG_RE.match(rest[0]):
            tag, fname = rest
            d = qa_dir(game, tag)
            if fname == "new.png":
                if not 0 < n <= 16 << 20:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                data = self.rfile.read(n)
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                    return
                with _QA_LOCK:
                    os.makedirs(d, exist_ok=True)
                    num = qa_next(d)
                    with open(os.path.join(d, num + ".png"), "wb") as f:
                        f.write(data)
                print(f"QA 캡처 받음(덱): {game}/{tag}/{num}.png", file=sys.stderr)
                self._done(HTTPStatus.CREATED, num)
                return
            num, ext = os.path.splitext(fname)
            if (
                ext == ".txt"
                and NUM_RE.match(num)
                and os.path.isfile(os.path.join(d, num + ".png"))
            ):
                if not 0 <= n <= 64 << 10:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                memo = self.rfile.read(n).decode("utf-8", "replace").strip()
                p = os.path.join(d, num + ".txt")
                if memo:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(memo + "\n")
                elif os.path.isfile(p):
                    os.remove(p)
                self._done()
                return
        self.send_error(HTTPStatus.BAD_REQUEST)

    def do_DELETE(self):
        """QA 캡처 지우기 — 실제로는 `deck/.trash/<꼬리표>-NNN.<시각>.*` 로 옮긴다(되살릴 수 있게)."""
        parts = self._parts()
        if (
            not parts
            or len(parts) != 5
            or parts[:2] != ["api", "qa"]
            or not known_game(parts[2])
            or not TAG_RE.match(parts[3])
            or not NUM_RE.match(parts[4])
        ):
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        game, tag, num = parts[2:]
        d = qa_dir(game, tag)
        if not os.path.isfile(os.path.join(d, num + ".png")):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        trash = os.path.join(qa_dir(game), ".trash")
        os.makedirs(trash, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        with _QA_LOCK:
            for ext in (".png", ".txt"):
                p = os.path.join(d, num + ext)
                if os.path.isfile(p):
                    os.replace(p, os.path.join(trash, f"{tag}-{num}.{stamp}{ext}"))
        print(f"QA 캡처 휴지통(덱): {game}/{tag}/{num}", file=sys.stderr)
        self._done()

    def copyfile(self, source, outputfile):
        shutil.copyfileobj(source, outputfile, 1 << 20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--list", action="store_true", help="보이는 빌드 칸만 찍고 끝낸다")
    a = ap.parse_args()
    if a.list:
        for g, tags in sorted(build_dirs().items()):
            for t, d in sorted(tags.items()):
                print(f"{g}/{t}/  ←  {os.path.relpath(d, REPO)}")
        return
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    print(
        f"파일서버: http://{a.bind}:{a.port}/  (빌드 칸을 그 자리에서 보여 준다)", file=sys.stderr
    )
    srv.serve_forever()


if __name__ == "__main__":
    main()
