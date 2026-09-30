"""Build a copy of the Synthea jar whose breast_cancer module emits OMOP-standard LOINC codes.

Spike for ADR-0001: ETL-Synthea silently drops non-standard codes, so we swap
  - 21908-9 (Stage group.clinical, non-standard)    -> 42100-8 (Derived AJCC stage group, standard)
  - 85319-2 (HER2 in breast cancer specimen, non-std) -> 18474-7 (HER2 Ag in Tissue by IHC, standard)
and regenerate to check both survive the ETL. The original jar is never modified.

Usage: python synthea/spike/patch_breast_cancer_codes.py <original.jar> <patched.jar>
"""

import json
import logging
import sys
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

CODE_SWAPS: dict[str, tuple[str, str]] = {
    "21908-9": ("42100-8", "Derived American Joint Committee on Cancer stage group"),
    "85319-2": ("18474-7", "HER2 Ag [Presence] in Tissue by Immune stain"),
}
MODULE_PREFIX = "modules/breast_cancer"  # main module and all its submodules


def patch_module(node: object) -> int:
    """Swap LOINC codes anywhere in a module in place; return the number of swaps.

    Walks the whole JSON tree, not only the states' `codes`: guards and conditional
    transitions also reference these codes, and missing one would silently change the
    module's clinical logic.
    """
    swaps = 0
    if isinstance(node, dict):
        if node.get("system") == "LOINC" and node.get("code") in CODE_SWAPS:
            node["code"], node["display"] = CODE_SWAPS[node["code"]]
            swaps += 1
        for value in node.values():
            swaps += patch_module(value)
    elif isinstance(node, list):
        for value in node:
            swaps += patch_module(value)
    return swaps


def build_patched_jar(original: Path, patched: Path) -> None:
    """Copy every jar entry, replacing the breast cancer module files with patched versions."""
    with (
        zipfile.ZipFile(original) as src,
        zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith(MODULE_PREFIX) and item.filename.endswith(".json"):
                module = json.loads(data)
                logger.info("%s: %d code swaps", item.filename, patch_module(module))
                data = json.dumps(module, indent=2).encode()
            dst.writestr(item, data)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    original_jar, patched_jar = Path(sys.argv[1]), Path(sys.argv[2])
    patched_jar.unlink(missing_ok=True)
    build_patched_jar(original_jar, patched_jar)
    logger.info("wrote %s", patched_jar)
