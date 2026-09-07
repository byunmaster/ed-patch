# CLAUDE.md — 메가드라이브 『ドラゴンスレイヤー 英雄伝説』 (md-ed1)

**트랙: [kr]** — 일본 원판(G-5542, Sega 1994) 한글 번역 패치. 공용 규칙은 루트
[`CLAUDE.md`](../../CLAUDE.md), 진행 현황은 [`docs/status.md`](docs/status.md),
경위·삽질은 [`docs/devlog.md`](docs/devlog.md).

## 문안 방침 — PS1 은 **저본**이지 정본이 아니다 (유저 지시 2026-09-06)

ED1 문안은 **PS1 판**(1회차 인게임 QA 를 마치고 main 에 머지된 `ada1a54e`)을 참고한다 — 정본 자리는
`games/ps1-ed1+2/script/ED1SCN1~6.json` · `event.json` · `battle.json` · `ending_ed1.json` ·
`tools/patch_items.py`(낱말) · `tools/patch_sys_ui.py`(UI) · `tools/patch_gfx_cards.py`(장 카드).

🔴 **PS1 문안이 MD 원문과 다르면 원문을 따른다.** PS1 은 리메이크라 문장이 늘거나 줄고 의역이 있으며,
기종마다 없는 대사·있는 대사가 갈린다. 실제로 갈린 자리들:

- MD 에만 있는 자막(게일의 첫 대사 · 「하늘과 바다에 독을 뿌리고…」)은 **우리 문안을 유지**했다.
- 원문의 말투를 따랐다 — `手に入れました`·`見つけました` 는 존댓말, `気が付いた` 는 「깨어났다」
  (PS1 은 「정신을 차렸다」인데 MD 는 같은 장면에 `我に返った` 가 따로 있다).
- **칸이 표기를 이긴다** — 아이템 14B · 시스템 메시지 묶음이 제자리라 PS1 표기를 못 넣은 자리는
  `docs/status.md` 4f·7 에 적어 둔다.

## 이 게임이 다른 점

- **파일 시스템도 섹터도 없다 — 롬 2MB 하나다.** 좌표는 전부 **롬 오프셋 = 68000 주소**
  (매퍼 없음). 고치면 헤더 체크섬(0x18E)을 다시 맞춘다. 꼬리 0x1EC35C~ 81KB 가 FF 빈 공간이고,
  더 필요하면 **4MB 로 늘리는 길**이 열려 있다(MD 는 4MB 까지 매퍼 없이 잡힌다 — 헤더 ROM end 갱신).
- 🔴 **`.SMD` 확장자지만 인터리브가 아니다 — plain BIN.** `docs/ports-survey.md` 의 옛 판정
  (「인터리브 · 커스텀 문자 테이블 · SJIS 0」)은 이 파일을 디인터리브해 읽은 결과다. 실제로는
  **SJIS 평문 + 제어코드**(만트라 DOS·PC-98·PCE 와 같은 집안: `1E 화자 04` / `01` / `05` / `00`).
- **대본은 LZ 로 묶인 「씬 모듈」 225개다.** 모듈 = 헤더 + **68000 코드**(pc 상대 참조) +
  이벤트 자료 + 문안 스트림이 한 덩이. 코덱은 [`tools/lz.py`](tools/lz.py)(디컴프레서 `$0C9E` 이식,
  왕복 검증), 색인은 [`tools/archives.py`](tools/archives.py), 스트림 파서·재조립기는
  [`tools/scene.py`](tools/scene.py). 재조립은 **원본 바이트 제자리 + 스트림을 끝에 다시 쓰고 변위만
  돌리기**다(길이 변경 PoC 통과, `docs/status.md` 3·7절). 스트림의 끝은 00·06·07·**0A**·0D(0A 핸들러는 대기 뒤 07 핸들러로 끝난다 — 「계속」이 아니다), 페이지는 05.
- **글꼴은 롬 안에 있다** — 14×14 1bpp, 글리프마다 **채움 + 테두리 두 면**(56B). 리소스 6개,
  SJIS 표 1,459자(`tools/font.py`). ⚠ 글꼴은 **자리마다 다르다** — 대사 = 리소스 0(Galmuri11, 피치 12) · 자막 = **리소스 5 Galmuri14**(피치 14, `<fd85>`…`<fd80>`) · 타이틀 셀 = **네오둥근모 16px**. **방침 (b)(유저 확정 2026-09-05)**: 표 0 의 한자·가나 자리에
  **번역문이 쓰는 한글만**(≤1,370자, 코드 0x8A40~, `tools/hangul.py`) 넣는다. 4MB 확장은 SRAM 겹침으로
  불가. 글리프는 Galmuri11(대사창 피치 12px 라 14px 글꼴은 옆 글자를 갉는다).
- **씬 로더는 `$18460`** — 맵 ID 표 0x134DDC → 씬 번호 `$FF343C` → 블록을 **RAM 0xFF6650** 에 푼다.
  가시성·재압축·재배치 PoC 는 통과했다(`docs/status.md` 7절).
- **디버깅은 emucap(mednafen md)로 된다.** 브레이크포인트(exec·read·write, 값 필터)·상태 저장이
  다 걸린다 — 부팅 절차는 `docs/status.md` 6절.

