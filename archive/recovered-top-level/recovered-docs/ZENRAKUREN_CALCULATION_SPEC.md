# Focused Codex follow-up prompts

Run one section at a time. Each prompt assumes the root `AGENTS.md` is active.

---

## 1. Audit domain correctness

### Goal

Audit the deterministic domain layer and fix formula drift, hidden
assumptions, and missing provenance.

### Context

Read:

```text
specs/ZENRAKUREN_CALCULATION_SPEC.md
specs/VARIABLE_MODEL_SPEC.md
app/domain/
tests/
```

### Required result

- traceable calculation result objects;
- provenance on each displayed input and derived result;
- regression tests for every corrected defect;
- counterexamples for zero milk price, 99.9% variable cost, zero fans,
  excess existing fans, uneven rows, repayment beyond equipment life,
  and no feasible option.

### Boundaries

Do not redesign the UI or change a formula merely to make a test pass.
Flag specification conflicts.

### Verification

Run the full domain test suite and report exact commands and failures fixed.

---

## 2. Complete Choice Horizon

### Goal

Make Choice Horizon a deterministic, explainable year-by-year evaluation
of the selected future choices.

### Required result

```text
horizon_years
first_failing_year
first_failing_condition
yearly_trace
selected_choices
```

Model hard constraints with Specification objects. Keep all demo
assumptions in scenario data.

### Boundaries

Worsening a hard constraint must not extend the horizon. Do not introduce
probabilistic simulation.

### Verification

Add monotonicity, first-failure, debt-at-exit, and no-feasible-option tests.

---

## 3. Complete maximum affordable capex

### Goal

Return the highest capex that preserves all selected hard constraints
through the decision-deferral period.

### Required result

```text
amount_yen
status
binding_constraint
first_failing_year
calculation_trace
```

Use a deterministic monotonic search with documented precision and
iteration limits.

### Boundaries

Do not use the LLM, random sampling, OR-Tools, or an undocumented upper bound.

### Verification

Test low/high milk prices, electricity prices, interest rates, infeasible
lower bounds, and feasible values above the search ceiling.

---

## 4. Add natural-language constraint extraction

### Goal

Implement `LanguageModelPort` so a short farmer description becomes a
validated structured constraint object.

### Required result

```text
farm_facts
hard_constraints
soft_preferences
uncertain_fields
next_question
confidence_by_field
```

Keep a deterministic stub for tests.

### Boundaries

The model may extract and explain. It may not calculate investment results,
invent prices, or contradict the deterministic engine.

### Verification

Add schema-validation tests for unknown enums, missing required fields,
ambiguous statements, and malformed model output.

---

## 5. Harden the 90-second demo

### Goal

Make the existing golden path clear and reliable without expanding scope.

### Required result

- one-click Chiba scenario;
- usable phone and laptop layout;
- visible provenance drawer;
- milk-price sensitivity control;
- clear no-feasible-option state;
- quote-request copy action;
- `Demo script` section in README.

### Boundaries

Do not add 3D, authentication, a database, or new analytical models.

### Verification

Run all automated checks, start the application, and manually verify the
golden path. Report the local route and any unverified browser behavior.
