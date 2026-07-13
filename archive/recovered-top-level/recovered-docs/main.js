# Codex: start here

The prompting workflow is split into two runs.

## Run 1: plan only

From the repository root, start Codex, enter `/plan`, and provide:

```text
prompts/CODEX_PLAN_PROMPT.md
```

Review the plan before implementation.

## Run 2: implement the approved vertical slice

After the plan is acceptable, use `/goal` when Goal mode is available,
then provide:

```text
prompts/CODEX_BUILD_PROMPT.md
```

If Goal mode is unavailable, provide the build prompt normally.

## Later iterations

Run only one focused prompt at a time from:

```text
prompts/CODEX_PHASE_PROMPTS.md
```

## Confirm repository instructions

```bash
codex --ask-for-approval never       "Summarize the active repository instructions and name their source files."
```

The expected project instruction source is the root `AGENTS.md`.
