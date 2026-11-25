"""빈 공간 선언표 + 할당기 — 칸이 붙어 있어 못 늘리는 조각을 옮겨 실을 자리.

🔴 **빈 공간은 선언한 것만 쓴다.** 「0 이 이어져 있다」·「FF 가 이어져 있다」는 근거가 못 된다 —
PS1 에서 0 런 셋을 통과했는데 사운드 뱅크 안이었다(메모리 `free-space-vab-trap`), 이 게임에서도
`$3B00` 은 어느 덤프에서나 0 인데 게임이 썼다(hook.py 머리 주석). 그래서 자리마다
**원본 기대 바이트**와 **실측 근거**(쓰기·읽기 BP 를 건 채 한 바퀴)를 함께 적는다.
기대 바이트가 어긋나면 빌드가 멈춘다(다른 패치가 먼저 그 자리를 썼거나 원본이 다르다).

⚠ 창이 맞아야 한다 — 시스템 문구의 `0F 주소` 는 16비트 논리 주소라, 메시지 엔진이 도는 동안 **늘 같은 뱅크가
걸린 창**의 자리만 쓸 수 있다: 뱅크 0x6D(MPR4 `$8000~`) · 뱅크 0x74(MPR6 `$C000~`, 이름표 `$C330`·전투 블록
`$C400` 을 인터프리터가 이미 읽는 창 — 10-07 BP 실측에서 메시지마다 MPR6=0x74).
"""

from dataclasses import dataclass, field


@dataclass
class Span:
    bank: int
    off: int  # 뱅크 안 오프셋
    size: int
    fill: (
        int | None
    )  # 원본 기대 바이트(그 자리 전부가 이 값) — None 이면 원본 바이트 그대로가 기대값(안 쓰는 옛 자료)
    why: str  # 실측 근거
    window: int = 0x8000  # 메시지 엔진이 이 뱅크를 거는 논리 주소(`0F` 대상 = window + off)


# 뱅크 0x6D 끝 — FF 채움 224B. 근거(2026-09-26): 1장 필드·메뉴·종장 파티·HUD 수정본 네 덤프에서 FF 그대로
# + 쓰기 BP 를 건 채 한 바퀴(devlog 09-26 (8)).
import hud_half  # noqa: E402 — 앞쪽 `hud_half.CODE_LEN` B 는 HUD 이름 렌더러 꼬리 코드 자리
import list_strip  # noqa: E402 — 그 뒤 `list_strip.CODE_LEN` B 는 날개 목록 앞 공백 걷기 루틴 자리
import debug_labels  # noqa: E402 — 그 뒤 `debug_labels.CODE_LEN` B 는 디버그 화면 행 이름·ON/OFF 쌍 자리(11-25)

_FRONT = hud_half.CODE_LEN + list_strip.CODE_LEN + debug_labels.CODE_LEN

BANK6D_TAIL = Span(
    0x6D, 0x1F20 + _FRONT, 0xE0 - _FRONT, 0xFF, "뱅크 끝 FF 224B 중 앞 hud_half·list_strip 자리를 뺀 나머지 — 덤프 넷 + 쓰기 BP 한 바퀴"
)

# 뱅크 0x74 끝 — FF 채움 346B(+0x1EA6~). 근거(2026-10-07): 부팅 → 파일 로드 → 필드 → 전투 → 맵 전환(루디아) →
# 메뉴·도구 사용 동안 물리 쓰기 BP(0xE9EA6~0xE9FFF) 0회 · RAM 값 FF 그대로(devlog 10-07 (3)).
import defeat_strip  # noqa: E402 — 앞쪽 `defeat_strip.CODE_LEN` B 는 패배 귀환 확인창 앞 공백 걷기 루틴 자리

BANK74_TAIL = Span(
    0x74,
    0x1EA6 + defeat_strip.CODE_LEN,
    0x15A - defeat_strip.CODE_LEN,
    0xFF,
    "뱅크 끝 FF 346B 중 앞 defeat_strip 자리를 뺀 나머지 — 쓰기 BP 한 바퀴(10-07)",
    0xC000,
)

