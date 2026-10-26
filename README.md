# pandasito-bot

Publica 3 productos en el canal de Telegram PANDASITOFINDS a las 9, 12, 15, 18 y 21 (Madrid)
con GitHub Actions (`.github/workflows/tandas.yml`).

- `cola.md`: lo que falta por publicar (se rellena sola desde el spreadsheet si se vacía).
- `publicados.md`: lo ya publicado.
- `registro.log`: historial de cada tanda.
- `ultima-tanda.txt`: última tanda publicada. El workflow se ejecuta cada 15 min y publica la tanda
  que toque si todavía no ha salido (GitHub retrasa o se salta muchas ejecuciones programadas).
- Para lanzar una tanda a mano: pestaña Actions → Tandas Telegram → Run workflow.
- Necesita el secreto `TELEGRAM_BOT_TOKEN` (Settings → Secrets and variables → Actions).
