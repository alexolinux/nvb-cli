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
            "[bold red]Nenhuma chave de API configurada.[/bold red]\n"
            f"  Defina a variável de ambiente {config.ENV_VAR!r}, ou rode:\n"
            "  [bold]nvb auth set nvapi-xxxxxxxxxxxxxxxxxxxx[/bold]"
        )
        sys.exit(1)
    return NvidiaClient(api_key=key, base_url=config.get_base_url())


@click.group()
@click.version_option(package_name="nvb-cli")
def main() -> None:
    """nvb: liste e use modelos free-tier do NVIDIA Build (build.nvidia.com) no terminal."""


# ---------------------------------------------------------------- auth ----
@main.group()
def auth() -> None:
    """Gerencia a chave de API (nvapi-...) usada nas chamadas."""


@auth.command("set")
@click.argument("api_key")
def auth_set(api_key: str) -> None:
    """Salva a chave de API localmente (~/.config/nvb-cli/config.toml)."""
    if not api_key.startswith("nvapi-"):
        console.print("[yellow]Aviso:[/yellow] chaves do NVIDIA Build normalmente começam com 'nvapi-'.")
    config.set_api_key(api_key)
    console.print("[green]Chave salva.[/green]")


@auth.command("status")
def auth_status() -> None:
    """Mostra se há uma chave configurada (mascarada) e de onde ela vem."""
    import os

    if os.environ.get(config.ENV_VAR):
        console.print(f"Origem: variável de ambiente [bold]{config.ENV_VAR}[/bold]")
        console.print(f"Chave:  {config.mask_key(os.environ[config.ENV_VAR])}")
        return
    key = config.load_config().get("api_key")
    if key:
        console.print(f"Origem: {config.config_file()}")
        console.print(f"Chave:  {config.mask_key(key)}")
    else:
        console.print("[yellow]Nenhuma chave configurada.[/yellow]")


@auth.command("clear")
def auth_clear() -> None:
    """Remove a chave salva no arquivo de configuração local."""
    config.clear_api_key()
    console.print("Chave removida do arquivo de configuração.")


# -------------------------------------------------------------- models ----
@main.group()
def models() -> None:
    """Lista modelos do catálogo NVIDIA Build."""


@models.command("list")
@click.option("--json", "as_json", is_flag=True, help="Saída em JSON bruto.")
def models_list(as_json: bool) -> None:
    """Lista TODOS os modelos do catálogo (não indica quais são free)."""
    client = _client()
    try:
        items = client.list_models()
    except ApiError as exc:
        err_console.print(f"[bold red]Erro {exc.status_code}:[/bold red] {exc.message}")
        sys.exit(1)

    if as_json:
        import json as _json

        console.print_json(_json.dumps(items))
        return

    table = Table(title=f"Catálogo NVIDIA Build ({len(items)} modelos)")
    table.add_column("ID do modelo", style="bold")
    table.add_column("Owned by")
    for m in items:
        table.add_row(m.get("id", "?"), m.get("owned_by", "-"))
    console.print(table)
    console.print(
        "\n[dim]Isto lista o catálogo inteiro (inclui modelos pagos, embeddings, etc). "
        "Use `nvb models free` para descobrir quais respondem agora no endpoint hospedado.[/dim]"
    )


@models.command("free")
@click.option("--refresh", is_flag=True, help="Ignora o cache e testa tudo de novo.")
@click.option("--ttl", default=cache.DEFAULT_TTL_SECONDS, show_default=True, help="Validade do cache, em segundos.")
@click.option("--concurrency", default=10, show_default=True, help="Requisições simultâneas ao testar o catálogo.")
@click.option("--timeout", default=8.0, show_default=True, help="Timeout por requisição de teste (s).")
@click.option("--json", "as_json", is_flag=True, help="Saída em JSON bruto.")
def models_free(refresh: bool, ttl: int, concurrency: int, timeout: float, as_json: bool) -> None:
    """Descobre quais modelos respondem *agora* no endpoint free/hospedado.

    A API não expõe um campo "é free" — este comando manda uma requisição mínima
    de chat para cada modelo do catálogo e classifica pela resposta (200/429 =
    hospedado; 404/401/403 = indisponível). O resultado fica em cache local.
    """
    client = _client()
    base_url = config.get_base_url()

    cached = None if refresh else cache.load(ttl_seconds=ttl)
    if cached:
        results = cached["results"]
        console.print(f"[dim]Usando cache de {cache.cache_file()} (rode com --refresh para atualizar).[/dim]")
    else:
        try:
            catalog = client.list_models()
        except ApiError as exc:
            err_console.print(f"[bold red]Erro {exc.status_code}:[/bold red] {exc.message}")
            sys.exit(1)

        model_ids = [m["id"] for m in catalog]
        api_key = config.get_api_key()

        results = {}
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Testando modelos...", total=len(model_ids))

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

        console.print_json(_json.dumps({"free_or_hosted": free_ids, "all_results": results}))
        return

    table = Table(title=f"Modelos disponíveis agora ({len(free_ids)} de {len(results)})")
    table.add_column("ID do modelo", style="bold green")
    table.add_column("Status")
    for mid in free_ids:
        status = results[mid]
        label = "free (200)" if status == Status.FREE.value else "hospedado (429, rate-limited)"
        table.add_row(mid, label)
    console.print(table)
    console.print(
        "\n[dim]Use com: nvb chat <ID_DO_MODELO>   ou   nvb run <ID_DO_MODELO> \"pergunta\"[/dim]"
    )


# --------------------------------------------------------------- chat -----
@main.command()
@click.argument("model")
@click.option("--system", default=None, help="Mensagem de sistema opcional.")
@click.option("--temperature", default=0.7, show_default=True)
@click.option("--max-tokens", default=1024, show_default=True)
def chat(model: str, system: str | None, temperature: float, max_tokens: int) -> None:
    """Abre um chat interativo (REPL) com o MODEL informado."""
    client = _client()
    run_repl(client, model, system=system, temperature=temperature, max_tokens=max_tokens)


@main.command()
@click.argument("model")
@click.argument("prompt")
@click.option("--system", default=None, help="Mensagem de sistema opcional.")
@click.option("--temperature", default=0.7, show_default=True)
@click.option("--max-tokens", default=512, show_default=True)
def run(model: str, prompt: str, system: str | None, temperature: float, max_tokens: int) -> None:
    """Envia um único PROMPT ao MODEL e imprime a resposta (não interativo)."""
    client = _client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        reply = client.chat(model, messages, max_tokens=max_tokens, temperature=temperature)
    except ApiError as exc:
        err_console.print(f"[bold red]Erro {exc.status_code}:[/bold red] {exc.message}")
        sys.exit(1)
    console.print(reply)


if __name__ == "__main__":
    main()
