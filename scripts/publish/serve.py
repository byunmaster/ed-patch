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
"""

import argparse
import email.utils
import hashlib
import html
import io
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
PLAYABLE = re.compile(r"\.(sfc|smc|md|gen|smd|bin)$", re.IGNORECASE)


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


def sha1_of(p):
    """파일 sha1 — (경로·크기·시각)으로 캐시. 큰 파일(64MB+)은 뒤에서 계산하고 그동안은 None."""
    st = os.stat(p)
    key = (p, st.st_size, st.st_mtime)
    with _SHA_LOCK:
        if key in _SHA:
            return _SHA[key]
        if _SHA.get(("busy",) + key):
            return None
        _SHA[("busy",) + key] = True
    if st.st_size < _SHA_BIG:
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

    def send_head(self):
        parts = self._parts()
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
