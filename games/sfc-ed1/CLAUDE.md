# CLAUDE.md — 슈퍼패미컴 『ドラゴンスレイヤー英雄伝説』 (sfc-ed1)

**트랙: [kr]** — 일본 원판(에포크 1992, 8Mbit LoROM) 한글 번역 패치. 공용 규칙은 루트
[`CLAUDE.md`](../../CLAUDE.md), 진행 현황은 [`docs/status.md`](docs/status.md),
경위·삽질은 [`docs/devlog.md`](docs/devlog.md).

## 이 게임이 다른 점

- **한자가 없다.** 대사는 **가나 전용 1바이트 코드**($00~$CE)다. 글꼴은 롬 안의 **1bpp 8×8
  타일 시트**($18:E02C, 글자 하나 = 위·아래 타일 둘 = 8×16)이고 VRAM 에 상주한다.
  ⇒ 한글은 8×16 한 칸에 안 들어간다. **2칸(16×16) 한 글자**로 가면 한 줄 17칸이 8자가 되고,
  8×16 반각 한글을 새로 그리면 자수는 유지되지만 가독성이 문제다 — 설계 판단이 남아 있다
  (「남은 일」). 어느 쪽이든 글꼴 자리(VRAM 타일 $000~$1DF, 2bpp 추정)와 코드 공간($00~$CE,
  207자)이 병목이라 **동적 글리프 로딩**이 유력하다.
- **대본은 롬에 평문**이다(압축 없음). 3바이트 포인터 표 4벌(3,339 + 433 + 343 + 19건)이
  $05·$07~$0B·$1E 뱅크의 문안을 가리킨다. 사전 치환(`$D0 xx` 인명 · `$D1` 지명 · `$D2` 아이템 ·
  `$D3` 몬스터 · `$D5` 시스템 문장)이 많아 **문장 안에 이름이 코드로 박혀 있다** — 조사 처리는
  런타임 훅이 필요하다(PS1 의 동적 조사 훅과 같은 문제).
- **메시지가 스크립트다.** 조건(`$F0~$F6 flag`)·분기(`$F9/$FA`)·호출(`$FB/$FC`)·네이티브 코드
  호출(`$EE addr24`)이 문안 사이에 끼어 있다. 선형 덤프는 되지만 **재삽입 때 분기 오프셋을
  다시 계산해야 한다**(구조 계약 — `docs/patcher-checklist.md` 12).
- **롬 소스 파일명이 남아 있다** — `$Header: message.asm,v 2.26 …` 같은 RCS 태그가 모듈마다
  박혀 있어 코드 지도가 공짜다(`docs/status.md` 2절).
- **디버거는 아직 없다.** emucap 의 mednafen 빌드에 SNES 가 안 들어 있고 Mesen2 어댑터는 이
  머신에 안 깔렸다(.NET 필요). 지금까지는 전부 정적 분석이다 — 인게임 확인은 「남은 일」.

## 원본

`originals/jp/sfc-ed1/*.zip`(zip 째, 안에 1,048,576B `.sfc`, 복사기 헤더 없음). 지문·상수는
[`tools/common.py`](tools/common.py). ⚠ **읽기 전용**이고, 쓰기 헬퍼는 재삽입 설계가 서기
전까지 두지 않는다(`docs/patcher-checklist.md` 2).

## 도구

```bash
python3 games/sfc-ed1/tools/common.py           # 원본 지문 + 내부 헤더
python3 games/sfc-ed1/tools/text.py --check     # 포인터 표 4벌 · 사전 6벌 · 글자 수 · 문자표 불변식
python3 games/sfc-ed1/tools/text.py --dump      # work/derived/text/ 에 대본(11,271 조각)·사전 덤프
python3 games/sfc-ed1/tools/text.py --msg 5     # 메시지 하나 풀어 보기
python3 games/sfc-ed1/tools/script.py --roundtrip   # 라벨 모델 왕복(본체 153KB 바이트 동일)
python3 games/sfc-ed1/tools/build.py            # 원문을 확장 뱅크로 옮긴 2MB 롬(+창 넓히기·한글 메뉴 PoC) → work/build/<꼬리표>/
python3 games/sfc-ed1/tools/build.py --project  # 번역문을 인코딩해 뱅크에 담아 본 분량 투영(파일 안 남김)
python3 games/sfc-ed1/tools/units.py --stats --dump # 번역 단위·조각·조사 수요 → work/derived/units/
python3 games/sfc-ed1/tools/tm.py --readings --dump # PS1 번역본과 읽기 유사도 정렬 → work/derived/tm/
python3 games/sfc-ed1/tools/textmap.py --check  # 번역 정본(textmap/segments.json)의 토큰 계약
python3 games/sfc-ed1/tools/hangul_font.py --from-ps1 --preview x.png  # 한글 글리프 뱅크(Neo둥근모)
sh games/sfc-ed1/check.sh                       # ⭐ 이 게임의 커밋 전 게이트
```

⚠ **덤프는 `work/derived/` 로 나가고 커밋하지 않는다** — 원문이다(루트 「저작권」). 커밋되는 번역 정본은
`textmap/segments.json`(조각 sha1 → 한국어 + 상태, `docs/status.md` 10절)이다.
⚠ `tm.py` 는 **PS1 워크트리**의 번역본·JP 덤프를 읽는다(이 트리의 `games/ps1-ed1+2` 사본은 낡았다) —
pykakasi 가 `.venv` 에 있어야 한다.

## 좌표 규약 — `$뱅크:주소`(LoROM)

롬 안 자리는 **`$bb:aaaa`** 로 적는다(뱅크 $00~$1F, 주소 $8000~$FFFF). 파일 오프셋은
`bank × $8000 + (addr − $8000)` 이고 `common.snes2off()` 가 정본이다. 파일 오프셋만 적힌
상수는 뱅크 경계에서 조용히 틀린다 — 둘을 섞지 않는다. RAM 은 `$7E:xxxx`(직접 페이지 상수는
`$xxxx`).
