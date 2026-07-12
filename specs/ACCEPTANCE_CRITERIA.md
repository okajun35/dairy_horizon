# Dairy Horizon vertical-slice acceptance criteria

## Functional

- [ ] The Chiba 60-cow scenario loads without manual data entry.
- [ ] Cow count, rows, existing fans, milk price, and major cost inputs are editable.
- [ ] A 75-cow scenario generates 38 and 37 cows in two rows.
- [ ] Required fans are calculated per row.
- [ ] The SVG shows all cows and distinguishes existing/additional fans.
- [ ] Three investment options are compared.
- [ ] Break-even milk loss is calculated deterministically.
- [ ] Maximum affordable capex is calculated deterministically.
- [ ] Choice Horizon and first failing condition are shown.
- [ ] A no-feasible-option case is supported.
- [ ] A quote-request draft is generated.

## Financial behavior

- [ ] Milk price supports 0–300 yen/kg.
- [ ] Milk-price change supports -100–+100 yen/kg.
- [ ] Milk price 0 returns recovery-impossible rather than an exception.
- [ ] Higher milk price lowers break-even milk volume.
- [ ] Higher electricity price raises operating cost.
- [ ] Higher variable-cost ratio raises break-even sales.
- [ ] Tax-inclusive and tax-exclusive values cannot be mixed silently.

## Data trust

- [ ] Every displayed number has provenance.
- [ ] Demo assumptions are visibly labelled.
- [ ] Outdoor wind is not described as cow-body air speed.
- [ ] +1°C/+2°C data is described as a stress test, not a dated forecast.
- [ ] The Zenrakuren article is cited in the result explanation.

## Engineering

- [ ] Domain code is independent from FastAPI and OpenAI clients.
- [ ] Same input produces the same numeric output.
- [ ] Unit tests cover all domain invariants.
- [ ] Exact run and test commands exist in README.
- [ ] No database, authentication, 3D, OR-Tools, or hidden live API dependency.