# 뱅크 0x70 FF 패딩의 **조각 보관소**(4-17 확대 — 위 두 창 풀이 약 50B 모자랐다). 엔진이 글을 읽는 동안 이 뱅크는 창에 없으므로 `0F` 로 곧장 못 간다 —
# `hook` 의 `0F` 스텁이 MPR3 에 잠깐 걸어 RAM 버퍼로 복사한다(포인터 `$5C00~`). 읽는 쪽은 이 스텁뿐이다.
# 근거: 같은 뱅크 FF 패딩(`$7B4A~` 1206B)에 띠 폴백·디버그 코드가 이미 산다(독약 시험 선례, devlog 11-08) + 이 자리의 독약 시험(아래 devlog).
import hook  # noqa: E402

BANK70_STORE = Span(
    hook.FRAG_BANK,
    hook.STORE_OFF,
    hook.STORE_SIZE,
    0xFF,
    "뱅크 0x70 FF 패딩 256B — 독약 시험(표지 바이트로 채운 사본 vs 원본 화면·동작 동일)",
    0x4000,  # `0F` 마커 포인터 = 0x4000 + off (실제 읽기는 스텁이 MPR3 로 `0x6000 + off`)
)

SPANS = [BANK6D_TAIL, BANK74_TAIL, BANK70_STORE]
MEASURED_HUD_TAIL = 905  # 09-27 실측 범위의 시작(묶음 안 오프셋) — 물리 0xDAEB5~0xDAF20


def spans() -> list[Span]:
    """빌드가 쓰는 선언표 — 고정 자리 + HUD 묶음 꼬리(새 압축본 뒤, 길이는 HUD 굽기 결과로 정해진다).

    HUD 꼬리 근거(2026-09-27): 읽기·쓰기 BP 를 건 채 부팅·파일 로드(해제기 실행)·경험치표시 전환 두 번·다른 파티 세이브
    게임 안 LOAD — **읽기 0 · 쓰기는 부팅 CD 적재뿐**. ⚠ 전투·맵 전환은 아직. 옛 압축본 바이트가 원본에 남아 있으므로
    `fill=None` — 기대값은 원본 바이트 그대로(HUD 굽기는 이 꼬리를 안 쓴다, `hud_plate.apply`).
    """
    import hud_plate

    n = hud_plate.compressed_len()
    start = max(
        n + 1, MEASURED_HUD_TAIL
    )  # 실측한 범위 안에서만 — 압축본이 줄어도 안 잰 자리는 안 쓴다
    tail = Span(
        0x6D,
        hud_plate.BANK_BLOCK_OFF + start,
        hud_plate.BLOCK_LEN - start,
        None,
        "HUD 묶음 꼬리 — 읽기·쓰기 BP 한 바퀴(부팅·로드·EP 전환·파티 LOAD)",
    )
    return SPANS + [tail]


@dataclass
class Pool:
    """선언표의 자리에서 앞에서부터 잘라 준다. 할당은 결정적이다(입력 순서대로)."""

    spans: list[Span]
    used: dict[int, int] = field(default_factory=dict)  # spans 번호 → 쓴 길이

    def alloc(self, banks, n: int) -> tuple[Span, int] | None:
        """(자리, 뱅크 안 오프셋) — 없으면 None. 조각 사이는 한 칸 띄운다(앞 조각 끝을 흐리지 않게).
        `banks` = 받을 수 있는 뱅크(하나 또는 여럿, 선언 순서대로 채운다)."""
        banks = (banks,) if isinstance(banks, int) else tuple(banks)
        for i, s in enumerate(self.spans):
            if s.bank not in banks:
                continue
            u = self.used.get(i, 0)
            gap = 1 if u else 0
            if s.size - u - gap >= n:
                self.used[i] = u + gap + n
                return s, s.off + u + gap
        return None

    def check_original(self, bank_bytes_of) -> None:
        """선언한 자리가 원본에서 정말 fill 인가 — 아니면 빌드를 멈춘다."""
        for s in self.spans:
            if s.fill is None:
                continue
            b = bank_bytes_of(s.bank)[s.off : s.off + s.size]
            if b != bytes([s.fill]) * s.size:
                raise ValueError(
                    f"빈 공간 선언이 원본과 다르다: 뱅크 {s.bank:#x}+{s.off:#x} ({s.why})"
                )
