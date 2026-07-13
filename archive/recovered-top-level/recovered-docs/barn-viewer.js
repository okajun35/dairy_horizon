# Goal

Produce an implementation plan for one complete, reviewable Dairy Horizon
vertical slice. Do not edit files yet.

The finished slice must let a user open the Chiba reference farm, change
the herd and key financial assumptions, compare three heat-abatement
options, and see a deterministic recommendation with its evidence.

# Context to inspect

Read these files first:

```text
AGENTS.md
README.md
specs/ZENRAKUREN_CALCULATION_SPEC.md
specs/VARIABLE_MODEL_SPEC.md
specs/ACCEPTANCE_CRITERIA.md
templates/tie_stall_variable.json
templates/financial_input_schema.json
scenarios/chiba_60_cow_demo.json
data/provenance/sources.json
scripts/
tests/
```

Inspect the full repository tree and identify what already exists and what
is missing. Reuse correct code rather than replacing it.

# Plan output

Return a concise plan containing:

1. The proposed runtime architecture and module boundaries.
2. Exact files to create, modify, or delete.
3. The smallest end-to-end user flow that will be completed.
4. Domain tests to add before UI work.
5. Commands that will verify the implementation.
6. Assumptions or specification conflicts that require a decision.

Separate required work from optional polish.

# Boundaries

- Preserve the formulas and provenance rules in the supplied specifications.
- Keep all recommendation numbers deterministic and outside the LLM.
- Do not add 3D, authentication, a database, OR-Tools, OCR, subsidies, or
  live equipment-price lookup.
- Flag missing information instead of silently inventing production facts.

Do not begin implementation until the plan has been reviewed.
