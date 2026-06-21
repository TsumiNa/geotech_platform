"""
Per-map configuration for the GSJ 1:50,000 sheets (v2, standalone).

Identical field-profile logic to v1, but raw paths resolve via engine.config so
the v2 folder stays self-contained while referencing the shared raw data.
"""

from __future__ import annotations

import config

PROFILES = {
    "gsj_2013": {
        "age_fields_ja": ["LEGEND01", "LEGEND02", "LEGEND03"],
        "age_fields_en": ["LEGEND01E", "LEGEND02E", "LEGEND03E"],
        "name_fields_ja": ["LEGEND08", "LEGEND07", "LEGEND06", "LEGEND05", "LEGEND04"],
        "name_fields_en": ["LEGEND08E", "LEGEND07E", "LEGEND06E", "LEGEND05E", "LEGEND04E"],
        "litho_fields_ja": ["LEGEND09"], "litho_fields_en": ["LEGEND09E"],
        "symbol_field": "SYMBOL", "code_field": "MAJOR_CODE", "desc_field": None,
    },
    "gsj_1982": {
        "age_fields_ja": ["LEGEND01"], "age_fields_en": ["LEGEND01E"],
        "name_fields_ja": ["LEGEND03", "LEGEND02"], "name_fields_en": ["LEGEND03E", "LEGEND02E"],
        "litho_fields_ja": ["LEGEND04"], "litho_fields_en": ["LEGEND04E"],
        "symbol_field": "Symbol", "code_field": "MAJOR_CODE", "desc_field": "DESCRIPTIO",
    },
    "gsj_1984": {
        "age_fields_ja": ["LEGEND01", "LEGEND02"], "age_fields_en": ["LEGEND01E", "LEGEND02E"],
        "name_fields_ja": ["LEGEND04", "LEGEND03"], "name_fields_en": ["LEGEND04E", "LEGEND03E"],
        "litho_fields_ja": ["LEGEND05"], "litho_fields_en": ["LEGEND05E"],
        "symbol_field": "Symbol", "code_field": "MAJOR_CODE", "desc_field": "DESCRIPTIO",
    },
}

MAPS = [
    {"region": "08062", "map_name_ja": "八王子", "map_name_en": "Hachioji", "scale": "1:50,000",
     "year": 2013, "publisher": "Geological Survey of Japan, AIST",
     "shp_dir": "GSJ_MAP_G050_08062_2013_V01/shp", "geo_a": "geo_A.shp", "geo_l": "geo_L.shp",
     "pdf_desc": "GSJ_MAP_G050_08062_2013_V01/description.pdf",
     "pdf_monograph": "GSJ_MAP_G050_08062_2013_D.pdf",
     "readme": "GSJ_MAP_G050_08062_2013_V01/readme_08062.txt",
     "meta": "GSJ_MAP_G050_08062_2013/meta.txt", "profile": "gsj_2013"},
    {"region": "08063", "map_name_ja": "東京西南部", "map_name_en": "Tokyo-Seinambu (SW Tokyo)",
     "scale": "1:50,000", "year": 1984, "publisher": "Geological Survey of Japan",
     "shp_dir": "GSJ_MAP_G050_08063_1984_v02/shp", "geo_a": "geo_A.shp", "geo_l": "geo_L.shp",
     "pdf_desc": "GSJ_MAP_G050_08063_1984_v02/description.pdf",
     "pdf_monograph": "GSJ_MAP_G050_08063_1984_D.pdf",
     "readme": "GSJ_MAP_G050_08063_1984_v02/readme_08063.txt",
     "meta": "GSJ_MAP_G050_08063_1984/meta.txt", "profile": "gsj_1984"},
    {"region": "08074", "map_name_ja": "横浜", "map_name_en": "Yokohama", "scale": "1:50,000",
     "year": 1982, "publisher": "Geological Survey of Japan",
     "shp_dir": "GSJ_MAP_G050_08074_1982_v02/shp", "geo_a": "geo_A.shp", "geo_l": "geo_L.shp",
     "pdf_desc": "GSJ_MAP_G050_08074_1982_v02/description.pdf",
     "pdf_monograph": "GSJ_MAP_G050_08074_1982_D.pdf",
     "readme": "GSJ_MAP_G050_08074_1982_v02/readme_08074.txt",
     "meta": "GSJ_MAP_G050_08074_1982/meta.txt", "profile": "gsj_1982"},
]


def raw_path(*parts):
    return config.raw_path(*parts)


def get_profile(name):
    return PROFILES[name]
