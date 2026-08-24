"""디스크 이미지 공용 — ISO9660 읽기.

쓰기는 **MODE1 만** 있다(`mode1.py`) — 새턴 둘이 둘째 소비자다. MODE2 Form1(PS1)은 EDC
범위도 ECC 의 헤더 처리도 달라 같은 코드를 못 쓰고, 아직 게임 쪽에 남아 있다.
"""

from . import mode1
from .iso9660 import MODE1_USER_OFF, MODE2_FORM1_USER_OFF, Disc, digests

__all__ = ["MODE1_USER_OFF", "MODE2_FORM1_USER_OFF", "Disc", "digests", "mode1"]
