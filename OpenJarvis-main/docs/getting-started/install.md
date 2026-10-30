# Installation

## Platform-specific guides

| Platform | One-liner | Detailed guide |
|---|---|---|
| **macOS** | `curl -fsSL https://open-jarvis.github.io/OpenJarvis/install.sh \| bash` | [macOS install](macos.md) |
| **Linux** | `curl -fsSL https://open-jarvis.github.io/OpenJarvis/install.sh \| bash` | [Linux install](linux.md) |
| **WSL2 on Windows** | `curl -fsSL https://open-jarvis.github.io/OpenJarvis/install.sh \| bash` (run inside Ubuntu) | [WSL2 install](wsl2.md) |
| **Native Windows** | `irm https://open-jarvis.github.io/OpenJarvis/install.ps1 \| iex` | [Native Windows install](windows-native.md) |
| **Desktop GUI** | Download from the [latest release](https://github.com/open-jarvis/OpenJarvis/releases) | — |

The bash and PowerShell installers do the same thing on their respective hosts. When `OPENROUTER_API_KEY` is present, both switch to cloud-only mode: they write an OpenRouter config and skip installing, starting, and downloading Ollama. Without that key, they keep the local-first Ollama path. The rest of this page documents the bash installer in detail; the [native Windows guide](windows-native.md) is the equivalent reference for PowerShell.

## Bash installer

```bash
curl -fsSL https://open-jarvis.github.io/OpenJarvis/install.sh | bash
```

The installer downloads everything for you — including [uv](https://docs.astral.sh/uv/)
(the Python package manager) and the Python venv. Without `OPENROUTER_API_KEY`,
it also installs Ollama and a small starter model. With that key, it skips all
local inference setup and writes the cloud config. **You don't need to install
uv or any other prerequisite first.**

!!! info "Install URL"
    This script is served straight from the project's own GitHub Pages site,
    so HTTPS always works. You may also see `https://openjarvis.ai/install.sh`
    referenced in older docs — that domain is community-operated and has had
    intermittent TLS issues ([#337](https://github.com/open-jarvis/OpenJarvis/issues/337)).
    The `open-jarvis.github.io` URL above is the canonical one.

About 3 minutes on a typical broadband connection. Type `jarvis` to start chatting.

Before sending any installation analytics, the Bash installer displays a
dedicated optional-sharing prompt: **Press Enter or Y to consent, or N to
decline**. The choice also controls runtime analytics. No terminal, EOF, or
cancelled input leaves sharing off. See [Telemetry](../telemetry.md) for details.

## What the installer does

| Phase | Step | Where |
|---|---|---|
| Foreground | Install `uv` (Python package manager) | `~/.cargo/bin/` or `~/.local/bin/` |
| Foreground | Clone OpenJarvis repo | `~/.openjarvis/src/` |
| Foreground | Create a Python 3.10–3.13 venv | `~/.openjarvis/.venv/` |
| Foreground | `uv pip install -e .` (editable install) | venv |
| Foreground | Install/start Ollama and pull `qwen3.5:2b` | Local mode only; skipped with `OPENROUTER_API_KEY` |
| Foreground | Write `config.toml` (local or OpenRouter) | `~/.openjarvis/config.toml` |
| Foreground | Symlink `jarvis` and `jarvis-uninstall` | `~/.local/bin/` |
| Foreground | Add `~/.local/bin` to PATH if missing (with on-screen notice) | `~/.bashrc` or `~/.zshrc` |
| Background | Install Rust toolchain via rustup | `~/.cargo/` |
| Background | Build the maturin extension (memory + security features) | venv |
| Background | Pull hardware-tier and tier+1 models | Ollama's model store; skipped in cloud-only mode |

## What the installer does NOT touch

- Your existing Python installations
- Your `~/.bashrc` / `~/.zshrc` other than appending one PATH line (with on-screen notice)
- Your existing Ollama models
- Any other tool or dotfile

## Idempotent re-runs

Re-running the curl line is safe. The installer reads `~/.openjarvis/.state/install-state.json` and skips completed steps. If your venv got nuked, re-running heals it.

## Cloud quick-path

If any of these env vars are set when the installer writes the initial config,
cloud is selected as the initial provider. `OPENROUTER_API_KEY` additionally
activates cloud-only installation, so Ollama is not installed or started. The
other provider keys keep the existing local dependencies while selecting cloud
in the generated config. `jarvis init` reports a detected key, but an explicit
cloud configuration or the `openrouter` preset is still required when replacing
an existing config:

- `OPENROUTER_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY` (or `GEMINI_API_KEY`)

Local-first remains the default when no key is in env. Precedence during the
installer bootstrap is OpenRouter > Anthropic > OpenAI > Google. The installer
does not remove an existing Ollama installation or its models; for a new
cloud-only setup, use the [OpenRouter guide](openrouter.md) or:

```bash
jarvis init --preset openrouter --force
```

## Flags

| Flag | Effect |
|---|---|
| `--minimal` | Skip the foreground model pull. First chat will need to wait for the bg pull to finish. |
| `--no-bg-orchestrator` | Don't detach the background work pipeline. (Mostly for testing.) |
| `--force` | Re-run all steps even if `install-state.json` says they're done. |
| `--analytics` | Consent to installation and runtime usage analytics without prompting. |
| `--no-analytics` | Decline analytics without prompting. |

## Environment overrides

| Variable | Default | Purpose |
|---|---|---|
| `OPENJARVIS_HOME` | `$HOME/.openjarvis` | Install location. |
| `OPENJARVIS_REPO_URL` | `https://github.com/open-jarvis/OpenJarvis.git` | Source repo for the clone step. |

## Uninstall

```bash
jarvis-uninstall
```

Removes `~/.openjarvis/`, `~/.local/bin/jarvis`, and `~/.local/bin/jarvis-uninstall`. Leaves Ollama, uv, and the Rust toolchain in place (they may be used by other tools); the script prints removal hints.

## Updating

```bash
jarvis self-update
```

Fetches release-tag history, pulls the latest source with a fast-forward-only
update, and rebuilds OpenJarvis in the Python environment that launched Jarvis.
Previously installed extras are preserved. Older shallow installs are repaired
automatically so `jarvis --version` reports a version derived from release tags.

Use `jarvis self-update --check` to preview the update plan, or `--yes` to skip
the confirmation prompt. If Git reports a conflict or diverged branch, resolve
it before retrying; self-update does not reset local changes.

## Troubleshooting

### "command not found: jarvis"

`~/.local/bin` isn't on your PATH. Run `source ~/.bashrc` (or `~/.zshrc`) or open a new terminal.

### "memory features unavailable"

Rust extension hasn't finished building yet (or failed). Check status:

```bash
jarvis doctor
```

Manually retry:

```bash
~/.openjarvis/.scripts/install-rust.sh && ~/.openjarvis/.scripts/build-extension.sh
```

### A bigger model failed to download

Check status and retry:

```bash
jarvis doctor
~/.openjarvis/.scripts/pull-model.sh qwen3.5:9b
```

### Behind a corporate proxy

Set `HTTPS_PROXY` and `CURL_CA_BUNDLE` in your environment before running the installer.
