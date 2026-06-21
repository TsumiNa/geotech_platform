"""
Tiny bilingual (English / Japanese) display helper.

Loads reference/i18n_ja.yaml and resolves coded values (ground types,
material families, risk flags, confidence) and UI strings into the chosen
language. Japanese terms use Japanese geotechnical-community vocabulary.

The underlying database codes are never changed; this is a display layer only.
If a code has no translation, the helper falls back to a readable version of the
code so the app never crashes on a missing key.
"""

from __future__ import annotations

import os
import yaml

REF = os.path.join(os.path.dirname(__file__), "..", "reference", "i18n_ja.yaml")

_DOC = None


def _doc() -> dict:
    global _DOC
    if _DOC is None:
        with open(REF, "r", encoding="utf-8") as fh:
            _DOC = yaml.safe_load(fh)
    return _DOC


def _readable(code: str) -> str:
    return str(code).replace("_", " ").strip()


def _lookup(section: str, code, lang: str) -> str:
    if code in (None, ""):
        return ""
    entry = _doc().get(section, {}).get(code)
    if not entry:
        return _readable(code)
    return entry.get(lang) or entry.get("en") or _readable(code)


def ground_type(code, lang="en") -> str:
    return _lookup("ground_types", code, lang)


def material_family(code, lang="en") -> str:
    return _lookup("material_families", code, lang)


def risk_flag(code, lang="en") -> str:
    return _lookup("risk_flags", code, lang)


def risk_flags(codes, lang="en") -> list[str]:
    return [risk_flag(c, lang) for c in (codes or [])]


def confidence(code, lang="en") -> str:
    return _lookup("confidence", code, lang)


def ground_type_note(code) -> str:
    entry = _doc().get("ground_types", {}).get(code, {})
    return entry.get("note_ja", "")


def ui(key_path: str, lang="en") -> str:
    """Resolve a UI string by dotted path, e.g. ui('tabs.inventory', 'ja')."""
    node = _doc().get("ui", {})
    for part in key_path.split("."):
        if not isinstance(node, dict):
            return key_path
        node = node.get(part, {})
    if isinstance(node, dict):
        return (node.get(lang) or node.get("en") or key_path).strip()
    return str(node).strip()


def all_ground_type_codes() -> list[str]:
    return list(_doc().get("ground_types", {}).keys())


def all_risk_flag_codes() -> list[str]:
    return list(_doc().get("risk_flags", {}).keys())


if __name__ == "__main__":
    for lang in ("en", "ja"):
        print(f"--- {lang} ---")
        print(" gt:", ground_type("weak_sedimentary_rock", lang))
        print(" fam:", material_family("weak_rock", lang))
        print(" flag:", risk_flag("liquefaction_screening", lang))
        print(" conf:", confidence("medium", lang))
        print(" tab:", ui("tabs.point", lang))
