"""맵 스크립트 옵코드 길이표 — `/0.BIN` 의 처리기를 읽어 **인자 길이**를 뽑는다.

    python3 games/ss-ed3/tools/script_ops.py --table      # 길이표
    python3 games/ss-ed3/tools/script_ops.py --walk MAP076 0x1bbc4   # 그 자리부터 해독
    python3 games/ss-ed3/tools/script_ops.py --path MAP076 trace.json 0x1bc74  # 실측 경로로 해독
    python3 games/ss-ed3/tools/script_ops.py --timeline MAP014 0x1779a  # FF 42 뒤 정적 시각표(초안 배치용)

🔴 **이 표가 있어야 스크립트를 안전하게 건드린다.** 길이를 모르면 삽입 지점을 잘못 잡아
   인자 한복판을 옵코드로 오해한다.

구조(실측 2026-08-30) — 디스패처 `0x0600fb50` 가 **16비트 낱말의 상위 바이트**로 갈래를
가르고 하위 바이트로 표를 찾는다:

    0xFD → 표 0x0600ce20 (6칸)    흐름 제어: 00=GOTO 01=CALL 02=RETURN 03=조건분기
    0xFF → 표 0x0600ce38 (144칸)  본체
    0xFE → 표 0x0600d078
    그 밖(0x02 등)은 표를 안 타고 별도 경로 — **대사 본문**이 여기 든다

⚠ 길이는 **처리기가 PC 전역(`0x0609408c`)에 되쓰는 값**으로 잰다. `add #-2` 는 「창이
  아직 준비 안 됐으니 다음 프레임에 다시」라는 **되돌림**이라 길이가 아니다(`FF 00`·`FF 02`).

🔴 **표 하나로는 안 끝난다 — 길이가 자리마다 다른 옵코드가 있다.** 「144칸을 다 채웠다」는
   과장이었다(2026-08-30 자기정정). 실측으로 확인된 가변 길이:

     · `FF 36` — 첫 낱말의 **상위 바이트가 3이면 2 바이트 더**(처리기 `0x06011a28` 에서
       `r0 = (word>>8)+1; if r0==4` 로 갈린다). 실측 2 · 4 둘 다 나온다.
     · ~~`FF 0A`~~ — **가변이 아니었다.** 처리기 `0x060118f4` 의 PC 저장은 `0x060119ca`
       한 곳이고 거기서 늘 `+10` 이다(앞의 `-2` 는 되돌림). 12 로 잘못 읽어서 그 뒤가
       통째로 어긋났던 것이다.
     · `FD 03`·`FD 04` — 목표 4 바이트 뒤에 **가변 길이 조건식**

⚠ 그래서 이 도구는 **고른 후킹 지점 둘레를 국소로 확인**하는 용도다. 파일 전체를 훑는
   용도로 믿지 않는다 — 조용히 어긋난 채 그럴듯한 결과를 낸다.

⚠ `FF FF`(=0xFFFF)는 표 두 곳 다 무효 주소라 dispatch 대상이 아니다 — **2 바이트 무동작
   (패딩)** 으로 보고 건너뛴다. 「루틴 끝 표식」으로 봤다가 뒤집었다(2026-08-30): `FF 0A` 를
   10 으로 바로잡으니 `FF FF` 뒤로 스크립트가 멀쩡히 이어진다.

⚠ 표 A 는 144 칸이 아니라 **208 칸**이다(`0x600ce38`~`0x600d174`). 0xFE 갈래 표로 잡았던
   `0x600d078` 이 그 안에 든다 — 경계를 처음에 잘못 그었다.

🔴 **`--walk` 로 뽑은 자리를 「실행된다」고 믿지 말 것.** 스크립트는 곧게 안 흐른다 —
   조건분기로 통째로 건너뛰는 구간이 있다. 실측(2026-08-31): V01 장면에서 `--walk` 가 낸
   후킹 후보 12 개 중 **실제로 실행된 건 2 개**뿐이었다. 나머지 10 개는 죽은 코드였고,
   자막을 걸어도 아무 일도 안 일어난다(그런데 빌드도 검사도 전부 통과한다).
   ⇒ **진짜 경로는 에뮬에서 읽어 온다.** 스크립트 영역에 **읽기 브레이크포인트**를 걸고
     장면을 돌리면 디스패처가 훑은 자리가 그대로 남는다:

       set_breakpoint(kind="read", memory_type="workraml",
                      start=<장면 시작>, end=<장면 끝>, pause_on_hit=False)
       ... 장면을 돌린다 ...
       poll_events(output_path="trace.json")

     그 JSON 을 `--path` 에 주면 **실행된 자리만** 해독한다.
   ⚠ 스크립트는 `0x00200000`(LWRAM)에 통째로 올라오므로 맵 오프셋 = `주소 - 0x200000` 이다.

⚠ 아직 못 읽는 것 둘 — 삽입 지점을 고를 땐 이 자리를 피한다:
  · `FD 03`·`FD 04`(조건분기) — 목표 4바이트 뒤에 **가변 길이 조건식**이 붙는다
    (평가기 `0x0600d528` 이 스크립트에서 더 읽어 간다)
  · **한 바이트짜리 옵코드** — `FD/FE/FF` 가 아닌 낱바이트(예: 본문 종결 뒤의 `09`)가
    있다. 디스패처의 「그 밖」 경로다.
  실측 연속 해독: MAP076 40개 · MAP031 56개 · MAP006 32개 (본문은 건너뛴다)

대사 한 칸의 생김새 — `voice_sub.py` 가 이걸 그대로 낸다:

    FF 02 00 02   창 설정
    FF 00         창 열기 (준비될 때까지 PC 를 되돌리며 기다린다)
    02 <화자ID>   본문 시작
    …본문…
    16            종결
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

PC_VAR = 0x0609408C
BASE_ROM = 0x06004000
TBL = {0xFD: (0x0600CE20, 6), 0xFF: (0x0600CE38, 144)}
#   눈으로 확인한 값 — 자동 추출이 틀리면 이쪽이 이긴다(실측 우선)
KNOWN = {
    0x00: 0, 0x02: 2, 0x07: 12, 0x0A: 10, 0x1F: 6, 0x22: 2, 0x23: 6,
    0x24: 2, 0x25: 4, 0x2E: 6, 0x30: 6, 0x33: 6, 0x35: 2, 0x36: 2,
    0x37: 2, 0x3D: 0, 0x42: 2, 0x46: 2, 0x0C: 4, 0x79: 4,
}  # fmt: skip


def _rom():
    with C.open_disc(1) as d:
        return d.read("/0.BIN")


def _lit(b, a):
    return struct.unpack(">I", b[a - BASE_ROM : a - BASE_ROM + 4])[0]


def arg_len(b, fa, md, span=0x140):
    """처리기가 PC 를 얼마나 미는가 — 되돌림(`add #-2`)은 세지 않는다."""
    pcreg, hold, best = set(), {}, 0
    for i in md.disasm(b[fa - BASE_ROM : fa - BASE_ROM + span], fa):
        m, o = i.mnemonic, i.op_str
        if m == "mov.l" and o.startswith("0x") and "," in o:
            src, dst = o.split(",")
            #   리터럴 풀이 파일 밖을 가리키면 그냥 건너뛴다(디스어셈이 데이터를 씹은 것)
            try:
                v = _lit(b, int(src, 16))
            except (ValueError, struct.error):
                continue
            if v == PC_VAR:
                pcreg.add(dst.strip())
        elif m == "mov.l" and "@" in o and not o.startswith("0x") and o.count(",") == 1:
            src, dst = (x.strip() for x in o.split(","))
            if src.startswith("@") and src.lstrip("@") in pcreg:
                hold[dst] = 0  # PC 값을 담았다
            elif dst.startswith("@") and dst.lstrip("@") in pcreg and src in hold:
                best = max(best, hold[src])
        elif m == "add" and o.startswith("#"):
            if o.count(",") != 1:
                continue
            n, r = o.split(",")
            r = r.strip()
            if r in hold:
                hold[r] += int(n[1:])
        elif m == "mov" and o.count(",") == 1:
            a1, a2 = (x.strip() for x in o.split(","))
            if a1 in hold:
                hold[a2] = hold[a1]
    return max(best, 0)


def table():
    from capstone import CS_ARCH_SH, CS_MODE_BIG_ENDIAN, CS_MODE_SH2, Cs

    b = _rom()
    md = Cs(CS_ARCH_SH, CS_MODE_SH2 | CS_MODE_BIG_ENDIAN)
    base, n = TBL[0xFF]
    out = {}
    for i in range(n):
        fa = _lit(b, base + i * 4)
        out[i] = KNOWN.get(i, arg_len(b, fa, md) if 0x6004000 <= fa < 0x6083000 else None)
    return out


def ops(name, start, count=40):
    """그 자리부터 옵코드를 이어 읽는다 — `(오프셋, 꼬리표, 인자 길이, 비고)` 를 낸다.

    정렬이 깨지거나 길이를 모르는 옵코드를 만나면 비고에 이유를 적고 멈춘다(인자 길이 None).

    ⚠ **대사 본문은 옵코드가 아니라 데이터다.** `02 <화자>` 블록과 `FF 87` 뒤 장 제목이
      스크립트 한복판에 그대로 박혀 있어서, 안 건너뛰면 거기서 매번 이탈한다.
      블록 경계는 `mapfile` 이 정본이라 그걸 그대로 쓴다.
    """
    import mapfile

    T = table()
    with C.open_disc(1) as d:
        b = d.read(f"/MAP/{name}.BIN")
    #   본문 구간 — {시작: 끝}
    #   ⚠ `mapfile` 의 `off` 는 **본문 첫 바이트**고 `head`(`02 <화자>`)는 그 앞 2 바이트다.
    #     걸어오는 쪽은 head 부터 밟으므로 두 자리 다 등록한다 — `FF 87`(장 제목)처럼
    #     head 자리가 앞 옵코드의 인자인 경우엔 본문에 곧장 도착한다.
    spans = {}
    for blk in mapfile.blocks(b):
        o, end = blk["off"], blk["off"] + len(blk["body"]) + 1
        spans[o - len(blk["head"])] = end
        spans[o] = end
    i, ok = start, 0
    while ok < count and i < len(b) - 2:
        if b[i] == 0xFD:
            #   ⚠ `FD 03`·`FD 04`(조건분기)는 목표 4바이트 **뒤에 가변 길이 조건식**이
            #     붙는다 — 평가기 `0x0600d528` 이 스크립트에서 더 읽어 간다. 아직 안 푼다.
            ln = {0: 4, 1: 4, 2: 0, 5: 0}.get(b[i + 1])
            tag = f"FD {b[i + 1]:02X}"
        elif b[i] == 0xFF and b[i + 1] == 0xFF:
            yield i, "FF FF", 0, "무동작"
            i += 2
            ok += 1
            continue
        elif b[i] == 0xFF:
            ln = T.get(b[i + 1])
            #   `FF 36` 은 첫 낱말 상위 바이트가 3 이면 2 바이트 더 읽는다
            if b[i + 1] == 0x36 and b[i + 2] == 0x03:
                ln = 4
            tag = f"FF {b[i + 1]:02X}"
        elif i in spans:
            t = b[i : spans[i] - 1].decode("cp932", "replace").lstrip("\x00\x02")
            yield i, "본문", spans[i] - i - 2, t[:28]
            i = spans[i]
            ok += 1
            continue
        else:
            yield i, f"{b[i]:02x}", None, "옵코드 아님 — 정렬 이탈"
            return
        if ln is None:
            yield i, tag, None, "길이 모름"
            return
        yield i, tag, ln, b[i + 2 : i + 2 + ln].hex(" ")
        i += 2 + ln
        ok += 1


def walk(name, start, count=40):
    """`ops()` 를 찍는다 — 몇 개를 이어 읽었나를 돌려준다."""
    n = 0
    for o, tag, ln, note in ops(name, start, count):
        if ln is None:
            print(f"  {o:#07x}  {tag}  ← {note}")
        elif tag == "본문":
            print(f"  {o:#07x}  [본문 {ln + 2}B] {note}")
            n += 1
        elif tag == "FF FF":
            print(f"  {o:#07x}  FF FF  (무동작)")
            n += 1
        else:
            print(f"  {o:#07x}  {tag} +{ln:<2} {note}")
            n += 1
    return n


def timeline(name, start, count=400):
    """`FF 42` 뒤를 **정적으로** 걸어 `FF 35` 누적 시각과 후킹 가능 자리를 낸다.

    `--path` 와 같은 셈(시각 = `FF 35` 프레임 합)을 추적 없이 한다 — 음성 장면은 `FF 42`
    뒤가 대체로 곧게 흐르므로(V01 실측: 실제 후킹 자리 전부가 정적 걸음 위에 있었다)
    **초안 배치**엔 이걸로 족하고, 조건분기(`FD 03`)에서 멈춘 뒤는 추적으로 잇는다.
    ⚠ 실행 여부는 보장 못 한다 — 정본에 올리기 전 인게임에서 본다.

    후킹 자리 = 옵코드 하나가 6B 이상이거나, 뒤에 `FF 35` 가 붙어 합쳐 6B 이상인 것.
    뒤에 붙은 대기는 `delay` 로 쪼갤 수 있다(`voice_sub.chain`).
    """
    import struct

    rows = list(ops(name, start, count))
    t = 0
    out = []  # (프레임, 오프셋, 길이, 대기 프레임, 설명)
    i = 0
    while i < len(rows):
        o, tag, ln, note = rows[i]
        if ln is None:
            print(f"  {t / 60:6.1f}초  {o:#07x}  {tag}  ← {note} — 여기서 멈춘다")
            break
        if tag == "본문":
            print(f"  {t / 60:6.1f}초  {o:#07x}  [본문] {note}")
            i += 1
            continue
        size = 2 + ln
        #   뒤따르는 FF 35 를 이 자리에 붙인다(대기 한복판 `delay` 자리)
        w, j = 0, i + 1
        while j < len(rows) and rows[j][1] == "FF 35":
            w += struct.unpack(">H", bytes.fromhex(rows[j][3]))[0] + 1
            size += 4
            j += 1
        if tag == "FF 35":
            w += struct.unpack(">H", bytes.fromhex(note))[0] + 1
        if size >= 6 and tag != "FF FF":
            mark = f"후킹 {size}B" + (f" · 대기 {w}f({w / 60:.1f}초)" if w else "")
            print(f"  {t / 60:6.1f}초  {o:#07x}  {tag} {note[:20]:20} ← {mark}")
            out.append((t, o, size, w, tag))
        elif w:
            print(f"  {t / 60:6.1f}초  {o:#07x}  {tag} 대기 {w}f")
        t += w
        i = j
    return out


def path(name, trace_json, start, as_timeline=False):
    """읽기 추적(JSON)에 실제로 나온 자리만 해독한다 — 죽은 코드를 안 센다.

    🔴 `as_timeline` 이면 **`--timeline` 과 같은 줄 꼴**로 낸다 — 그대로
    `work/review/voice/timeline/V0N.txt` 에 넣어 `voice_place.py --place` 가 읽는다.
    정적 걷기(`--timeline`)는 **정렬을 잃으면 거기서 멈춘다**(V02 는 `0x140a1` 에서 4 줄).
    실측 경로는 그 자리를 넘어가므로, 음성 장면은 **이쪽이 정본**이다(2026-09-07).
    ⚠ 추적 이벤트는 `{"address": <스크립트 절대주소>}` 꼴이다 — emucap 의 쓰기 BP 는
      `value` 에 그 주소를 싣는다(`address` 는 PC 전역 `0x0609408c`). 옮겨 담아서 준다.
    """
    import json
    import struct

    T = table()
    with C.open_disc(1) as d:
        b = d.read(f"/MAP/{name}.BIN")
    with open(trace_json, encoding="utf-8") as f:
        raw = json.load(f)
    ev = raw if isinstance(raw, list) else raw.get("events", raw)
    seen, t = [], 0.0
    for e in ev:
        o = e["address"] - 0x200000
        if not seen or seen[-1] != o:
            seen.append(o)
    if not as_timeline:
        print(f"실행된 자리 {len(seen)}개 · 시작 {start:#07x}")
    i = 0
    while i < len(seen):
        o = seen[i]
        if b[o] == 0xFF and b[o + 1] != 0xFF:
            ln = T.get(b[o + 1])
            if ln is None:
                i += 1
                continue
            tag = f"FF {b[o + 1]:02X}"
            size = 2 + ln
            if b[o + 1] == 0x35:
                f = struct.unpack(">H", b[o + 2 : o + 4])[0]
                if as_timeline:
                    #   ⚠ **홀로 선 `FF 35` 는 후킹 자리가 아니다** — 4B 라 트램펄린
                    #     (`FD 00` + BE32 = 6B)이 안 들어간다. `--timeline` 과 같은 규약으로
                    #     후킹 표시 없이 적는다(대기는 시각에만 쓰인다).
                    print(f"  {t:6.1f}초  {o:#07x}  {tag} 대기 {f}f")
                else:
                    print(f"  {t:6.1f}초  {o:#07x}  {tag} 대기 {f / 60:.1f}초")
                t += f / 60
            elif size >= 6:
                #   바로 뒤가 `FF 35` 면 그 대기를 이 자리에 달아 준다(`--timeline` 과 같은 셈)
                w = 0
                nxt = o + size
                if nxt + 4 <= len(b) and b[nxt] == 0xFF and b[nxt + 1] == 0x35:
                    w = struct.unpack(">H", b[nxt + 2 : nxt + 4])[0]
                if as_timeline:
                    mark = f"후킹 {size}B" + (f" · 대기 {w}f" if w else "")
                    print(f"  {t:6.1f}초  {o:#07x}  {tag:20} ← {mark}")
                else:
                    print(f"  {t:6.1f}초  {o:#07x}  {tag} {size}B  ← 후킹 가능")
            #   그 명령이 삼킨 자리는 건너뛴다
            while i < len(seen) and seen[i] < o + size:
                i += 1
            continue
        i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--walk", nargs=2, metavar=("MAP", "OFF"))
    ap.add_argument(
        "--path", nargs=3, metavar=("MAP", "TRACE", "START"), help="실측 경로(읽기 추적)로 해독"
    )
    ap.add_argument(
        "--as-timeline",
        action="store_true",
        help="`--path` 를 타임라인 줄 꼴로 (voice_place 가 읽는 형식)",
    )
    ap.add_argument(
        "--timeline",
        nargs=2,
        metavar=("MAP", "OFF"),
        help="FF 42 뒤를 정적으로 걸어 시각·후킹 자리",
    )
    a = ap.parse_args()
    if a.table:
        T = table()
        known = sum(1 for v in T.values() if v is not None)
        print(f"FF 갈래 144칸 · 길이를 얻은 것 {known}")
        row = []
        for i in range(144):
            v = T[i]
            row.append(f"{i:02X}:{'?' if v is None else v}")
            if len(row) == 12:
                print("   " + "  ".join(row))
                row = []
        if row:
            print("   " + "  ".join(row))
    if a.walk:
        n = walk(a.walk[0], int(a.walk[1], 0))
        print(f"\n연속 해독 {n}개")
    if a.timeline:
        timeline(a.timeline[0], int(a.timeline[1], 0))
    if a.path:
        name, trace, start = a.path
        path(name, trace, int(start, 0), as_timeline=a.as_timeline)
    if not (a.table or a.walk or a.path or a.timeline):
        ap.error("--table · --walk · --path · --timeline 중 하나")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
