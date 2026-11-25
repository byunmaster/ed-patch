"""장 제목 번호–제목 간격 — 마스터 11-03 판정(반각 2칸)을 다른 작업이 바꾸지 못하게 잠근다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chapters


def test_gap_is_two_half_cells():
    assert chapters.GAP == "  "
