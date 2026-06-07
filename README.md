# mcp-ads-arxiv

A local **astrophysics paper library** as an MCP server. It discovers papers via the
[NASA Astrophysics Data System (ADS)](https://ui.adsabs.harvard.edu/), acquires the best text
form — **arXiv LaTeX source preferred**, otherwise a PDF converted to **markdown** — and serves
only lightweight text to the model. **Raw PDFs are never read**; they are always converted first.

Built for literature reviewers who want a fast, token-frugal, reusable local corpus. Works with
**Claude Desktop and Claude Code** (and any MCP client) over stdio.

## What it does

- **Local-first search** over a persistent library (`literature_review.bib` + a SQLite index).
- **ADS discovery** (metadata only: title, abstract, keywords, authors, year).
- **Citation-graph traversal** — a paper's `references` (the *roots* of a project), its forward
  `citations` (impact), or `similar` papers.
- **Pre-Flight Survey** — clusters results into 4 focus + 4 exclude topics so you align on scope
  *before* any full text is read.
- **Acquisition** — arXiv `.tex` → PDF → (manual `inbox/` drop), then `read_paper` serves the
  text, optionally a chosen subset of sections.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_library` | Local, free search over already-acquired papers. |
| `search_ads` | NASA ADS metadata search (fills gaps after `search_library`). |
| `related_papers` | Citation graph: `references` / `citations` / `similar`, optional `topic`. |
| `generate_dynamic_survey` | Cluster metadata into 4 focus + 4 exclude topics. |
| `get_paper` | Acquire into the library: arXiv `.tex` → PDF→markdown → inbox prompt. |
| `read_paper` | Serve stored text; optional `sections` to save tokens. |
| `ingest_inbox` | Convert PDFs dropped in `inbox/` to markdown. |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/estevesjh/mcp-ads-arxiv.git
cd mcp-ads-arxiv
uv sync
```

### Get an ADS API token

1. Create a free account at [NASA ADS](https://ui.adsabs.harvard.edu/).
2. Go to [Settings → API Token](https://ui.adsabs.harvard.edu/user/settings/token).
3. Generate a key and copy it. The server reads it from `ADS_API_TOKEN`.

Without a token the server still runs; ADS tools return a clear "set ADS_API_TOKEN" message.

### Library location

By default the library lives in the current working directory. Set `LIT_CACHE_DIR` to put it
anywhere (e.g. a shared research folder). See `.env.example`.

## Register with Claude

### Claude Code

```bash
claude mcp add --scope user mcp-ads-arxiv \
  -e ADS_API_TOKEN=your-token-here \
  -e LIT_CACHE_DIR=/absolute/path/to/your/library \
  -- uv run --directory /absolute/path/to/mcp-ads-arxiv mcp-ads-arxiv
```

### Claude Desktop

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "mcp-ads-arxiv": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-ads-arxiv", "mcp-ads-arxiv"],
      "env": {
        "ADS_API_TOKEN": "your-token-here",
        "LIT_CACHE_DIR": "/absolute/path/to/your/library"
      }
    }
  }
}
```

Restart the client afterwards.

### Skip the per-call permission prompts (Claude Code only)

By default Claude Code asks for approval the first time each tool is used. To pre-approve all 8
tools from this server, add one entry to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["mcp__mcp-ads-arxiv"]
  }
}
```

The `mcp__<server-name>` prefix matches every tool the server exposes. Merge with any existing
`allow` array — don't replace it. Restart Claude Code to pick up the change.

## Development

```bash
uv run pytest          # pure-logic tests (no network/token needed)
uv run mcp-ads-arxiv   # boots the stdio server
```

## Acknowledgments

This project builds directly on two excellent upstream MCP projects and depends on them rather
than reimplementing their work:

- **[cbyrohl/mcp-server-ads](https://github.com/cbyrohl/mcp-server-ads)** — its `ADSClient`
  (HTTP, auth, rate-limit tracking, typed errors) backs all NASA ADS access here.
- **[takashiishida/arxiv-latex-mcp](https://github.com/takashiishida/arxiv-latex-mcp)** and the
  underlying **[arxiv-to-prompt](https://github.com/takashiishida/arxiv-to-prompt)** library —
  arXiv source download, `\input`/`\include` flattening, and section listing/extraction.

PDF→markdown conversion uses **[docling](https://github.com/DS4SD/docling)** (IBM).

## License

MIT
