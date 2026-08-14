# Aurea Finance 3.1 — Public Deploy Edition

Aurea é uma aplicação web full-stack de planejamento financeiro pessoal. Ela transforma renda, contas recorrentes, transações, limites por categoria e metas em uma pergunta simples: **quanto é seguro gastar sem invadir suas prioridades?**

## Destaques

- cadastro com confirmação de e-mail por OTP;
- login em duas etapas;
- recuperação e troca de senha;
- sessões server-side, CSRF, rate limiting e headers de segurança;
- painel mensal, contas pagas/pendentes e histórico;
- renda extra e gastos variáveis;
- limites por categoria e metas financeiras;
- motor financeiro determinístico;
- Saúde do Orçamento e histórico de seis meses;
- assistente contextual local sem API;
- integração opcional com OpenAI Responses API;
- exportação CSV/JSON, tema claro/escuro e PWA;
- **modo demonstração público e isolado** para compartilhar o projeto;
- SQLite no desenvolvimento e PostgreSQL automático via `DATABASE_URL` no deploy;
- configuração pronta para Render por `render.yaml`.

## Testar localmente no Windows

1. Extraia o projeto.
2. Tenha Python 3.11+ instalado.
3. Execute `INICIAR_AUREA.bat`.
4. Abra `http://127.0.0.1:8765`.

Em desenvolvimento, se nenhum serviço de e-mail estiver configurado, os OTPs aparecem no terminal.

## Publicar e mandar para amigos

Leia **`DEPLOY_RENDER.md`**. A edição pública inclui um botão **Explorar demonstração**, então seus amigos conseguem entrar e testar o painel sem criar conta nem receber e-mail.

O `render.yaml` cria:

- um Web Service;
- um PostgreSQL;
- uma chave interna aleatória;
- cookies seguros;
- health check;
- conexão automática com o banco.

## E-mail no deploy

Para Render gratuito, a opção recomendada neste projeto é um provedor transacional por HTTPS. A Aurea suporta:

```env
RESEND_API_KEY=...
RESEND_FROM=Aurea Finance <acesso@seu-dominio.com>
```

SMTP continua disponível localmente e em hospedagens que permitam essas conexões.

## IA em nuvem

Opcional:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

Sem chave, a assistente local continua ativa. Por padrão, visitantes do **modo demo não consomem sua OpenAI API**, mesmo que você configure uma chave.

## Privacidade da versão compartilhável

As páginas públicas carregam `noindex,nofollow` e o projeto serve um `robots.txt` que pede aos buscadores para não indexar o site. Isso é apropriado para a fase em que você só quer compartilhar o link diretamente.

## Estrutura

```text
├── aurea/
│   ├── ai.py
│   ├── db.py
│   ├── finance.py
│   └── security.py
├── public/
├── tests/
├── server.py
├── render.yaml
├── Dockerfile
├── DEPLOY_RENDER.md
└── INICIAR_AUREA.bat
```

Aurea 3.1 é uma aplicação de portfólio/MVP. Não é software bancário auditado.
