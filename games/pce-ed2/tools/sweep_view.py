"""전 씬 대사 검수 — 대사 보기(`pceview`)로 번역이 맡은 줄 전부를 실제 대사창에 띄워 찍는다(마스터 10-19 밤샘 검수).

덩이(`rel:원문 덩이 시작`)마다 번역이 맡은 줄을 묶음(기본 10줄)으로 나눠 한 번에 띄운다 — 줄 사이 `00`(줄 끝)을 빼고 이어 붙인 덩이를 LZ 로 다시 압축해
도착 장면의 메시지 자리에 넣는다. 찍힌 쪽 순서 = 묶음 줄 순서(쪽 가름 `13` 이 줄 안에도 있어 쪽 수는 줄 수와 다르다).

    python3 sweep_view.py --iso <디버그 이미지> --out <폴더> [--budget 1100] [--only 386]
산출: `<out>/<rel>_<덩이>_<묶음>_<쪽>.png`(대사창만 잘라 작게) · `<out>/index.tsv`(파일 · 열쇠 · 묶음 줄) · `<out>/done.txt`(끝낸 묶음 — 이어 돌린다).
⚠ 원문(일본어)은 안 남긴다 — 열쇠뿐이다. 변수 자리(이름·숫자·아이템)는 도착 장면 상태의 값이 들어간다.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import dialogue
import lz
import package
import pceview


LIMIT = 230  # 묶음 풀린 바이트 상한


def pages_of(group: bytes) -> int:
    """묶음 한 덩이의 쪽 수 — 쪽 끝 제어(`13` · `12`)의 수(글리프 2바이트는 건너뛴다). 끝이 그 제어가 아니면 한 쪽 더."""
    import font

    n = 0
    last = None
    i = 0
    while i < len(group):
        b = group[i]
        if font.LEAD0 <= b < font.LEAD0 + font.MAX_LEADS + 1 and i + 1 < len(group):
            i += 2
            last = "g"
            continue
        if b in (0x12, 0x13):
            n += 1
        last = b
        i += 1
    if last not in (0x12, 0x13):
        n += 1
    return max(n, 1)


def has_pause(body: bytes) -> bool:
    """본문에 정해진 멈춤(`11 nn mm`)이 있나 — 글 중간 멈춤 뒤 이어지는 글은 끝 제어 없이 창이 닫히면 놓친다."""
    import font
    import jptext

    i = 0
    while i < len(body):
        b = body[i]
        if font.LEAD0 <= b < font.LEAD0 + font.MAX_LEADS + 1 and i + 1 < len(body):
            i += 2
        elif b < 0x20:
            if b == 0x11:
                return True
            i += 1 + jptext.ARGS.get(b, 0)
        else:
            i += 1
    return False


def groups(final_iso: str, batch: int, only: set[int] | None, tail13: bool = False, pause_only: bool = False, extra: set[tuple[int, int, int]] | None = None):
    cache: dict[int, bytes] = {}
    for rel, start in sorted(set(dialogue._chunks_with_work()) | {(r_, s_) for r_, s_, _l in (extra or ())}):
        if only and rel not in only:
            continue
        orig = common.track_data(rel, 128)
        _oT, otab = package.msg_table(orig)
        m = otab.index(start)
        fin = cache.setdefault(rel, pceview.iso_pkg(final_iso, rel))
        _fT, ftab = package.msg_table(fin)
        fs = ftab[m]
        fe = next(e for s, e in package.chunks(fin) if s == fs)
        raw, _ = package.decode_chunk(fin, fs, fe)
        lines = raw.split(b"\x00")
        cov = sorted(set(dialogue.covered(rel, start)) | {li for r_, s_, li in (extra or ()) if (r_, s_) == (rel, start)})
        gl = fin[ftab[0] : ftab[0] + 16 * 255]
        # 묶음 = 풀린 바이트 합이 한 줄 버퍼(`$30E5`~`$31E5`, 256B)를 안 넘게(넘으면 중간에 밀어내며 쪽이 엉킨다 — 실측)
        packs: list[list[int]] = []
        cur: list[int] = []
        size = 0
        for j in cov:
            n = len(lines[j])
            new_speaker = lines[j][:1] == b"\x16"  # 화자 머리가 있는 줄은 원판에서도 새 창으로 뜬다 — 따로 찍는다(이어 붙이면 앞 줄 창에 머리가 겹쳐 가짜 결함이 된다)
            if cur and (new_speaker or size + n > LIMIT or len(cur) >= batch):
                packs.append(cur)
                cur, size = [], 0
            cur.append(j)
            size += n
        if cur:
            packs.append(cur)
        for g, sel in enumerate(packs):
            body = b"".join(lines[j] for j in sel)
            if pause_only and not has_pause(body):
                continue
            if tail13 and body[-1:] not in (b"\x12", b"\x13"):
                body += b"\x13"  # 촬영용 쪽 대기 — 끝 제어 없는 줄은 창이 바로 닫혀 못 찍는다
            data = lz.encode_opt(b"\x00" * pceview.SKIP + body + b"\x00" * 64)  # 도착 장면이 줄 번호 78 부터 부른다 — 빈 줄 78개를 앞에 둔다
            yield f"{rel}_{start}_{g:02d}", f"{rel}:{start}", sel, data, gl, pages_of(body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.sav")
    ap.add_argument("--batch", type=int, default=1)  # 한 줄씩(여러 줄을 잇댄 묶음은 화자 바뀜·쪽 끝 제어가 엉켜 가짜 결함을 만든다 — 10-19 실측)
    ap.add_argument("--budget", type=int, default=1100, help="초 — 이 시간을 넘기면 끝낸 데까지 두고 나간다(잠금 20분 규칙)")
    ap.add_argument("--stop", action="store_true", help="메시지 속도를 멈춤(한 번에 표시)으로 두고 찍는다")
    ap.add_argument("--retry", help="앞 촬영의 index.tsv — 거기서 「못 찍음」이던 묶음만 다시(줄 끝에 쪽 대기 `13` 을 덧붙여 창이 안 닫히게 한다 — 끝 제어 없이 이어지는 줄·정해진 멈춤으로 끝나는 줄)")
    ap.add_argument("--pause", action="store_true", help="글 중간 멈춤(`11`)이 있는 줄만, 끝에 쪽 대기 `13` 을 덧붙여(멈춤 뒤 이어지는 글이 창이 닫히기 전에 찍히게)")
    ap.add_argument("--force", nargs="*", help="`rel:덩이:줄` 을 번역 범위 밖이어도(틀 줄 등) 만들어 찍는다")
    ap.add_argument("--keys", nargs="*", help="`rel:덩이:줄` 만 찍는다(고친 줄 재촬영)")
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--allow-stale", action="store_true", help="롬 소스 지문이 지금 소스와 달라도 찍는다")
    a = ap.parse_args()
    import romtag

    desc = romtag.check(a.iso, a.allow_stale)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "rom.txt", "a") as f:
        f.write(desc + "\n")
    done_f = out / "done.txt"
    done = set(done_f.read_text().split()) if done_f.exists() else set()
    t0 = time.time()
    cue = str(Path(a.iso).with_suffix(".cue"))
    v = pceview.Viewer(cue, a.iso, a.bram, out / "_work", stop=a.stop)
    n_groups = n_pages = 0
    retry = None
    if a.retry:
        retry = {l.split("\t")[1] + "\t" + l.split("\t")[2] for l in open(a.retry) if l.rstrip("\n").endswith("못 찍음")}
    for gid, key, sel, data, gl, npg in groups(a.iso, a.batch, set(a.only) if a.only else None, tail13=bool(a.retry) or a.pause, pause_only=a.pause, extra={tuple(int(x) for x in k.split(":")) for k in (a.force or [])}):
        if gid in done:
            continue
        if a.keys and not any(f"{key}:{j}" in a.keys for j in sel):
            continue
        if retry is not None:
            if f"{key}\t{','.join(map(str, sel))}" not in retry:
                continue
        if time.time() - t0 > a.budget:
            print(f"예산 {a.budget}s 소진 — 묶음 {n_groups} · 쪽 {n_pages}, 이어서 다시 돌린다")
            return 3
        shots = v.show_data(data, gl, out, gid, max_pages=npg + 6)  # 쪽 끝 `12`(자동 넘김)도 있어 쪽 수는 어림 — 뒤에 빈 줄을 깔아 두므로 넘쳐 찍히지 않는다
        with open(out / "index.tsv", "a") as f:
            for k, name in enumerate(shots):
                f.write(f"{name}\t{key}\t{','.join(map(str, sel))}\t{k}/{npg}\n")
            if not shots:
                f.write(f"-\t{key}\t{','.join(map(str, sel))}\t못 찍음\n")
        with open(done_f, "a") as f:
            f.write(gid + "\n")
        n_groups += 1
        n_pages += len(shots)
        print(gid, key, len(sel), "줄 →", len(shots), "쪽", flush=True)
    print(f"끝 — 묶음 {n_groups} · 쪽 {n_pages}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
