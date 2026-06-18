"""ARA (Agent-Native Research Artifact) compilation via hybrid approach.

Phase 1 (Python, no LLM): Extract structured atoms from LaTeX source
Phase 2 (Parallel LLM agents): Write ARA layers concurrently
Phase 3 (Python, no LLM): Validate cross-references + assemble PAPER.md

Storage: library/<key>/ara/
  PAPER.md, logic/, src/, trace/, evidence/
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import cache, config

SKILL_PATH = Path(__file__).parent / "skills" / "ara-compiler" / "SKILL.md"
SCHEMA_PATH = SKILL_PATH.parent / "references" / "ara-schema.md"
TREE_SPEC_PATH = SKILL_PATH.parent / "references" / "exploration-tree-spec.md"


def ara_dir(key: str) -> Path:
    """Return the ARA output directory for a paper."""
    return config.paper_dir(key) / "ara"


def is_compiled(key: str) -> bool:
    """Check if a paper already has a compiled ARA."""
    d = ara_dir(key)
    return (d / "PAPER.md").exists() and (d / "logic" / "claims.md").exists()


# ---------------------------------------------------------------------------
# Phase 1: Programmatic LaTeX extraction (no LLM)
# ---------------------------------------------------------------------------

def extract_atoms(tex_path: str, figures_dir: str | None = None) -> dict[str, Any]:
    """Extract structured atoms from LaTeX source. Pure Python, no LLM."""
    from arxiv_to_prompt import extract_abstract, list_sections, extract_section

    text = Path(tex_path).read_text(encoding="utf-8")

    sections_raw = list_sections(text)
    sections = {}
    for s in sections_raw:
        content = extract_section(text, s)
        if content:
            sections[s] = content

    abstract = extract_abstract(text) or ""

    # Extract equations
    equations = re.findall(
        r'\\begin\{(?:equation|align|eqnarray)\*?\}(.*?)\\end\{(?:equation|align|eqnarray)\*?\}',
        text, re.DOTALL
    )

    # Extract figures
    figures = []
    for m in re.finditer(
        r'\\begin\{figure[*]?\}(.*?)\\end\{figure[*]?\}', text, re.DOTALL
    ):
        fig_content = m.group(1)
        caption = re.search(r'\\caption\{(.+?)\}', fig_content, re.DOTALL)
        includes = re.findall(r'\\includegraphics(?:\[.*?\])?\{(.+?)\}', fig_content)
        label = re.search(r'\\label\{(.+?)\}', fig_content)
        figures.append({
            "caption": caption.group(1).strip() if caption else "",
            "files": includes,
            "label": label.group(1) if label else None,
        })

    # Extract tables (table, table*, deluxetable, deluxetable*)
    tables = []
    for pattern in [
        r'\\begin\{table[*]?\}(.*?)\\end\{table[*]?\}',
        r'\\begin\{deluxetable[*]?\}(.*?)\\end\{deluxetable[*]?\}',
    ]:
        for m in re.finditer(pattern, text, re.DOTALL):
            tab_content = m.group(1)
            caption = re.search(r'\\caption\{(.+?)\}', tab_content, re.DOTALL)
            label = re.search(r'\\label\{(.+?)\}', tab_content)
            tables.append({
                "caption": caption.group(1).strip() if caption else "",
                "label": label.group(1) if label else None,
                "raw": tab_content[:2000],
            })

    # Extract citations
    cite_keys = set()
    for m in re.findall(r'\\cite[tp]?\{([^}]+)\}', text):
        for k in m.split(","):
            cite_keys.add(k.strip())

    # Title and authors from preamble
    title_m = re.search(r'\\title\{(.+?)\}', text, re.DOTALL)
    author_m = re.search(r'\\author\{(.+?)\}', text, re.DOTALL)

    # Figure file paths
    fig_files = []
    if figures_dir and Path(figures_dir).exists():
        fig_files = [f.name for f in Path(figures_dir).iterdir() if f.is_file()]

    return {
        "title": title_m.group(1).strip() if title_m else "",
        "authors_raw": author_m.group(1).strip() if author_m else "",
        "abstract": abstract,
        "sections": sections,
        "section_names": sections_raw,
        "equations": equations,
        "figures": figures,
        "tables": tables,
        "cite_keys": sorted(cite_keys),
        "figure_files": fig_files,
        "figures_dir": figures_dir,
        "total_chars": len(text),
    }


# ---------------------------------------------------------------------------
# Phase 2: Parallel LLM agents
# ---------------------------------------------------------------------------

def _logic_prompt(atoms: dict, output_dir: str, schema: str) -> str:
    """Prompt for the logic layer agent."""
    sections_text = ""
    for name, content in atoms["sections"].items():
        sections_text += f"\n\n### Section: {name}\n{content[:8000]}"

    return f"""You are writing the LOGIC layer of an ARA (Agent-Native Research Artifact).

