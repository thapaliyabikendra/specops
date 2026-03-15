# SDD CLI — Spec-Driven Development via LM Studio

Run a full SDD workflow from your terminal using **Qwen3.5-4b** through **LM Studio**.

---

## Prerequisites

1. **LM Studio** installed and running on `http://localhost:1234`
2. **Qwen3.5-4b** (or compatible model) loaded in LM Studio
3. **Python 3.9+**

---

## Setup

```bash
# 1. Create the environment:
uv venv 
# 2. Install dependencies
uv pip install -r requirements.txt

# 3. Run the CLI
uv run sdd_cli.py
```

> No API keys needed — LM Studio runs fully locally.

---

## Slash Commands

| Command | SDD Phase | What it does |
|---------|-----------|--------------|
| `/discovery` | Phase 1 | Analyze stakeholder notes → structured problem statement |
| `/spec` | Phase 2 | Generate a full specification from a user story |
| `/review` | Phase 3 | AI quality audit before stakeholder sign-off |
| `/tests` | Phase 4 | Generate test scaffolding from acceptance criteria |
| `/gap` | Phase 6 | Post-release gap analysis to refine living specs |
| `/fastspec` | Phase 2 | Lightweight 1-page spec for small features |
| `/list` | — | List all saved spec files |
| `/view` | — | Render a saved spec as formatted markdown |
| `/help` | — | Show all commands |
| `/exit` | — | Exit |

---

## Typical Workflow

```
sdd> /discovery
# Paste stakeholder notes, type END to finish

sdd> /spec
# Fill in story ID, domain, user story, etc.

sdd> /review
# Load or paste a spec → get quality score + APPROVE / REJECT

sdd> /tests
# Paste acceptance criteria → get test scaffolding

sdd> /gap
# After a test run, load spec + paste results → get changelog
```

All generated specs are saved as Markdown files in the `./specs/` folder.

---

## Configuration

Edit the top of `sdd_cli.py` to change defaults:

```python
LMSTUDIO_BASE_URL = "http://localhost:1234/v1"   # LM Studio URL
MODEL_NAME        = "qwen3-4b"                    # Match your LM Studio model name exactly
SPECS_DIR         = Path("./specs")               # Where specs are saved
```

> **Model name:** In LM Studio → Developer tab, copy the model identifier exactly and paste it into `MODEL_NAME`.

---

## Tips

- Type `END` on a new line to finish any multi-line paste input
- `/view` renders markdown with syntax highlighting
- Spec files are named by type + story ID + timestamp for easy sorting
- All prompts use `temperature=0.2` for structured, consistent output
