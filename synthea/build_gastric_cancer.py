"""Build `synthea/modules/gastric_cancer.json`, the GMF module for gastric cancer (ADR-0001).

The module is generated, not hand-written, so every clinical probability lives in `PARAMS` and
can be changed in one place when it is checked against the RAG corpus. Scope and decisions:
`docs/alcance-clinico-modulo-gastrico.md`.

Usage (from the repo root): python synthea/build_gastric_cancer.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT = Path(__file__).resolve().parent / "modules" / "gastric_cancer.json"

# Provisional probabilities, from memory: to be checked against the corpus (see the scope doc).
PARAMS: dict[str, Any] = {
    # Diagnosis window: the module fires between 2021-01 and 2023-12, so the whole pathway fits
    # before the reference date of the generation run.
    "window_start_year": 2021,
    "window_months": 36,
    "p_cardia": 0.20,  # malignant neoplasm of cardia, vs. adenocarcinoma of stomach
    # Stage at diagnosis (I-III localized, IV advanced): 55 % de novo stage IV.
    "stage": {"I": 0.10, "II": 0.15, "III": 0.20, "IV": 0.55},
    # Recurrence to advanced disease by initial stage: ~15 % of all patients end up recurrent,
    # so ~70 % reach advanced disease (de novo + recurrent).
    "p_recurrence": {"I": 0.15, "II": 0.30, "III": 0.45},
    # Perioperative exposure for stage II-III (a single antecedent event, not a full pathway).
    "p_perioperative": 0.80,
    "p_flot_given_perioperative": 0.70,  # rest: adjuvant platinum (CAPOX)
    "recurrence_delay_months": (6, 18),
    # Biomarkers, drawn independently (v1).
    "p_her2_positive": 0.20,
    "p_cldn18_positive": 0.38,
    "p_cps_high": 0.60,  # CPS >= 5
    "p_msi_high": 0.05,
    "ecog": {0: 0.35, 1: 0.50, 2: 0.10, 3: 0.04, 4: 0.01},  # ECOG >= 2: 15 %
    # First line.
    "p_capox": 0.60,  # rest: FOLFOX
    "p_targeted_given_eligible": 0.85,  # eligible patients who get the targeted drug
    "p_mono_given_poor_ecog": 0.60,  # rest: no systemic therapy
    "n_cycles": 6,
    "cycle_days": 21,
    "p_death": 0.70,
}

# --- Codes: all standard in OMOP (Athena v5.0 29-AUG-26), checked by synthea_codes.py ---------
SNOMED, LOINC, RXNORM = "SNOMED-CT", "LOINC", "RxNorm"

DX_ADENOCARCINOMA = (SNOMED, "408647009", "Adenocarcinoma of stomach")
DX_CARDIA = (SNOMED, "187732006", "Malignant neoplasm of cardia of stomach")
ENCOUNTER = (SNOMED, "185347001", "Encounter for problem")
CHEMO_PROCEDURE = (SNOMED, "367336001", "Chemotherapy")

OBS_STAGE = (LOINC, "42100-8", "Derived American Joint Committee on Cancer stage group")
OBS_HER2 = (LOINC, "18474-7", "HER2 Ag [Presence] in Tissue by Immune stain")
OBS_CLDN18 = (
    LOINC,
    "105011-1",
    "Claudin 18 Ag [Interpretation] in Tissue by Immune stain Narrative",
)
OBS_CPS = (
    LOINC,
    "105303-2",
    (
        "Tumor cells+Macrophages+Lymphocytes.Programmed cell death ligand 1/Viable tumor cells "
        "[Ratio] in Tissue by Immune stain"
    ),
)
OBS_MSI = (LOINC, "81695-9", "Microsatellite instability [Interpretation] in Cancer specimen")
OBS_ECOG = (LOINC, "89247-1", "ECOG Performance Status score")

POSITIVE = (SNOMED, "10828004", "Positive (qualifier value)")
NEGATIVE = (SNOMED, "260385009", "Negative (qualifier value)")
STAGE_VALUE = {
    "I": (SNOMED, "258215001", "Stage 1 (qualifier value)"),
    "II": (SNOMED, "258219007", "Stage 2 (qualifier value)"),
    "III": (SNOMED, "258224005", "Stage 3 (qualifier value)"),
    "IV": (SNOMED, "258228008", "Stage 4 (qualifier value)"),
}

# Clinical Drug codes (RxNorm concept_code); the ingredient is reached through concept_ancestor.
DRUG = {
    "oxaliplatin": (RXNORM, "1736786", "oxaliplatin 100 MG Injection"),
    "capecitabine": (RXNORM, "200328", "capecitabine 500 MG Oral Tablet"),
    "fluorouracil": (RXNORM, "1791704", "fluorouracil 50 MG/ML Injection"),
    "leucovorin": (RXNORM, "1803937", "leucovorin 200 MG Injection"),
    "docetaxel": (RXNORM, "1860617", "docetaxel 10 MG/ML Injection"),
    "trastuzumab": (RXNORM, "1922509", "trastuzumab 150 MG Injection"),
    "zolbetuximab": (RXNORM, "2695876", "zolbetuximab-clzb 100 MG Injection"),
    "nivolumab": (RXNORM, "1657193", "nivolumab 10 MG/ML Injection"),
}

CONDITION_ATTR = "gastric_cancer_condition"
Code = tuple[str, str, str]


def code(c: Code) -> dict[str, str]:
    """Return a GMF code object."""
    return {"system": c[0], "code": c[1], "display": c[2]}


def dist(*pairs: tuple[str, float]) -> list[dict[str, Any]]:
    """Return a GMF `distributed_transition`; the weights must add up to 1."""
    total = sum(weight for _, weight in pairs)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"distribution adds up to {total}, not 1: {pairs}")
    return [{"transition": name, "distribution": round(weight, 6)} for name, weight in pairs]


def when(condition: dict[str, Any], target: str) -> dict[str, Any]:
    """Return one branch of a `conditional_transition`."""
    return {"condition": condition, "transition": target}


def prior(state: str) -> dict[str, Any]:
    """Condition: the person already went through `state`."""
    return {"condition_type": "PriorState", "name": state}


def attr_is(attribute: str, value: str) -> dict[str, Any]:
    """Condition: attribute equals value."""
    return {"condition_type": "Attribute", "attribute": attribute, "operator": "==", "value": value}


def either(*conditions: dict[str, Any]) -> dict[str, Any]:
    """Condition: any of the conditions."""
    return {"condition_type": "Or", "conditions": list(conditions)}


def both(*conditions: dict[str, Any]) -> dict[str, Any]:
    """Condition: all of the conditions."""
    return {"condition_type": "And", "conditions": list(conditions)}


def age(operator: str, years: int) -> dict[str, Any]:
    """Condition on age in years."""
    return {"condition_type": "Age", "operator": operator, "quantity": years, "unit": "years"}


def build_states(p: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the module states."""
    s: dict[str, dict[str, Any]] = {}

    def add(name: str, state: dict[str, Any]) -> None:
        if name in s:
            raise ValueError(f"duplicate state {name!r}")
        s[name] = state

    def encounter(name: str, nxt: str, remark: str = "") -> None:
        add(
            name,
            {
                "type": "Encounter",
                "encounter_class": "ambulatory",
                "codes": [code(ENCOUNTER)],
                "reason": CONDITION_ATTR,
                "direct_transition": nxt,
                **({"remarks": [remark]} if remark else {}),
            },
        )

    def encounter_end(name: str, nxt: str) -> None:
        add(name, {"type": "EncounterEnd", "direct_transition": nxt})

    def observation(name: str, c: Code, nxt: str, value: Code | None = None, **extra: Any) -> None:
        state: dict[str, Any] = {
            "type": "Observation",
            "category": "laboratory",
            "unit": "",
            "codes": [code(c)],
            "direct_transition": nxt,
        }
        if value is not None:
            state["value_code"] = code(value)
        state.update(extra)
        add(name, state)

    def drug(
        name: str, key: str, nxt: str | list[dict[str, Any]], conditional: bool = False
    ) -> None:
        state: dict[str, Any] = {
            "type": "MedicationOrder",
            "codes": [code(DRUG[key])],
            "administration": True,
            "reason": CONDITION_ATTR,
        }
        state["conditional_transition" if conditional else "direct_transition"] = nxt
        add(name, state)

    def set_attr(name: str, attribute: str, value: str, nxt: str) -> None:
        add(
            name,
            {
                "type": "SetAttribute",
                "attribute": attribute,
                "value": value,
                "direct_transition": nxt,
            },
        )

    # --- Entry: calendar window (age and sex come from the generation flags -a / -g) -------------------------------------------
    add("Initial", {"type": "Initial", "direct_transition": "Window Guard"})
    add(
        "Window Guard",
        {
            "type": "Guard",
            "allow": {
                "condition_type": "Date",
                "operator": ">=",
                "year": p["window_start_year"],
            },
            "direct_transition": "Onset Delay",
        },
    )
    add(
        "Onset Delay",
        {
            "type": "Delay",
            "range": {"low": 0, "high": p["window_months"], "unit": "months"},
            "direct_transition": "Diagnosis Encounter",
        },
    )
    # --- Diagnosis and stage (grouped I-IV only; sub-stages are out of scope) -----------------
    encounter("Diagnosis Encounter", "Diagnosis Site")
    add(
        "Diagnosis Site",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Gastric Adenocarcinoma", 1 - p["p_cardia"]),
                ("Cardia Malignant Neoplasm", p["p_cardia"]),
            ),
        },
    )
    for name, dx in (
        ("Gastric Adenocarcinoma", DX_ADENOCARCINOMA),
        ("Cardia Malignant Neoplasm", DX_CARDIA),
    ):
        add(
            name,
            {
                "type": "ConditionOnset",
                "codes": [code(dx)],
                "target_encounter": "Diagnosis Encounter",
                "assign_to_attribute": CONDITION_ATTR,
                "direct_transition": "Stage Draw",
            },
        )
    add(
        "Stage Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                *((f"Stage {k} at Diagnosis", w) for k, w in p["stage"].items())
            ),
        },
    )
    for k in p["stage"]:
        observation(f"Stage {k} at Diagnosis", OBS_STAGE, "End Diagnosis Encounter", STAGE_VALUE[k])
    encounter_end("End Diagnosis Encounter", "Stage Router")
    add(
        "Stage Router",
        {
            "type": "Simple",
            "conditional_transition": [
                when(prior("Stage IV at Diagnosis"), "Advanced Start"),
                when(prior("Stage I at Diagnosis"), "Recurrence Stage I"),
                {"transition": "Perioperative Decision"},
            ],
        },
    )

    # --- Localized disease: simple antecedent exposure, then recurrence or end --------------
    add(
        "Perioperative Decision",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Perioperative Delay", p["p_perioperative"]),
                ("Recurrence Router", 1 - p["p_perioperative"]),
            ),
        },
    )
    add(
        "Perioperative Delay",
        {
            "type": "Delay",
            "range": {"low": 4, "high": 8, "unit": "weeks"},
            "distributed_transition": dist(
                ("Prior FLOT Encounter", p["p_flot_given_perioperative"]),
                ("Prior Platinum Encounter", 1 - p["p_flot_given_perioperative"]),
            ),
        },
    )
    encounter(
        "Prior FLOT Encounter",
        "Prior FLOT Docetaxel",
        "FLOT = fluorouracil, leucovorin, oxaliplatin, docetaxel.",
    )
    drug("Prior FLOT Docetaxel", "docetaxel", "Prior FLOT Oxaliplatin")
    drug("Prior FLOT Oxaliplatin", "oxaliplatin", "Prior FLOT Fluorouracil")
    drug("Prior FLOT Fluorouracil", "fluorouracil", "Prior FLOT Leucovorin")
    drug("Prior FLOT Leucovorin", "leucovorin", "Prior FLOT Procedure")
    add("Prior FLOT Procedure", _chemo_procedure("End Prior FLOT Encounter"))
    encounter_end("End Prior FLOT Encounter", "Recurrence Router")
    encounter("Prior Platinum Encounter", "Prior Platinum Oxaliplatin", "Adjuvant CAPOX.")
    drug("Prior Platinum Oxaliplatin", "oxaliplatin", "Prior Platinum Capecitabine")
    drug("Prior Platinum Capecitabine", "capecitabine", "Prior Platinum Procedure")
    add("Prior Platinum Procedure", _chemo_procedure("End Prior Platinum Encounter"))
    encounter_end("End Prior Platinum Encounter", "Recurrence Router")

    add(
        "Recurrence Router",
        {
            "type": "Simple",
            "conditional_transition": [
                when(prior("Stage II at Diagnosis"), "Recurrence Stage II"),
                {"transition": "Recurrence Stage III"},
            ],
        },
    )
    for k, prob in p["p_recurrence"].items():
        add(
            f"Recurrence Stage {k}",
            {
                "type": "Simple",
                "distributed_transition": dist(
                    ("Recurrence Delay", prob), ("Localized Course End", 1 - prob)
                ),
            },
        )
    add(
        "Localized Course End",
        {"type": "Terminal", "remarks": ["Localized disease without recurrence: not advanced."]},
    )
    low, high = p["recurrence_delay_months"]
    add(
        "Recurrence Delay",
        {
            "type": "Delay",
            "range": {"low": low, "high": high, "unit": "months"},
            "direct_transition": "Recurrence Encounter",
        },
    )
    encounter("Recurrence Encounter", "Stage IV at Recurrence")
    observation("Stage IV at Recurrence", OBS_STAGE, "End Recurrence Encounter", STAGE_VALUE["IV"])
    encounter_end("End Recurrence Encounter", "Advanced Start")

    # --- Advanced disease: biomarker panel, same visit ---------------------------------------
    add("Advanced Start", {"type": "Simple", "direct_transition": "Biomarker Encounter"})
    encounter("Biomarker Encounter", "HER2 Draw")
    add(
        "HER2 Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("HER2 Positive", p["p_her2_positive"]), ("HER2 Negative", 1 - p["p_her2_positive"])
            ),
        },
    )
    observation("HER2 Positive", OBS_HER2, "CLDN18 Draw", POSITIVE)
    observation("HER2 Negative", OBS_HER2, "CLDN18 Draw", NEGATIVE)
    add(
        "CLDN18 Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("CLDN18 Positive", p["p_cldn18_positive"]),
                ("CLDN18 Negative", 1 - p["p_cldn18_positive"]),
            ),
        },
    )
    observation("CLDN18 Positive", OBS_CLDN18, "CPS Draw", POSITIVE)
    observation("CLDN18 Negative", OBS_CLDN18, "CPS Draw", NEGATIVE)
    add(
        "CPS Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("CPS High", p["p_cps_high"]), ("CPS Low", 1 - p["p_cps_high"])
            ),
        },
    )
    observation("CPS High", OBS_CPS, "MSI Draw", range={"low": 5, "high": 100}, unit="{score}")
    observation("CPS Low", OBS_CPS, "MSI Draw", range={"low": 0, "high": 4}, unit="{score}")
    add(
        "MSI Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("MSI High", p["p_msi_high"]), ("MSI Stable", 1 - p["p_msi_high"])
            ),
        },
    )
    observation("MSI High", OBS_MSI, "ECOG Draw", POSITIVE)
    observation("MSI Stable", OBS_MSI, "ECOG Draw", NEGATIVE)
    add(
        "ECOG Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(*((f"ECOG {k}", w) for k, w in p["ecog"].items())),
        },
    )
    for k in p["ecog"]:
        observation(
            f"ECOG {k}",
            OBS_ECOG,
            "End Biomarker Encounter",
            category="survey",
            exact={"quantity": k},
            unit="{score}",
        )
    encounter_end("End Biomarker Encounter", "Treatment Decision")

    # --- First-line decision (eligibility traps for the attrition table) ----------------------
    poor_ecog = either(prior("ECOG 2"), prior("ECOG 3"), prior("ECOG 4"))
    add(
        "Treatment Decision",
        {
            "type": "Simple",
            "conditional_transition": [
                when(poor_ecog, "Poor ECOG Decision"),
                when(prior("HER2 Positive"), "HER2 Positive Decision"),
                when(both(prior("CLDN18 Positive"), prior("CPS High")), "CLDN18 and CPS Decision"),
                when(prior("CLDN18 Positive"), "CLDN18 Only Decision"),
                when(prior("CPS High"), "CPS Only Decision"),
                {"transition": "Set Add-on None"},
            ],
        },
    )
    t = p["p_targeted_given_eligible"]
    add(
        "Poor ECOG Decision",
        {
            "type": "Simple",
            "remarks": ["ECOG >= 2: capecitabine alone or no systemic therapy (excluded)."],
            "distributed_transition": dist(
                ("Set Add-on None Mono", p["p_mono_given_poor_ecog"]),
                ("No Systemic Therapy", 1 - p["p_mono_given_poor_ecog"]),
            ),
        },
    )
    add(
        "HER2 Positive Decision",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Set Add-on Trastuzumab", t), ("Set Add-on None", 1 - t)
            ),
        },
    )
    add(
        "CLDN18 and CPS Decision",
        {
            "type": "Simple",
            "remarks": ["HER2-negative, CLDN18.2+ and CPS >= 5: zolbetuximab or nivolumab, 50/50."],
            "distributed_transition": dist(
                ("Set Add-on Zolbetuximab", t / 2),
                ("Set Add-on Nivolumab", t / 2),
                ("Set Add-on None", 1 - t),
            ),
        },
    )
    add(
        "CLDN18 Only Decision",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Set Add-on Zolbetuximab", t), ("Set Add-on None", 1 - t)
            ),
        },
    )
    add(
        "CPS Only Decision",
        {
            "type": "Simple",
            "distributed_transition": dist(("Set Add-on Nivolumab", t), ("Set Add-on None", 1 - t)),
        },
    )
    for label in ("Trastuzumab", "Zolbetuximab", "Nivolumab", "None"):
        set_attr(f"Set Add-on {label}", "gc_addon", label.lower(), "Backbone Draw")
    set_attr("Set Add-on None Mono", "gc_addon", "none", "Set Backbone Mono")
    set_attr("Set Backbone Mono", "gc_backbone", "mono", "Cycle Encounter")
    add(
        "Backbone Draw",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Set Backbone CAPOX", p["p_capox"]), ("Set Backbone FOLFOX", 1 - p["p_capox"])
            ),
        },
    )
    set_attr("Set Backbone CAPOX", "gc_backbone", "capox", "Cycle Encounter")
    set_attr("Set Backbone FOLFOX", "gc_backbone", "folfox", "Cycle Encounter")
    add(
        "No Systemic Therapy",
        {"type": "Simple", "direct_transition": "Death Decision"},
    )

    # --- First-line cycles --------------------------------------------------------------------
    encounter("Cycle Encounter", "Cycle Router")
    add(
        "Cycle Router",
        {
            "type": "Simple",
            "conditional_transition": [
                when(attr_is("gc_backbone", "mono"), "Cycle Capecitabine"),
                {"transition": "Cycle Oxaliplatin"},
            ],
        },
    )
    drug(
        "Cycle Oxaliplatin",
        "oxaliplatin",
        [
            when(attr_is("gc_backbone", "folfox"), "Cycle Fluorouracil"),
            {"transition": "Cycle Capecitabine"},
        ],
        conditional=True,
    )
    drug("Cycle Fluorouracil", "fluorouracil", "Cycle Leucovorin")
    drug("Cycle Leucovorin", "leucovorin", "Add-on Router")
    drug("Cycle Capecitabine", "capecitabine", "Add-on Router")
    add(
        "Add-on Router",
        {
            "type": "Simple",
            "conditional_transition": [
                when(attr_is("gc_addon", "trastuzumab"), "Cycle Trastuzumab"),
                when(attr_is("gc_addon", "zolbetuximab"), "Cycle Zolbetuximab"),
                when(attr_is("gc_addon", "nivolumab"), "Cycle Nivolumab"),
                {"transition": "Cycle Procedure"},
            ],
        },
    )
    drug("Cycle Trastuzumab", "trastuzumab", "Cycle Procedure")
    drug("Cycle Zolbetuximab", "zolbetuximab", "Cycle Procedure")
    drug("Cycle Nivolumab", "nivolumab", "Cycle Procedure")
    add("Cycle Procedure", _chemo_procedure("End Cycle Encounter"))
    encounter_end("End Cycle Encounter", "Cycle Counter")
    add(
        "Cycle Counter",
        {
            "type": "Counter",
            "attribute": "gc_cycles",
            "action": "increment",
            "conditional_transition": [
                when(
                    {
                        "condition_type": "Attribute",
                        "attribute": "gc_cycles",
                        "operator": "<",
                        "value": p["n_cycles"],
                    },
                    "Cycle Delay",
                ),
                {"transition": "Progression Delay"},
            ],
        },
    )
    add(
        "Cycle Delay",
        {
            "type": "Delay",
            "exact": {"quantity": p["cycle_days"], "unit": "days"},
            "direct_transition": "Cycle Encounter",
        },
    )

    # --- Progression and death (second line is out of scope) ---------------------------------
    add(
        "Progression Delay",
        {
            "type": "Delay",
            "range": {"low": 3, "high": 9, "unit": "months"},
            "direct_transition": "Death Decision",
        },
    )
    add(
        "Death Decision",
        {
            "type": "Simple",
            "distributed_transition": dist(
                ("Death Delay", p["p_death"]), ("Alive After First Line", 1 - p["p_death"])
            ),
        },
    )
    add(
        "Alive After First Line",
        {"type": "Terminal", "remarks": ["Second and later lines are out of scope in v1."]},
    )
    add(
        "Death Delay",
        {
            "type": "Delay",
            "range": {"low": 3, "high": 12, "unit": "months"},
            "direct_transition": "Gastric Cancer Death",
        },
    )
    add(
        "Gastric Cancer Death",
        {
            "type": "Death",
            "referenced_by_attribute": CONDITION_ATTR,
            "direct_transition": "Terminal",
        },
    )
    add("Terminal", {"type": "Terminal"})
    return s


def _chemo_procedure(nxt: str) -> dict[str, Any]:
    """Return a chemotherapy administration procedure state."""
    return {
        "type": "Procedure",
        "codes": [code(CHEMO_PROCEDURE)],
        "reason": CONDITION_ATTR,
        "duration": {"low": 30, "high": 240, "unit": "minutes"},
        "direct_transition": nxt,
    }


def build_module(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the full GMF module as a dict."""
    p = PARAMS if params is None else params
    return {
        "name": "gastric_cancer",
        "remarks": [
            "Gastric cancer (stomach adenocarcinoma and cardia) for the OMOP oncology assistant.",
            "Generated by synthea/build_gastric_cancer.py; do not edit by hand.",
            "Scope: docs/alcance-clinico-modulo-gastrico.md. Provisional probabilities.",
        ],
        "states": build_states(p),
        "gmf_version": 2,
    }


def render(module: dict[str, Any]) -> str:
    """Serialize the module deterministically."""
    return json.dumps(module, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """Write the module file."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUTPUT.write_text(render(build_module()), encoding="utf-8")
    logger.info("wrote %s", OUTPUT)


if __name__ == "__main__":
    main()
