# File-formats database

TextView ships with a curated database of file formats — what each
one is for, where it's used, what tools handle it, and how to open
or convert it. Open it from **Help → File formats database…** or
press **Ctrl+Shift+D**.

## What's in it

For each format the database stores:

- **Identity**: id (slug), display name, extensions, recognised
  filenames (e.g. `Dockerfile`), MIME types.
- **Classification**: category (text / code / data / document /
  image / video / audio / archive / database / 3d / font /
  binary / crypto / config / other), text-vs-binary, magic-byte
  signature.
- **Use**: short description, common use cases, tooling, how to
  open / inspect, how to convert, links to specs / docs, tags.

The starter set is in `data/file_formats.json` at the project root.
You can extend it freely (see below).

## How TextView uses it

- **Help menu** → opens a search-and-browse modal with a category
  filter and a Markdown-rendered detail pane.
- **Unknown-file inspector** automatically attaches the matching
  database entry to the report when you open a file TextView doesn't
  natively render. So opening a `.parquet` file now shows the
  inspector's hex preview *plus* the curated info card.
- **Chat agent tools**:
  - `lookup_format(name_or_extension)` — JSON entry for one format.
  - `search_formats(query)` — keyword search.
  - `list_format_categories()` — overview of categories + counts.
  - `add_format_entry(entry)` — append/replace an entry (gated by
    "Allow actions").

## Extending the database

Two ways:

### 1. The user-extension file

Drop a JSON file at
`~/.config/TextView/file_formats.json` with the same shape as
`data/file_formats.json`:

```json
{
  "schema_version": 1,
  "formats": [
    {
      "id": "myformat",
      "name": "My in-house container",
      "extensions": [".myf"],
      "category": "data",
      "binary": true,
      "magic_bytes": "MYF1",
      "description": "Internal columnar dump used by the analytics team.",
      "use_cases": ["Quarterly snapshots", "Replication source"],
      "tools": [{"name": "myf-cli", "kind": "cli"}]
    }
  ]
}
```

User entries are merged on top of the bundled set — same `id`
**overrides** the bundled entry. Reload happens at app launch (or
when an agent calls `add_format_entry`).

### 2. Ask the chat agent

With **Allow actions** on, ask the agent: *"Save a format database
entry for HEIC images."* The agent calls `add_format_entry({...})`
and the new entry is available immediately.

## Schema reference

| Field | Type | Required |
| --- | --- | --- |
| `id` | string slug | yes |
| `name` | string | yes |
| `extensions` | string[] | no |
| `filenames` | string[] | no — for by-name detection |
| `mime` | string[] | no |
| `category` | string | no — defaults to `"other"` |
| `binary` | bool | no — defaults to `false` |
| `description` | string | no |
| `magic_bytes` | string | no — human-readable magic description |
| `use_cases` | string[] | no |
| `tools` | object[] | no — `{name, kind, url, lang}` |
| `open_with` | string | no — TextView-specific notes |
| `convert` | string | no — conversion tips |
| `links` | object[] | no — `{title, url}` |
| `tags` | string[] | no |
