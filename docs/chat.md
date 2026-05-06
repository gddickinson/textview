# Chat panel (LLM)

**Ctrl+J** toggles the chat panel. It speaks to one of three providers
and exposes a substantial tool surface (see **agent-api.md**).

## Providers

| Provider | Auth | Notes |
| --- | --- | --- |
| Anthropic | API key in keyring (or env var `ANTHROPIC_API_KEY`) | Default model: `claude-opus-4-7`. Best tool-calling behavior. |
| OpenAI | API key in keyring (or `OPENAI_API_KEY`) | Default model: configurable. |
| Ollama | Local; no key | Defaults to `qwen2.5:14b` (or whatever's pulled). Smaller models have flakier tool-calling — there's a system-prompt nudge that helps. |

Set credentials in the Configuration panel under "LLM" → "Set API key…",
or directly in `keyring`. Keys are stored OS-securely; never written to
files in the project.

## Modes

- **Chat mode**: just conversation. Tools NOT exposed.
- **Agent mode**: tools exposed. The model can read your files,
  manipulate the table, save/run scripts, etc.

Toggle "Agent mode" in the panel header. Action tools (anything that
writes / spawns) require user confirmation by default — there's a
"Allow" button in the chat that the user clicks to approve.

## What gets sent in the system prompt

Always:
- A reference to the documentation (so the model knows it can call
  `read_doc("INDEX")` to find out what's available).
- An index of the user's saved memories — names + descriptions only,
  not bodies. The model calls `memory_recall(query)` to fetch.

Conditionally:
- The current file's content, if the "Include current file" checkbox
  is on. Truncated to 200 KB.
- Ollama nudges: structured tool-call format, one tool per turn,
  re-read after sort/filter.

## Memory

The model has access to a persistent memory store at
`~/.config/TextView/memory/`. Five types: `session`, `user`, `project`,
`reference`, `feedback`. Three importance levels.

The model decides what's worth remembering. Each memory is a markdown
file with frontmatter. An auto-generated `MEMORY.md` index is written
at the top level (and shown in the system prompt).

## Tools

See **agent-api.md** for the full reference. Highlights:

- **Read** anything: `read_file`, `read_doc`, `memory_recall`,
  `list_dir`, `current_file`, `find_in_file`.
- **Drive the GUI**: `switch_tab`, `goto_line`, `apply_table_filter`,
  `sort_table`, `make_chart`, `add_derived_column`.
- **Author scripts**: `create_script`, `run_script`. Scripts persist
  in `~/.config/TextView/agent_scripts/`.
- **Persist what's worth keeping**: `memory_save`.

## Streaming + audit

Responses stream in. Every tool call is logged to a JSONL audit at
`~/.config/TextView/audit.log` so you can review what the agent did.

## Tips for the user

- Keep "Include current file" off when chatting about something
  unrelated, to keep context windows small.
- For large refactors, save useful patterns as memories so they
  survive the next conversation.
- If a small Ollama model goes off the rails, switch to an Anthropic
  Sonnet/Opus or 70B local model — there's a real reasoning ceiling
  on multi-step plans.