## 원본

`originals/jp/md-ed1/*.zip` 안의 `.SMD` 하나(2,097,152B). 지문·헤더 상수는
[`tools/common.py`](tools/common.py). ⚠ **읽기 전용**이고, 쓰기 헬퍼는 재삽입 설계가 서기
전까지 두지 않는다(`docs/patcher-checklist.md` 2). emucap 은 zip 을 못 열어 `work/emu/ed1.bin` 사본을
쓴다 — **거기 쓰지 마라**(원본 사본이지 빌드가 아니다).
🔴 **실제로 한 번 덮여 있었다**(2026-09-07 발견 — sha1 이 빌드의 것이었다). 「원판과 대조한다」면서
그 파일을 띄우면 **우리 것끼리 대조**하게 된다. 대조 전에 **sha1 을 `tools/common.py` 의 원본 지문과
맞춰 본다**(`f67c9139…`). 안전한 사본은 `work/emu/ed1_orig.bin` 에도 있다.

## 도구

```bash
python3 games/md-ed1/tools/common.py             # 원본 지문 + 헤더 체크섬 + 꼬리 빈 공간
python3 games/md-ed1/tools/archives.py --check   # 아카이브 7 · 대본 225블록 663,896B · 전투 110
python3 games/md-ed1/tools/archives.py --dump    # work/derived/text/{script,battle}/NNN.{bin,txt}
python3 games/md-ed1/tools/archives.py --scan    # 색인 없이 LZ 체인 전수 (그래픽까지)
python3 games/md-ed1/tools/font.py --check       # 글꼴 리소스 6 · 형상
python3 games/md-ed1/tools/font.py --png out.png [--outline]
python3 games/md-ed1/tools/lz.py encode|decode <in> <out>
python3 games/md-ed1/tools/scene.py --check      # 스트림 2,750(끝 = 00·06·07·0A·0D) · 화자 태그 도달 · 항등 재조립 225
python3 games/md-ed1/tools/scene.py --dump 104   # 블록 104 의 스트림을 읽기 좋게
python3 games/md-ed1/tools/build.py              # ⭐ 정본(script/*.json) → work/build/<꼬리표>/ed1-kr.bin
python3 games/md-ed1/tools/build.py --check      # 빌드 없이 정본 게이트만
python3 games/md-ed1/tools/textmap.py --seed 104 # 블록 104 정본 초안(해시만) + work/derived 에 원문 골격
python3 games/md-ed1/tools/tables.py --check     # 고정 폭 표·00 묶음 분모 (아이템·주문·지명·메뉴·설정·HUD)
python3 games/md-ed1/tools/tables.py --seed      # textmap/names.json 초안 — glossary 로 채움
python3 games/md-ed1/tools/gfxtext.py               # 타이틀 메뉴 그래픽 셀(변형별 색)
python3 games/md-ed1/tools/vdp.py <덤프폴더> out.png [base] [width]  # 화면 재구성(⚠ VRAM 덤프는 바이트 스왑)
python3 games/md-ed1/tools/vdp.py <덤프폴더> --guess                # 네임테이블 base·width 추정
python3 games/md-ed1/tools/sysmsg.py --check/--seed  # 시스템 메시지 160 (lea/pea + 워드 표 0x73bc + 고정 스트림)
python3 games/md-ed1/tools/jp_left.py --check       # ⭐ 코드·전투 아카이브에 **남은 일본어**(참조로 못 찾는 자리를 잡는다)
python3 games/md-ed1/tools/check_text.py [-v]      # 문안 품질 — 원문 잔존 · 부호 규칙 · 표기 일치(PS1 정본·용어집)
python3 games/md-ed1/tools/battle.py --check/--seed    # 전투 아카이브 110블록 — 몬스터 이름 269 · 메시지 320(참조 없는 연쇄·레코드 영역 포함)
python3 games/md-ed1/tools/captions.py --check/--seed  # 오프닝 자막 8 · 엔딩 나레이션 11 · 엔딩 대사 20 (워드 스크립트 표)
python3 games/md-ed1/tools/ps1_reuse.py --stats  # PS1 번역 재사용 가능률 (⚠ PS1 QA 뒤에 채운다)
python3 games/md-ed1/tools/hangul.py --preview out.png "가나다"   # 글리프 미리보기
python3 games/md-ed1/tools/hangul.py --freeze     # 새 글자에 코드 부여 → textmap/hangul_codes.json (⚠ 코드는 세이브 호환 — 뒤에만 붙인다)
python3 games/md-ed1/tools/ending_preview.py       # 엔딩을 오프닝 자리에서 트는 시험용 롬(work/emu/ed1_ending.bin)
python3 games/md-ed1/tools/poc_visibility.py       # PoC 롬(work/emu/poc2.bin) — 글꼴 교체 + 블록 104 길이 변경·재압축·재배치
sh games/md-ed1/check.sh                         # ⭐ 이 게임의 커밋 전 게이트
```

⚠ **덤프는 `work/derived/` 로 나가고 커밋하지 않는다** — 원문이다(루트 「저작권」).
