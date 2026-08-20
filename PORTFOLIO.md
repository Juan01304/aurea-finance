# Como apresentar a Aurea no portfólio

## Problema

Aplicativos financeiros costumam registrar o passado, mas a pergunta prática é: **“posso gastar isso agora sem comprometer o mês?”**

## Solução

Aurea consolida renda, compromissos recorrentes, gastos variáveis, limites e metas. Um motor determinístico calcula a situação do mês e uma assistente contextual transforma esses números em orientação legível.

## Pontos técnicos para entrevista

- IA não calcula o orçamento: o domínio financeiro permanece testável;
- autenticação implementa confirmação de e-mail, senha + OTP e recuperação;
- sessão é server-side e rotacionada após o segundo fator;
- OTP é armazenado como HMAC e expira;
- contas recorrentes e status mensal são separados para preservar histórico;
- SQLite e PostgreSQL compartilham a mesma camada de acesso;
- IA em nuvem é opcional e possui fallback local;
- PWA, tema, exportação e histórico melhoram a experiência sem framework;
- CI testa regras, autenticação, onboarding, exportação, demo e PostgreSQL.

## Como descrever sem exagerar

> Aurea Finance é um projeto full-stack de portfólio para planejamento financeiro pessoal, com autenticação em duas etapas, motor financeiro determinístico, PostgreSQL, PWA e assistente contextual opcional com OpenAI.

Não apresente como banco, software financeiro auditado ou consultoria de investimentos.
