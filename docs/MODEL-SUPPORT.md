# Какие модели работают с TruthProbe

Цифры уверенности появляются только там, где провайдер отдаёт **token logprobs**.
Это свойство API и модели, а не наша настройка: если провайдер поле вырезает,
никакой патч его не восстановит — под ответом будет `no confidence signal` с причиной.

Обновлено: 19.11.2026.

## Проверено

| провайдер / модель | цифры | что показал зонд |
| --- | --- | --- |
| `freepi/particle` | ✅ | `status: ok`, score 0.798, first-token 0.989 |
| `freepi/deepseek-v4.1-flash` | ✅ | `status: ok`, score 0.689, первый флаг 0.485 |
| `opencode/deepseek-v4.1-flash-free` | ❌ | 200 OK, поля `logprobs` в ответе нет — `no logprobs in response` |

## Как читать статусы

| статус зонда | смысл | что увидит человек |
| --- | --- | --- |
| `ok` | logprobs пришли, альтернативы есть | проценты и уровни под ответом |
| `ignored` | 200 OK, провайдер молча вырезал поле | `no confidence signal` |
| `rejected` | 4xx с упоминанием logprobs | `no confidence signal` + причина |
| `auth` / `rate` | ключ не принят / 429 | вердикт не кэшируется, зонд повторится |
| `error` | прочее | `no confidence signal` + текст ошибки |

## Что заведомо работает

- **OpenAI-совместимые локальные шлюзы** с включённым `logprobs`: llama.cpp, vLLM, LM Studio,
  Ollama (OpenAI-эндпоинт, если версия отдаёт `logprobs`).
- **Шлюзы-агрегаторы**, которые пробрасывают поле: free-pi (проверено), большинство
  `openai-compatible` прокси.
- Любой провайдер, для которого `scripts/probe-logprobs.py` печатает `ok`.

## Что заведомо не работает

- Собственный инференс `opencode.ai` — поле не пробрасывается.
- Anthropic Claude и Google Gemini через их нативные API: logprobs не отдаются в текстовом
  completion (проверять не пробовали — запись появится только после зонда, не по памяти).

## Как проверить свою модель

```bash
# free-pi шлюз (локальный)
python3 scripts/probe-logprobs.py \
  --base http://127.0.0.1:8790/v1 --key local \
  --models particle,deepseek-v4.1-flash,deepseek-v4-pro

# любой OpenAI-совместимый endpoint
python3 scripts/probe-logprobs.py \
  --base https://api.openai.com/v1 --key "$OPENAI_API_KEY" \
  --models gpt-4.1-mini,gpt-4o-mini
```

Результат печатается по строке на модель и кэшируется в
`~/.local/share/opencode/truthprobe/capabilities.json` (TTL 7 дней). Для готовой таблицы:

```bash
python3 scripts/probe-logprobs.py --base http://127.0.0.1:8790/v1 --key local \
  --models particle,deepseek-v4.1-flash --md
```

## Наследование по провайдеру

Если зонд подтвердил хотя бы одну модель шлюза, остальные модели того же провайдера тоже
получают `logprobs`. Это сделано осознанно: у free-pi в кэше только `particle`, и без
наследования `deepseek-*` остались бы без цифр. Обратная сторона: шлюз, где часть моделей
поле не знает, ответит 400 — лечится `OPENCODE_TRUTHPROBE=off` или правкой
`capabilities.json`.

## Если цифр нет на первой попытке

При пустом кэше самый первый запрос уходит без `logprobs`: зонд ещё не успел ответить.
Вердикт применяется со следующего сообщения. Если строка `no confidence signal` осталась и
после второго запроса — зонд вернул не `ok`, смотрите причину в скобках.
