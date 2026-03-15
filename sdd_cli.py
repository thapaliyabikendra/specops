#!/usr/bin/env python3
"""
SDD CLI — Spec-Driven Development via LM Studio (Qwen3.5-4b)
Run: python sdd_cli.py
"""

import os
import sys
import json
import datetime
from pathlib import Path
from openai import OpenAI

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.rule import Rule

# ─── Config ────────────────────────────────────────────────────────────────────

LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
MODEL_NAME = "qwen3.5-4b-claude-4.6-opus-reasoning-distilled"          # adjust to match your LM Studio model name
SPECS_DIR = Path("./specs")      # where generated specs are saved
SPECS_DIR.mkdir(exist_ok=True)

client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key="lm-studio")
console = Console()

# ─── Prompts ───────────────────────────────────────────────────────────────────

PROMPTS = {
    "discovery": {
        "system": (
            "You are a senior product analyst specializing in translating vague stakeholder input "
            "into structured problem statements. You are rigorous and never assume unstated requirements.\n\n"
            "Produce output with these exact markdown sections:\n"
            "## Problem Statement\n## Confirmed Requirements\n## Open Questions\n"
            "## Suggested Success Metrics\n## Risks & Dependencies"
        ),
        "user_template": (
            "Analyze the following raw input and produce a structured discovery report.\n\n"
            "Feature Request / Stakeholder Notes:\n\"\"\"\n{input}\n\"\"\"\n\n"
            "Rules:\n"
            "- Do not invent requirements not present in the input\n"
            "- Flag contradictions explicitly\n"
            "- Keep Problem Statement to 3 sentences max\n"
            "- Phrase Open Questions as direct questions to ask a stakeholder"
        ),
    },
    "spec": {
        "system": (
            "You are an expert software architect and test designer specializing in Spec-Driven Development. "
            "Create comprehensive, testable specifications with zero ambiguity. "
            "Every statement must be verifiable through automated or manual testing.\n\n"
            "Use these markdown sections:\n"
            "## Feature Overview\n## Prerequisites & Context\n## User Flow (Happy Path)\n"
            "## Acceptance Criteria\n## Edge Cases & Error Scenarios\n"
            "## Non-Functional Requirements\n## Verification Plan"
        ),
        "user_template": (
            "Generate a complete SDD specification for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Domain:** {domain}\n"
            "**User Story:** {user_story}\n"
            "**Current State:** {current_state}\n"
            "**NFR Targets:** {nfr}\n\n"
            "Rules:\n"
            "- Criterion IDs: AC-{story_id}-001, AC-{story_id}-002, ...\n"
            "- Minimum 5 acceptance criteria, maximum 50\n"
            "- Each criterion must be binary (pass/fail)\n"
            "- Include at least one negative test case\n"
            "- Mark each priority: high / medium / low"
        ),
    },
    "review": {
        "system": (
            "You are a senior QA architect conducting a spec quality audit. "
            "Find gaps, ambiguities, and untestable statements before stakeholder sign-off.\n\n"
            "Output these markdown sections:\n"
            "## Ambiguous Statements\n## Untestable Criteria\n## Missing Edge Cases\n"
            "## Non-Functional Gaps\n## Dependency Risks\n## Overall Score"
        ),
        "user_template": (
            "Review this specification and produce a structured quality report.\n\n"
            "Specification:\n\"\"\"\n{spec}\n\"\"\"\n\n"
            "Rules:\n"
            "- Be specific — quote directly from the spec when flagging issues\n"
            "- Suggest rewrites, not just problems\n"
            "- Score each dimension 1–5: Completeness, Testability, Clarity, NFR Coverage, Edge Case Coverage\n"
            "- End with: APPROVE / APPROVE WITH CHANGES / REJECT"
        ),
    },
    "tests": {
        "system": (
            "You are a senior test engineer. Write clean test code that maps 1:1 to acceptance criteria. "
            "Each test function name must include the criterion ID for traceability. "
            "Use Arrange / Act / Assert structure with inline comments linking to spec IDs."
        ),
        "user_template": (
            "Generate test scaffolding for these acceptance criteria.\n\n"
            "**Language / Framework:** {framework}\n"
            "**Acceptance Criteria:**\n\"\"\"\n{criteria}\n\"\"\"\n"
            "**Available Mocks / Fixtures:** {mocks}\n\n"
            "Rules:\n"
            "- Function names: test_AC_XXX_short_description\n"
            "- Use describe/class blocks to group related criteria\n"
            "- Mark incomplete stubs with TODO\n"
            "- Include at least one negative test per group\n"
            "- Avoid generic assertions like toBeTruthy()"
        ),
    },
    "gap": {
        "system": (
            "You are a spec refinement engine. Analyze test results against an original spec "
            "to identify gaps, outdated criteria, and recommend living-document updates.\n\n"
            "Output these sections:\n"
            "## Failing Criteria Analysis\n## New Edge Cases Discovered\n"
            "## Outdated or Redundant Criteria\n## Spec Changelog"
        ),
        "user_template": (
            "Analyze test run results against the original spec.\n\n"
            "**Original Spec Acceptance Criteria:**\n\"\"\"\n{spec}\n\"\"\"\n\n"
            "**Test Results:**\n\"\"\"\n{results}\n\"\"\"\n\n"
            "**Bug Reports:**\n\"\"\"\n{bugs}\n\"\"\"\n\n"
            "Rules:\n"
            "- Distinguish spec bugs from implementation bugs\n"
            "- Proposed new criteria must follow existing spec format\n"
            "- Changelog date: {date}"
        ),
    },
    "fastspec": {
        "system": (
            "You are a concise spec writer for small, low-risk features. "
            "Generate lightweight fast-track specifications under 1 page.\n\n"
            "Output these sections:\n"
            "## Overview\n## Acceptance Criteria\n## Edge Cases\n## Definition of Done"
        ),
        "user_template": (
            "Generate a fast-track spec for:\n\n"
            "**Feature:** {feature}\n"
            "**Description:** {description}\n"
            "**Estimated Complexity:** Small (< 3 days)\n\n"
            "Rules:\n"
            "- Overview: 2 sentences max\n"
            "- Minimum 3, maximum 8 acceptance criteria\n"
            "- Edge cases: bullet list, max 5\n"
            "- Include a Definition of Done checklist"
        ),
    },
}

