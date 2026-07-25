from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from nvb_cli import cache, config
from nvb_cli.api import ApiError, NvidiaClient
from nvb_cli.chat import run_repl
from nvb_cli.probe import Status, probe_all

console = Console()
err_console = Console(stderr=True)


def _client() -> NvidiaClient:
    key = config.get_api_key()
    if not key:
        err_console.print(
            "[bold red]No API key configured.[/bold red]\n"
            f"  Set environment variable {config.ENV_VAR!r}, or run:\n"
            "  [bold]nvb auth set nvapi-xxxxxxxxxxxxxxxxxxxx[/bold]"
        )
        sys.exit(1)
    return NvidiaClient(api_key=key, base_url=config.get_base_url())


@click.group()
@click.version_option(package_name="nvb-cli")
def main() -> None:
    """nvb: list and use free-tier models from NVIDIA Build (build.nvidia.com) in your terminal."""


# ---------------------------------------------------------------- auth ----
@main.group()
def auth() -> None:
    """Manage the API key (nvapi-...) used for requests."""


@auth.command("set")
@click.argument("api_key")
def auth_set(api_key: str) -> None:
    """Save the API key locally (~/.config/nvb-cli/config.toml)."""
    if not api_key.startswith("nvapi-"):
        console.print("[yellow]Warning:[/yellow] NVIDIA Build keys usually start with 'nvapi-'.")
    config.set_api_key(api_key)
    console.print("[green]Key saved.[/green]")


@auth.command("status")
def auth_status() -> None:
    """Show if an API key is configured (masked) and its source."""
    import os

    if os.environ.get(config.ENV_VAR):
        console.print(f"Source: environment variable [bold]{config.ENV_VAR}[/bold]")
        console.print(f"Key:    {config.mask_key(os.environ[config.ENV_VAR])}")
        return
    key = config.load_config().get("api_key")
    if key:
        console.print(f"Source: {config.config_file()}")
        console.print(f"Key:    {config.mask_key(key)}")
    else:
        console.print("[yellow]No API key configured.[/yellow]")


@auth.command("clear")
def auth_clear() -> None:
    """Remove the saved key from local config file."""
    config.clear_api_key()
    console.print("Key removed from configuration file.")


# -------------------------------------------------------------- models ----
@main.group()
def models() -> None:
    """List models from the NVIDIA Build catalog."""


@models.command("list")
@click.option("--json", "as_json", is_flag=True, help="Raw JSON output.")
def models_list(as_json: bool) -> None:
    """List ALL models in the catalog (does not indicate which are free)."""
    client = _client()
    try:
        items = client.list_models()
    except ApiError as exc:
        err_console.print(f"[bold red]Error {exc.status_code}:[/bold red] {exc.message}")
        sys.exit(1)

    if as_json:
        import json as _json

        console.print_json(_json.dumps(items))
        return

    table = Table(title=f"NVIDIA Build Catalog ({len(items)} models)")
    table.add_column("Model ID", style="bold")
    table.add_column("Owned by")
    for m in items:
        table.add_row(m.get("id", "?"), m.get("owned_by", "-"))
    console.print(table)
    console.print(
        "\n[dim]This lists the full catalog (includes paid models, embeddings, etc). "
        "Use `nvb models free` to discover which ones respond now on the hosted endpoint.[/dim]"
    )


@models.command("free")
@click.option("--refresh", is_flag=True, help="Bypass cache and test everything again.")
@click.option("--ttl", default=cache.DEFAULT_TTL_SECONDS, show_default=True, help="Cache TTL in seconds.")
@click.option("--concurrency", default=10, show_default=True, help="Concurrent requests when probing catalog.")
@click.option("--timeout", default=8.0, show_default=True, help="Timeout per probe request (seconds).")
@click.option("--json", "as_json", is_flag=True, help="Raw JSON output.")
def models_free(refresh: bool, ttl: int, concurrency: int, timeout: float, as_json: bool) -> None:
    """Discover which models respond *now* on the free/hosted endpoint.

    The API does not expose a "is_free" field — this command sends a minimal
    chat request to each model in the catalog and classifies by response
    (200/429 = hosted; 404/401/403 = unavailable). The result is cached locally.
    """
    client = _client()
    base_url = config.get_base_url()

    cached = None if refresh else cache.load(ttl_seconds=ttl)
    if cached:
        results = cached["results"]
        if not as_json:
            console.print(f"[dim]Using cache from {cache.cache_file()} (run with --refresh to update).[/dim]")
    else:
        try:
            catalog = client.list_models()
        except ApiError as exc:
            err_console.print(f"[bold red]Error {exc.status_code}:[/bold red] {exc.message}")
            sys.exit(1)

        model_ids = [m["id"] for m in catalog]
        api_key = config.get_api_key()

        results = {}
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            disable=as_json,
        ) as progress:
            task = progress.add_task("Testing models...", total=len(model_ids))

            def on_result(r):
                results[r.model_id] = r.status.value
                progress.advance(task)

            asyncio.run(
                probe_all(
                    model_ids,
                    api_key=api_key,
                    base_url=base_url,
                    concurrency=concurrency,
                    timeout=timeout,
                    on_result=on_result,
                )
            )

        cache.save(results, base_url=base_url)

    free_ids = sorted(
        mid for mid, status in results.items() if status in (Status.FREE.value, Status.RATE_LIMITED.value)
    )

    if as_json:
        import json as _json

        console.print_json(_json.dumps({"base_url": base_url, "free_or_hosted": free_ids, "all_results": results}))
        return

    table = Table(title=f"Models available now ({len(free_ids)} of {len(results)})")
    table.add_column("Model ID", style="bold green")
    table.add_column("Status")
    table.add_column("Base URL", style="cyan")
    for mid in free_ids:
        status = results[mid]
        label = "free (200)" if status == Status.FREE.value else "hosted (429, rate-limited)"
        table.add_row(mid, label, base_url)
    console.print(table)
    console.print(
        f"\n[dim]Base URL for OpenAI-compatible clients (Cline, Cursor, etc.): [bold cyan]{base_url}[/bold cyan][/dim]\n"
        "[dim]Use with: nvb chat <MODEL_ID>   or   nvb run <MODEL_ID> \"prompt\"[/dim]"
    )


# --------------------------------------------------------------- chat -----
@main.command()
@click.argument("model")
@click.option("--system", default=None, help="Optional system message.")
@click.option("--temperature", default=0.7, show_default=True)
@click.option("--max-tokens", default=1024, show_default=True)
def chat(model: str, system: str | None, temperature: float, max_tokens: int) -> None:
    """Open an interactive chat (REPL) with specified MODEL."""
    client = _client()
    run_repl(client, model, system=system, temperature=temperature, max_tokens=max_tokens)


@main.command()
@click.argument("model")
@click.argument("prompt")
@click.option("--system", default=None, help="Optional system message.")
@click.option("--temperature", default=0.7, show_default=True)
@click.option("--max-tokens", default=512, show_default=True)
def run(model: str, prompt: str, system: str | None, temperature: float, max_tokens: int) -> None:
    """Send a single PROMPT to MODEL and print response (non-interactive)."""
    client = _client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        reply = client.chat(model, messages, max_tokens=max_tokens, temperature=temperature)
    except ApiError as exc:
        err_console.print(f"[bold red]Error {exc.status_code}:[/bold red] {exc.message}")
        sys.exit(1)
    console.print(reply)


if __name__ == "__main__":
    main()
