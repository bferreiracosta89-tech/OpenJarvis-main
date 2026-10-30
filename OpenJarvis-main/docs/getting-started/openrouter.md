---
title: OpenRouter
description: Use OpenJarvis with OpenRouter instead of a local model
search:
  boost: 3
---

# OpenRouter

OpenRouter is an optional cloud backend for OpenJarvis. It lets you use models
from multiple providers through one OpenAI-compatible API. This path does not
require Ollama, downloaded model weights, or a local inference server.

!!! warning "Data boundary"
    Prompts, memory context, and tool results sent through OpenRouter leave your
    machine. Review your OpenRouter account, model-provider, and privacy settings
    before enabling cloud inference.

## Install the cloud dependency

From the repository root:

```bash
uv sync --extra inference-cloud
```

The extra installs the OpenAI-compatible client used by OpenRouter. OpenRouter
does not have a separate Python SDK requirement in OpenJarvis.

## Set the API key

Keep the key in the process environment; do not put it in `config.toml`, source
control, frontend variables, or browser storage.

=== "Bash / macOS / Linux / WSL2"

    ```bash
    export OPENROUTER_API_KEY="sk-or-v1-..."
    ```

=== "PowerShell / Windows"

    ```powershell
    $env:OPENROUTER_API_KEY = "sk-or-v1-..."
    ```

Use the same terminal session when running `jarvis`. A `.env` file is not loaded
automatically by the CLI; source it explicitly in Bash or set the variable in
PowerShell.

## Run the first request

OpenRouter model identifiers must use the `openrouter/` prefix so OpenJarvis
routes the request to the OpenRouter client:

=== "Bash / macOS / Linux / WSL2"

    ```bash
    uv run jarvis ask \
      --engine cloud \
      --model openrouter/auto \
      "Explain how OpenJarvis selects an inference engine."
    ```

=== "PowerShell / Windows"

    ```powershell
    uv run jarvis ask `
      --engine cloud `
      --model openrouter/auto `
      "Explain how OpenJarvis selects an inference engine."
    ```

`openrouter/auto` lets OpenRouter choose a compatible route. You can also use a
specific model from the OpenRouter catalog, for example:

```text
openrouter/anthropic/claude-sonnet-4
openrouter/openai/gpt-4o
openrouter/google/gemini-2.5-pro
```

Model availability and names change at the provider, so replace these examples
with a currently supported ID from the [OpenRouter models catalog](https://openrouter.ai/models).

## Make OpenRouter the default

To persist the choice in the user configuration, edit
`~/.openjarvis/config.toml` (on Windows, `%USERPROFILE%\\.openjarvis\\config.toml`):

```toml
[engine]
default = "cloud"

[intelligence]
provider = "openrouter"
default_model = "openrouter/auto"
```

Then run:

```bash
jarvis doctor
jarvis ask "Hello from OpenRouter"
```

The API key remains outside the file and must still be present in the process
environment whenever OpenJarvis runs.

## Browser app with OpenRouter

Set `OPENROUTER_API_KEY` before starting the backend. Do not run Ollama or pull a
local model:

```bash
uv sync --extra desktop --extra inference-cloud
uv run jarvis serve --port 8000 --engine cloud --model openrouter/auto
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). On native Windows, run the
same commands in PowerShell with the PowerShell environment-variable form above;
`scripts/quickstart.sh` is intended for Bash-compatible environments such as
macOS, Linux, and WSL2.

## Troubleshooting

| Symptom | Check |
|---|---|
| `OpenRouter client not available` | `OPENROUTER_API_KEY` is set in the same terminal and `uv sync --extra inference-cloud` completed. |
| The request goes to Ollama | Use `--engine cloud` and a model beginning with `openrouter/`, or set the TOML defaults above. |
| Model not found | Confirm the model ID in the [OpenRouter catalog](https://openrouter.ai/models). |
| Local model download starts | Stop the local quickstart path and start `jarvis serve` explicitly with `--engine cloud`. |

