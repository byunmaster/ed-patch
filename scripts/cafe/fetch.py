#!/usr/bin/env python3
"""네이버 카페 레퍼런스 수집기 — 로그인된 크롬에 CDP 로 붙어 카페 JSON API 를 부른다.

입구는 `scripts/cafe.sh` 다. 여기는 부품이라 직접 부르지 않아도 된다.

⚠ 자격증명은 이 파일 어디에도 없다. 인증은 스크립트가 아니라 **크롬 프로필**이 든다 —
  쿠키는 `~/.cache/chrome-cdp-profile` 안에 있고 in-page `fetch(url,{credentials:'include'})`
  가 자동으로 싣는다. 이 스크립트가 아는 건 CDP 포트뿐이다.
🔴 **쿠키를 파일로 떨구지 않는다.** 그건 세션 탈취용 토큰이고 이 레포는 공개 전제다
  (docs/publishing.md).

⚠ `Page.navigate` 로 목록을 직접 열면 SPA 가 안 채운다(iframe 미하이드레이션).
  **반드시 API** — 대신 탭은 cafe.naver.com 에 세워 둔다(apis.naver.com 이 Origin 을 본다).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).resolve().parent / "sources.json"
INVENTORY = ROOT / "docs" / "reference" / "_inventory"

LIST_API = (
    "https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{club}/menus/{menu}"
    "/articles?page={page}&pageSize={size}&sort=TIME"
)
ARTICLE_API = (
    "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{club}/articles/{art}"
    "?query=&menuId={menu}&boardType=L&useCafeId=true&requestFrom=A"
)
# probe 용 — 카페마다 사는 API 가 달라서 순서대로 두들긴다.
MENU_APIS = [
    "https://apis.naver.com/cafe-web/cafe-home-api/v1/cafes/{club}/menus",
    "https://apis.naver.com/cafe-web/cafe2/SideMenuList.json?search.clubid={club}",
    "https://apis.naver.com/cafe-web/cafe-mobile/CafeMenuList.json?cafeId={club}",
]


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


# ── CDP ───────────────────────────────────────────────────────────────────────
class CDP:
    """로그인된 크롬의 탭 하나를 잡고 in-page 로 코드를 돌린다."""

    def __init__(self, endpoint: str = "localhost:9222", verbose: bool = False):
        self.endpoint = endpoint
        self.verbose = verbose
        self.n = 0
        try:
            import websocket  # noqa: PLC0415  (선택 의존물이라 여기서 문다)
        except ImportError:
            die(".venv 에 websocket-client 가 없다 → .venv/bin/pip install websocket-client")
        self._ws_mod = websocket
        self.ws = None

    def _http(self, path: str, method: str = "GET"):
        url = f"http://{self.endpoint}{path}"
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (로컬 고정)
                return json.loads(r.read().decode())
        except Exception as e:
            die(
                f"CDP 에 못 붙었다({url}): {e}\n"
                "  크롬을 CDP 모드로 띄웠나? → sh scripts/cafe.sh chrome"
            )

    def connect(self, want_url: str) -> None:
        """cafe.naver.com 에 선 탭을 잡거나, 없으면 하나 만들어 세운다."""
        self._http("/json/version")  # 살아 있나
        tabs = [t for t in self._http("/json/list") if t.get("type") == "page"]
        tab = next((t for t in tabs if "cafe.naver.com" in (t.get("url") or "")), None)
        if tab is None:
            tab = next((t for t in tabs if (t.get("url") or "").startswith("http")), None)
        if tab is None:
            # 빈 새 탭(chrome://newtab)뿐이면 그걸 쓰고, 그마저 없으면 하나 연다.
            # ⚠ 요즘 크롬은 /json/new 가 **PUT** 이다(GET 은 405).
            tab = tabs[0] if tabs else self._http("/json/new?" + want_url, method="PUT")
        self._open(tab["webSocketDebuggerUrl"])
        cur = self.eval_js("location.href", raw=True) or ""
        if "cafe.naver.com" not in cur:
            self.navigate(want_url)

    def _open(self, ws_url: str) -> None:
        # suppress_origin: Origin 헤더를 안 보내면 크롬이 --remote-allow-origins 없이도 받는다.
        self.ws = self._ws_mod.create_connection(ws_url, timeout=30, suppress_origin=True)

    def send(self, method: str, params: dict | None = None, timeout: float = 60.0):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            self.ws.settimeout(max(1.0, end - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except Exception as e:
                die(f"CDP 응답이 끊겼다: {e}")
            if msg.get("id") == mid:
                if "error" in msg:
                    die(f"CDP {method} 실패: {msg['error']}")
                return msg.get("result", {})
        die(f"CDP {method} 응답이 없다(timeout)")

    def navigate(self, url: str) -> str:
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        for _ in range(60):
            time.sleep(0.5)
            state = self.eval_js("document.readyState", raw=True)
            if state == "complete":
                break
        time.sleep(0.5)
        return self.eval_js("location.href", raw=True) or ""

    def eval_js(self, expr: str, raw: bool = False, timeout: float = 60.0):
        r = self.send(
            "Runtime.evaluate",
            {"expression": expr, "awaitPromise": True, "returnByValue": True},
            timeout=timeout,
        )
        if r.get("exceptionDetails"):
            die(f"in-page 예외: {r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value") if raw else r.get("result", {}).get("value")

    def api(self, url: str, referer: str) -> dict:
        """카페 API 를 **탭 안에서** 부른다 — 쿠키가 자동으로 실린다."""
        expr = (
            "(async()=>{try{const r=await fetch(" + json.dumps(url) + ",{credentials:'include',"
            "headers:{'Referer':" + json.dumps(referer) + ",'Accept':'application/json'}});"
            "const t=await r.text();return JSON.stringify({ok:r.ok,status:r.status,body:t});}"
            "catch(e){return JSON.stringify({ok:false,status:0,body:String(e)});}})()"
        )
        raw = self.eval_js(expr, raw=True)
        try:
            env = json.loads(raw)
        except Exception:
            die(f"응답을 못 읽었다: {str(raw)[:200]}")
        if not env["ok"]:
            return {"_http": env["status"], "_body": env["body"][:400]}
        try:
            return json.loads(env["body"])
        except Exception:
            # 로그인이 풀리면 JSON 대신 로그인 HTML 이 온다.
            head = env["body"][:200].replace("\n", " ")
            die(
                "JSON 이 아니라 HTML 이 왔다 — 그 크롬 프로필의 네이버 로그인이 풀렸을 수 있다.\n"
                f"  앞부분: {head}"
            )


# ── sources.json ──────────────────────────────────────────────────────────────
def load_sources() -> dict:
    if not SOURCES.exists():
        die(f"{SOURCES} 가 없다")
    return json.loads(SOURCES.read_text())


def save_sources(d: dict) -> None:
    SOURCES.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def get_cafe(src: dict, slug: str) -> dict:
    if slug not in src["cafes"]:
        die(f"모르는 카페 '{slug}' — 아는 건: {', '.join(src['cafes'])}")
    c = dict(src["cafes"][slug])
    c.setdefault("url", f"https://cafe.naver.com/ca-fe/cafes/{c['clubid']}")
    c["slug"] = slug
    return c


# ── 목록 항목 정규화 ──────────────────────────────────────────────────────────
def pick(d: dict, *keys, default=None):
    for k in keys:
        cur = d
        for part in k.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if cur not in (None, ""):
            return cur
    return default


def norm(item: dict, menu: str) -> dict | None:
    """API 항목 → `_inventory/*.jsonl` 한 줄. 옛 수집분과 **키·형식이 같아야** 병합된다."""
    art = pick(item, "articleId", "id")
    if art is None:
        return None
    img = pick(item, "representImage", "hasImage", "image", default=False)
    return {
        "id": str(art),
        "menu": str(menu),
        "subject": str(pick(item, "subject", "title", default="")),
        "summary": str(pick(item, "summary", "content", default="")),
        "like": str(pick(item, "likeCount", "likeItCount", "upCount", default=0)),
        "cmt": str(pick(item, "commentCount", "comment.count", "commentcount", default=0)),
        "read": str(pick(item, "readCount", "readcount", "viewCount", default=0)),
        "img": str(bool(img)),
        "link": str(bool(pick(item, "hasLink", "hasAttachedLink", "link", default=False))),
        "ts": str(pick(item, "writeDateTimestamp", "writeDate", "addDate", default=0)),
        "writer": str(
            pick(item, "writerInfo.nickName", "writerNickname", "writerInfo.id", default="")
        ),
    }


def read_jsonl(p: Path) -> list[dict]:
    """⚠ 값을 전부 문자열로 맞춘다 — 옛 수집분은 id·조회수가 **int** 로 들어 있어서,
    그대로 두면 `'31618' != 31618` 이라 이미 있는 글이 매번 신규로 다시 붙는다(실측)."""
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            row = json.loads(line)
            out.append({k: (v if isinstance(v, str) else str(v)) for k, v in row.items()})
    return out


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ── 명령: fetch ───────────────────────────────────────────────────────────────
def cmd_fetch(a) -> None:
    src = load_sources()
    cafe = get_cafe(src, a.cafe)
    menus = a.menus or list(cafe["menus"])
    unknown = [m for m in menus if m not in cafe["menus"]]
    if unknown:
        die(f"sources.json 에 없는 menuid: {', '.join(unknown)}")

    cdp = CDP(a.cdp, a.verbose)
    cdp.connect(cafe["url"])
    outdir = INVENTORY / cafe["slug"]
    total_new = 0
    empties = []

    for menu in menus:
        path = outdir / f"{menu}.jsonl"
        old = [] if a.full else read_jsonl(path)
        known = {r["id"] for r in old}
        fresh: dict[str, dict] = {}
        pages = 0
        for page in range(1, a.max_pages + 1):
            url = LIST_API.format(club=cafe["clubid"], menu=menu, page=page, size=a.page_size)
            data = cdp.api(url, cafe["url"])
            if "_http" in data:
                print(f"  ! menu {menu} p{page}: HTTP {data['_http']}", file=sys.stderr)
                break
            res = data.get("result") or {}
            entries = res.get("articleList") or res.get("articles") or []
            items = [(e.get("item") if isinstance(e, dict) and "item" in e else e) for e in entries]
            if a.verbose and page == 1 and items:
                print(f"  · menu {menu} 항목 키: {sorted(items[0])}", file=sys.stderr)
            pages = page
            got = 0
            for it in items:
                row = norm(it, menu)
                if row and row["id"] not in known and row["id"] not in fresh:
                    fresh[row["id"]] = row
                    got += 1
            if not items or len(items) < a.page_size:
                break
            if got == 0 and not a.full:
                break  # 증분: 새 글이 하나도 없는 면을 만나면 멈춘다
            time.sleep(a.delay)

        merged = list(fresh.values())
        seen = set(fresh)
        for r in old:  # 옛 줄은 뒤에 붙이되 같은 id 가 있으면 새 줄이 이긴다
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append(r)
        merged.sort(key=lambda r: int(r.get("ts") or 0), reverse=True)
        write_jsonl(path, merged)
        total_new += len(fresh)
        name = cafe["menus"][menu]
        mark = "＋" if fresh else "  "
        print(f"{mark} [{menu}] {name}: 신규 {len(fresh)}건 / 누적 {len(merged)}건 ({pages}면)")
        if not merged:
            empties.append(f"{menu}({name})")

    print(f"\n== 신규 {total_new}건 → {outdir.relative_to(ROOT)}/")
    if empties:
        print(
            "⚠ 수집 0건인 게시판: " + ", ".join(empties) + "\n"
            "  에러가 아니라 **빈 결과**로 오는 경우가 있다 — 그 크롬 프로필이 이 카페에\n"
            "  가입돼 있는지, 등급 제한 게시판은 아닌지 먼저 의심한다.",
            file=sys.stderr,
        )


# ── 명령: body ────────────────────────────────────────────────────────────────
TAG = re.compile(r"<[^>]+>")


def html_to_text(src: str) -> str:
    """스마트에디터 HTML → 읽을 수 있는 글.

    ⚠ 엔티티를 **끝까지** 푼다 — 스마트에디터는 따옴표·등호까지 `&#x27;`·`&#x3D;` 로
    쓴다. 안 풀면 본문에 박힌 **오프셋 표기(`44D4C=44D4F`)가 깨져서** 읽을 수가 없다.
    """
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", src or "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|tr|h\d)>", "\n", s)
    # 이미지·첨부는 자리만 남긴다(기법 글은 그림에 값이 있어 「여기 그림이 있다」를 남긴다)
    s = re.sub(r"(?i)<img[^>]*>", "\n[그림]\n", s)
    s = TAG.sub("", s)
    s = unescape(unescape(s))  # 두 번 — 이중 인코딩된 글이 실제로 있다
    s = re.sub(r"\[\[\[CONTENT-ELEMENT-\d+\]\]\]", "[그림]", s)
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"(?:\[그림\]\n*){2,}", "[그림]\n", s)
    return s.strip()


def cmd_body(a) -> None:
    src = load_sources()
    cafe = get_cafe(src, a.cafe)
    cdp = CDP(a.cdp, a.verbose)
    cdp.connect(cafe["url"])
    outdir = INVENTORY / cafe["slug"] / "bodies"
    for art in a.ids:
        url = ARTICLE_API.format(club=cafe["clubid"], art=art, menu=a.menu)
        data = cdp.api(url, cafe["url"])
        if "_http" in data:
            print(f"  ! {art}: HTTP {data['_http']}", file=sys.stderr)
            continue
        res = (data.get("result") or {}).get("article") or {}
        cmts = [
            {
                "writer": pick(c, "writer.nick", "writer.id", default=""),
                "text": c.get("content", ""),
            }
            for c in ((data.get("result") or {}).get("comments") or {}).get("items", [])
        ]
        rec = {
            "id": str(art),
            "menu": str(a.menu),
            "subject": res.get("subject", ""),
            "text": html_to_text(res.get("contentHtml", "")),
            "comments": cmts,
        }
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / f"{a.menu}-{art}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1) + "\n"
        )
        print(f"  · {art} {rec['subject'][:40]} ({len(rec['text'])}자, 댓글 {len(cmts)})")
        time.sleep(a.delay)
    print(f"\n== → {outdir.relative_to(ROOT)}/")


# ── 명령: probe ───────────────────────────────────────────────────────────────
def walk_menus(node, out: dict) -> None:
    """카페마다 응답 모양이 달라 menuId/menuName 짝을 재귀로 줍는다."""
    if isinstance(node, dict):
        mid = node.get("menuId", node.get("menuid"))
        name = node.get("menuName", node.get("name"))
        if mid is not None and isinstance(name, str) and name.strip():
            out[str(mid)] = name.strip()
        for v in node.values():
            walk_menus(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_menus(v, out)


def cmd_probe(a) -> None:
    cdp = CDP(a.cdp, a.verbose)
    target = a.target
    if target.isdigit():
        club, url = target, f"https://cafe.naver.com/ca-fe/cafes/{target}"
    else:
        url = target if target.startswith("http") else f"https://cafe.naver.com/{target}"
        club = ""
    cdp.connect(url)
    final = cdp.navigate(url)
    if not club:
        m = re.search(r"/cafes/(\d+)", final) or re.search(r"clubid=(\d+)", final)
        if not m:
            club = str(
                cdp.eval_js(
                    "String(window.g_sClubId||window.clubid||"
                    "(document.documentElement.innerHTML.match(/cafeId[\"':= ]+(\\d{6,})/)||[])[1]"
                    "||'')",
                    raw=True,
                )
                or ""
            )
        else:
            club = m.group(1)
    if not club.isdigit():
        die(f"clubid 를 못 캤다(최종 URL: {final}) — 카페 주소를 직접 확인해서 숫자로 넘긴다")
    print(f"clubid = {club}  ({final})")

    menus: dict[str, str] = {}
    for tpl in MENU_APIS:
        data = cdp.api(tpl.format(club=club), url)
        if "_http" in data:
            continue
        walk_menus(data, menus)
        if menus:
            print(f"  (menu API: {tpl.split('?')[0]})")
            break
    if not menus:
        die("게시판 목록을 못 받았다 — 그 프로필이 이 카페에 가입돼 있는지 본다")

    print(f"\n게시판 {len(menus)}개:")
    for mid, name in sorted(menus.items(), key=lambda kv: int(kv[0])):
        print(f"  {mid:>4}  {name}")

    if a.save:
        src = load_sources()
        src["cafes"].setdefault(a.save, {})
        src["cafes"][a.save].update(
            {
                "name": a.name or src["cafes"][a.save].get("name", a.save),
                "clubid": club,
                "url": f"https://cafe.naver.com/ca-fe/cafes/{club}",
                "menus": src["cafes"][a.save].get("menus", {}),
                "candidates": menus,
            }
        )
        save_sources(src)
        print(
            f"\n→ sources.json 의 '{a.save}' 에 candidates 로 적었다.\n"
            "  수집할 게시판만 candidates 에서 menus 로 옮긴다(전부 긁지 않는다)."
        )


# ── 명령: list ────────────────────────────────────────────────────────────────
def cmd_list(a) -> None:
    src = load_sources()
    for slug, c in src["cafes"].items():
        print(f"\n■ {slug} — {c.get('name', '')} (clubid {c['clubid']})")
        for mid, name in c.get("menus", {}).items():
            p = INVENTORY / slug / f"{mid}.jsonl"
            rows = read_jsonl(p)
            when = ""
            if rows:
                ts = max(int(r.get("ts") or 0) for r in rows) / 1000
                when = time.strftime("  최신 %Y-%m-%d", time.localtime(ts))
            print(f"  {mid:>4}  {name:<20} {len(rows):>5}건{when}")
        cand = c.get("candidates") or {}
        if cand:
            print(f"  (미선정 게시판 {len(cand)}개 — probe 로 캔 목록)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="cafe.sh", description=__doc__)
    ap.add_argument("--cdp", default="localhost:9222", help="크롬 CDP 엔드포인트")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="게시판 목록 증분 수집")
    f.add_argument("cafe")
    f.add_argument("menus", nargs="*")
    f.add_argument("--full", action="store_true", help="증분이 아니라 전량 재수집")
    f.add_argument("--max-pages", type=int, default=40)
    f.add_argument("--page-size", type=int, default=50)
    f.add_argument("--delay", type=float, default=0.4)
    f.set_defaults(fn=cmd_fetch)

    b = sub.add_parser("body", help="글 본문·댓글 받기")
    b.add_argument("cafe")
    b.add_argument("menu")
    b.add_argument("ids", nargs="+")
    b.add_argument("--delay", type=float, default=0.4)
    b.set_defaults(fn=cmd_body)

    p = sub.add_parser("probe", help="카페 좌표(clubid·menuid) 캐기")
    p.add_argument("target", help="카페 URL·주소슬러그·clubid")
    p.add_argument("--save", metavar="SLUG", help="sources.json 에 적는다")
    p.add_argument("--name", help="카페 이름(--save 와 함께)")
    p.set_defaults(fn=cmd_probe)

    ls = sub.add_parser("list", help="좌표·수집 현황")
    ls.set_defaults(fn=cmd_list)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
