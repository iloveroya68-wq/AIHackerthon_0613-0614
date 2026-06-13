#!/usr/bin/env python
"""
Generate JSON Schema files from Pydantic v2 models and validate examples.

Usage:
    python contracts/gen_schemas.py          # generate schemas
    python contracts/gen_schemas.py --check  # also validate all examples
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
SCHEMAS_DIR = HERE / "schemas"
EXAMPLES_DIR = HERE / "examples"

# Model → output filename mapping
MODELS = {
    "PredictionRequest": "prediction_request.json",
    "EnginePredictionResult": "engine_prediction_result.json",
    "BriefingResult": "briefing_result.json",
    "RiskForecastResult": "risk_forecast_result.json",
}


def generate() -> None:
    from contracts.models import (
        BriefingResult,
        EnginePredictionResult,
        PredictionRequest,
        RiskForecastResult,
    )

    model_classes = {
        "PredictionRequest": PredictionRequest,
        "EnginePredictionResult": EnginePredictionResult,
        "BriefingResult": BriefingResult,
        "RiskForecastResult": RiskForecastResult,
    }

    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for name, filename in MODELS.items():
        schema = model_classes[name].model_json_schema()
        dest = SCHEMAS_DIR / filename
        dest.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [OK] {dest.relative_to(HERE.parent)}")


def check_examples() -> bool:
    try:
        import jsonschema
    except ImportError:
        print("  [SKIP] jsonschema not installed — pip install jsonschema")
        return True

    ok = True
    for name, schema_file in MODELS.items():
        example_file = EXAMPLES_DIR / schema_file.replace(".json", "_example.json")
        schema_path = SCHEMAS_DIR / schema_file

        if not schema_path.exists():
            print(f"  [MISSING] schema: {schema_path}")
            ok = False
            continue
        if not example_file.exists():
            print(f"  [MISSING] example: {example_file}")
            ok = False
            continue

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_file.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(instance=example, schema=schema)
            print(f"  [OK] {example_file.name} validates against {schema_path.name}")
        except jsonschema.ValidationError as e:
            print(f"  [FAIL] {example_file.name}: {e.message}")
            ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate examples after generating")
    args = parser.parse_args()

    print("Generating JSON Schemas...")
    generate()

    if args.check:
        print("\nValidating examples against schemas...")
        passed = check_examples()
        if not passed:
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
