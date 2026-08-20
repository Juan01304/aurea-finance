<h1 align="center">Aurea Finance</h1>

<p align="center">
  Aplicação web de planejamento financeiro pessoal com motor de orçamento determinístico, assistente contextual e modo de demonstração.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

## Sobre o projeto

A **Aurea Finance** nasceu de uma pergunta simples: depois de considerar renda, contas, gastos e prioridades, **quanto ainda é seguro gastar sem bagunçar o mês?**

O projeto reúne dados financeiros em um único contexto e gera métricas objetivas para ajudar o usuário a visualizar comprometimento da renda, margem disponível, reserva sugerida e limites de orçamento.

Esta versão pública funciona como **MVP de portfólio** e possui um modo de demonstração que cria dados isolados para cada visitante.

## Funcionalidades atuais

- painel mensal com renda, contas e gastos variáveis;
- cálculo de valor comprometido e saldo restante;
- sugestão de reserva baseada na situação do orçamento;
- cálculo de **teto seguro para gastar** e estimativa diária;
- indicador de **Saúde do Orçamento** de 0 a 100;
- acompanhamento de contas pagas e pendentes;
- limites por categoria e detecção de orçamento excedido;
- acompanhamento e contribuição para metas financeiras;
- assistente contextual local baseado nos números calculados pelo sistema;
- modo de demonstração público com usuários temporários e dados isolados;
- persistência em SQLite local ou PostgreSQL em produção.

## Arquitetura

```text
Browser
  │
  ├── HTML / CSS / JavaScript
  │
  ▼
server.py
  │
  ├── aurea/finance.py   → regras e cálculos financeiros
  ├── aurea/db.py        → SQLite / PostgreSQL
  ├── aurea/security.py  → CSRF, hashing e utilitários de segurança
  └── aurea/ai.py        → assistente contextual
```

A lógica financeira fica separada da interface e do acesso ao banco. Os cálculos do orçamento são determinísticos: a assistente recebe os resultados já calculados e os interpreta, em vez de inventar valores financeiros.

## Stack

**Backend**

- Python 3.13;
- `http.server` da biblioteca padrão;
- SQLite para desenvolvimento;
- PostgreSQL via `psycopg` quando `DATABASE_URL` está definida.

**Frontend**

- HTML5;
- CSS3;
- JavaScript sem framework.

**Infraestrutura**

- Docker;
- Render Blueprint (`render.yaml`);
- GitHub Actions.

## Segurança

A aplicação inclui algumas medidas importantes para um MVP web:

- sessões armazenadas no servidor;
- cookie de sessão `HttpOnly` e `SameSite=Lax`;
- suporte a cookie `Secure` em produção;
- tokens CSRF para operações autenticadas de escrita;
- headers como `X-Content-Type-Options`, `X-Frame-Options` e `Referrer-Policy`;
- hashing de senha com PBKDF2-HMAC-SHA256 no módulo de segurança.

> A Aurea é um projeto educacional/de portfólio. Ela não deve ser tratada como software bancário auditado nem como substituto de aconselhamento financeiro profissional.

## Assistente

O endpoint utilizado pela versão pública atual trabalha com um **assistente local**, que responde usando exclusivamente o snapshot financeiro calculado pelo sistema.

O código também contém um módulo preparado para integração opcional com a **OpenAI Responses API**, mas essa integração não é necessária para executar o modo de demonstração atual.

## Banco de dados

A mesma camada de acesso suporta dois ambientes:

```text
Desenvolvimento → SQLite
Produção        → PostgreSQL via DATABASE_URL
```

O schema inclui usuários, sessões, perfis financeiros, contas, transações, metas, limites por categoria e status mensal de pagamentos.

## Executar localmente

### 1. Clone o projeto

```bash
git clone https://github.com/Juan01304/aurea-finance.git
cd aurea-finance
```

### 2. Crie um ambiente virtual

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

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Inicie a aplicação

```bash
python server.py
```

Abra:

```text
http://127.0.0.1:10000
```

## Docker

```bash
docker build -t aurea-finance .
docker run --rm -p 10000:10000 aurea-finance
```

Depois acesse `http://localhost:10000`.

## CI

O repositório possui workflows no GitHub Actions que validam o projeto automaticamente.

Entre os testes atuais estão:

- compilação dos módulos Python;
- inicialização real do servidor;
- health check em `/healthz`;
- criação de uma sessão de demonstração;
- validação das métricas financeiras esperadas;
- execução do mesmo fluxo usando PostgreSQL 16.

Isso ajuda a verificar não apenas funções isoladas, mas o caminho completo entre servidor, banco e API.

## Estrutura principal

```text
.
├── .github/workflows/      # CI e smoke tests
├── aurea/
│   ├── ai.py               # assistente contextual
│   ├── db.py               # banco e schema
│   ├── finance.py          # motor financeiro
│   └── security.py         # utilitários de segurança
├── public/
│   ├── index.html          # landing page
│   ├── app.html            # dashboard
│   ├── app.js              # interação do frontend
│   └── style.css           # interface
├── Dockerfile
├── render.yaml
├── requirements.txt
└── server.py               # servidor HTTP e API
```

## Status

**MVP em evolução.**

O foco atual é continuar melhorando arquitetura, experiência de uso, cobertura de testes e segurança enquanto o projeto evolui de exercício prático para uma aplicação de portfólio cada vez mais sólida.
