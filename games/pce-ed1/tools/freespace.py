"""빈 공간 선언표 + 할당기 — 칸이 붙어 있어 못 늘리는 조각을 옮겨 실을 자리.

🔴 **빈 공간은 선언한 것만 쓴다.** 「0 이 이어져 있다」·「FF 가 이어져 있다」는 근거가 못 된다 —
PS1 에서 0 런 셋을 통과했는데 사운드 뱅크 안이었다(메모리 `free-space-vab-trap`), 이 게임에서도
`$3B00` 은 어느 덤프에서나 0 인데 게임이 썼다(hook.py 머리 주석). 그래서 자리마다
**원본 기대 바이트**와 **실측 근거**(쓰기·읽기 BP 를 건 채 한 바퀴)를 함께 적는다.
기대 바이트가 어긋나면 빌드가 멈춘다(다른 패치가 먼저 그 자리를 썼거나 원본이 다르다).

⚠ 같은 창이어야 한다 — 시스템 문구의 `0F 주소` 는 16비트 논리 주소라 **뱅크 0x6D($8000~)** 안의
자리만 쓸 수 있다. 전투 문구(C축)가 쓰면 그쪽 창의 자리를 따로 선언한다.
"""

from dataclasses import dataclass, field


@dataclass
class Span:
    bank: int
    off: int  # 뱅크 안 오프셋
    size: int
    fill: int  # 원본 기대 바이트(그 자리 전부가 이 값이어야 한다)
    why: str  # 실측 근거


# 뱅크 0x6D 끝 — FF 채움 224B. 근거(2026-09-26): 1장 필드·메뉴·종장 파티·HUD 수정본 네 덤프에서 FF 그대로
# + 쓰기 BP 를 건 채 한 바퀴(devlog 09-26 (8)).
BANK6D_TAIL = Span(0x6D, 0x1F20, 0xE0, 0xFF, "뱅크 끝 FF 224B — 덤프 넷 + 쓰기 BP 한 바퀴")

SPANS = [BANK6D_TAIL]


@dataclass
class Pool:
    """선언표의 자리에서 앞에서부터 잘라 준다. 할당은 결정적이다(입력 순서대로)."""

    spans: list[Span]
    used: dict[int, int] = field(default_factory=dict)  # spans 번호 → 쓴 길이

    def alloc(self, bank: int, n: int) -> tuple[Span, int] | None:
        """(자리, 뱅크 안 오프셋) — 없으면 None. 조각 사이는 한 칸 띄운다(앞 조각 끝을 흐리지 않게)."""
        for i, s in enumerate(self.spans):
            if s.bank != bank:
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
            b = bank_bytes_of(s.bank)[s.off : s.off + s.size]
            if b != bytes([s.fill]) * s.size:
                raise ValueError(f"빈 공간 선언이 원본과 다르다: 뱅크 {s.bank:#x}+{s.off:#x} ({s.why})")
