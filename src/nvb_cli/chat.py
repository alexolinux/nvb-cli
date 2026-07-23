"""Loop de chat interativo (REPL) no terminal, com streaming token a token."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

from nvb_cli.api import ApiError, NvidiaClient

console = Console()


def run_repl(
    client: NvidiaClient,
    model: str,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    markdown: bool = True,
) -> None:
    console.print(f"[bold cyan]nvb chat[/bold cyan] — modelo: [bold]{model}[/bold]")
    console.print("[dim]Digite sua mensagem. /sair para encerrar, /novo para limpar o histórico.[/dim]\n")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})

    while True:
        try:
            user_input = console.input("[bold green]voce>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]encerrado.[/dim]")
            break

        if not user_input:
            continue
        if user_input in ("/sair", "/exit", "/quit"):
            break
        if user_input == "/novo":
            messages = [messages[0]] if system else []
            console.print("[dim]histórico limpo.[/dim]")
            continue

        messages.append({"role": "user", "content": user_input})
        console.print(f"[bold magenta]{model}>[/bold magenta] ", end="")

        collected = ""
        try:
            for token in client.chat_stream(
                model, messages, max_tokens=max_tokens, temperature=temperature
            ):
                collected += token
                console.print(token, end="", soft_wrap=True)
        except ApiError as exc:
            console.print(f"\n[bold red]Erro ({exc.status_code}):[/bold red] {exc.message}")
            if exc.status_code in (401, 403):
                console.print("[dim]Confira sua chave com `nvb auth status`.[/dim]")
            if exc.status_code == 404:
                console.print(
                    "[dim]Esse modelo pode não ter endpoint de chat hospedado agora. "
                    "Rode `nvb models free --refresh` para conferir.[/dim]"
                )
            messages.pop()  # remove a pergunta que falhou, para não poluir o histórico
            continue

        console.print()  # nova linha ao fim do streaming
        if markdown and collected.strip():
            pass  # já foi impresso em streaming; markdown completo fica no /novo (ver README)
        messages.append({"role": "assistant", "content": collected})
