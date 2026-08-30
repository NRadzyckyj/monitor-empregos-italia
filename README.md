# Monitor de empregos na Itália

Bot independente do monitor de PC. Consulta diariamente vagas públicas recentes de hospitalidade na Itália, salva todas as oportunidades elegíveis em `data/jobs.json` e alerta somente por seu próprio bot de Telegram.

## Configuração

1. Crie no BotFather um novo bot, por exemplo `Empregos Italia`.
2. No repositório GitHub, crie o secret `TELEGRAM_JOBS_BOT_TOKEN`; abra o novo bot no Telegram e envie `/start`.
3. Execute **Descobrir Chat ID do bot de empregos** e copie o valor exibido como `TELEGRAM_JOBS_CHAT_ID` nos secrets.
4. Execute **Monitor de empregos na Itália** manualmente com `send_test_alert` para validar o novo bot.

O arquivo `data/jobs.json` é a fonte da aba “Oportunidades encontradas” no plano HTML. Ele contém data de descoberta, última verificação, prioridade, motivo da seleção, fonte e link direto.

O monitor não automatiza Facebook privado/fechado e não coleta EURES, cujos termos proíbem a extração automatizada de vagas.
