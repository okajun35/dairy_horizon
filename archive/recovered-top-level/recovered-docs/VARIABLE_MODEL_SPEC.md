# Goal

Implement the approved Dairy Horizon vertical slice as a working, tested
web application.

A user must be able to complete this flow:

> Open the Chiba reference farm → change herd size, fan count, milk price,
> and key costs → see the generated tie-stall layout → compare three
> heat-abatement options → see break-even milk loss, maximum affordable
> capex, Choice Horizon, first failing condition, provenance, and a
> quote-request draft.

# Source of truth

Follow:

```text
AGENTS.md
specs/ZENRAKUREN_CALCULATION_SPEC.md
specs/VARIABLE_MODEL_SPEC.md
specs/ACCEPTANCE_CRITERIA.md
```

Use the approved plan from the previous run. Inspect existing code before
editing, and preserve correct work already present.

# Required deliverable

Deliver one complete local application with:

- FastAPI, Jinja2, small vanilla JavaScript, and SVG unless the approved
  plan justifies an equivalent smaller stack;
- a deterministic domain layer independent from FastAPI and OpenAI clients;
- variable cow count, one/two rows, existing fan count, milk price,
  variable-cost ratio, electricity price, active heat days, and tax basis;
- automatic cow and target-fan layout generation;
- current state, missing-fan addition, and missing-fan-plus-roof comparison;
- the Zenrakuren break-even calculation;
- deterministic maximum-affordable-capex and Choice Horizon calculations;
- explicit no-feasible-option behavior;
- provenance displayed for all recommendation inputs and outputs;
- a deterministic language-model stub so the demo works without an API key;
- exact local run and test commands in `README.md`.

# Critical boundaries

- The LLM must not calculate or override numeric recommendations.
- Do not change the supplied formulas without a failing test and an
  explicit note in the final report.
- Do not call external climate APIs in the request path.
- Do not present demo assumptions as observed prices or statistics.
- Do not stop after scaffolding; the browser flow must work end to end.

# Verification

Before finishing:

1. Run the full test suite.
2. Run the smallest relevant lint/type checks available in the repository.
3. Start the app and verify the golden path manually.
4. Check every item in `specs/ACCEPTANCE_CRITERIA.md`.
5. Confirm these cases:
   - 60 cows / 2 rows / 10 existing fans → 20 target, 10 additional;
   - 75 cows / 2 rows / 12 existing fans → 26 target, 14 additional;
   - default Zenrakuren case → approximately 3.1377 kg/cow/day;
   - milk price zero → recovery-impossible status;
   - no feasible option → explicit result, not an exception.

# Final report

Report only:

- what now works;
- files changed;
- commands run and their results;
- acceptance criteria not met;
- assumptions added;
- remaining risks or information that could not be verified.
