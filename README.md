# nvb-cli

CLI não oficial para listar e usar, direto do terminal, os modelos disponíveis
na sua conta free tier do [NVIDIA Build](https://build.nvidia.com/) (catálogo
NIM, API compatível com OpenAI).

> ⚠️ Projeto não afiliado à NVIDIA. Usa a API pública documentada em
> https://docs.api.nvidia.com/nim/docs/api-quickstart. O catálogo de modelos
> "free endpoint" muda com frequência — este CLI descobre o estado atual
> testando os endpoints, não depende de uma lista fixa.

## Por que existe

A conta free tier do build.nvidia.com dá acesso a um key `nvapi-...` que
funciona com o SDK da OpenAI apontando para
`https://integrate.api.nvidia.com/v1`. O catálogo completo sai em
`GET /v1/models`, só que essa resposta **não diz quais modelos estão
disponíveis no endpoint hospedado gratuito agora** — inclui modelos pagos,
modelos de embedding, e modelos retirados de catálogo. O `nvb-cli` resolve
isso testando cada modelo com uma chamada mínima de chat e classificando pela
resposta (200/429 = disponível; 404/401/403 = indisponível), com cache local
para não repetir o teste toda hora.

## Instalação

Requer Python 3.10+.

```bash
git clone https://github.com/SEU_USUARIO/nvb-cli.git
cd nvb-cli
pip install -e .
```

Isso instala o comando `nvb` no seu PATH (via `pip install -e .`, usando o
`project.scripts` do `pyproject.toml`).

## Configurar a chave de API

Gere sua chave em build.nvidia.com → ícone da conta → **API Keys** → **Generate
API Key** (começa com `nvapi-`).

```bash
# opção 1: salvar localmente (~/.config/nvb-cli/config.toml, permissão 600)
nvb auth set nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# opção 2: variável de ambiente (tem prioridade sobre o arquivo salvo)
export NVIDIA_API_KEY="nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

nvb auth status
```

## Uso

### Listar o catálogo inteiro

```bash
nvb models list
```

### Descobrir quais modelos estão free/hospedados agora

```bash
nvb models free
```

Isso testa (com concorrência limitada) cada modelo do catálogo contra
`/v1/chat/completions` e mostra só os que responderam. O resultado fica em
cache por 6h por padrão:

```bash
nvb models free --refresh          # força novo teste, ignora cache
nvb models free --ttl 3600          # cache válido por 1h
nvb models free --concurrency 20    # mais requisições em paralelo
nvb models free --json              # saída em JSON, para scripts
```

### Conversar com um modelo (chat interativo)

```bash
nvb chat meta/llama-3.1-8b-instruct
nvb chat qwen/qwen3.5-397b-a17b --system "Responda sempre em português."
```

Dentro do chat: `/novo` limpa o histórico, `/sair` encerra.

### Uma pergunta só, sem REPL (bom para scripts)

```bash
nvb run meta/llama-3.1-8b-instruct "Explique o que é NIM em uma frase."
```

## Estrutura do projeto

```
nvb-cli/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .github/workflows/ci.yml
├── src/nvb_cli/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py        # comandos click (auth, models, chat, run)
│   ├── api.py         # cliente HTTP para /v1/models e /v1/chat/completions
│   ├── probe.py        # testa em paralelo quais modelos respondem (free)
│   ├── cache.py         # cache local em JSON com TTL
│   ├── chat.py           # REPL de chat com streaming
│   └── config.py          # chave de API e config em ~/.config/nvb-cli
└── tests/
    ├── test_config.py
    ├── test_cache.py
    └── test_probe.py
```

## Limitações conhecidas

- A classificação "free" é uma inferência (heurística baseada na resposta
  HTTP), não um campo oficial da API — a NVIDIA pode mudar comportamento sem
  aviso.
- Modelos muito grandes podem "esfriar" (cold start) e estourar timeout,
  aparecendo como ambíguos; aumente `--timeout` se notar isso.
- Respeite o rate limit da sua conta (na ordem de dezenas de req/min); o
  probing usa concorrência limitada e delay implícito via semáforo, mas
  catálogos grandes ainda levam alguns minutos para testar por completo.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest -v
```

## Licença

MIT — veja [LICENSE](LICENSE).
