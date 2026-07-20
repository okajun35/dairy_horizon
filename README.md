# Dairy Horizon

[日本語版 README](README_ja.md)

Dairy Horizon is a 30-second heat-stress investment screening tool for dairy
farms. From four initial inputs, it shows the barn's current ventilation gap,
compares a small first-phase improvement with full coverage, and identifies the
conditions that matter before the farmer commits to an investment.

It is not an automated investment planner. The product presents transparent
assumptions and comparable options so that farmers can preserve their ability
to continue, succeed, or exit the business on their own terms.

## What It Does

- Starts with four inputs: region, lactating cows, barn lanes, and existing fans.
- Calculates required fans, the current shortage, and estimated uncovered cows.
- Compares the current barn, a first-phase addition, and full coverage.
- Displays each option in an interactive Three.js 2.5D barn view.
- Shows equipment cost, electricity cost, and break-even conditions using
  explicit standard assumptions.
- Separates observed climate data, model projections, industry guidance, user
  inputs, derived values, and demo assumptions.
- Keeps working with deterministic forms and explanation templates when the
  OpenAI API is unavailable.

## 30-Second Screening Flow

```text
Region, cows, barn lanes, and existing fans
                    |
                    v
See the current gap on the barn view
                    |
                    v
Compare current, first-phase, and full-coverage options
                    |
                    v
Review whether each option appears viable under standard assumptions
                    |
                    v
See the one condition most likely to change the interpretation
```

The primary demo uses 60 lactating cows, two barn lanes, 10 existing fans, a
five-fan first phase, and a future comparison condition of 45 cows.

## How Codex and GPT-5.6 Were Used

### Codex as the Development Agent

Codex was used throughout the engineering workflow to inspect the existing
codebase, refine and enforce the Phase 1 scope, implement tested vertical
slices, and verify the browser experience. Its work included:

- translating the product north star into a constrained Phase 1 implementation
  plan;
- test-driven implementation of fan capacity, financial screening, climate
  adjustment, decision policy, and failure boundaries;
- integration of FastAPI, deterministic Python modules, Jinja templates, and
  the Three.js barn view;
- development of Structured Output schemas, prompt constraints, validation,
  retry behavior, and deterministic fallbacks;
- automated unit, integration, syntax, and Chromium golden-path verification;
- maintaining ADRs, daily implementation reports, and explicit non-goals.

Codex supported the implementation process; numerical correctness and product
behavior are enforced by the repository's code and tests rather than by an
unverified model response.

### GPT-5.6 in the Product

The runtime default is `gpt-5.6-luna`, configured through `OPENAI_MODEL`.
GPT-5.6 is used for two bounded tasks:

1. **Candidate input extraction.** It extracts only farm conditions explicitly
   stated by the user and returns missing fields as unknown. It does not infer
   fan requirements, economics, investment timing, or future climate.
2. **Plain-language explanation.** It explains already-calculated screening
   results and phrases a Python-determined economic guardrail in accessible
   Japanese. It cannot change the selected condition, introduce numerical
   claims, or recommend a single option.

Both paths use the OpenAI Responses API with strict JSON Schema outputs and
`store: false`. Optional prompt evaluations exercise both `gpt-5.6-luna` and
`gpt-5.6-terra` across multiple decision cases before production wording is
accepted.

### Deterministic Python Boundary

GPT-5.6 reduces input and interpretation effort. It does not own the investment
calculations or override the deterministic engine.

| Responsibility | GPT-5.6 | Deterministic Python |
|---|---:|---:|
| Extract candidate farm inputs | Yes | Validates ranges and confirmation |
| Calculate required and missing fans | No | Yes |
| Calculate covered cow IDs | No | Yes |
| Calculate equipment, electricity, and break-even values | No | Yes |
| Process observed and projected climate data | No | Yes |
| Determine the comparison position and economic guardrail | No | Yes |
| Explain the calculated result | Yes | Supplies facts and validates output |
| Produce a fallback when the API fails | No | Yes |
| Recommend an investment year | No | No |

