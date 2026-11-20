# 0.2.0 — 2026-11-19

Проверяемость и упаковка.

**Тесты**

- 45 юнит-тестов скоринга и сегментации (`packages/core/test/truthprobe.test.ts`).
- 8 тестов протокола OpenAI (`packages/ai/test/truthprobe.test.ts`): гейт по capabilities/`OPENCODE_TRUTHPROBE`,
  состав полей запроса, разбор `choices[i].logprobs → providerMetadata`.
- Полные прогоны: core 7 661 тестов, ai 2 305, schema 95; типизация schema/ai/core/client/tui.

**Исправлено**

- Токен, который начинается с пробела на границе предложений, больше не теряется:
  привязка считается по пересечению диапазонов, а не по смещению начала.
- CJK-предложения (`。！？`) режутся без обязательного пробела после терминатора.
- Сокращение больше не склеивает предложения, если следующее слово начинается с заглавной буквы
  (`etc. And more.` → два предложения).

**Добавлено**

- Экспорт `truthprobeBody` / `truthprobeEnabled` / `truthprobeFromDelta` для тестов.
- Сборка под Windows: `dist/opencode-truthprobe-windows-x64.exe` (233 MB) проверена на живом моке.
- `scripts/install-cross-deps.py` — ставит win32 optional-зависимости для кросс-сборки из Linux.
- GitHub-обвязка: CI, лицензия, контрибьютинг, `scripts/build-*.sh`.

# 0.1.0 — 2026-11-18

Первый рабочий патч.

- Схема `Truthprobe.Info`, поле `truthprobe` в `session.text.ended` и в `AssistantText`.
- Запрос `logprobs: true, top_logprobs: 20` для моделей с `capabilities.logprobs` или при `OPENCODE_TRUTHPROBE=1`.
- Скоринг по первому токену (нормированная энтропия), по предложению и по ответу целиком.
- TUI: бейдж перед ответом, блок уверенности с номерами спорных предложений после ответа.
- Сквозной прогон на мок-провайдере, живой рендер в pty, сборка в один бинарь.