# ─── Core LLM call (streaming) ────────────────────────────────────────────────

def stream_llm(system: str, user: str, title: str) -> str:
    """Stream response from LM Studio and render markdown live."""
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]", style="cyan"))
    console.print()

    full_response = []
    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=4096,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            full_response.append(delta)
            console.print(delta, end="", markup=False)

    except Exception as e:
        console.print(f"\n[bold red]LM Studio Error:[/bold red] {e}")
        console.print(
            "[yellow]Tip: Make sure LM Studio is running on http://localhost:1234 "
            f"with model '{MODEL_NAME}' loaded.[/yellow]"
        )
        return ""

    console.print("\n")
    return "".join(full_response)


# ─── Save helper ──────────────────────────────────────────────────────────────

def save_spec(content: str, prefix: str, story_id: str = "") -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"{prefix}_{story_id}_{ts}" if story_id else f"{prefix}_{ts}"
    path = SPECS_DIR / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    console.print(f"[green]✔ Saved →[/green] [dim]{path}[/dim]\n")
    return path


# ─── Slash commands ────────────────────────────────────────────────────────────

def cmd_discovery():
    """/discovery — Analyze raw stakeholder notes into a structured problem statement."""
    console.print(Panel(
        "[bold]Phase 1 · Discovery Kickoff Analyzer[/bold]\n"
        "[dim]Paste your stakeholder notes or feature request. Type END on a new line to finish.[/dim]",
        style="cyan"
    ))
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    raw = "\n".join(lines)
    if not raw.strip():
        console.print("[red]No input provided.[/red]")
        return

    prompt = PROMPTS["discovery"]
    result = stream_llm(prompt["system"], prompt["user_template"].format(input=raw), "Discovery Report")
    if result:
        save_spec(result, "discovery")


def cmd_spec():
    """/spec — Generate a full SDD specification from a user story."""
    console.print(Panel(
        "[bold]Phase 2 · Full Spec Generator[/bold]\n"
        "[dim]Fill in the details below to generate a complete specification.[/dim]",
        style="cyan"
    ))
    story_id    = Prompt.ask("[cyan]Story ID[/cyan]", default="STORY-001")
    domain      = Prompt.ask("[cyan]Product Domain[/cyan]", default="Web Application")
    user_story  = Prompt.ask("[cyan]User Story[/cyan]")
    current_state = Prompt.ask("[cyan]Current System State[/cyan]", default="Not yet implemented")
    nfr         = Prompt.ask("[cyan]NFR Targets[/cyan]", default="p95 latency < 300ms, 99.9% uptime")

    prompt = PROMPTS["spec"]
    user_msg = prompt["user_template"].format(
        story_id=story_id, domain=domain, user_story=user_story,
        current_state=current_state, nfr=nfr
    )
    result = stream_llm(prompt["system"], user_msg, f"Specification — {story_id}")
    if result:
        save_spec(result, "spec", story_id)


