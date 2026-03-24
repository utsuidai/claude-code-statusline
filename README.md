# claude-code-statusline

A rich two-line status line for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

![Python 3](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Screenshot

<p align="center">
  <img src="screenshot.svg" alt="statusline screenshot" width="880">
</p>

## What it shows

**Line 1** — Model, working directory, git status, worktree, vim mode

| Segment | Description |
|---------|-------------|
| Model | Current Claude model name |
| Directory | Working directory (~ abbreviated) |
| Git branch | Branch name with powerline icon |
| Git status | `*N` dirty, `+N` staged, `?N` untracked |
| Ahead/Behind | `↑N` ahead, `↓N` behind upstream |
| Worktree | Active worktree name (if any) |
| Vim mode | `[NORMAL]` / `[INSERT]` / `[VISUAL]` (if enabled) |

**Line 2** — Context window, rate limits, cost, duration

| Segment | Description |
|---------|-------------|
| Context | Fine-grained progress bar with truecolor gradient |
| 5h / 7d | Rate limit progress bar with truecolor gradient and countdown to reset |
| Cost | Total session cost in USD |
| Duration | Total session duration |

Each segment (label, progress bar, percentage, reset countdown) uses the same truecolor (24-bit RGB) gradient that smoothly shifts from green → yellow → red as usage increases. Progress bars use Unicode block elements (`▏▎▍▌▋▊▉█`) for ~1% precision.

## Setup

### 1. Copy the script

```bash
curl -o ~/.claude/statusline.py \
  https://raw.githubusercontent.com/utsuidai/claude-code-statusline/main/statusline.py
chmod +x ~/.claude/statusline.py
```

### 2. Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py"
  }
}
```

That's it. Restart Claude Code and the status line will appear.

## Requirements

- Python 3.10+
- Git (for git status segments)
- A terminal with truecolor (24-bit) support and Unicode (e.g. iTerm2, Ghostty, WezTerm, Windows Terminal)

## How it works

Claude Code pipes a JSON object to stdin containing session metadata (model, context window usage, cost, rate limits, etc.). This script reads that JSON and outputs ANSI-colored text that Claude Code renders as the status line.

The JSON schema includes:

```json
{
  "model": { "display_name": "..." },
  "workspace": { "current_dir": "..." },
  "context_window": { "used_percentage": 0 },
  "cost": { "total_cost_usd": 0, "total_duration_ms": 0 },
  "rate_limits": {
    "five_hour": { "used_percentage": 0 },
    "seven_day": { "used_percentage": 0 }
  },
  "vim": { "mode": "NORMAL" },
  "worktree": { "name": "..." }
}
```

## License

MIT