Model output is rejected if it introduces unsupported numbers, prohibited
recommendations, or a guardrail that conflicts with Python. Temporary failures
may be retried once; authentication failures are not retried. A deterministic
Japanese template is always available as the fallback.

## System Architecture

```text
Natural-language description
            |
            v
GPT-5.6 candidate extraction
            |
            v
User confirmation and Python validation
            |
            v
Deterministic screening engine
  |         |          |
  |         |          +-- Financial and decision policy
  |         +------------- Pre-generated climate profiles
  +----------------------- Barn capacity and coverage
            |
            v
Three.js barn view and comparison cards
            |
            v
Optional GPT-5.6 explanation
            |
            v
Validated model output or deterministic fallback
```

Important modules include:

- `app/natural_input.py`: bounded GPT-5.6 candidate extraction.
- `app/navigator.py` and `app/pathways.py`: fan and barn pathway calculations.
- `app/financial_screening.py`: deterministic investment screening.
- `app/decision_policy.py`: comparison position and economic guardrails.
- `app/result_explanation.py`: GPT-5.6 explanation adapter and validation.
- `static/js/barn-viewer.js`: interactive Three.js barn visualization.

## Climate Data and Assumptions

Climate information is background context for operating duration and electricity
cost, not a trigger for recommending fan quantities or an investment year.

- Current conditions use Japan Meteorological Agency observations for Chiba.
- Future periods use pre-generated CMIP6 multi-model JSON profiles.
- Future ranges are anchored by adding paired model changes to the observed
  baseline.
- Missing periods remain unavailable; the application does not extrapolate them.
- Outdoor 10 m wind speed is never treated as cow-level barn wind speed.

Equipment prices, avoided milk loss, operating hours, and similar defaults are
labelled by source type. A `demo_assumption` is never presented as a measured
value or official recommendation. See [data/README.md](data/README.md) for the
generation process and missing-data rules.

## Run Locally

Python 3.12 is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`.

The deterministic application works without an API key. To enable natural
language extraction and optional GPT-5.6 explanations, set `OPENAI_API_KEY` in
the untracked `.env` file. The model can be changed with `OPENAI_MODEL`.

## Testing

Run the default test and syntax checks:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall app tests
```

Live OpenAI integration tests are skipped by default. Run them explicitly with:

```bash
set -a
source .env
set +a
RUN_OPENAI_INTEGRATION_TESTS=1 python -m unittest \
  tests.test_natural_input.OpenAINaturalInputLiveTest \
  tests.test_result_explanation.OpenAIResultExplainerLiveTest -v
```

For the Chromium golden path, start the application and a separate debug browser:

```bash
chromium --headless --disable-gpu --no-sandbox --remote-debugging-port=9224 \
  --user-data-dir=/tmp/dairy-horizon-browser-check http://127.0.0.1:8000/
```

Then run:

```bash
node tests/browser_golden_path.mjs
```

## Project Status and Limitations

Phase 1 implements the 30-second screening flow. It deliberately does not
include:

- automatic equipment optimization or investment-year recommendations;
- detailed debt, tax, subsidy, or retirement-liability models;
- CFD, roof-insulation analysis, real-time IoT, or cow-level airflow simulation;
- authentication, a database, nationwide climate coverage, or PDF generation;
- a complete long-term Choice Horizon model.

The current climate dataset supports Chiba City. Barn coverage is a screening
estimate based on an explicit placement assumption, not a guarantee of measured
airflow or cooling performance. Dairy Horizon is not professional engineering,
financial, tax, or investment advice.

## Documentation

- [Japanese README](README_ja.md)
- [Phase 1 implementation plan](CODEX_PHASE1_PLAN.md)
- [Long-term roadmap](DAIRY_HORIZON_ROADMAP.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Climate data documentation](data/README.md)
