"""
hub/shrinkage_config.py
Standalone, configurable shrinkage allowance and artboard sizing module.
Supports in-memory caching with mtime checking for hot-reloading rules without restart.
Thread-safe, cache-isolated (deepcopy), and protected against NaN/Inf and boolean type coercion.
"""

from __future__ import annotations

import copy
import json
import math
import threading
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Default location for the rules file relative to this module
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "shrinkage_rules.json"

# In-memory cache state
_cache_lock = threading.Lock()
_cached_rules: Optional[Dict[str, Any]] = None
_cached_mtime: float = -1.0
_cached_path: Optional[str] = None

# Built-in fallback rule definition (CANAVI Canvas Bag defaults)
SYSTEM_FALLBACK_RULE: Dict[str, Any] = {
    "id": "bag_canvas_legacy",
    "rule_id": "bag_canvas_legacy",
    "name": "Túi vải Canvas / Kaki (Quy chuẩn xưởng CANAVI)",
    "product_type": "bag",
    "material": "canvas",
    "aliases": ["canvas", "kaki", "vai bo", "bo", "tho", "canvas_tho", "tui", "bag_panel", "tui vai", "tote", "canvas bag", "vai bat", "bat"],
    "calculation_mode": "absolute_deduction",
    "width_shrink_cm": 2.0,
    "height_shrink_cm": 2.5,
    "joined_height_threshold_cm": 70.0,
    "joined_height_shrink_cm": 5.0,
    "width_shrink_percent": 0.0,
    "height_shrink_percent": 0.0,
    "fixed_width_cm": None,
    "fixed_height_cm": None,
    "allow_shrink_compensation": True,
    "description": "Built-in fallback: CANAVI canvas bag default shrinkage (-2cm width, -2.5cm/5cm height)"
}

