"""대사 보기 — 장면 패키지의 메시지(덩이) 번호를 지정해 실제 대사창에 띄워 찍는다(마스터 10-19 「대사보기 만들어서 진행해」).

기전(헤드리스 실행기 `pcehl` + 상태 저장 편집 — 롬은 안 바뀐다, 디버그 빌드 하나면 된다):
  ① 디버그 메뉴 WARP(엘아스타)로 장면 도착 대사가 도는 중에 상태를 저장한다 — 서장 패키지(3)가 CD RAM 에 올라 있고 장면 VM 이 살아 있다.
  ② 도착 대사의 첫 메시지(상태의 `$3233`) 표 항목을 **보고 싶은 덩이의 압축 바이트**로 바꿔 놓는다(저장 상태 안의 CD RAM 을 고친다).
     덩이는 서로 독립이다(링 창을 덩이마다 새로 연다) — 어느 패키지 것이든 압축 바이트를 그대로 옮기면 된다.
     그 패키지의 지역 글리프 표(메시지 표 항목 0)도 같이 옮긴다.
  ③ 상태를 되살려 I 를 눌러 가며 쪽마다 찍는다. 끝 = `$3233` 이 바뀔 때(다음 도착 대사).
"""

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import package
import pcehl
from PIL import Image

HDR = bytes.fromhex("4c15604c15604c1560000001")  # 장면 패키지 머리(JMP $6015 ×3)
BANK = 8192
PKG_BASE_BANK = 0x73  # 서장 패키지가 올라오는 첫 뱅크
LOW_START, LOW_END = 0x6200, 0xC000
SKIP = 78  # 도착 장면이 메시지 20 을 부를 때의 건너뛸 줄 수(실측 — 덩이 안의 78번째 줄을 부른다. 앞에 빈 줄 78개를 둬야 내 줄이 첫 줄이 된다)


def boot_field(cue: str, bram: str) -> "pcehl.Emu":
    e = pcehl.Emu(cue, bram=bram)
    e.run(2900)
    e.hold("i")
    e.run(60)
    e.hold("i+run")
    e.run(10)
    e.hold("i")
    e.run(1500)
    e.hold(None)
    e.run(100)
    return e


def set_msg_stop(e: "pcehl.Emu") -> None:
    """메뉴 기타 → 시스템 → 메시지 속도를 「멈춤」(한 번에 표시)으로 바꾼다 — I 가 빠름→느림→멈춤으로 돈다(마스터 10-19). 값은 필드 RAM 이라 장면이 바뀌어도 남는다."""
    e.press("ii", 5, 60)
    for _ in range(5):
        e.press("down", 5, 15)
    e.press("i", 5, 40)
    for _ in range(2):
        e.press("down", 5, 15)
    e.press("i", 5, 40)
    for _ in range(5):
        e.press("down", 5, 15)
    for _ in range(2):
        e.press("i", 5, 25)
    for _ in range(4):  # 시스템 창 → 기타 → 메뉴 닫기(II)
        e.press("ii", 5, 30)
    e.run(60)


def warp_arrival(e: "pcehl.Emu", state_path: str) -> None:
    """디버그 메뉴 WARP → 엘아스타. 도착 대사가 시작되기 직전(몇 프레임)에 저장한다."""
    e.press("run+i+ii", 10, 30)
    e.press("i", 5, 30)
    e.press("down", 5, 20)
    e.hold("i")
    e.run(4)
    e.hold(None)
    e.run(60)  # 패키지가 CD 에서 다시 올라오는 검은 화면을 지나고(그 전에 고치면 덮인다), 보일 대사(메시지 번호 20)가 풀리기 전
    e.save(state_path)


