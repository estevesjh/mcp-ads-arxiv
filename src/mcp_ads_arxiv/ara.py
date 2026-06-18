"""ARA (Agent-Native Research Artifact) compilation via Claude Code SDK.

Compiles a paper's LaTeX source into a structured ARA directory:
  library/<key>/ara/
    PAPER.md, logic/, src/, trace/, evidence/

Uses the Claude Code SDK to spawn a compiler agent with the ARA skill prompt.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import cache, config

SKILL_PATH = Path(__file__).parent / "skills" / "ara-compiler" / "SKILL.md"


def ara_dir(key: str) -> Path:
    """Return the ARA output directory for a paper."""
    return config.paper_dir(key) / "ara"


def is_compiled(key: str) -> bool:
    """Check if a paper already has a compiled ARA."""
    d = ara_dir(key)
    return (d / "PAPER.md").exists()


def _build_compiler_prompt(tex_path: str, output_dir: str, bib_path: str | None = None) -> str:
    """Build the prompt that drives the compiler agent."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    sources = f"- LaTeX source: {tex_path}"
    if bib_path and Path(bib_path).exists():
        sources += f"\n- Bibliography: {bib_path}"

    return f"""{skill_text}

---

## Task

Compile the following research source into a complete ARA artifact.

### Inputs
{sources}

### Output directory
Write all ARA files to: {output_dir}

### Instructions
1. Read the LaTeX source thoroughly (including all sections, appendices, equations).
2. Follow the 4-stage epistemic protocol exactly.
3. Generate all mandatory core files + whatever additional files the paper warrants.
4. Run the coverage check loop.
5. Validate via Seal Level 1.
6. Fix any failures and re-validate.

Begin by reading the source file, then proceed through the stages.
"""


def compile_ara(
    key: str,
    *,
    model: str | None = None,
    max_tokens: int = 200_000,
) -> dict[str, Any]:
    """Compile a paper's .tex source into an ARA artifact using Claude Code SDK.

    Returns a status dict with the ARA path on success.
    """
    paper = cache.get(key)
    if paper is None:
        return {"error": f"{key!r} not in library."}

    state = paper.get("state")
    tex_path = paper.get("tex_path")

    if state != "tex" or not tex_path or not Path(tex_path).exists():
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

    bib_path = _find_bib(key)
    prompt = _build_compiler_prompt(tex_path, str(output), bib_path)

    model_arg = model or os.environ.get("ARA_COMPILER_MODEL", "sonnet")

    try:
        result = _run_claude_code(prompt, model=model_arg, max_tokens=max_tokens, cwd=str(output))
    except Exception as exc:
        return {"error": f"Compilation failed: {exc}", "key": key}

    if (output / "PAPER.md").exists():
        cache.set_state(key, "ara", ara_path=str(output))
        return {
            "key": key,
            "state": "ara",
            "path": str(output),
            "files": _list_ara_files(output),
        }
    else:
        return {
            "error": "Compilation produced no PAPER.md — likely incomplete.",
            "key": key,
            "output_dir": str(output),
            "agent_output": result[:2000] if result else None,
        }


def _find_bib(key: str) -> str | None:
    """Look for a .bib file near the paper's source."""
    paper_d = config.paper_dir(key)
    bibs = list(paper_d.glob("*.bib"))
    if bibs:
        return str(bibs[0])
    global_bib = config.bib_path()
    if global_bib.exists():
        return str(global_bib)
    return None


def _run_claude_code(prompt: str, *, model: str, max_tokens: int, cwd: str) -> str:
    """Spawn claude CLI as a subprocess to run the compiler agent.

    Uses `claude` CLI with --print flag for non-interactive execution.
    Falls back to Claude Code SDK Python API if available.
    """
    try:
        return _run_via_sdk(prompt, model=model, max_tokens=max_tokens, cwd=cwd)
    except ImportError:
        pass

    return _run_via_cli(prompt, model=model, max_tokens=max_tokens, cwd=cwd)


def _run_via_sdk(prompt: str, *, model: str, max_tokens: int, cwd: str) -> str:
    """Run via claude-code-sdk Python package."""
    from claude_code_sdk import ClaudeCodeOptions, query, ResultMessage, AssistantMessage

    options = ClaudeCodeOptions(
        model=model,
        max_turns=50,
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        cwd=cwd,
    )
    import asyncio

    async def _run():
        result_parts = []
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, (ResultMessage, AssistantMessage)):
                if hasattr(msg, "content"):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            result_parts.append(block.text)
        return "\n".join(result_parts)

    return asyncio.run(_run())


def _run_via_cli(prompt: str, *, model: str, max_tokens: int, cwd: str) -> str:
    """Run via claude CLI subprocess."""
    cmd = [
        "claude",
        "--print",
        "--model", model,
        "--max-turns", "50",
        "--allowedTools", "Read,Write,Edit,Bash(python *),Bash(ls *),Bash(mkdir *),Glob,Grep",
        "-p", prompt,
    ]

    print(f"[ara] Spawning compiler agent (model={model})...", file=sys.stderr, flush=True)

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


def _list_ara_files(d: Path) -> list[str]:
    """List files in an ARA directory relative to it."""
    return sorted(str(f.relative_to(d)) for f in d.rglob("*") if f.is_file())


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
        # Try as a direct relative path
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