def cmd_review():
    """/review — AI quality audit of a specification before sign-off."""
    console.print(Panel(
        "[bold]Phase 3 · Spec Quality Reviewer[/bold]\n"
        "[dim]Paste your spec document. Type END on a new line to finish.[/dim]",
        style="cyan"
    ))

    # List available saved specs
    saved = sorted(SPECS_DIR.glob("spec_*.md"))
    if saved:
        console.print("[dim]Saved specs found:[/dim]")
        for i, f in enumerate(saved, 1):
            console.print(f"  [dim]{i}.[/dim] {f.name}")
        choice = Prompt.ask(
            "Load a saved spec? Enter number or press Enter to paste manually",
            default=""
        )
        if choice.isdigit() and 1 <= int(choice) <= len(saved):
            spec_text = saved[int(choice) - 1].read_text(encoding="utf-8")
            console.print(f"[green]Loaded:[/green] {saved[int(choice)-1].name}")
        else:
            spec_text = _read_multiline()
    else:
        spec_text = _read_multiline()

    if not spec_text.strip():
        console.print("[red]No spec provided.[/red]")
        return

    prompt = PROMPTS["review"]
    result = stream_llm(prompt["system"], prompt["user_template"].format(spec=spec_text), "Spec Quality Report")
    if result:
        save_spec(result, "review")


def cmd_tests():
    """/tests — Generate test scaffolding from acceptance criteria."""
    console.print(Panel(
        "[bold]Phase 4 · Test Code Generator[/bold]\n"
        "[dim]Paste your acceptance criteria section. Type END on a new line to finish.[/dim]",
        style="cyan"
    ))
    framework = Prompt.ask("[cyan]Language / Framework[/cyan]", default="Python / pytest")
    mocks     = Prompt.ask("[cyan]Available mocks / fixtures[/cyan]", default="None specified")
    console.print("[dim]Paste acceptance criteria now:[/dim]")
    criteria = _read_multiline()

    if not criteria.strip():
        console.print("[red]No criteria provided.[/red]")
        return

    prompt = PROMPTS["tests"]
    user_msg = prompt["user_template"].format(
        framework=framework, criteria=criteria, mocks=mocks
    )
    result = stream_llm(prompt["system"], user_msg, f"Test Scaffolding — {framework}")
    if result:
        save_spec(result, "tests")


def cmd_gap():
    """/gap — Post-release regression & gap analyzer to refine living specs."""
    console.print(Panel(
        "[bold]Phase 6 · Gap & Regression Analyzer[/bold]\n"
        "[dim]Feed in test results and bug reports to refine your spec.[/dim]",
        style="cyan"
    ))

    # Load spec
    saved = sorted(SPECS_DIR.glob("spec_*.md"))
    spec_text = ""
    if saved:
        console.print("[dim]Available specs:[/dim]")
        for i, f in enumerate(saved, 1):
            console.print(f"  [dim]{i}.[/dim] {f.name}")
        choice = Prompt.ask("Load a spec by number, or Enter to paste", default="")
        if choice.isdigit() and 1 <= int(choice) <= len(saved):
            spec_text = saved[int(choice) - 1].read_text(encoding="utf-8")

    if not spec_text:
        console.print("[dim]Paste spec acceptance criteria:[/dim]")
        spec_text = _read_multiline()

    console.print("[dim]Paste test results / log:[/dim]")
    results = _read_multiline()

    console.print("[dim]Paste bug report summary (or leave blank):[/dim]")
    bugs = _read_multiline() or "None"

    prompt = PROMPTS["gap"]
    user_msg = prompt["user_template"].format(
        spec=spec_text, results=results, bugs=bugs,
        date=datetime.date.today().isoformat()
    )
    result = stream_llm(prompt["system"], user_msg, "Gap Analysis & Spec Changelog")
    if result:
        save_spec(result, "gap")


def cmd_fastspec():
    """/fastspec — Lightweight fast-track spec for small features."""
    console.print(Panel(
        "[bold]Fast-Track Spec · Small / Low-Risk Features[/bold]\n"
        "[dim]For features estimated < 3 days. Generates a concise, 1-page spec.[/dim]",
        style="cyan"
    ))
    feature     = Prompt.ask("[cyan]Feature name[/cyan]")
    description = Prompt.ask("[cyan]Brief description[/cyan]")

    prompt = PROMPTS["fastspec"]
    user_msg = prompt["user_template"].format(feature=feature, description=description)
    result = stream_llm(prompt["system"], user_msg, f"Fast-Track Spec — {feature}")
    if result:
        save_spec(result, "fastspec", feature.replace(" ", "_").lower())