## Schema Reference
{schema}

## Paper Content

**Title:** {atoms['title']}
**Abstract:** {atoms['abstract']}

{sections_text}

**Equations count:** {len(atoms['equations'])}
**Citations:** {', '.join(atoms['cite_keys'][:30])}

## Your Task

Write these files to {output_dir}/logic/:

1. **problem.md** — Observations (with numbers) → Gaps → Key insight → Assumptions
2. **claims.md** — Falsifiable claims (C01, C02...) with Statement, Status, Falsification criteria, Proof (experiment IDs), Dependencies, Tags
3. **concepts.md** — Key technical terms, one ## per term, with formal definition
4. **experiments.md** — Declarative verification plans (E01, E02...) with Verifies, Setup, Procedure, Expected outcome (directional only, NO exact numbers)
5. **related_work.md** — Typed dependency graph of cited works (imports/extends/bounds/baseline)
6. **solution/constraints.md** — Boundary conditions, assumptions, limitations
7. **solution/method.md** — The paper's method/model description

Also create {output_dir}/logic/solution/ directory.

Rules:
- Every claim MUST have a Proof field referencing experiment IDs
- Experiments have NO exact numbers — directional only ("X increases with Y")
- Never hallucinate — if info isn't in the paper, write "Not specified in paper"
- Use exact numbers from the paper for problem.md observations
"""


def _evidence_prompt(atoms: dict, output_dir: str) -> str:
    """Prompt for the evidence layer agent."""
    figs_desc = json.dumps(atoms["figures"], indent=2)
    tables_desc = json.dumps(atoms["tables"], indent=2)

    return f"""You are writing the EVIDENCE layer of an ARA (Agent-Native Research Artifact).

## Paper: {atoms['title']}
## Abstract: {atoms['abstract'][:500]}

## Extracted Figures
{figs_desc}

## Extracted Tables
{tables_desc}

## Figure files available at: {atoms.get('figures_dir', 'N/A')}
Files: {', '.join(atoms.get('figure_files', []))}

## Your Task

Write these files to {output_dir}/evidence/:

1. **README.md** — Index mapping every evidence file to claims. Format:
   | File | Description | Claims |
   |------|-------------|--------|

2. For each figure: **figures/figure{{N}}.md** — with:
   - Source: Figure N from paper
   - Caption: (exact from paper)
   - Figure type: quantitative_plot / diagram / qualitative_sample
   - Description of what it shows
   - Data extraction (for plots: axis labels, units, trends, approximate values)

3. For each table: **tables/table{{N}}.md** — with:
   - Source: Table N from paper
   - Caption: (exact)
   - Full data transcription in markdown table format
   - Column descriptions

Rules:
- Transcribe ALL numerical values EXACTLY as in the paper
- Mark estimated values with ≈
- Every figure/table gets its own file
- Never skip a figure or table
"""


def _trace_prompt(atoms: dict, output_dir: str, tree_spec: str) -> str:
    """Prompt for the trace/exploration layer agent."""
    sections_summary = "\n".join(f"- {name}" for name in atoms["section_names"])

    return f"""You are writing the TRACE layer (exploration tree) of an ARA (Agent-Native Research Artifact).

## Tree Spec
{tree_spec}

## Paper: {atoms['title']}
## Abstract: {atoms['abstract'][:500]}

## Paper sections:
{sections_summary}

## Key equations: {len(atoms['equations'])}
## Method sections content (for identifying decisions/alternatives):
{list(atoms['sections'].keys())}

## Your Task

