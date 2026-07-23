"""공통 텍스트 유틸(한글화 파이프라인 공유)."""

from .krwrap import (
    NO_HEAD,
    NO_TAIL,
    default_cell_width,
    paginate,
    text_width,
    wrap,
    wrap_hard,
    wrap_page,
)

__all__ = [
    "wrap",
    "wrap_hard",
    "wrap_page",
    "paginate",
    "text_width",
    "default_cell_width",
    "NO_HEAD",
    "NO_TAIL",
]
