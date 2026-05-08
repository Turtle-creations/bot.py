## Shared Website + Bot Database Notes

This bot now prefers `DATABASE_URL` whenever it is present, so production can use the same PostgreSQL database as the website.

### What changed

- The bot keeps SQLite only as a local-development fallback when `DATABASE_URL` is absent.
- PostgreSQL startup now performs additive schema alignment for existing tables.
- Existing website tables are not dropped or recreated destructively.
- Payment upserts now use portable `ON CONFLICT` SQL, so they work on both SQLite and PostgreSQL.
- PostgreSQL connections explicitly request UTF-8 client encoding for Hindi and other Unicode text.

### Safe rollout

1. Set the same `DATABASE_URL` for the website and Telegram bot.
2. Keep the old local bot SQLite file in place for now as a backup only.
3. Start the bot once against PostgreSQL so it can run additive `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN`, and index creation.
4. Verify row counts and sample records before removing any legacy fallback configuration.

### Expected shared tables

- `users`
- `exams`
- `exam_sets`
- `questions`
- `quiz_attempts`
- `payment_orders`
- `payments`
- `processed_webhooks`
- `notifications`
- `support_messages`
- `settings`
- `password_reset_requests`

### Verification checklist

- Website-added exams, sets, and questions appear in bot quiz menus.
- Bot-created users appear in the shared `users` table.
- Bot quiz completions create rows in `quiz_attempts`.
- Payment rows created by website checkout/webhook are visible to the bot in `payment_orders` and `payments`.
- Hindi question text round-trips correctly in both website and bot views.

### Important note about old SQLite data

Legacy JSON bootstrap and local SQLite files are intentionally left untouched. This change does not delete or reset them.
