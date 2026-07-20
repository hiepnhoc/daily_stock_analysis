"""Small, explicit Vietnam equity taxonomy used by deterministic workflows.

This mapping is intentionally labelled as local coverage rather than a complete
exchange classification. Unknown symbols must remain unclassified.
"""

from __future__ import annotations

from typing import Optional


VN_SECTOR_MAP = {
    "HPG": "Thép",
    "HSG": "Thép",
    "NKG": "Thép",
    "FPT": "Công nghệ",
    "CMG": "Công nghệ",
    "CTR": "Công nghệ",
    "SSI": "Chứng khoán",
    "VCI": "Chứng khoán",
    "VND": "Chứng khoán",
    "HCM": "Chứng khoán",
    "VIX": "Chứng khoán",
    "TCB": "Ngân hàng",
    "CTG": "Ngân hàng",
    "VCB": "Ngân hàng",
    "MBB": "Ngân hàng",
    "ACB": "Ngân hàng",
    "SHB": "Ngân hàng",
    "MWG": "Bán lẻ",
    "FRT": "Bán lẻ",
    "DGW": "Bán lẻ",
    "VHM": "Bất động sản",
    "NLG": "Bất động sản",
    "KDH": "Bất động sản",
    "DXG": "Bất động sản",
    "GAS": "Dầu khí",
    "PLX": "Dầu khí",
    "PVD": "Dầu khí",
    "PVS": "Dầu khí",
}


def resolve_vn_sector(symbol: str) -> Optional[str]:
    normalized = str(symbol or "").strip().upper()
    return VN_SECTOR_MAP.get(normalized)