DEFAULT_RULES_CATALOG: Dict[str, Any] = {
    "version": "1.1.0",
    "description": "CANAVI & Apparel Artboard Shrinkage Rules (E2E Contract & Factory Standard)",
    "default_rule_id": "bag_canvas_legacy",
    "defaults": SYSTEM_FALLBACK_RULE,
    "rules": [
        SYSTEM_FALLBACK_RULE,
        {
            "id": "bag_kaki",
            "rule_id": "bag_kaki",
            "name": "Túi vải kaki (Độ co rút thấp hơn canvas)",
            "product_type": "bag",
            "material": "kaki",
            "aliases": ["kaki", "khaki"],
            "calculation_mode": "absolute_deduction",
            "width_shrink_cm": 1.5,
            "height_shrink_cm": 2.0,
            "joined_height_threshold_cm": 70.0,
            "joined_height_shrink_cm": 4.0,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Túi vải kaki: độ co rút thấp hơn canvas."
        },
        # Authoritative E2E Rule 1: T-shirt Cotton (Fixed deduction -1.5w, -3.0h)
        {
            "id": "tshirt_cotton",
            "rule_id": "tshirt_cotton",
            "name": "Áo thun Cotton (Tiêu chuẩn E2E CANAVI)",
            "product_type": "tshirt",
            "material": "cotton",
            "aliases": ["cotton", "cotton 100", "cotton_100", "thun cotton", "ao thun cotton"],
            "calculation_mode": "absolute_deduction",
            "width_shrink_cm": 1.5,
            "height_shrink_cm": 3.0,
            "joined_height_threshold_cm": 90.0,
            "joined_height_shrink_cm": 5.0,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Áo thun cotton theo hợp đồng E2E: trừ ngang 1.5cm, trừ dọc 3.0cm; nếu cao >= 90cm trừ 5.0cm."
        },
        # Workshop specialized rule: T-shirt 100% Cotton (Percentage deduction)
        {
            "id": "tshirt_cotton_100",
            "rule_id": "tshirt_cotton",
            "name": "Áo thun 100% Cotton (PET / Decal nhiệt xưởng)",
            "product_type": "tshirt",
            "material": "cotton_100",
            "aliases": ["cotton 100", "cotton 100%", "100% cotton", "cotton_100", "cotton 2 chieu", "cotton 4 chieu"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.5,
            "height_shrink_percent": 4.5,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Cotton 100% sợi tự nhiên co dọc mạnh khi qua buồng sấy/ép nhiệt: ngang co 2.5%, dọc co 4.5%."
        },
        {
            "id": "tshirt_poly",
            "rule_id": "tshirt_poly",
            "name": "Áo thun 100% Poly / Thun lạnh (In chuyển nhiệt toàn thân)",
            "product_type": "tshirt",
            "material": "poly",
            "aliases": ["poly", "thun lanh", "thun lanh 4 chieu", "polyester", "thun lanh poly"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.0,
            "height_shrink_percent": 2.5,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Vải poly in all-over print co giãn nhiệt: ngang co 2.0%, dọc co 2.5%."
        },
        {
            "id": "tshirt_cvc_tc",
            "rule_id": "tshirt_cvc_tc",
            "name": "Áo thun CVC 65/35 / TC 35/65",
            "product_type": "tshirt",
            "material": "cvc_tc",
            "aliases": ["cvc", "tc", "cvc 65/35", "tc 35/65", "cotton pha", "thun cvc"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.0,
            "height_shrink_percent": 3.5,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Thun pha cotton ép nhiệt co dọc nhiều hơn: ngang co 2.0%, dọc co 3.5%."
        },
        # Authoritative E2E Rule 2: Polo Pique (Fixed deduction -1.0w, -2.0h)
        {
            "id": "polo_pique",
            "rule_id": "polo_pique",
            "name": "Áo Polo Pique (Tiêu chuẩn E2E CANAVI)",
            "product_type": "polo",
            "material": "pique",
            "aliases": ["pique", "cotton pique", "ca sau", "polo pique", "vai ca sau"],
            "calculation_mode": "absolute_deduction",
            "width_shrink_cm": 1.0,
            "height_shrink_cm": 2.0,
            "joined_height_threshold_cm": 85.0,
            "joined_height_shrink_cm": 4.0,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Áo Polo pique theo hợp đồng E2E: trừ ngang 1.0cm, trừ dọc 2.0cm; nếu cao >= 85cm trừ 4.0cm."
        },
        # Workshop specialized rule: Polo Cotton Pique (Percentage deduction)
        {
            "id": "polo_cotton_pique",
            "rule_id": "polo_pique",
            "name": "Áo Polo Cá sấu Cotton / CVC (Quy chuẩn xưởng)",
            "product_type": "polo",
            "material": "cotton_pique",
            "aliases": ["cotton pique", "ca sau cotton", "ca sau cvc", "ca sau 4 chieu", "ca sau 65/35", "polo", "ca sau"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.5,
            "height_shrink_percent": 4.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Vải cá sấu cotton/CVC co dọc mạnh do mắt dệt tổ ong: ngang co 2.5%, dọc co 4.0%."
        },
        {
            "id": "polo_poly_pique",
            "rule_id": "polo_poly_pique",
            "name": "Áo Polo Cá sấu Poly / Mè thái",
            "product_type": "polo",
            "material": "poly_pique",
            "aliases": ["poly pique", "ca sau poly", "me thai", "poly ca sau", "ca sau thai"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.0,
            "height_shrink_percent": 3.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Vải dệt mắt cá sấu sợi poly: ngang co 2.0%, dọc co 3.0%."
        },
        # Authoritative E2E Rule 3: Sportswear Polyester (Fixed deduction -0.8w, -1.2h)
        {
            "id": "sportswear_polyester",
            "rule_id": "sportswear_polyester",
            "name": "Đồ thể thao Polyester (Tiêu chuẩn E2E CANAVI)",
            "product_type": "sportswear",
            "material": "polyester",
            "aliases": ["polyester", "poly", "poly_mesh", "thun me"],
            "calculation_mode": "absolute_deduction",
            "width_shrink_cm": 0.8,
            "height_shrink_cm": 1.2,
            "joined_height_threshold_cm": 80.0,
            "joined_height_shrink_cm": 2.5,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Đồ thể thao polyester theo hợp đồng E2E: trừ ngang 0.8cm, trừ dọc 1.2cm; nếu cao >= 80cm trừ 2.5cm."
        },
        # Workshop specialized rule: Sportswear Poly Mesh
        {
            "id": "sportswear_mesh",
            "rule_id": "sportswear_mesh",
            "name": "Đồ thể thao Thun mè (Poly Mesh)",
            "product_type": "sportswear",
            "material": "poly_mesh",
            "aliases": ["thun me", "poly mesh", "me the thao", "me caro", "bong da", "ao the thao", "me"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 1.5,
            "height_shrink_percent": 2.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Thun mè thể thao chuyên dụng in chuyển nhiệt ổn định nhiệt: ngang co 1.5%, dọc co 2.0%."
        },
        {
            "id": "sportswear_poly_spandex",
            "rule_id": "sportswear_poly_spandex",
            "name": "Đồ thể thao Thun lạnh Spandex 4 chiều",
            "product_type": "sportswear",
            "material": "poly_spandex",
            "aliases": ["poly spandex", "thun lanh the thao", "spandex 4 chieu", "thun gym", "yoga", "spandex"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.0,
            "height_shrink_percent": 2.5,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Thun spandex thể thao đàn hồi cao: ngang co 2.0%, dọc co 2.5%."
        },
        # Authoritative E2E Rule 4: Fleece Terry (Fixed deduction -2.5w, -4.0h, joined -6.0h >= 75cm)
        {
            "id": "fleece_terry",
            "rule_id": "fleece_terry",
            "name": "Áo Nỉ Terry (Tiêu chuẩn E2E CANAVI)",
            "product_type": "fleece",
            "material": "terry",
            "aliases": ["terry", "da ca", "french terry", "fleece_da_ca"],
            "calculation_mode": "absolute_deduction",
            "width_shrink_cm": 2.5,
            "height_shrink_cm": 4.0,
            "joined_height_threshold_cm": 75.0,
            "joined_height_shrink_cm": 6.0,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Áo Nỉ terry theo hợp đồng E2E: trừ ngang 2.5cm, trừ dọc 4.0cm; nếu cao >= 75cm trừ 6.0cm."
        },
        # Workshop specialized rule: Fleece Da Cá (Hybrid)
        {
            "id": "fleece_da_ca",
            "rule_id": "fleece_da_ca",
            "name": "Áo Nỉ Da Cá (French Terry)",
            "product_type": "fleece",
            "material": "fleece_da_ca",
            "aliases": ["da ca", "french terry", "ni da ca", "hoodie da ca", "ao ni da ca", "chan cua"],
            "calculation_mode": "hybrid",
            "width_shrink_cm": 0.5,
            "height_shrink_cm": 1.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 2.0,
            "height_shrink_percent": 3.5,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Nỉ da cá dày dặn: co theo % cộng thêm đường may (2% + 0.5cm ngang, 3.5% + 1.0cm dọc)."
        },
        {
            "id": "fleece_bong",
            "rule_id": "fleece_bong",
            "name": "Áo Nỉ Bông Cào (Polar Fleece / Heavy Fleece)",
            "product_type": "fleece",
            "material": "fleece_bong",
            "aliases": ["ni bong", "ni cao long", "polar fleece", "hoodie day", "ao ni bong"],
            "calculation_mode": "percentage_deduction",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 3.0,
            "height_shrink_percent": 5.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": True,
            "description": "Nỉ bông cào xẹp và rút mạnh nhất dưới áp lực nhiệt: ngang co 3.0%, dọc co 5.0%."
        },
        {
            "id": "hat_standard",
            "rule_id": "hat_standard",
            "name": "Nón / Mũ (In PET / Thêu)",
            "product_type": "hat",
            "material": "all",
            "aliases": ["non", "mu", "ket", "mu luoi trai", "non ket", "hat", "cap", "any"],
            "calculation_mode": "none",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": None,
            "fixed_height_cm": None,
            "allow_shrink_compensation": False,
            "description": "Nón in PET logo rời theo profile pet_hat không áp dụng độ co rút artboard."
        },
        {
            "id": "meter_fabric_standard",
            "rule_id": "meter_fabric_standard",
            "name": "Vải mét khổ cuộn 160cm (CANAVI Roll Sublimation)",
            "product_type": "meter_fabric",
            "material": "all",
            "aliases": ["vai met", "met", "vai cay", "roll", "in cuon", "cuon"],
            "calculation_mode": "none",
            "width_shrink_cm": 0.0,
            "height_shrink_cm": 0.0,
            "joined_height_threshold_cm": None,
            "joined_height_shrink_cm": None,
            "width_shrink_percent": 0.0,
            "height_shrink_percent": 0.0,
            "fixed_width_cm": 160.0,
            "fixed_height_cm": None,
            "allow_shrink_compensation": False,
            "description": "Vải mét in cuộn cố định khổ ngang 160cm; chiều cao theo chu kỳ hoa văn hoặc mét dài; không trừ co rút."
        }
    ]
}


def _strip_accents(text: str) -> str:
    """Normalize text to lowercase ASCII without accents."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d").strip()


def normalize_token(token: Optional[str]) -> str:
    """Normalize product type or material name with common Vietnamese aliases."""
    if not token:
        return ""
    clean = _strip_accents(str(token))

    # Product aliases
    if clean in ("tui", "tui vai", "bag", "tote", "canvas bag", "bag_panel", "bag-panel"):
        return "bag"
    if clean in ("ao thun", "tshirt", "t-shirt", "t_shirt", "ao phong", "tee", "garment"):
        return "tshirt"
    if clean in ("ao polo", "polo", "ca sau", "polo_shirt"):
        return "polo"
    if clean in ("the thao", "sport", "sportswear", "do the thao", "ao the thao"):
        return "sportswear"
    if clean in ("ni", "ao ni", "fleece", "hoodie", "sweater", "ao ni da ca", "ao ni bong"):
        return "fleece"
    if clean in ("non", "mu", "ket", "hat", "cap", "mu luoi trai", "non ket"):
        return "hat"
    if clean in ("vai met", "meter_fabric", "met", "cuon", "vai cay", "roll", "in cuon"):
        return "meter_fabric"

    # Material aliases - DO NOT map cotton -> cotton_100 or polyester -> poly
    if clean in ("bo", "canvas", "vai bo", "bat", "vai bat", "tho", "canvas_tho"):
        return "canvas"
    if clean in ("kaki", "khaki"):
        return "kaki"
    if clean in ("cotton", "cotton tron", "vai cotton", "thun cotton", "ao thun cotton"):
        return "cotton"
    if clean in ("cotton 100", "cotton 100%", "cotton_100", "100% cotton", "cotton 2 chieu", "cotton 4 chieu"):
        return "cotton_100"
    if clean in ("polyester", "vai polyester", "thun polyester"):
        return "polyester"
    if clean in ("poly", "thun lanh", "thun lanh 4 chieu", "thun lanh poly", "vai poly"):
        return "poly"
    if clean in ("cvc", "tc", "cvc 65/35", "tc 35/65", "cotton pha", "thun cvc", "cvc_tc"):
        return "cvc_tc"
    if clean in ("pique", "vai ca sau", "thun pique"):
        return "pique"
    if clean in ("cotton pique", "ca sau cotton", "ca sau cvc", "ca sau 4 chieu", "ca sau 65/35", "cotton_pique"):
        return "cotton_pique"
    if clean in ("poly pique", "ca sau poly", "me thai", "poly ca sau", "ca sau thai", "poly_pique"):
        return "poly_pique"
    if clean in ("me", "thun me", "poly_mesh", "mesh", "me the thao", "me caro", "bong da"):
        return "poly_mesh"
    if clean in ("poly spandex", "thun lanh the thao", "spandex 4 chieu", "thun gym", "yoga", "spandex", "poly_spandex"):
        return "poly_spandex"
    if clean in ("terry", "french terry", "vai terry"):
        return "terry"
    if clean in ("da ca", "ni da ca", "hoodie da ca", "chan cua", "fleece_da_ca"):
        return "fleece_da_ca"
    if clean in ("ni bong", "ni cao long", "polar fleece", "hoodie day", "fleece_bong"):
        return "fleece_bong"
    if clean in ("all", "*", "any", "mac dinh", "tat ca"):
        return "all"

    return clean.replace(" ", "_").replace("-", "_")


def clear_cache() -> None:
    """Reset the in-memory rules cache."""
    global _cached_rules, _cached_mtime, _cached_path
    with _cache_lock:
        _cached_rules = None
        _cached_mtime = -1.0
        _cached_path = None


def load_rules(config_path: Optional[Union[str, Path]] = None, force_reload: bool = False) -> Dict[str, Any]:
    """
    Load rules from JSON configuration file with thread-safe in-memory caching and mtime checks.
    Returns copy.deepcopy to prevent in-memory cache mutation.
    """
    global _cached_rules, _cached_mtime, _cached_path

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    resolved_path_str = str(path.resolve())

    # Fast check without lock if cache is valid and mtime unchanged
    if not force_reload and _cached_rules is not None and _cached_path == resolved_path_str:
        try:
            current_mtime = path.stat().st_mtime
            if current_mtime == _cached_mtime:
                return copy.deepcopy(_cached_rules)
        except OSError:
            pass

    with _cache_lock:
        # Double check inside lock
        if not force_reload and _cached_rules is not None and _cached_path == resolved_path_str:
            try:
                current_mtime = path.stat().st_mtime
                if current_mtime == _cached_mtime:
                    return copy.deepcopy(_cached_rules)
            except OSError:
                pass

        # Case 1: Config file does not exist on disk -> return default catalog
        if not path.is_file():
            _cached_rules = DEFAULT_RULES_CATALOG
            _cached_mtime = -1.0
            _cached_path = resolved_path_str
            return copy.deepcopy(_cached_rules)

        # Case 2: Config file exists -> load and parse
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Basic schema validation
            if not isinstance(data, dict) or "rules" not in data:
                raise ValueError("Rules configuration missing 'rules'")

            _cached_rules = data
            _cached_mtime = path.stat().st_mtime
            _cached_path = resolved_path_str
            return copy.deepcopy(_cached_rules)
        except Exception:
            # If disk read/parse fails but we have an existing cache, keep existing cache
            if _cached_rules is not None and _cached_path == resolved_path_str:
                return copy.deepcopy(_cached_rules)
            # Otherwise fall back to safe default catalog
            _cached_rules = DEFAULT_RULES_CATALOG
            _cached_mtime = -1.0
            _cached_path = resolved_path_str
            return copy.deepcopy(_cached_rules)


def match_rule(
    product_type: str = "bag",
    material: str = "canvas",
    config_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Find matching shrinkage rule based on product type and material.
    Returns copy.deepcopy(rule) to prevent caller mutation of cache.
    """
    catalog = load_rules(config_path=config_path)
    raw_rules = catalog.get("rules", [])
    if isinstance(raw_rules, dict):
        rules: List[Dict[str, Any]] = list(raw_rules.values())
    elif isinstance(raw_rules, list):
        rules = raw_rules
    else:
        rules = []

    p_norm = normalize_token(product_type) or "bag"
    m_norm = normalize_token(material) or "canvas"

    # Precedence 1: Exact match
    for rule in rules:
        r_p = normalize_token(rule.get("product_type"))
        r_m = normalize_token(rule.get("material"))
        if r_p == p_norm and r_m == m_norm:
            return copy.deepcopy(rule)

    # Precedence 2: Match via rule aliases
    for rule in rules:
        r_p = normalize_token(rule.get("product_type"))
        if r_p == p_norm:
            aliases = rule.get("aliases", [])
            for alias in aliases:
                if normalize_token(alias) == m_norm:
                    return copy.deepcopy(rule)

    # Precedence 3: Product match with wildcard material
    for rule in rules:
        r_p = normalize_token(rule.get("product_type"))
        r_m = normalize_token(rule.get("material"))
        if r_p == p_norm and r_m in ("all", "*", ""):
            return copy.deepcopy(rule)

    # Precedence 4: Material match with wildcard product
    for rule in rules:
        r_p = normalize_token(rule.get("product_type"))
        r_m = normalize_token(rule.get("material"))
        if r_p in ("all", "*", "") and r_m == m_norm:
            return copy.deepcopy(rule)

    # Precedence 5: Catalog default rule
    if "defaults" in catalog and isinstance(catalog["defaults"], dict):
        return copy.deepcopy(catalog["defaults"])

    default_id = catalog.get("default_rule_id")
    if default_id:
        for rule in rules:
            if rule.get("id") == default_id or rule.get("rule_id") == default_id:
                return copy.deepcopy(rule)

    # Precedence 6: Built-in hardcoded fallback
    return copy.deepcopy(SYSTEM_FALLBACK_RULE)


def calculate_artboard_size(
    width: float,
    height: float,
    basis: str,
    kind: str,
    product_type: str = "bag",
    material: str = "canvas",
    shrink_compensation: Union[float, Tuple[float, float], List[float], Dict[str, float]] = 0.0,
    config_path: Optional[Union[str, Path]] = None
) -> Tuple[float, float]:
    """
    Calculate final artboard size [output_width, output_height] in cm.
    Protected with finite checks, boolean type validation, and null-safe parameter parsing.
    """
    # 1. Validation of dimension values (Boolean check + numeric validation)
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError("Chiều rộng và chiều cao phải là số thực, không được là kiểu boolean")
    if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
        raise ValueError("Chiều rộng và chiều cao phải là số thực")
    if not (math.isfinite(width) and math.isfinite(height)):
        raise ValueError("Chiều rộng và chiều cao không hợp lệ (NaN hoặc vô cực)")
    if width <= 0 or height <= 0:
        raise ValueError(f"Khổ vải phải lớn hơn 0: {width}x{height}")

    # 2. meter_fabric contract
    if kind == "meter_fabric":
        if basis != "explicit_output" or abs(width - 160.0) > 0.01:
            raise ValueError("Vải mét cần khổ xuất ngang 160 và cao có căn cứ")
        return round(float(width), 2), round(float(height), 2)

    # 3. explicit_output / post_shrink basis
    if basis in ("explicit_output", "post_shrink"):
        return round(float(width), 2), round(float(height), 2)

    # 4. Unknown basis guard
    if basis != "raw_fabric":
        raise ValueError("Chưa rõ khổ trước/sau co")

    # 5. Extract shrink compensation with boolean checks and null safety
    comp_w = 0.0
    comp_h = 0.0
    if isinstance(shrink_compensation, bool):
        raise ValueError("Giá trị bù co rút không được là kiểu boolean")
    elif isinstance(shrink_compensation, (int, float)):
        comp_h = float(shrink_compensation)
    elif isinstance(shrink_compensation, (tuple, list)):
        raw_w = shrink_compensation[0] if len(shrink_compensation) >= 1 else 0.0
        raw_h = shrink_compensation[1] if len(shrink_compensation) >= 2 else 0.0
        if isinstance(raw_w, bool) or isinstance(raw_h, bool):
            raise ValueError("Giá trị bù co rút không được là kiểu boolean")
        try:
            comp_w = float(raw_w) if raw_w is not None else 0.0
            comp_h = float(raw_h) if raw_h is not None else 0.0
        except (ValueError, TypeError):
            raise ValueError("Giá trị bù co rút phải là số thực")
    elif isinstance(shrink_compensation, dict):
        raw_w = shrink_compensation.get("width")
        raw_h = shrink_compensation.get("height")
        if isinstance(raw_w, bool) or isinstance(raw_h, bool):
            raise ValueError("Giá trị bù co rút không được là kiểu boolean")
        try:
            comp_w = float(raw_w) if raw_w is not None else 0.0
            comp_h = float(raw_h) if raw_h is not None else 0.0
        except (ValueError, TypeError):
            raise ValueError("Giá trị bù co rút phải là số thực")
    elif shrink_compensation is None:
        comp_w = 0.0
        comp_h = 0.0
    else:
        raise ValueError("Giá trị bù co rút không đúng định dạng")

    if not (math.isfinite(comp_w) and math.isfinite(comp_h)):
        raise ValueError("Giá trị bù co rút không hợp lệ (NaN hoặc vô cực)")

    # 6. Match rule & apply calculation mode with null-safe parameter fallback
    rule = match_rule(product_type=product_type, material=material, config_path=config_path)
    mode = rule.get("calculation_mode", "absolute_deduction")

    delta_w = 0.0
    delta_h = 0.0

    if mode in ("none", "zero_shrinkage", "fixed_artboard"):
        delta_w = 0.0
        delta_h = 0.0

    elif mode in ("absolute_deduction", "piecewise_threshold"):
        delta_w = float(rule.get("width_shrink_cm") or 2.0) if rule.get("width_shrink_cm") is None else float(rule.get("width_shrink_cm"))

        # Piecewise joined-height threshold logic
        threshold = rule.get("joined_height_threshold_cm")
        joined_deduction = rule.get("joined_height_shrink_cm")
        standard_deduction = float(rule.get("height_shrink_cm") or 2.5)

        if threshold is not None and joined_deduction is not None and height >= float(threshold):
            delta_h = float(joined_deduction)
        else:
            delta_h = standard_deduction

    elif mode == "percentage_deduction":
        w_pct = float(rule.get("width_shrink_percent") or 0.0)
        h_pct = float(rule.get("height_shrink_percent") or 0.0)
        delta_w = width * (w_pct / 100.0)
        delta_h = height * (h_pct / 100.0)

    elif mode == "hybrid":
        w_pct = float(rule.get("width_shrink_percent") or 0.0)
        w_cm = float(rule.get("width_shrink_cm") or 0.0)
        h_pct = float(rule.get("height_shrink_percent") or 0.0)
        h_cm = float(rule.get("height_shrink_cm") or 0.0)
        delta_w = width * (w_pct / 100.0) + w_cm
        delta_h = height * (h_pct / 100.0) + h_cm

    else:
        raise ValueError(f"Chế độ tính co rút không được hỗ trợ: {mode}")

    # 7. Apply deduction and shrink compensation
    if rule.get("allow_shrink_compensation", True):
        out_w = (width - delta_w) + comp_w
        out_h = (height - delta_h) + comp_h
    else:
        out_w = width - delta_w
        out_h = height - delta_h

    # 8. Boundary safeguards (Finite and strictly positive checks)
    if not (math.isfinite(out_w) and math.isfinite(out_h)) or out_w <= 0 or out_h <= 0:
        raise ValueError(f"Kích thước sau trừ co không hợp lệ: {out_w:.2f}x{out_h:.2f}")

    return round(out_w, 2), round(out_h, 2)
