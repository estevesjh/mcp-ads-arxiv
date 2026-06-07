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
| `list_sections` | Cheap heading list + abstract (a few hundred tokens). |
| `read_topic` | One-shot "show me the methodology / results / [section]" with fuzzy match. |
| `ingest_inbox` | Convert PDFs dropped in `inbox/` to markdown. |

## Talking to the tool: prompt cookbook

You don't call these tools yourself — you ask Claude in plain English, and the directives in
`CLAUDE.md` route the request. The phrasings below are battle-tested; copy them, adapt the
identifier/topic, and Claude will pick the right tool path.

### Discover papers

- *"Search ADS for galaxy cluster mass calibration with weak lensing, last 5 years."*
- *"Find papers on tree-ring distortions in CCD photometry."*
- *"Look for papers I already have on [topic] before going to ADS."* — forces local-first.

### Acquire a paper into the library

- *"Get paper 2023PASP..135k5003E."* (ADS bibcode)
- *"Acquire arXiv 2308.00919 into the library."*
- *"Download Esteves et al. 2023 PASP photometry paper."* — Claude resolves via ADS first.
- *"Get a PDF I can read for [paper]."* — runs `fetch_pdf` for human reading too.

### Save papers to *this* project folder

By default, every paper goes to one global library so search stays unified. To also drop a
shortcut into the current project folder, **tell the server which folder is "this project"**:

- *"Set the project directory to the current folder."* — call once at the start of a session;
  Claude should pass its `cwd` to `set_project_dir`.
- *"Use `/abs/path/to/myproject` as my project folder for this session."*

After that, every `get_paper` automatically creates two symlinks under `<project>/papers/`:
- `<bibcode>/` → the source directory in the global library
- `<FirstAuthorLastNameYear>.pdf` → the PDF for human reading (e.g. `Esteves2023.pdf`)

The originals stay in the global library — no data duplication.

- *"Show me what's been linked into this project."* → `library_status`
- *"Stop tracking [paper] in this project."* → `unlink_paper` (the global copy stays)

### Read a paper without burning tokens

For natural-language asks, **one tool call is enough** — `read_topic` resolves the topic to
the right section(s) automatically (fuzzy match on LaTeX macros, whitespace, and case):

- *"Summarize the **methodology** of 2010ApJ...720.1038B."* — one call to `read_topic`.
- *"Show me the **Tree-rings** section of 2023PASP..135k5003E."*
- *"What does the **discussion** of [paper] say?"*

When you already know the exact labels, or want multiple specific sections:

- *"Read just the **Application** and **Discussion** sections of [paper]."* → `read_paper(sections=[...])`
- *"List the section headings of [paper]."* → `list_sections`
- *"Read the full text of [paper]."* — only when you really need it.

### Pre-flight survey (the token-saving habit)

When a search returns more than a handful of papers, ask Claude to **survey first**:

- *"Search ADS for [topic], then run the pre-flight survey on the results."*
- *"Cluster these papers into focus and exclude topics so I can pick a scope."*

Claude returns 4 focus + 4 exclude options and **waits**. Reply with your scope, and only then
will it acquire/read the chosen subset.

### PDF-only papers

If arXiv has no LaTeX source, `get_paper` downloads the PDF and runs **docling** to produce a
markdown copy. Claude reads the markdown, never the raw PDF.

- *"Acquire [closed-access bibcode]; if you can't auto-download, tell me where to drop the PDF."*
- After dropping a PDF in `inbox/`: *"Ingest the inbox."* → `ingest_inbox`

### Inspect usage and saved tokens

- *"What's my ADS quota and how many tokens has the library served?"* → `usage_stats`
- *"How much was saved by reading sections instead of full papers?"*

## Phrasing matters: "citations" vs "references"

NASA ADS (and `related_papers`) splits the citation graph into two **opposite** directions:

- **`references`** — the papers this paper **cites** (its bibliography; backward; the
  *foundations*).
- **`citations`** — the papers that **cite this** paper (forward; the *impact / what came after*).

Everyday English mixes them up, so when prompting be explicit. Examples:

### To get the paper's bibliography (references) on a topic

| Say this | What runs |
|---|---|
| "What does 2010ApJ...720.1038B cite about the halo model?" | `mode="references", topic="halo model"` |
| "Methodology references in 2010ApJ...720.1038B for the gas density profile." | `mode="references", topic="gas density"` |
| "What is this paper built on for its mass profile?" | `mode="references", topic="mass profile"` |

### To get works that cited this paper (forward citations) on a topic

| Say this | What runs |
|---|---|
| "**What papers cite** 2010ApJ...720.1038B about density profiles?" | `mode="citations", topic="density profile"` |
| "**Who built on** this paper for gas density work?" | `mode="citations", topic="gas density"` |
| "**What came after** 2010ApJ...720.1038B on cluster mass profiles?" | `mode="citations", topic="cluster mass"` |
| "Forward citations of this paper, filtered by ICM thermodynamics." | `mode="citations", topic="ICM"` |

### Avoid (ambiguous — triggers a clarifying question)

- *"the citations of this paper"* — could mean either direction
- *"its citations"* — same problem
- *"citing papers"* — slightly forward-leaning, but still ask to be safe

### Topically adjacent (no direct graph edge)

- "Papers similar to 2010ApJ...720.1038B" → `mode="similar"`

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
