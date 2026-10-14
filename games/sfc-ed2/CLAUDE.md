# CLAUDE.md — 슈퍼패미컴 『ドラゴンスレイヤー英雄伝説Ⅱ』 (sfc-ed2)

**트랙: [kr]** — 일본 원판(에포크 1993, **HiROM 12Mbit**) 한글 번역 패치. 공용 규칙은 루트 [`CLAUDE.md`](../../CLAUDE.md),
현재 상태는 [`docs/status.md`](docs/status.md), 경위는 [`docs/devlog.md`](docs/devlog.md).
형제 게임 [`sfc-ed1`](../sfc-ed1/CLAUDE.md)의 함정(VWF·동적 글리프·조사 훅)을 먼저 읽는다 — 단 **엔진이 다르다**.

## 이 게임이 다른 점 (sfc-ed1 과)

- **HiROM Fast**(map $31), 1,572,864B, SRAM 8KB. 주소는 `$C0~$D7:xxxx` = 파일 `(뱅크&0x3F)*0x10000+주소`.
  ED1 의 LoROM 상수(`snes2off`·`ROM_SIZE`)를 가져오면 조용히 틀린다 — `tools/common.py` 가 정본.
- **전각 12×12 비트맵 글꼴 + 한자가 있다.** 글리프표는 롬 `$D6:81D1`(18B/글리프, 비압축, 약 1,200~1,500자)이고
  화면에는 BG1 4bpp 캔버스(28타일 폭)에 **동적으로 그려 넣는다**(1=획, 2=그림자). 외곽선은 롬이 아니라 코드가 만든다.
  → 한글 12×12 글리프를 같은 표에 넣는 방식이 자연스럽다(ED1 의 8×16 반각 한 칸과 다른 길).
- **대본은 비압축 2바이트 코드**(`$80~$85`+색인, JIS 순서에 가까움)이고 `$C2~$CA` 뱅크에 약 13만 자가 평문으로 있다.
  자세한 코드 규칙은 `tools/scan_text.py` 머리말.
- 맵·이벤트 아카이브(`MAP006.BIN` 같은 파일명이 롬에 있다)는 압축 가능성 — 미조사.

## 도구

```bash
python3 games/sfc-ed2/tools/common.py        # 원본 지문 + 내부 헤더
python3 games/sfc-ed2/tools/font.py 0x9c     # 12×12 글리프 한 개 보기
python3 games/sfc-ed2/tools/scan_text.py     # 2바이트 코드 덩이 후보 — 뱅크별 분포
python3 games/sfc-ed2/tools/dis65816.py 0xC09395 0xC09400   # 65816 디스어셈블(조사용, `m16`/`x16` 인자)
sh games/sfc-ed2/check.sh                    # 커밋 전 게이트
```

에뮬(Mesen2)로 확인할 때: `read`/`write` 중단점은 **`pause_on_hit` 를 주고**, `poll_events` 는 큐가 비었는지 모르면 부르지
않는다(`exec` 중단점이 NMI 마다 맞아 수만 자가 쏟아졌다). 덤프는 `debug dump_memory` 가 파일로 뽑는다(`read_memory` 는 인라인 hex).
