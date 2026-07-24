# ![](./img.png) nvb-cli

---------

Unofficial CLI to list and use, directly from the terminal, the available models
in your free tier account on [NVIDIA Build](https://build.nvidia.com/) (NIM catalog,
OpenAI-compatible API).

> ⚠️ Project not affiliated with NVIDIA. Uses the public API documented at
> https://docs.api.nvidia.com/nim/docs/api-quickstart. The "free endpoint"
> model catalog changes frequently — this CLI discovers the current state
> by testing the endpoints, not relying on a fixed list.

This project is primarily a study project: it was created to explore how to
build a small CLI around an external API, experiment with model discovery and
probing logic, and practice Python tooling and packaging in a practical
context. It is not intended as an official or production-grade NVIDIA client.

## Why it exists

The free tier account on build.nvidia.com grants access to an `nvapi-...` key that
works with the OpenAI SDK pointing to
`https://integrate.api.nvidia.com/v1`. The complete catalog comes from
`GET /v1/models`, but this response **doesn't indicate which models are
available on the free hosted endpoint right now** — it includes paid models,
embedding models, and models removed from the catalog. `nvb-cli` solves
this by testing each model with a minimal chat call and classifying by
response (200/429 = available; 404/401/403 = unavailable), with local caching
to avoid repeating the test every time.

## Installation

Requires Python 3.10+.

```shell
git clone https://github.com/YOUR_USER/nvb-cli.git
cd nvb-cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs the `nvb` command in your PATH (via `pip install -e .`, using the
`project.scripts` from `pyproject.toml`).

## Setting up the API key

Generate your key at build.nvidia.com → account icon → **API Keys** → **Generate
API Key** (starts with `nvapi-`).

```shell
# API Key: save locally (~/.config/nvb-cli/config.toml, permission 600)
nvb auth set nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Validate your key
nvb auth status
```

## Usage

### List the entire catalog

```shell
nvb models list
```

### Discover which models are free/hosted now

```shell
nvb models free
```

This tests (with limited concurrency) each model in the catalog against
`/v1/chat/completions` and shows only those that responded. The result is cached
for 6h by default:

```shell
nvb models free --refresh          # force new test, ignore cache
nvb models free --ttl 3600          # cache valid for 1h
nvb models free --concurrency 20    # more requests in parallel
nvb models free --json              # output in JSON, for scripts
```

### Chat with a model (interactive chat)

```shell
nvb chat meta/llama-3.1-8b-instruct
nvb chat qwen/qwen3.5-397b-a17b --system "Always respond in English."
```

Within the chat: `/clear` clears history, `/exit` exits.

### Single question, no REPL (good for scripts)

```shell
nvb run meta/llama-3.1-8b-instruct "Explain what NIM is in one sentence."
```

## Project structure

```shell
nvb-cli/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .github/workflows/ci.yml
├── src/nvb_cli/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py          # click commands (auth, models, chat, run)
│   ├── api.py          # HTTP client for /v1/models and /v1/chat/completions
│   ├── probe.py        # tests in parallel which models respond (free)
│   ├── cache.py        # local JSON cache with TTL
│   ├── chat.py         # chat REPL with streaming
│   └── config.py       # API key and config at ~/.config/nvb-cli
└── tests/
    ├── test_config.py
    ├── test_cache.py
    └── test_probe.py
```

## Known limitations

- The "free" classification is an inference (heuristic based on HTTP response),
  not an official API field — NVIDIA may change behavior without notice.
- Very large models may "cool down" (cold start) and timeout, appearing
  ambiguous; increase `--timeout` if you notice this.
- Respect your account's rate limit (on the order of tens of req/min); probing
  uses limited concurrency and implicit delay via semaphore, but large catalogs
  still take a few minutes to fully test.

## ⚙️ Development

```shell
pip install -e ".[dev]"
pytest -v
```

## ©️ License

[GPL-3.0](LICENSE)

## 🐧 Author

[alexolinux](https://alexolinux.com)
