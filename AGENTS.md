# AGENTS.md — Dairy Horizon

## 1. Product purpose

Dairy Horizon helps a dairy farmer decide which heat-abatement investment
preserves future choices for the longest time.

The first supported case is a Japanese small or medium dairy farm with an
existing tie-stall barn.

The central question is:

> この投資は、農場の未来の選択肢を何年守れるか。

This is not a generic chatbot, a farm ERP, a CFD tool, or a final financial
advisory product.

---

## 2. Primary user flow

The application must support this complete path:

1. Receive a short description of the farm and the owner's uncertainty.
2. Convert the description into structured hard and soft constraints.
3. Generate a reference tie-stall barn from a small number of inputs.
4. Show current heat exposure and fan coverage.
5. Compare investment options.
6. Calculate the break-even avoided milk loss.
7. Calculate the maximum affordable investment and Choice Horizon.
8. Explain why each option passes or fails.
9. Generate a short quote-request/action sheet.

The demo must work without requiring the user to enter every value.

---

## 3. Non-negotiable architecture rules

### 3.1 LLM boundary

The LLM may:

- extract structured constraints from natural language;
- identify missing information;
- choose the next highest-value question;
- explain deterministic results;
- generate a quote-request draft.

The LLM must not:

- calculate THI;
- calculate airflow;
- calculate investment returns;
- calculate loan repayment;
- estimate prices without an explicit tagged assumption;
- decide a result that contradicts the deterministic engine.

All numeric outputs used in the recommendation must come from tested Python
functions.

### 3.2 Determinism

The same validated input must produce the same numeric output.

No random number generation is allowed in the core calculation path unless:

- a seed is explicit;
- the output is labelled as simulation;
- deterministic unit tests exist.

### 3.3 Separation of concerns

Use a ports-and-adapters structure.

Recommended modules:

```text
app/
  domain/
    models.py
    heat.py
    barn.py
    finance.py
    choice_horizon.py
    specifications.py
  application/
    build_reference_farm.py
    compare_investments.py
    build_quote_request.py
  ports/
    climate.py
    equipment.py
    language_model.py
  adapters/
    json_climate.py
    json_equipment.py
    openai_language_model.py
  web/
    routes.py
    schemas.py
    templates/
    static/
tests/
```

The domain layer must not import FastAPI, OpenAI SDK classes, HTTP clients,
database clients, or template engines.

### 3.4 Python practices

- Target Python 3.12 or later.
- Use type hints on public functions.
- Prefer immutable dataclasses or frozen Pydantic models for domain values.
- Include units in field names, such as `temperature_c`, `amount_yen`,
  `air_speed_mps`, and `milk_price_yen_per_kg`.
- Prefer pure functions for calculations.
- Use `Decimal` only where currency rounding materially affects the result;
  otherwise use float with explicit rounding at presentation boundaries.
- Raise domain-specific exceptions rather than generic exceptions.
- Avoid hidden module-level mutable state.
- Keep functions small and testable.
- Do not catch `Exception` unless re-raising with context at an adapter boundary.

---

## 4. Source data and provenance

Every value shown to the user must have one of these provenance kinds:

```text
official_observation
official_statistics
official_projection_report
industry_guidance
manufacturer_spec
literature
derived
demo_assumption
user_input
```

The result must preserve provenance through calculations.

At minimum, each displayed assumption must expose:

- value;
- unit;
- provenance kind;
- source ID;
- explanation;
- whether the user can override it.

Never present `demo_assumption` as an observed market price.

---

## 5. Core formulas

The source of the fan-investment screening formula is documented in:

```text
specs/ZENRAKUREN_CALCULATION_SPEC.md
```

Do not silently change the formula.

If the implementation differs from the specification:

1. stop;
2. write a failing test;
3. document the proposed change;
4. ask for approval before changing the domain rule.

The variable barn rules are documented in:

```text
specs/VARIABLE_MODEL_SPEC.md
```

---

## 6. Required domain invariants

Tests must prove the following.

### Heat and climate

- Higher temperature must not reduce THI when humidity is unchanged.
- Higher humidity must not reduce THI under the supported hot-weather range.
- A hotter stress scenario must not produce a lower heat-risk result.
- Outdoor wind speed must never be labelled as cow-body air speed.

