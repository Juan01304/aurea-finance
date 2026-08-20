# Segurança da Aurea Finance

## Implementado

- senhas com PBKDF2-HMAC-SHA256, salt aleatório e 350 mil iterações;
- OTP de 6 dígitos armazenado como HMAC, nunca em texto puro no banco;
- OTP expira em 10 minutos, é de uso único e tem limite de tentativas;
- novo OTP invalida códigos anteriores do mesmo fluxo;
- cadastro com confirmação de e-mail e login em duas etapas;
- recuperação de senha com OTP e invalidação das sessões autenticadas existentes;
- sessões server-side, rotacionadas após autenticação;
- cookies `HttpOnly`, `SameSite=Lax` e suporte a `Secure` em produção;
- CSRF obrigatório nas operações autenticadas de escrita;
- rate limiting básico em memória para autenticação, demo e assistente;
- CSP, `X-Frame-Options`, `nosniff`, Permissions Policy e Referrer Policy;
- chave da OpenAI apenas no backend e fallback para assistente local;
- exclusão de conta com confirmação de senha;
- exportação dos dados do usuário em JSON e CSV;
- demos temporárias removidas automaticamente.

## Modelo de ameaça e limites

A Aurea é um projeto de portfólio/MVP. O rate limiting atual é por processo e não substitui um limitador distribuído. O banco gratuito do Render não deve ser tratado como armazenamento permanente. Não há auditoria independente de segurança.

## Antes de uso com dados importantes ou escala real

- HTTPS obrigatório e `AUREA_SECURE_COOKIE=1`;
- PostgreSQL gerenciado com backups e plano de recuperação;
- secrets manager e rotação de credenciais;
- rate limiting distribuído e proteção anti-bot/credential stuffing;
- logs de auditoria sem conteúdo financeiro sensível;
- observabilidade, alertas e testes E2E;
- revisão independente de segurança;
- política de privacidade/termos adequados à operação real e processo LGPD;
- confirmação adicional para alterações sensíveis de conta.

## Reporte responsável

Se encontrar uma vulnerabilidade, não publique dados ou credenciais. Abra um contato privado com o mantenedor antes de divulgar detalhes exploráveis.