Write: {output_dir}/trace/exploration_tree.yaml

This is a nested YAML tree representing the research DAG. Node types:
- question: A research question
- experiment: An experimental test
- dead_end: A rejected approach (hypothesis, failure_mode, lesson)
- decision: A design choice (alternatives_considered, rationale)
- pivot: A change in direction

Requirements:
- Root node(s) = central research question(s)
- Map experiments and outcomes as children
- Document dead ends from ablations, rejected alternatives, parameter choices
- Every node declares support_level: explicit (from paper text) or inferred
- Explicit nodes carry source_refs (section names)
- Minimum: capture every decision and alternative the paper mentions

Format each node as:
```yaml
- id: Q01
  type: question
  title: "..."
  support_level: explicit
  source_refs: ["Section Name"]
  children:
    - id: E01
      type: experiment
      ...
```
"""


def _src_prompt(atoms: dict, output_dir: str) -> str:
    """Prompt for the src layer + PAPER.md agent."""
    return f"""You are writing the SRC layer and PAPER.md manifest of an ARA (Agent-Native Research Artifact).

## Paper: {atoms['title']}
## Authors: {atoms['authors_raw'][:300]}
## Abstract: {atoms['abstract'][:500]}
## Sections: {', '.join(atoms['section_names'])}
## Equations: {len(atoms['equations'])}
## Figures: {len(atoms['figures'])}
## Tables: {len(atoms['tables'])}

## Your Task

Write these files:

### 1. {output_dir}/src/environment.md
- Software dependencies (languages, libraries mentioned)
- Hardware requirements (if mentioned)
- Data sources (datasets, catalogs, observations)
- Seeds / reproducibility notes
- Any computational methods mentioned

### 2. {output_dir}/PAPER.md
YAML frontmatter:
```yaml
---
title: "{atoms['title']}"
authors: [from the paper]
year: [from the paper]
venue: ""
doi: ""
ara_version: "1.0"
domain: "astrophysics"
keywords: [5-10 keywords]
claims_summary:
  - "one-line per main claim"
abstract: "{atoms['abstract'][:200]}..."
---
```

