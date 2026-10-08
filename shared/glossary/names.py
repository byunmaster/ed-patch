"""🔴 옛 입구 — 이름 검사는 `canon.names` 로 옮겼다(마스터 2026-10-08, 사전을 정본 안으로). 한 라운드만 둔다."""

import sys

from canon import names as _names

sys.modules[__name__] = _names
