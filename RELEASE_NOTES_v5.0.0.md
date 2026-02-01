# ROURA-AGENT v5.0.0 - "HARD MODE" RELEASE

**Release Date:** 2026-02-01

---

## MAJOR FEATURES

### 1. HARD MODE AUTO-ROUTING
When any of 48 code-related tokens are detected, automatically escalates to exhaustive workflows. No more generic chat responses when you're asking about code.

**Tokens include:** code, repo, review, swift, xcode, firebase, api, error, crash, build, test, refactor, auth, service, model, view, viewmodel, concurrency, actor, performance, memory, and more.

**Routing logic:**
- `DIAGNOSE` → Errors, crashes, build failures
- `CODE_WRITE` → Implement, create, refactor, fix
- `CODE_REVIEW_EXHAUSTIVE` → Review, analyze, audit
- `CHAT` → Only when no code tokens detected

### 2. DEEP EXHAUSTIVE CODE REVIEW
New `/review deep` command that NEVER outputs "No issues found" alone.

**Checks performed:**
- God file detection (>400 lines → suggest split)
- Duplicate code pattern detection
- Missing tests for public modules
- Routing correctness verification
- Execution loop presence check
- CI/CD workflow analysis
- Code quality patterns (TODOs, function size)

**Always outputs:**
- Prioritized actions
- Structural improvements
- Next investments

### 3. EXECUTION LOOP (Apply → Run → Feed → Repeat)
After code changes, automatically runs verification commands and iterates until green.

**Features:**
- Auto-detects project type (Python, Node.js, Swift, Go, Rust)
- Maximum 12 iterations (local powerhouse mode)
- Stall detection via failure signatures
- Automatic Unblocker agent invocation when stuck
- Atomic file edits with temp file + replace

### 4. PERSISTENT REPO INDEX
Build and cache repository metadata for faster exploration.

**Index includes:**
- File counts by extension
- Largest files by line count
- Test file detection
- Key file identification
- Primary language detection

**Stored at:** `.roura/index.json`

### 5. PROGRESS UI
Consistent task tracking for all grind-mode operations.

**Features:**
- Task list with status icons (○ ● ✓ ✗)
- Live progress updates with Rich
- Retry tracking with "approach failed, switching" messages
- Duration tracking per task

### 6. AGENT PROMPTS SYSTEM
Structured prompts for specialized agents with strict output contracts.

**Agents:**
- ReviewArchitect → JSON findings with severity levels
- Coding → FileEdits JSON with verification commands
- Verifier → Execution results with exit codes
- Unblocker → Targeted fixes for stall resolution

### 7. NEW BANNER
Updated ASCII art banner prominently displaying **ROURA.IO**.

---

## NEW MODULES

| Module | Purpose |
|--------|---------|
| `roura_agent/intent.py` | Hard Mode intent classification |
| `roura_agent/repo_tools.py` | File listing, search, read |
| `roura_agent/repo_index.py` | Persistent repo intelligence |
| `roura_agent/review_v2.py` | Deep exhaustive review |
| `roura_agent/execution_loop.py` | Apply → run → feed → repeat |
| `roura_agent/ui/progress.py` | Task list and progress tracking |
| `roura_agent/agents/prompts.py` | Agent prompt templates |

---

## TEST COVERAGE

- **1213 tests passing** (95 new tests added)
- All new modules have comprehensive test coverage
- Regression tests for critical features

---

## BREAKING CHANGES

None. v5.0.0 is fully backward compatible with v4.x.

---

## SELL CHECKLIST

✅ **Hard Mode is always ON** - No more missed code context
✅ **Deep review produces actionable findings** - Never "no issues found"
✅ **Execution loop grinds to green** - Up to 12 iterations
✅ **Unblocker resolves stalls** - Automatic intervention
✅ **Progress is visible** - Task lists with status updates
✅ **Repo is indexed** - Fast exploration
✅ **Banner shows ROURA.IO** - Clear branding
✅ **1213 tests pass** - Production ready

---

## UPGRADE

```bash
pip install --upgrade roura-agent
# or
roura-agent --version  # Should show 5.0.0
```

---

## WHAT'S NEXT

- v5.1: Multi-agent parallel execution
- v5.2: MCP integration for external tools
- v5.3: GitHub PR review workflow

---

© ROURA.IO 2026
