# Arquitetura

A Aurea separa o cálculo financeiro da interface e da camada de dados.

```text
Browser / PWA
  │
  ├── landing + autenticação + painel (HTML/CSS/JS)
  │
  ▼
server.py  ── autenticação, sessão, CSRF, API e arquivos estáticos
  │
  ├── aurea/finance.py   regras e métricas determinísticas
  ├── aurea/db.py        SQLite local / PostgreSQL em produção
  ├── aurea/security.py  senha, OTP, CSRF e identificador seguro
  ├── aurea/emailer.py   Resend / SMTP / console local
  └── aurea/ai.py        assistente local + OpenAI opcional
```

## Princípios

1. **IA não é fonte de verdade financeira.** O motor calcula renda, comprometimento, reserva sugerida, teto seguro e score antes da resposta da assistente.
2. **Fallback útil.** Sem OpenAI, o modo local continua funcionando. Sem provedor de e-mail, desenvolvimento local imprime OTP no terminal.
3. **Histórico mensal.** Contas recorrentes ficam separadas do status pago/pendente por mês. Arquivamento preserva meses anteriores.
4. **Portabilidade.** SQLite atende execução local; `DATABASE_URL` ativa PostgreSQL sem mudar a API.
5. **Frontend sem framework.** O projeto mantém a camada cliente pequena e fácil de inspecionar em entrevista.

## Fluxo de autenticação

```text
Cadastro → OTP de e-mail → sessão autenticada → onboarding
Login → senha → OTP → rotação de sessão → painel
Esqueci senha → OTP → nova senha → sessões antigas invalidadas
```

## Dados principais

- `users`: identidade, hash de senha e estado de verificação;
- `sessions`: sessão server-side e estados temporários dos fluxos OTP;
- `email_codes`: HMAC, expiração e tentativas dos códigos;
- `finance_profiles`: renda, dia de pagamento e preferências;
- `bills` + `bill_status`: conta recorrente e pagamento por mês;
- `transactions`: entradas e saídas variáveis;
- `goals`: metas e progresso;
- `category_budgets`: limites mensais por categoria.