Body: Layer Index table listing ALL files that will exist:
- logic/problem.md, logic/claims.md, logic/concepts.md, logic/experiments.md
- logic/related_work.md, logic/solution/constraints.md, logic/solution/method.md
- src/environment.md
- trace/exploration_tree.yaml
- evidence/README.md, evidence/figures/*, evidence/tables/*

Format:
## Layer Index
### Cognitive Layer (`/logic`)
| File | Description |
|------|-------------|

### Physical Layer (`/src`)
| File | Description |
|------|-------------|

### Exploration Graph (`/trace`)
| File | Description |
|------|-------------|

### Evidence (`/evidence`)
| File | Description |
|------|-------------|
"""


# ---------------------------------------------------------------------------
# Phase 2 execution: parallel agent spawning
# ---------------------------------------------------------------------------

async def _run_parallel_agents(
    atoms: dict,
    output_dir: str,
    model: str,
) -> dict[str, str]:
    """Spawn 4 parallel agents, each writing one ARA layer."""
    schema = ""
    if SCHEMA_PATH.exists():
        schema = SCHEMA_PATH.read_text(encoding="utf-8")[:4000]

    tree_spec = ""
    if TREE_SPEC_PATH.exists():
        tree_spec = TREE_SPEC_PATH.read_text(encoding="utf-8")[:3000]

    prompts = {
        "logic": _logic_prompt(atoms, output_dir, schema),
        "evidence": _evidence_prompt(atoms, output_dir),
        "trace": _trace_prompt(atoms, output_dir, tree_spec),
        "src": _src_prompt(atoms, output_dir),
    }

    async def run_one(name: str, prompt: str) -> tuple[str, str]:
        print(f"[ara] Starting {name} agent...", file=sys.stderr, flush=True)
        try:
            result = await _run_agent_async(prompt, model=model, cwd=output_dir)
        except ImportError:
            result = _run_via_cli(prompt, model=model, max_tokens=100_000, cwd=output_dir)
        except Exception as exc:
            result = f"ERROR: {exc}"
        print(f"[ara] {name} agent done.", file=sys.stderr, flush=True)
        return name, result

    tasks = [run_one(name, prompt) for name, prompt in prompts.items()]
    results = await asyncio.gather(*tasks)
    return dict(results)


async def _run_agent_async(prompt: str, *, model: str, cwd: str) -> str:
    """Run a single agent via SDK."""
    from claude_code_sdk import ClaudeCodeOptions, query, ResultMessage, AssistantMessage

    options = ClaudeCodeOptions(
        model=model,
        max_turns=30,
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        cwd=cwd,
    )

    result_parts = []
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, (ResultMessage, AssistantMessage)):
            if hasattr(msg, "content"):
                for block in msg.content:
                    if hasattr(block, "text"):
                        result_parts.append(block.text)
    return "\n".join(result_parts)


def _run_via_cli(prompt: str, *, model: str, max_tokens: int, cwd: str) -> str:
    """Run via claude CLI subprocess."""
    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--max-turns", "30",
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
        "-p", prompt,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=cwd,
        env={**os.environ, "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(max_tokens)},
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI exited {result.returncode}: {result.stderr[:500]}"
        )

    return result.stdout


# ---------------------------------------------------------------------------
# Phase 3: Validation (no LLM)
# ---------------------------------------------------------------------------

def _validate_ara(output_dir: Path) -> list[str]:
    """Check mandatory files exist and cross-references resolve. Returns issues list."""
    issues = []

    mandatory = [
        "PAPER.md",
        "logic/problem.md",
        "logic/claims.md",
        "logic/concepts.md",
        "logic/experiments.md",
        "logic/related_work.md",
        "logic/solution/constraints.md",
        "src/environment.md",
        "trace/exploration_tree.yaml",
        "evidence/README.md",
    ]

    for f in mandatory:
        fp = output_dir / f
        if not fp.exists():
            issues.append(f"MISSING: {f}")
        elif fp.stat().st_size == 0:
            issues.append(f"EMPTY: {f}")

    # Check claims reference experiment IDs
    claims_path = output_dir / "logic" / "claims.md"
    experiments_path = output_dir / "logic" / "experiments.md"
    if claims_path.exists() and experiments_path.exists():
        claims_text = claims_path.read_text()
        experiments_text = experiments_path.read_text()
        claim_ids = re.findall(r'##\s+(C\d+)', claims_text)
        exp_ids = re.findall(r'##\s+(E\d+)', experiments_text)
        for eid in set(re.findall(r'E\d+', claims_text)):
            if eid not in exp_ids:
                issues.append(f"BROKEN REF: claims.md references {eid} not in experiments.md")

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compile_ara_async(
    key: str,
    *,
    model: str | None = None,
    max_tokens: int = 200_000,
) -> dict[str, Any]:
    """Compile a paper's .tex source into an ARA artifact.

    Hybrid approach:
      Phase 1: Python extracts structured atoms from LaTeX
      Phase 2: 4 parallel LLM agents write layers concurrently
      Phase 3: Python validates cross-references
    """
    paper = cache.get(key)
    if paper is None:
        return {"error": f"{key!r} not in library."}

    state = paper.get("state")
    tex_path = paper.get("tex_path")

    if state not in ("tex", "ara") or not tex_path or not Path(tex_path).exists():
        return {"error": f"{key!r} has no LaTeX source (state={state}). Need state=tex."}

    if is_compiled(key):
        return {
            "key": key,
            "state": "ara",
            "path": str(ara_dir(key)),
            "already_compiled": True,
        }

    output = ara_dir(key)
    output.mkdir(parents=True, exist_ok=True)
    (output / "logic" / "solution").mkdir(parents=True, exist_ok=True)
    (output / "src").mkdir(parents=True, exist_ok=True)
    (output / "trace").mkdir(parents=True, exist_ok=True)
    (output / "evidence" / "figures").mkdir(parents=True, exist_ok=True)
    (output / "evidence" / "tables").mkdir(parents=True, exist_ok=True)

    # Phase 1: Extract
    figures_dir = _find_figures_dir(key)
    print(f"[ara] Phase 1: Extracting atoms from LaTeX...", file=sys.stderr, flush=True)
    atoms = extract_atoms(tex_path, figures_dir)
    atoms_path = output / ".atoms.json"
    atoms_path.write_text(json.dumps(atoms, indent=2, default=str), encoding="utf-8")
    print(f"[ara] Extracted: {len(atoms['sections'])} sections, {len(atoms['equations'])} eqs, "
          f"{len(atoms['figures'])} figs, {len(atoms['tables'])} tables",
          file=sys.stderr, flush=True)

    # Phase 2: Parallel agents
    model_arg = model or os.environ.get("ARA_COMPILER_MODEL", "sonnet")
    print(f"[ara] Phase 2: Spawning 4 parallel agents (model={model_arg})...",
          file=sys.stderr, flush=True)

    try:
        agent_results = await _run_parallel_agents(atoms, str(output), model_arg)
    except Exception as exc:
        return {"error": f"Phase 2 failed: {exc}", "key": key}

    # Phase 3: Validate
    print(f"[ara] Phase 3: Validating...", file=sys.stderr, flush=True)
    issues = _validate_ara(output)

    if (output / "PAPER.md").exists():
        cache.set_state(key, "ara", ara_path=str(output))
        result: dict[str, Any] = {
            "key": key,
            "state": "ara",
            "path": str(output),
            "files": _list_ara_files(output),
        }
        if issues:
            result["validation_issues"] = issues
        return result
    else:
        return {
            "error": "Compilation produced no PAPER.md.",
            "key": key,
            "output_dir": str(output),
            "validation_issues": issues,
            "agents_completed": list(agent_results.keys()),
        }


def compile_ara(
    key: str,
    *,
    model: str | None = None,
    max_tokens: int = 200_000,
) -> dict[str, Any]:
    """Sync wrapper for compile_ara_async."""
    return asyncio.run(compile_ara_async(key, model=model, max_tokens=max_tokens))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_bib(key: str) -> str | None:
    paper_d = config.paper_dir(key)
    bibs = list(paper_d.glob("*.bib")) + list(paper_d.glob("*.bbl"))
    if bibs:
        return str(bibs[0])
    global_bib = config.bib_path()
    if global_bib.exists():
        return str(global_bib)
    return None


def _find_figures_dir(key: str) -> str | None:
    figs = config.paper_dir(key) / "figures"
    if figs.exists() and any(figs.iterdir()):
        return str(figs)
    return None


def _list_ara_files(d: Path) -> list[str]:
    """List files in an ARA directory relative to it."""
    return sorted(
        str(f.relative_to(d)) for f in d.rglob("*")
        if f.is_file() and not f.name.startswith(".")
    )


def read_ara_layer(key: str, layer: str) -> dict[str, Any]:
    """Read a specific layer from a compiled ARA.

    layer: "paper" | "claims" | "problem" | "experiments" | "concepts" |
           "heuristics" | "constraints" | "exploration" | "evidence" | "environment"
    """
    d = ara_dir(key)
    if not (d / "PAPER.md").exists():
        return {"error": f"{key!r} has no compiled ARA. Call compile_to_ara first."}

    layer_map = {
        "paper": "PAPER.md",
        "claims": "logic/claims.md",
        "problem": "logic/problem.md",
        "experiments": "logic/experiments.md",
        "concepts": "logic/concepts.md",
        "related_work": "logic/related_work.md",
        "constraints": "logic/solution/constraints.md",
        "heuristics": "logic/solution/heuristics.md",
        "architecture": "logic/solution/architecture.md",
        "algorithm": "logic/solution/algorithm.md",
        "method": "logic/solution/method.md",
        "exploration": "trace/exploration_tree.yaml",
        "evidence": "evidence/README.md",
        "environment": "src/environment.md",
    }

    if layer == "all_files":
        return {"key": key, "files": _list_ara_files(d)}

    target = layer_map.get(layer)
    if target is None:
        target = layer

    fp = d / target
    if not fp.exists():
        available = _list_ara_files(d)
        return {
            "error": f"Layer {layer!r} not found at {target}",
            "available_files": available,
        }

    text = fp.read_text(encoding="utf-8")
    return {
        "key": key,
        "layer": layer,
        "path": str(fp),
        "text": text,
        "tokens_approx": len(text) // 4,
    }
