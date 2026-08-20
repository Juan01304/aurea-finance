<h1 align="center">Aurea Finance</h1>

<p align="center">
  Planejamento financeiro pessoal com autenticação em duas etapas, motor de orçamento determinístico, histórico, PWA e assistente contextual.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

## O problema

A maioria dos controles financeiros responde **quanto você gastou**. A Aurea tenta responder uma pergunta mais imediata:

> **Quanto eu posso gastar agora sem comprometer contas e prioridades do mês?**

Ela combina renda, compromissos recorrentes, transações, metas e limites por categoria para calcular margem, reserva sugerida e um teto seguro de gasto.

## Funcionalidades

### Conta e segurança

- cadastro com confirmação de e-mail por OTP de 6 dígitos;
- login em duas etapas: senha + OTP;
- recuperação de senha por OTP;
- senhas com PBKDF2-HMAC-SHA256;
- OTP armazenado como HMAC, com expiração e limite de tentativas;
- sessão server-side, rotação após autenticação, CSRF e headers de segurança;
- rate limiting básico para fluxos sensíveis;
- exportação dos dados e exclusão da conta.

### Planejamento financeiro

- renda mensal, dia de pagamento e percentual desejado para reserva;
- contas fixas, cartão, assinaturas e dívidas;
- status pago/pendente preservado por mês;
- transações de entrada e saída;
- renda extra;
- limites por categoria;
- metas financeiras, contribuições e ritmo estimado até o prazo;
- indicador interno de Saúde do Orçamento;
- reserva sugerida adaptativa;
- teto seguro mensal e diário;
- histórico resumido de seis meses;
- exportação CSV e JSON.

### Assistente

- assistente local baseada nos números do painel, sem API paga;
- integração opcional com OpenAI Responses API;
- fallback automático para o modo local se a API externa falhar;
- IA nunca é a fonte de verdade dos cálculos financeiros.

### Experiência e infraestrutura

- interface responsiva;
- tema claro/escuro;
- PWA instalável;
- SQLite em desenvolvimento;
- PostgreSQL quando `DATABASE_URL` está configurada;
- Docker;
- Render Blueprint;
- GitHub Actions com testes SQLite, autenticação, exportação e PostgreSQL.

## Arquitetura

```text
Browser / PWA
  │
  ├── HTML / CSS / JavaScript
  │
  ▼
server.py
  │
  ├── aurea/finance.py   → regras e cálculos financeiros
  ├── aurea/db.py        → SQLite / PostgreSQL
  ├── aurea/security.py  → senha, OTP, CSRF e identificador seguro
  ├── aurea/emailer.py   → Resend / SMTP / console local
  └── aurea/ai.py        → assistente local + OpenAI opcional
```

Mais detalhes em [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Executar localmente

### 1. Clone

```bash
git clone https://github.com/Juan01304/aurea-finance.git
cd aurea-finance
```

### 2. Ambiente virtual

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Dependências

```bash
pip install -r requirements.txt
```

O modo SQLite usa apenas a biblioteca padrão do Python. `psycopg` é usado quando há PostgreSQL.

### 4. Configuração

Copie `.env.example` como referência. O projeto lê variáveis de ambiente do processo.

Para o mínimo local, basta:

```text
AUREA_SECRET=um-segredo-local
AUREA_HOST=127.0.0.1
AUREA_PORT=10000
```

### 5. Execute

```bash
python server.py
```

Abra `http://127.0.0.1:10000`.

Sem Resend/SMTP, códigos OTP aparecem no terminal. Isso é proposital para desenvolvimento local.

## E-mail real

A opção recomendada para deploy é **Resend**:

```text
RESEND_API_KEY=re_...
RESEND_FROM=Aurea Finance <acesso@seudominio.com>
```

Também há suporte a SMTP com `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` e `SMTP_FROM`.

## OpenAI opcional

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

Sem chave, a Aurea continua funcionando com a assistente local. A chave fica somente no backend.

## Docker

```bash
docker build -t aurea-finance .
docker run --rm -p 10000:10000 -e AUREA_SECRET=local-secret aurea-finance
```

## Testes

```bash
python -m unittest discover -s tests -v
python -m py_compile server.py aurea/*.py
```

O CI também sobe o servidor, testa cadastro + OTP + onboarding + exportação, valida a demonstração e executa o caminho com PostgreSQL 16.

## Estrutura

```text
.
├── .github/workflows/      # CI SQLite/auth e PostgreSQL
├── aurea/
│   ├── ai.py               # assistente contextual
│   ├── db.py               # conexão, schema e migrações simples
│   ├── emailer.py          # Resend / SMTP
│   ├── finance.py          # motor financeiro
│   └── security.py         # senha, OTP e CSRF
├── public/
│   ├── index.html          # landing page
│   ├── auth.html           # cadastro/login/OTP/reset
│   ├── onboarding.html     # configuração inicial
│   ├── app.html            # painel
│   ├── app.js              # interação do painel
│   ├── style.css           # interface e temas
│   ├── manifest.webmanifest
│   └── sw.js               # service worker
├── tests/
├── ARCHITECTURE.md
├── SECURITY.md
├── ROADMAP.md
├── PORTFOLIO.md
├── Dockerfile
├── render.yaml
└── server.py
```

## Status

**Escopo de portfólio concluído.** Veja [`ROADMAP.md`](ROADMAP.md) para a diferença entre o MVP atual e o que seria necessário para operar com usuários e dados importantes em escala real.

> Aurea é um projeto educacional/de portfólio. Não é banco, software financeiro auditado nem substituto de aconselhamento financeiro profissional.
