"""디버그 진입키 — 필드에서 SELECT 를 1초 누르고 있으면(RUN 없이 — RUN+SELECT 는 원판 소프트 리셋) 「기타 → 디버그」 화면이 바로 열린다(마스터 10-24 「다른 기종 스타일도 추가해줘」).

원판 공식 경로(필드 II → 기타 → 디버그, `build.py` 그룹 `debug`)는 그대로 둔다. 이 키는 같은 화면을 한 번에 여는 지름길이다.
🔴 RUN+I+II 는 충돌해서(II 가 6프레임 안에 메뉴, I 가 발밑 행동) 못 쓰고, SELECT·RUN 은 필드·메뉴·전투·대사에서 원판이 아무 반응도 안 한다
(실측 10-24, status). 원판의 RUN+SELECT 리셋 조합은 카드 BIOS 가 안 건다(헤드리스 75프레임 누름에서 리셋 없음).

동작:
  · `tick`(VBlank 마다 — 후킹 틱 트램펄린 끝에서 부른다, MPR3 에 글리프 뱅크 1 을 걸고): 패드(`$2228`)가 SELECT **만**(방향키 무시 — RUN 이 섞이면 원판 소프트 리셋)이면
    카운터를 올려 60프레임(1초)에 `req` 를 세우고 II 를 눌린 것으로 꾸며(`$2228`·`$2232`) 필드가 주메뉴를 열게 한다. 키를 뗄 때 `req` 를 거둔다(옛 「열두 프레임 뒤」 시한은 뺐다 — 느린 장면은 메뉴가 그 안에 안 열려 디버그가 안 열렸다. 메뉴가 안 열리는 자리에
    요청이 남지 않게). 다른 버튼이 섞이거나 떼면 카운터를 0 으로. 1초 미만은 아무 일 없다. 모드 바이트 검사는 없다(`$CC` 는 모드가 아니라 상태 표 인덱스 — 10-29).
  · `menu`(주메뉴 `$6000` 뱅크 0x6E 맨 앞 복사 세 쌍 자리에서 부른다, MPR4 에 글리프 뱅크 1): 원래 하던 복사를 TII 로 하고 `req` 가 있으면 C=1 로
    돌려준다. **MPR4 를 되돌린 뒤** 부른 쪽이 「기타」 메뉴의 디버그 항목 핸들러(`$64CB`)를 직접 부른다 — 서브메뉴 글을 MPR4 의 글자 뱅크에서 읽기 때문.
    디버그 화면을 닫으면 주메뉴가 이어진다(II 로 닫는다).
상태 두 바이트(`CNT`·`REQ`)는 후킹 페이로드 안 FRAMECNT 곁의 빈 칸(`$247A·$247B`). 코드 자리는 글리프 뱅크 1 의 동적 칸 16~23(144B —
씬 하나가 쓰는 동적 글자는 ≤15 라 안 쓰이고, 빌드가 ≤16 을 지킨다). 틱이 일반 필드에서도 돌도록 씬을 열 때마다(`splitload.check`) 틱 트램펄린을 건다.
🔴 교훈(10-24): ① 매핑을 바꾼 창에서 **그 창의 코드를 실행하는 채로 되돌리면** 다음 명령을 엉뚱한 뱅크에서 읽는다 — 복원은 늘 부른 쪽(창 밖)에서 한다
② 글리프 뱅크 1 꼬리의 「0 이 이어진 곳」은 반각 표(`hook.HALF_TAB`)였다 — 빈 곳 판정은 0 이 아니라 쓰는 쪽을 찾아서.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font

BANK = font.GLYPH_BANK0 + 1  # 글리프 뱅크 1(0x87) — 꼬리 빈 자리
OFF = font.glyph_at(font.DYN0) % 0x2000 + font.DYN_RESERVE_FROM * font.PACKED_BYTES  # 글리프 뱅크 1 의 동적 칸 꼬리(쓰이지 않는 칸 — `font.DYN_RESERVE_FROM` 부터)
ORG = 0x8000 + OFF  # MPR4 창 기준(`menu`) — 틱은 같은 코드를 MPR3 창(`ORG - 0x2000`)으로 부른다
ROOM = (font.KAGI_SLOT0 - font.DYN_RESERVE_FROM) * font.PACKED_BYTES  # 뒤 둘(`font.KAGI_SLOT0`~)은 「」 글리프가 쓴다
CNT = 0x247A  # FRAMECNT+6 — hook 이 이 모듈을 부르는 순환 임포트를 피하려고 값으로 둔다(아래 `_asm` 이 대조)
REQ = 0x247B
PAD = 0x2228
PAD2 = 0x2232
HOLD = 60
SELECT_ENTRY_MASK = 0xFF  # 🔴 마스터 11-26 「시스템메뉴에 디버그가 생겼으니 셀렉트키로 호출하던 건 제거」 — `AND #$0F` 결과는 0xFF 일 수 없어 SELECT 길게 누름이 더는 안 센다(원판 SELECT 동작). 옛 값 0x04 = SELECT 만

MENU_SITE_OFF = 0x0000  # 뱅크 0x6E(주메뉴) 안 오프셋 — `$6000`
MENU_SITE_OLD = bytes.fromhex("adb3c18dae37adb4c18daf37adb5c18db037")  # LDA $C1B3 STA $37AE … ×3


def _asm():
    import hook

    assert (hook.FRAMECNT + 6, hook.FRAMECNT + 7) == (CNT, REQ)
    a = hook.Asm(ORG)
    # tick — A·X·Y 는 IRQ 핸들러가 저장했다
    a.label("tick")
    a.op("LDA", "abs", CNT)
    a.op("CMP", "imm", HOLD - 1)
    a.op("BCS", "rel", "post")
    # ── 누르는 중(아직 안 지핌): SELECT 만 눌렸으면 센다
    a.op("LDA", "abs", PAD)
    a.op("AND", "imm", 0x0F)  # 방향키는 무시 — I·II·SELECT·RUN 만 본다
    a.op("CMP", "imm", SELECT_ENTRY_MASK)  # SELECT 만(RUN 이 섞이면 원판 소프트 리셋 조합 — 10-28 마스터 「enter 먼저 누르고 left shift 면 리셋」)
    a.op("BNE", "rel", "clr")
    a.op("INC", "abs", CNT)
    a.op("RTS")
    # ── 지핌(CNT = HOLD−1 … HOLD+4): II 를 여섯 프레임 꾸민다(셋 이하면 필드가 못 받는다 — 시험) + 요청
    a.label("post")
    a.op("CMP", "imm", HOLD + 5)
    a.op("BCS", "rel", "real")
    a.op("INC", "abs", CNT)
    a.op("LDA", "imm", 0x02)  # II — REQ 도 같은 값(0 이 아니면 요청)
    a.op("STA", "abs", REQ)
    a.op("STA", "abs", PAD)
    a.op("STA", "abs", PAD2)
    a.op("RTS")
    # ── 꾸밈이 끝난 뒤: 패드를 「SELECT 만」으로 다시 보지 않는다 — 꾸민 II 가 패드 변수에 남아 있을 수 있어서다(집 안처럼 패드 갱신이 드문 장면에서 다음 틱에 「SELECT 만」이 깨져
    #    요청이 메뉴가 열리기 전에 거둬졌다 — 마스터 11-16 마스쿤 집 안: 주메뉴만 열리고 디버그가 안 열렸다. 실측: 지핀 직후 CNT 가 리셋). 다 뗐을 때(눌린 단추 0)만 거둔다.
    #    CNT 는 HOLD+5 에서 멈춘다 — 같은 누름에 다시 안 열린다. 메뉴가 안 열리는 자리(대사·전투)에서 누른 채면 요청이 남지만 뗄 때 거두고 `menu` 는 메뉴를 열 때만 부른다.
    a.label("real")
    a.op("LDA", "abs", PAD)
    a.op("AND", "imm", 0x0F)
    a.op("BNE", "rel", "done")
    a.label("clr")
    a.op("STZ", "abs", CNT)
    a.op("STZ", "abs", REQ)  # 떼면 요청도 거둔다
    a.label("done")
    a.op("RTS")  # 🔴 매핑 복원은 부른 쪽(`entry`)이 한다 — 이 코드가 도는 창을 이 안에서 되돌리면 다음 명령을 엉뚱한 뱅크에서 읽는다
    # menu — 주메뉴 맨 앞(`$6000`, 뱅크 0x6E)에서 부른다: 원래 하던 일(`$C1B3~5` → `$37AE~B0` 복사)을 그대로 한 뒤 디버그 요청이면 「기타」 서브메뉴를 연다
    a.label("menu")
    a.tii(0xC1B3, 0x37AE, 3)
    a.op("LDA", "abs", REQ)
    a.op("BEQ", "rel", "none")
    a.op("STZ", "abs", REQ)
    a.op("SEC")  # C=1 → 부른 쪽이 「기타」 서브메뉴(`$6201`)를 연다 — 여기서 부르면 MPR4(글자 뱅크)가 글리프 뱅크라 서브메뉴 글이 빈다
    a.op("RTS")
    a.label("none")
    a.op("CLC")
    a.op("RTS")
    return a


def code() -> bytes:
    b = _asm().bytes()
    assert len(b) <= ROOM, (len(b), ROOM)
    return b


def labels() -> dict:
    a = _asm()
    a.bytes()
    return a.labels


def tramp(target: int) -> bytes:
    """MPR4 에 글리프 뱅크 1 을 걸고 `target` 을 부른 뒤 돌려놓는다(13B)."""
    import hook

    a = hook.Asm(0)
    a.op("TMA", "tma", 4)
    a.op("PHA")
    a.op("LDA", "imm", BANK)
    a.op("TAM", "tam", 4)
    a.op("JSR", "abs", target)
    a.op("PLA")
    a.op("TAM", "tam", 4)
    return a.bytes()


def entry() -> bytes:
    """틱 트램펄린(`hook.tick_routine`) 끝 16B — MPR3 를 저장하고 글리프 뱅크 1 을 건 뒤 `tick` 을 **JSR** 로 부르고, 돌아와서 MPR3 를 되돌린 다음
    원래 대상(`$57A5`)으로 `JMP`. (먼저 JMP 로 가서 안에서 복원하면 안 된다 — 복원하는 순간 그 창에서 다음 명령을 읽는다.)
    MPR3 는 사운드 드라이버가 IRQ 안에서 쓰는 창이라 같은 저장·복원 패턴이 이미 있다(`$57D7`)."""
    import hook

    a = hook.Asm(0)
    a.op("TMA", "tma", 3)
    a.op("PHA")
    a.op("LDA", "imm", BANK)
    a.op("TAM", "tam", 3)
    a.op("JSR", "abs", labels()["tick"] - 0x2000)  # MPR3($6000) 창 주소
    a.op("PLA")
    a.op("TAM", "tam", 3)
    a.op("JMP", "abs", hook.IRQ_ORIG)
    return a.bytes()


def menu_site() -> tuple[bytes, bytes]:
    """(기대 원본 18B, 새 18B) — 주메뉴 맨 앞 복사 세 쌍 자리를 트램펄린 + 「요청이면 `$6201`」로(복사는 `menu` 가 TII 로 한다).
    `$6201` 은 MPR4 의 글자 뱅크에서 서브메뉴 글을 읽으므로 **MPR4 를 되돌린 뒤** 부른다."""
    a = tramp(labels()["menu"])
    a += bytes([0x90, 0x03, 0x20, 0xCB, 0x64])  # BCC +3 · JSR $64CB (「기타」 메뉴의 디버그 항목 핸들러 — 자기 화면을 직접 그린다)
    assert len(a) == len(MENU_SITE_OLD), len(a)
    return MENU_SITE_OLD, a