### Barn and fan layout

- The number of generated cows equals the requested cow count.
- The number of generated rows equals the requested row count.
- Every cow belongs to exactly one row and stall.
- Every target fan covers at least one cow.
- Required fan count is calculated per row.
- 60 cows in two equal rows at three cows per fan requires 20 fans.
- 75 cows split into 38 and 37 requires 26 fans.
- Additional fan count cannot be negative.

### Finance

- Higher milk price must not increase break-even milk volume.
- Higher electricity price must not reduce annual operating cost.
- Higher variable-cost ratio must not reduce break-even sales.
- Higher interest rate must not reduce annualised capital cost.
- Milk price zero returns a non-calculable/recovery-impossible status.
- Mixing tax-inclusive and tax-exclusive amounts must fail validation.
- The default Zenrakuren example must reproduce approximately
  `3.1377 kg/cow/day`, while the explanation may show the published rounded
  value `3.2 kg/cow/day`.

### Choice Horizon

- Choice Horizon ends at the first year in which a required specification
  fails.
- A scenario cannot pass after its hard debt-at-exit constraint fails.
- A scenario with no feasible option must return `no_feasible_option`.
- The engine must explain the first failing condition.
- Worsening a hard constraint cannot extend Choice Horizon.

---

## 7. Choice Horizon definition

Choice Horizon is the number of consecutive years for which all selected
future choices remain feasible.

Supported choices for the MVP:

```text
continue_operation
successor_handover
debt_free_exit
```

Each choice is represented by a Specification object.

Examples:

- `MinimumAnnualCashSpecification`
- `MaximumDebtAtExitSpecification`
- `RemainingEquipmentLifeSpecification`
- `MaximumHeatRiskSpecification`

Do not hide missing values. Missing financial values may be introduced only
inside the demo scenario and must be tagged `demo_assumption`.

---

## 8. Tax and milk-price handling

The canonical milk-price unit is `yen_per_kg`.

The UI may show a reference conversion to `yen_per_litre`, but it must label
the density assumption.

Supported milk-price input:

```text
direct input: 0–300 yen/kg
change from base: -100–+100 yen/kg
```

At zero milk price, do not divide by zero. Return:

```text
recovery_impossible_at_zero_price
```

Consumption tax must not be applied as one blanket percentage to every input.

The source material instructs users to use either tax-inclusive or
tax-exclusive values consistently. Validate this basis explicitly.

---

## 9. UI requirements

For the hackathon MVP, prefer:

- FastAPI;
- Jinja2;
- small amounts of vanilla JavaScript;
- SVG for the barn plan;
- server-rendered pages.

Do not introduce React, Next.js, Three.js, a database, authentication, or a
large CSS framework unless the repository already depends on them and the
change clearly reduces work.

Every result screen must show:

- recommendation;
- maximum acceptable investment;
- break-even avoided milk loss;
- Choice Horizon;
- first failing condition;
- provenance labels;
- a sensitivity control for milk price;
- a clear warning that the result is a screening estimate.

---

## 10. Scope exclusions for the first vertical slice

Do not implement:

- CFD;
- arbitrary CAD-like barn editing;
- free-stall barns;
- national demand forecasting;
- milk-price forecasting;
- OCR;
- PDF generation;
- user accounts;
- database persistence;
- subsidy eligibility;
- tax advice;
- automatic live equipment prices;
- Monte Carlo simulation;
- OR-Tools.

---

## 11. Development workflow

For every task:

1. Inspect existing files before editing.
2. State a short implementation plan.
3. Write or update tests first for domain-rule changes.
4. Implement the smallest complete change.
5. Run all tests.
6. Report:
   - changed files;
   - test command and result;
   - assumptions added;
   - remaining risks.

Do not claim success without running the tests.

Do not replace working deterministic code with an LLM call.

---

## 12. Completion criteria

The first vertical slice is complete only when:

- a 60-cow demo scenario runs end to end;
- a 75-cow scenario proves the layout is variable;
- the default Zenrakuren calculation is reproduced;
- milk price can be changed interactively;
- zero milk price is handled safely;
- three investment options are compared;
- one no-feasible-option case is tested;
- provenance appears in the UI;
- all domain tests pass;
- the README contains exact run commands.
