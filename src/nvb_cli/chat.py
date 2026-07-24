"""Interactive terminal chat loop (REPL) with token-by-token streaming."""

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
    console.print(f"[bold cyan]nvb chat[/bold cyan] — model: [bold]{model}[/bold]")
    console.print("[dim]Type your message. /exit to quit, /clear to clear history.[/dim]\n")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})

    while True:
        try:
            user_input = console.input("[bold green]you>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]exited.[/dim]")
            break

        if not user_input:
            continue
        if user_input in ("/exit", "/quit", "/sair"):
            break
        if user_input in ("/clear", "/new", "/novo"):
            messages = [messages[0]] if system else []
            console.print("[dim]history cleared.[/dim]")
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
            console.print(f"\n[bold red]Error ({exc.status_code}):[/bold red] {exc.message}")
            if exc.status_code in (401, 403):
                console.print("[dim]Check your key with `nvb auth status`.[/dim]")
            if exc.status_code == 404:
                console.print(
                    "[dim]This model may not have a hosted chat endpoint right now. "
                    "Run `nvb models free --refresh` to check.[/dim]"
                )
            messages.pop()  # remove failed question so it does not clutter history
            continue

        console.print()  # new line after streaming
        if markdown and collected.strip():
            pass  # already printed via streaming
        messages.append({"role": "assistant", "content": collected})
