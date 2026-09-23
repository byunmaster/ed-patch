# CLAUDE.md — PC엔진 CD-ROM² 『드래곤 슬레이어 영웅전설』 (pce-ed1)

**트랙: [kr]** — 일본 원판(HCD1020, Hudson 1991) 한글 번역 패치. 공용 규칙은 루트
[`CLAUDE.md`](../../CLAUDE.md), 진행 현황은 [`docs/status.md`](docs/status.md),
**번역·표기 방침은 [`docs/policy.md`](docs/policy.md)**, 경위·삽질은 [`docs/devlog.md`](docs/devlog.md).
🔴 대사 문안을 쓰거나 검수하기 전에 스킬 `rpg-translate` 와 `docs/policy.md` 를 연다.
🎮 **인게임을 켜기 전에 [`docs/playbook.md`](docs/playbook.md)** — 조작·부팅 순서·전투가 나는 자리와 안 나는 자리. 없어서 회차를 한 번 접었다(2026-09-07).

## 이 게임이 다른 점

- 🔴 **글꼴이 디스크에 없다 — 시스템 카드(BIOS) 것이다.** 게임은 글자마다 BIOS 의
  `EX_GETFNT`($E060)를 불러 12×12 글리프를 받아 타일로 굽는다. PC-98(CGROM)과 같은 상황이라
  폰트 작업은 「변환」이 아니라 **「후킹 + 한글 글리프를 RAM 에 상주」**다. 이스 IV 한글판처럼
  BIOS 에 얹는 길도 있지만 그건 실기 배포 조건이 하나 는다(`docs/reference/msx-and-ports.md` 1).
- **파일 시스템이 없다.** ISO9660 이 아니고 로더가 트랙 상대 섹터 번호로 직접 읽는다 ⇒
  파일 교체가 아니라 **섹터 패치**다. 좌표 규약은 아래.
- **대본은 SJIS 평문이지만 LZ 로 묶여 있다.** 씬 블록(이벤트 코드 + 대본) 220개가 컨테이너
  24개에 압축돼 있고, 게임이 RAM 에 풀어 놓는다. 코덱은 [`tools/lz.py`](tools/lz.py)(왕복 검증됨).
  제어코드는 만트라 DOS·PC-98 과 같은 집안(`1F 화자 04` / `01` / `05` / `00`).
- **음성이 있다.** 데이터 트랙의 3/4(rel ~1,750 이후, ~14MB)가 ADPCM 이다. 텍스트 없이
  음성만 나가는 장면이 있으면 그건 kr 이 아니라 mod 다(루트 ROADMAP).
- **디버깅은 emucap(mednafen pce)로 된다.** 브레이크포인트·트레이스가 다 걸린다 —
  부팅 절차는 `docs/status.md` 5절.

## 원본

`originals/jp/pce-ed1/` — redump `.cue`+`.iso`(2352B raw, 22트랙). 지문·경로 정본은
[`tools/common.py`](tools/common.py). ⚠ **읽기 전용**이고, 쓰기 헬퍼는 재삽입 설계가 서기
전까지 두지 않는다(`docs/patcher-checklist.md` 2).
⚠ 같은 폴더의 `.ccd/.img/.sub` 세트는 중복 덤프라 도구가 안 읽는다. 원본 cue 는 ISO 파일명을
대문자로 적어 리눅스에서 못 여니, 실행용 사본은 `work/emu/`(하드링크 + cue)다 — **거기 쓰지 마라.**

## 도구

```bash
python3 games/pce-ed1/tools/common.py              # 원본 지문 + IPL + 트랙 22 복제 확인
python3 games/pce-ed1/tools/containers.py --check  # 컨테이너 24 · 블록 332 · 고유 220 · 13.3만 자 + 참조표 분모
python3 games/pce-ed1/tools/containers.py --dump   # work/derived/text/ 에 블록(.bin)·대본 덤프
python3 games/pce-ed1/tools/lz.py encode <in> <out>
python3 games/pce-ed1/tools/build.py [--edits work/edits_poc.json]   # work/build/<꼬리표>/ed1.iso+cue
python3 games/pce-ed1/tools/ram_map.py <dump>...       # 워크 RAM 빈 자리(덤프 겹치기)
python3 games/pce-ed1/tools/hook.py                    # 후킹 루틴·스텁 바이트(미니 어셈블러)
python3 games/pce-ed1/tools/font.py                    # 글리프 표·코드 배정 확인
python3 games/pce-ed1/tools/messages.py                # 메시지 파싱 → work/derived/messages/ (열쇠↔원문)
python3 games/pce-ed1/tools/sysstrings.py              # 시스템 문구 가족 덤프 → work/derived/sys/
python3 games/pce-ed1/tools/savefile.py goto <sav> 224 --out <sav2> --boost   # 씬 점프 세이브(슬롯 3, 종장 등)
python3 games/pce-ed1/tools/gfx_text.py                # 그림 글자(엔딩 카드·오마케 간판·끝) 미리보기 → work/review/
sh games/pce-ed1/check.sh                          # ⭐ 이 게임의 커밋 전 게이트
```

⚠ **덤프는 `work/derived/` 로 나가고 커밋하지 않는다** — 원문이다(루트 「저작권」).
번역 정본은 `script/`(scnNNN.json · speakers.json) — 형식·재삽입 규칙은 `docs/status.md` 10절.

## 좌표 규약 — **데이터 트랙 상대 섹터(rel)** 기준이다

섹터를 적을 때는 트랙 2 시작(파일 섹터 3,365)을 0 으로 세는 `rel` 로 적는다 — 게임 자신이
쓰는 좌표다(IPL 의 load record 가 rel 2 를 가리키고 거기 코드가 있다). 파일 오프셋도
절대 LBA(+225 프리갭)도 아니다. 바이트 오프셋은 `rel:offset`(유저 데이터 2048B 안).
⚠ 세 좌표계가 섞이면 **조용히 엉뚱한 자리를 고친다** — 어느 계인지 안 적힌 상수는 못 믿는다.
RAM 주소는 `뱅크:오프셋`(8KB 뱅크, 물리 = 뱅크×0x2000)으로 적는다 — 논리 주소($8000 등)는
MPR 에 따라 바뀐다.
