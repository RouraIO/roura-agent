# Changelog

All notable changes to Roura Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-01-26

### Added

- **Multi-provider support**: Seamlessly switch between Ollama, OpenAI, and Anthropic
  - Auto-detection based on available credentials
  - `--provider` flag to force specific provider
  - Provider info displayed on startup
- **45+ tools** for filesystem, git, shell, testing, building, and linting
- **Autonomous fix loops**: test.fix, build.fix, typecheck.fix for iterative problem solving
- **Session persistence** with auto-save
  - Sessions automatically saved after each turn
  - `/history` to view past sessions
  - `/resume <id>` to continue conversations
  - `/export` to export sessions as JSON or Markdown
- **Safety controls**:
  - Blast radius limits with `--allow` and `--block` patterns
  - Secrets detection to prevent credential commits
  - Dry-run mode (`--dry-run`) for previewing changes
  - Read-only mode (`--readonly`) to block all modifications
  - Safe mode (`--safe-mode`) to disable dangerous tools
- **Rich TUI** with streaming responses and progress indicators
- **Undo support** with `/undo` command
- **GitHub integration**: List, view, and create PRs and issues
- **Jira integration**: Search, view, create, and transition issues
- **CI/CD pipeline** with GitHub Actions

### Changed

- Provider architecture refactored to use registry pattern
- Improved error messages with recovery hints

## [0.4.0] - 2026-01-20

### Added

- OpenAI provider implementation
- Anthropic provider implementation
- Provider registry for dynamic provider management

## [0.3.0] - 2026-01-15

### Added

- Session management module
- Undo stack for file changes
- Context summarization for long conversations

## [0.2.0] - 2026-01-10

### Added

- GitHub integration tools
- Jira integration tools
- Safety mode and blast radius limits

## [0.1.0] - 2026-01-05

### Added

- Initial release
- Ollama provider with native tool calling
- File operations (read, write, edit, list)
- Git operations (status, diff, log, add, commit)
- Shell command execution with safety guardrails
- Rich terminal interface