def cmd_list():
    """/list — List all saved spec files."""
    files = sorted(SPECS_DIR.glob("*.md"))
    if not files:
        console.print("[yellow]No specs saved yet. Run /spec or /fastspec to generate one.[/yellow]")
        return
    table = Table(title="Saved Specifications", style="cyan", header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="white")
    table.add_column("Type", style="green")
    table.add_column("Size", justify="right", style="dim")
    for i, f in enumerate(files, 1):
        kind = f.stem.split("_")[0].capitalize()
        size = f"{f.stat().st_size // 1024} KB" if f.stat().st_size >= 1024 else f"{f.stat().st_size} B"
        table.add_row(str(i), f.name, kind, size)
    console.print(table)


def cmd_view():
    """/view — View a saved spec file rendered as markdown."""
    cmd_list()
    files = sorted(SPECS_DIR.glob("*.md"))
    if not files:
        return
    choice = Prompt.ask("Enter file number to view")
    if choice.isdigit() and 1 <= int(choice) <= len(files):
        content = files[int(choice) - 1].read_text(encoding="utf-8")
        console.print(Markdown(content))
    else:
        console.print("[red]Invalid selection.[/red]")


def cmd_help():
    """/help — Show all available commands."""
    table = Table(title="SDD CLI — Available Slash Commands", style="cyan", header_style="bold cyan")
    table.add_column("Command", style="bold white", width=14)
    table.add_column("Phase", style="green", width=8)
    table.add_column("Description")
    rows = [
        ("/discovery", "1", "Analyze raw stakeholder notes → structured problem statement"),
        ("/spec",       "2", "Generate a full SDD specification from a user story"),
        ("/review",     "3", "AI quality audit — find gaps before sign-off"),
        ("/tests",      "4", "Generate test scaffolding from acceptance criteria"),
        ("/gap",        "6", "Post-release gap analyzer — refine living specs"),
        ("/fastspec",   "2", "Lightweight 1-page spec for small features"),
        ("/list",       "—", "List all saved spec files"),
        ("/view",       "—", "Render a saved spec as formatted markdown"),
        ("/help",       "—", "Show this help message"),
        ("/exit",       "—", "Exit the CLI"),
    ]
    for cmd, phase, desc in rows:
        table.add_row(cmd, phase, desc)
    console.print(table)
    console.print(
        f"\n[dim]Model:[/dim] [cyan]{MODEL_NAME}[/cyan]  "
        f"[dim]LM Studio:[/dim] [cyan]{LMSTUDIO_BASE_URL}[/cyan]  "
        f"[dim]Specs saved to:[/dim] [cyan]{SPECS_DIR.resolve()}[/cyan]\n"
    )


# ─── Utilities ─────────────────────────────────────────────────────────────────

def _read_multiline() -> str:
    """Read multi-line input until user types END."""
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


COMMANDS = {
    "/discovery": cmd_discovery,
    "/spec":      cmd_spec,
    "/review":    cmd_review,
    "/tests":     cmd_tests,
    "/gap":       cmd_gap,
    "/fastspec":  cmd_fastspec,
    "/list":      cmd_list,
    "/view":      cmd_view,
    "/help":      cmd_help,
}

# ─── REPL ──────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel.fit(
        "[bold cyan]SDD CLI[/bold cyan]  ·  Spec-Driven Development\n"
        f"[dim]Model:[/dim] [cyan]{MODEL_NAME}[/cyan]  "
        f"[dim]LM Studio:[/dim] [cyan]{LMSTUDIO_BASE_URL}[/cyan]\n"
        "[dim]Type[/dim] [bold white]/help[/bold white] [dim]to see all commands[/dim]",
        border_style="cyan"
    ))
    console.print()

    while True:
        try:
            raw = Prompt.ask("[bold cyan]sdd[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if not raw:
            continue

        cmd = raw.split()[0].lower()

        if cmd in ("/exit", "/quit", "/q"):
            console.print("[dim]Bye![/dim]")
            break
        elif cmd in COMMANDS:
            try:
                COMMANDS[cmd]()
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
        else:
            console.print(
                f"[red]Unknown command:[/red] [bold]{cmd}[/bold]  "
                "[dim]— type /help for available commands[/dim]"
            )


if __name__ == "__main__":
    main()
