# Prompt design notes

These Codex prompts follow the official OpenAI prompting guidance.

## Applied changes

- Start with the required user-visible result.
- Keep stable project rules in `AGENTS.md`.
- Split planning and implementation into separate runs.
- Point Codex to exact repository paths.
- Repeat only the few boundaries that would make the result unusable.
- Define a ready-to-use browser deliverable rather than disconnected code.
- Require automated checks, app startup, manual verification, and a final
  report of anything not verified.
- Keep later iterations small and focused.

## Official references

- https://learn.chatgpt.com/docs/prompting
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
