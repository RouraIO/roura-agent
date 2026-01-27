# Roura Agent v2.0 - The Real Roadmap

## The Vision

**Roura Agent is the CLI you run when tests fail, CI is red, PRs are blocked, and migrations are scary.**

Not a chatbot. Not a code generator. An **autonomous coding agent** that fixes problems, not just describes them.

---

## Target User (ICP)

**Senior developers and tech leads at 10-100 person engineering teams** who:
- Spend 30%+ of time on maintenance, not features
- Have CI pipelines that break weekly
- Context-switch between 3-5 repos
- Value privacy (can't paste code into ChatGPT)
- Live in the terminal

**Pain point**: "I know what needs to be done, I just don't have time to do it."

---

## Value Proposition

1. **Fix failing tests autonomously** — point it at red CI, it fixes it
2. **Your codebase, your machine** — runs locally with Ollama, code never leaves
3. **Safe by design** — diffs, approvals, blast radius limits, secrets detection

---

## Pricing Model (Indie SaaS: Target $20-50k/mo)

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | Ollama only, 5 tools, no integrations |
| **Pro** | $29/mo | All providers, all tools, GitHub/Jira, 1 repo |
| **Team** | $99/mo | Unlimited repos, GitLab, CI integrations, priority support |
| **Enterprise** | Custom | SSO, audit logs, policy profiles, on-prem |

---

## ROI Metric

**"Roura Agent saves 8+ hours/week per developer on maintenance tasks."**

Measured by:
- Time to fix failing tests (before/after)
- PR cycle time reduction
- CI red-to-green time

---

## Security Guarantees

- Code never leaves your machine (Ollama mode)
- API keys never logged or transmitted
- Secrets detection before any commit
- Audit trail of all agent actions
- SOC2 compliance roadmap (Enterprise)

---

# The 100 Features

## Phase 1: Foundation (Items 1-25) — "Make It Real"
**Timeline: Weeks 1-4**
**Theme: Test/Build/Lint + Core Safety**

### Test Runner Tools (1-6)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 1 | `test.run` - Auto-detect and run test suite (pytest/cargo/npm/go/swift) | P0 | L |
| 2 | `test.failures` - Parse and return only failing tests with stack traces | P0 | M |
| 3 | `test.watch` - Watch mode with re-run on file change | P1 | M |
| 4 | `test.fix` - Autonomous loop: run tests → analyze failure → fix → retry | P0 | XL |
| 5 | `test.coverage` - Run with coverage, report uncovered lines | P1 | M |
| 6 | `test.last` - Re-run last failed test | P1 | S |

### Build Tools (7-11)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 7 | `build.run` - Auto-detect and run build (cargo/npm/go/swift/gradle) | P0 | L |
| 8 | `build.errors` - Parse compiler errors into structured format | P0 | M |
| 9 | `build.fix` - Autonomous loop: build → parse error → fix → retry | P0 | XL |
| 10 | `build.clean` - Clean build artifacts | P1 | S |
| 11 | `build.watch` - Watch mode with rebuild on change | P2 | M |

### Lint & Format Tools (12-17)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 12 | `lint.run` - Auto-detect linter (ruff/eslint/clippy/swiftlint/golangci) | P0 | L |
| 13 | `lint.fix` - Run linter with auto-fix | P0 | M |
| 14 | `format.run` - Auto-detect formatter (black/prettier/rustfmt/swift-format) | P0 | M |
| 15 | `format.check` - Check formatting without modifying | P1 | S |
| 16 | `typecheck.run` - Run type checker (mypy/pyright/tsc) | P1 | M |
| 17 | `typecheck.fix` - Fix type errors autonomously | P1 | L |

### Secrets & Safety (18-25)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 18 | Secrets detection before any file write or commit | P0 | L |
| 19 | Secrets redaction in logs and output | P0 | M |
| 20 | `--dry-run` mode - Simulate entire plan without touching disk | P0 | L |
| 21 | Blast radius: max files per edit (default 10) | P0 | M |
| 22 | Blast radius: max LOC per change (default 500) | P0 | M |
| 23 | Blast radius: forbidden directories (node_modules, .git, etc.) | P0 | S |
| 24 | `--readonly` mode - No writes, only analysis | P1 | S |
| 25 | File glob allowlist/blocklist per session | P1 | M |

---

## Phase 2: Memory & Intelligence (Items 26-45) — "Make It Smart"
**Timeline: Weeks 5-8**
**Theme: Deep Context + Project Understanding**

### Project Memory (26-35)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 26 | Auto-generate project summary on first run (architecture, stack, conventions) | P0 | L |
| 27 | Store build/test/lint commands per project | P0 | M |
| 28 | Store coding conventions (from .editorconfig, linter configs) | P1 | M |
| 29 | Store CI provider and pipeline structure | P1 | M |
| 30 | Store deploy steps and environments | P2 | M |
| 31 | Store secrets locations (not values) | P1 | S |
| 32 | `memory.project` - View/edit project memory | P0 | S |
| 33 | `memory.refresh` - Re-scan and update project memory | P1 | M |
| 34 | `memory.export` - Export project memory as markdown | P2 | S |
| 35 | Cross-session project memory persistence | P0 | M |

### User Preferences (36-40)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 36 | Store preferred editor/IDE | P2 | S |
| 37 | Store commit message style (conventional, etc.) | P1 | S |
| 38 | Store PR template preferences | P2 | S |
| 39 | Store verbosity preferences | P1 | S |
| 40 | Store default approval mode | P1 | S |

### Task Memory & Orchestration (41-45)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 41 | `/task start "description"` - Begin multi-session task | P1 | L |
| 42 | `/task status` - Show current task progress | P1 | M |
| 43 | `/task checkpoint` - Save progress point | P1 | M |
| 44 | `/task resume` - Continue from checkpoint | P1 | M |
| 45 | `/task abort` - Cancel with rollback option | P1 | M |

---

## Phase 3: Integrations (Items 46-60) — "Make It Connected"
**Timeline: Weeks 9-12**
**Theme: Git Platforms + CI Providers**

### GitLab Integration (46-50)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 46 | `gitlab.mr.list` - List merge requests | P0 | M |
| 47 | `gitlab.mr.view` - View MR details | P0 | M |
| 48 | `gitlab.mr.create` - Create merge request | P0 | M |
| 49 | `gitlab.issue.list/view/create` - Issue management | P1 | M |
| 50 | `gitlab.pipeline.status` - View pipeline status | P0 | M |

### CI Provider Integration (51-57)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 51 | `ci.status` - Get current CI status (auto-detect provider) | P0 | L |
| 52 | `ci.logs` - Fetch logs from failed jobs | P0 | L |
| 53 | `ci.rerun` - Re-run failed jobs | P1 | M |
| 54 | GitHub Actions integration | P0 | M |
| 55 | GitLab CI integration | P0 | M |
| 56 | CircleCI integration | P2 | M |
| 57 | `ci.fix` - Autonomous loop: fetch logs → analyze → fix → push → wait | P0 | XL |

### Dependency Management (58-60)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 58 | `deps.list` - List project dependencies | P1 | M |
| 59 | `deps.audit` - Security audit (npm audit, pip-audit, cargo audit) | P0 | L |
| 60 | `deps.upgrade` - Upgrade with test verification | P1 | L |

---

## Phase 4: Agent Control (Items 61-75) — "Make It Controllable"
**Timeline: Weeks 13-16**
**Theme: Planning + Policies + Observability**

### Planning Mode (61-66)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 61 | `/plan` - Generate execution plan before acting | P0 | L |
| 62 | `/plan approve` - Approve and execute plan | P0 | M |
| 63 | `/plan edit` - Modify plan before execution | P1 | M |
| 64 | `/estimate` - Estimate time/risk for proposed changes | P1 | L |
| 65 | `/risk` - Analyze risk of proposed changes | P1 | L |
| 66 | `/rollback` - Generate rollback plan | P1 | M |

### Policy Profiles (67-72)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 67 | `--policy strict` - Maximum approvals, no shell | P0 | M |
| 68 | `--policy ci-only` - Only build/test/lint tools | P1 | M |
| 69 | `--policy readonly` - Analysis only, no writes | P0 | S |
| 70 | `--policy prod-repo` - Extra confirmations, no force push | P1 | M |
| 71 | Custom policy files (.roura/policy.yaml) | P1 | L |
| 72 | Team-shared policies via config | P2 | M |

### Constraints System (73-75)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 73 | `/constraints "no new deps"` - Inject constraints | P1 | M |
| 74 | `/constraints "touch only src/api"` - Path constraints | P1 | M |
| 75 | `/constraints "keep API stable"` - Semantic constraints | P2 | L |

---

## Phase 5: Observability (Items 76-82) — "Make It Debuggable"
**Timeline: Weeks 17-18**
**Theme: Traces + Logs + Replay**

| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 76 | `/trace` - Show full reasoning trace for last action | P0 | M |
| 77 | `/tool-log` - Show all tool calls in session | P0 | S |
| 78 | `/reasoning` - Summarize agent's reasoning | P1 | M |
| 79 | `/replay` - Replay session from checkpoint | P1 | L |
| 80 | `/export-trace` - Export trace as JSON for debugging | P1 | M |
| 81 | Structured audit log (JSON) for all actions | P0 | M |
| 82 | Web dashboard for trace visualization (future) | P3 | XL |

---

## Phase 6: Language Power Features (Items 83-92) — "Make It Expert"
**Timeline: Weeks 19-22**
**Theme: Deep Language Integration**

### Swift-Specific (83-86)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 83 | SwiftPM dependency graph ingestion | P1 | L |
| 84 | Xcode build log parser | P1 | L |
| 85 | SwiftLint autofix loops | P1 | M |
| 86 | MainActor/concurrency checker | P2 | L |

### Python-Specific (87-89)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 87 | pyproject.toml parser for project config | P1 | M |
| 88 | virtualenv auto-activation | P1 | M |
| 89 | Coverage tracking and improvement suggestions | P2 | L |

### Rust/Go/Node (90-92)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 90 | Cargo clippy autonomous fix loops | P1 | M |
| 91 | Go module dependency analysis | P2 | M |
| 92 | npm/yarn/pnpm lockfile understanding | P1 | M |

---

## Phase 7: Distribution & Polish (Items 93-100) — "Make It Shippable"
**Timeline: Weeks 23-26**
**Theme: Updates + IDE + Business**

### Distribution (93-96)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 93 | Auto-update system with version check | P0 | L |
| 94 | Release channels (stable/beta/nightly) | P1 | M |
| 95 | `roura-agent changelog` - View recent changes | P1 | S |
| 96 | Homebrew formula | P0 | M |

### IDE Bridge (97-98)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 97 | VS Code extension (state sharing) | P1 | XL |
| 98 | Neovim plugin | P2 | L |

### Business Features (99-100)
| # | Feature | Priority | Effort |
|---|---------|----------|--------|
| 99 | License key validation system | P0 | L |
| 100 | Usage analytics (opt-in) for product improvement | P1 | M |

---

## Priority Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0** | 38 | Critical - blocks launch |
| **P1** | 42 | High - core differentiation |
| **P2** | 17 | Medium - nice to have |
| **P3** | 3 | Future - post-launch |

---

## Effort Summary

| Effort | Count | Time Each |
|--------|-------|-----------|
| **S** | 15 | 1-2 hours |
| **M** | 48 | 4-8 hours |
| **L** | 28 | 1-2 days |
| **XL** | 9 | 3+ days |

**Total Estimated**: ~16-20 weeks of focused development

---

## Phase 1 Sprint Plan (Weeks 1-4)

### Week 1: Test Runner Foundation
- [ ] #1 `test.run` - language detection + execution
- [ ] #2 `test.failures` - failure parsing
- [ ] #7 `build.run` - build system detection

### Week 2: Lint + Format + Build Errors
- [ ] #8 `build.errors` - compiler error parsing
- [ ] #12 `lint.run` - linter detection
- [ ] #13 `lint.fix` - autofix
- [ ] #14 `format.run` - formatter detection

### Week 3: Autonomous Fix Loops
- [ ] #4 `test.fix` - THE KILLER FEATURE
- [ ] #9 `build.fix` - compile error fixing
- [ ] #18 Secrets detection

### Week 4: Safety + Dry Run
- [ ] #19 Secrets redaction
- [ ] #20 `--dry-run` mode
- [ ] #21-23 Blast radius limits

---

## Success Metrics

### Phase 1 Complete When:
- [ ] `roura-agent test.fix` can fix simple test failures autonomously
- [ ] `roura-agent build.fix` can fix simple compile errors
- [ ] Secrets are detected and blocked before commit
- [ ] Dry-run mode shows full plan without execution

### MVP Complete When:
- [ ] 10 beta users using daily
- [ ] 90%+ of simple test failures fixed autonomously
- [ ] GitLab + GitHub Actions integrated
- [ ] $1k MRR from early adopters

### v2.0 Complete When:
- [ ] All 100 features shipped
- [ ] $20k MRR
- [ ] <5% of agent actions require manual correction
- [ ] VS Code extension live

---

## Comparison Grid (For Marketing)

| Feature | Roura Agent | GitHub Copilot | Cursor | Aider | Claude Code |
|---------|-------------|----------------|--------|-------|-------------|
| Local-first (Ollama) | ✅ | ❌ | ❌ | ✅ | ❌ |
| Autonomous test fixing | ✅ | ❌ | ❌ | ❌ | ❌ |
| CI log ingestion | ✅ | ❌ | ❌ | ❌ | ❌ |
| Git/GitHub/GitLab | ✅ | ✅ | ❌ | ✅ | ✅ |
| Jira integration | ✅ | ❌ | ❌ | ❌ | ❌ |
| Secrets detection | ✅ | ❌ | ❌ | ❌ | ❌ |
| Policy profiles | ✅ | ❌ | ❌ | ❌ | ❌ |
| Blast radius limits | ✅ | ❌ | ❌ | ❌ | ❌ |
| Multi-provider | ✅ | ❌ | ✅ | ✅ | ❌ |
| Session persistence | ✅ | ❌ | ✅ | ❌ | ✅ |
| Price | $29/mo | $19/mo | $20/mo | Free | $20/mo |

---

## The New Pitch (A+ Version)

# Roura Agent

## **Fix failing tests in 30 seconds, not 30 minutes.**

The AI coding agent that lives in your terminal. Point it at red CI — it reads the logs, finds the bug, fixes it, and opens the PR.

### For senior developers who are tired of maintenance work.

**Why Roura Agent?**

1. **Autonomous test fixing** — `roura-agent test.fix` runs your tests, parses failures, fixes code, and retries until green
2. **Local-first privacy** — Runs on Ollama. Your code never leaves your machine.
3. **Safe by design** — Secrets detection, blast radius limits, diff previews, and policy profiles

### Pricing

| Free | Pro ($29/mo) | Team ($99/mo) |
|------|--------------|---------------|
| Ollama only | + OpenAI/Claude | + Unlimited repos |
| 5 tools | + All 31 tools | + GitLab + CI |
| No integrations | + GitHub/Jira | + Policy profiles |

### Security

- ✅ Code never transmitted (Ollama mode)
- ✅ Secrets detected and blocked
- ✅ Full audit trail
- ✅ SOC2 roadmap

```bash
pip install roura-agent
roura-agent test.fix
```

**→ [Watch 90-second demo](#)**
**→ [Read the docs](https://docs.roura.io)**

*"Saved me 6 hours this week on test fixes alone." — Beta User*

---

*Built by Roura.io*