def iso_pkg(iso: str, rel: int, sectors: int = 128) -> bytes:
    """만든 이미지(raw 2352B 섹터)에서 패키지 바이트를 읽는다."""
    out = bytearray()
    with open(iso, "rb") as f:
        for i in range(sectors):
            f.seek((common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF)
            out += f.read(common.USER)
    return bytes(out)


def _ptr(tab: list[int], k: int) -> int:
    return tab[k]


CODE_PATCHES: list[tuple[int, int, bytes]] = []  # (본 프로그램 뱅크, 뱅크 안 오프셋, 바이트) — 롬 고침을 빌드 전에 상태에서 시험한다


def patch_state(state: bytes, data: bytes, gl: bytes, first_msg: int) -> bytes:
    """저장 상태의 CD RAM 에서 장면 패키지의 메시지 `first_msg` 를 `data`(LZ 압축 덩이)로 바꾸고, 지역 글리프 표(메시지 표 항목 0)를 `gl` 로 바꾼다."""
    d = bytearray(state)
    h = d.find(HDR)
    assert h >= 0, "장면 패키지 머리를 상태에서 못 찾았다"
    pkg = bytes(d[h : h + 8 * BANK])
    T, _tab = package.msg_table(pkg)
    # 놓을 자리: 상대 뱅크 0~4(`$C000` 아래)만 포인터가 먹는다(실측 — 뱅크 6·7 로 옮기면 메시지가 빈다. 6·7 에는 이 패키지의 지역 글리프 표가 있다).
    # 도착 장면에서 내 덩이 뒤에 쓰는 메시지(25 …)는 내 덩이가 끝난 뒤라 상관없으니 `$6200` 부터 `$C000` 까지(약 23KB)를 쓴다.
    gl_at = LOW_START  # 지역 글리프 표는 한 뱅크 안(0x6000~0x7FFF)
    ch_at = gl_at + len(gl)
    assert ch_at + len(data) <= LOW_END, f"덩이 {len(data)}B 가 자리에 안 들어간다"
    d[h + gl_at : h + gl_at + len(gl)] = gl
    d[h + ch_at : h + ch_at + len(data)] = data

    def put(idx: int, off: int) -> None:
        bank, o = off >> 13, off & 0x1FFF
        d[h + T + 2 * idx] = o & 0xFF
        d[h + T + 2 * idx + 1] = (bank << 5) | (o >> 8)

    for bank, off, b in CODE_PATCHES:
        at = h + (bank - PKG_BASE_BANK) * BANK + off
        d[at : at + len(b)] = b
    if gl:
        put(0, gl_at)
    put(first_msg, ch_at)
    return bytes(d)


def has_cursor(img) -> bool:
    """대사창 안에 ▽(키 대기 커서 — 청록)가 보이나 — 글자가 다 나온 쪽의 근거다."""
    box = img[135:214, 34:206].astype(int)
    return int(((box[:, :, 2] > 180) & (box[:, :, 1] > 180) & (box[:, :, 0] < 140)).sum()) >= 4


def ink(img) -> int:
    """대사창 안쪽에 글자(흰·노랑) 픽셀이 몇 개인가 — 빈 창을 찍지 않으려는 것."""
    box = img[135:210, 34:206]
    return int(((box[:, :, 0] > 200) & (box[:, :, 1] > 200)).sum())


class Viewer:
    def __init__(self, cue: str, iso: str, bram: str, work: Path, stop: bool = False):
        self.iso = iso
        self.work = work
        work.mkdir(parents=True, exist_ok=True)
        self.s0_path = str(work / "arrival.state")
        e = boot_field(cue, bram)
        if stop:
            set_msg_stop(e)
        warp_arrival(e, self.s0_path)
        self.e = e
        self.s0 = Path(self.s0_path).read_bytes()
        self.first = 20  # 도착 장면의 눈에 보이는 대사(디버그 빌드 서장 패키지 — 원판 번호)
        self._pk: dict[int, bytes] = {}

    def pkg(self, rel: int) -> bytes:
        if rel not in self._pk:
            self._pk[rel] = iso_pkg(self.iso, rel)
        return self._pk[rel]

    def show_data(self, data: bytes, gl: bytes, out: Path, tag: str, max_pages: int = 30, box=(28, 128, 214, 214)) -> list[str]:
        """압축 덩이 `data` · 지역 글리프 표 `gl` 을 띄워 쪽마다 찍는다(대사창 부분만 잘라). 찍은 파일 이름 목록."""
        e = self.e
        st = patch_state(self.s0, data, gl, self.first)
        p = self.work / "cur.state"
        p.write_bytes(st)
        e.load(str(p))
        e.run(2)
        shots: list[str] = []
        seen = False
        recent: list[str] = []
        blank = 0
        for _ in range(max_pages * 60):
            e.run(10)
            h = hashlib.sha1(e.frame_img[135:210, 34:206].tobytes()).hexdigest()  # 대사창 안쪽만(뒤 그림은 움직인다)
            recent = (recent + [h])[-8:]
            cur = e.peek(0x3233, 1)[0]
            if cur == self.first:
                seen = True
            elif seen:  # 내 메시지가 끝나고 다음 메시지로 넘어갔다
                break
            has_ink = ink(e.frame_img) >= 25
            blank = 0 if has_ink else blank + 1
            if seen and len(shots) and blank > 30:  # 글이 다 나온 뒤 300프레임 동안 빈 창 — 끝(뒤에 빈 줄을 깔아 두어 더 안 나온다)
                break
            # 글자가 다 나왔다 = 최근 8번(80프레임)이 많아야 둘(▽ 깜박임)뿐이고 글자가 있다
            if seen and len(recent) == 8 and len(set(recent)) <= 2 and has_ink:
                f = out / f"{tag}_{len(shots):02d}.png"
                x0, y0, x1, y1 = box
                Image.fromarray(e.frame_img[y0:y1, x0:x1]).save(f)
                shots.append(f.name)
                if len(shots) >= max_pages:
                    break
                e.press("i", 4, 4)
                recent = []
        return shots
