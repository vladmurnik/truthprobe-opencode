# Как контрибьютить

Проект держится на двух вещах: **чистая математика** (её можно проверять без сети и без модели)
и **тонкий шов** в ядре opencode (его легко пережить при обновлении upstream).

## Быстрый цикл

```bash
bun test test/score.test.ts        # 45 тестов, без зависимостей и без сети
```

Тесты дерева opencode живут в самом дереве и запускаются только там:

```bash
bash scripts/run-opencode-tests.sh # эталонные исходники → дерево, typecheck, оба набора тестов
```

## Если меняешь формулы

1. Меняй `src/truthprobe/score.ts` (это эталон; в ядро он копируется скриптом).
2. Добавь тест, который падает на старом поведении и проходит на новом.
3. Прогони `bun test`, затем `bash scripts/run-opencode-tests.sh`.
4. Обнови `docs/VALIDATION.md`: там записаны измеренные числа, а не обещания.

Порог `riskyThreshold = 0.45` подобран на моке и двух реальных ответах. Если у тебя есть
размеченный набор (верные/неверные предложения), присылай кривую precision/recall — порог
обсуждаем числом, не вкусом.

## Если добавляешь провайдера

`logprobs` есть не везде. Порядок:

- OpenAI-совместимый `/chat/completions` → достаточно `capabilities.logprobs: true`, менять нечего.
- Responses API / Anthropic messages / Gemini generate-content → нужен отдельный разборщик
  в соответствующем протоколе (см. `docs/PLAN-BUILTIN.md`), возвращающий те же `TokenLogprob[]`.
- Провайдер вообще не отдаёт вероятности → честный статус `unavailable`, без выдуманных чисел.

## Если обновляешь upstream

Патч прибит к базе `007afb1`. Порядок rebase:

```bash
git clone https://github.com/sst/opencode && cd opencode
git checkout <new-base>
git am ../patches/truthprobe-0001.patch     # ожидаемо упадёт на конфликтах
# правь только 6 точек: openai-chat.ts, publish-llm-event.ts, message-updater.ts,
# message-parts.tsx, client/src/solid/data.ts, схема события
git am --continue
bun run --cwd packages/core typecheck && cd packages/core && bun test test/truthprobe.test.ts
git format-patch <new-base> --stdout > ../patches/truthprobe-0001.patch
```

Если после обновления бейдж исчез — сначала проверь `packages/client/src/solid/data.ts`:
именно там терялись поля события `session.text.ended` (это уже случалось один раз).

## Стиль

- Комментарии по-русски там, где объясняют «почему», код — по-английски.
- Никаких новых зависимостей в ядре: скоринг — чистые функции, ноль импортов из внешних пакетов.
- Не логируй ни текст ответов, ни ключи, ни токены пользователя.
