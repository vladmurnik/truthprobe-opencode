# Сквозная проверка TruthProbe без внешних ключей

Мок-сервер отдаёт OpenAI-совместимый стрим с настоящими `logprobs`, поэтому весь путь
«запрос → парсинг → скоринг → durable-событие → парт сообщения» проверяется локально.

## Как воспроизвести

```bash
# 1. мок в отдельном терминале
python3 scripts/mock-openai-logprobs.py 8899

# 2. прогон opencode из исходников: TruthProbe включается сам
cd ~/src/opencode
OPENCODE_CONFIG=/path/to/opencode-truthprobe/scripts/mock-opencode.json \
bun run --cwd packages/cli src/index.ts run --model mock/mock-1 \
  "What is the capital of France? Answer in two sentences."

# 3. (опционально) что решила автопроверка
cat ~/.local/share/opencode/truthprobe/capabilities.json
```

Первый прогон на чистом кэше: сам запрос идёт без `logprobs`, параллельно уходит проверочная
посылка `{"model":"mock-1","messages":[{"role":"user","content":"ping"}],"max_tokens":1,
"logprobs":true,"top_logprobs":20,"stream":false}`, и вердикт `ok` ложится в кэш. Со второго
прогона все запросы к этому провайдеру идут уже с `logprobs: true, top_logprobs: 20` —
измерено: 2 из 2 streaming-запросов, 0 новых проб.

## Измеренный результат (прогон в VM)

Вывод CLI:

```
The capital of France is Paris. It is home to about 2 million people.
```

Запрос, который увидел мок-сервер (`/tmp/mock/requests.jsonl`):

```json
{"path": "/v1/chat/completions", "model": "mock-1", "logprobs": true, "top_logprobs": 20, "stream": true}
```

Сохранённый парт ассистента (таблица `session_part` в `~/.local/share/opencode/opencode-local.db`):

```json
{"type":"text","text":"The capital of France is Paris. It is home to about 2 million people.",
 "truthprobe":{"status":"ok","score":0.4442,"risk":0.5558,"level":"risky",
   "first":{"score":0.7076,"entropy":0.2924,"token":"The"},
   "sentences":[
     {"i":0,"start":0,"end":31,"text":"The capital of France is Paris.","score":0.9672,"risk":0.0328,
      "meanLp":0.9672,"minLp":-0.08,"phi":0.7076,"tokens":6,"flag":false},
     {"i":1,"start":32,"end":69,"text":"It is home to about 2 million people.","score":0.1584,"risk":0.8416,
      "meanLp":0.1584,"minLp":-2.9,"phi":0.1068,"tokens":7,"flag":true}],
   "flagged":1}}
```

Что это доказывает:

1. `logprobs: true, top_logprobs: 20` реально уходит в тело запроса — без переменных окружения,
   только за счёт вердикта автопроверки.
2. Стрим-чанки с `choices[].logprobs.content[]` разбираются, токены накапливаются по блоку текста.
3. Скоринг считает первое предложение уверенным (0.967, риск 0.033), второе — спорным (0.158, риск 0.842), φ первого токена 0.708. Оценка по умолчанию — вероятность геометрического среднего `exp(meanLp)`, без φ и без веса худшего токена (см. `docs/VALIDATION.md` §14).
4. Скоринг доезжает до хранилища через `session.text.ended`, без отдельного события `session.text.scored`
   (первоначальный вариант с отдельным durable-событием блокировался на шине и был заменён — см. `docs/VALIDATION.md`).

## Тот же сценарий в живом TUI

```bash
python3 scripts/tui-probe.py          # поднимает TUI в pty, печатает запрос, снимает экран
python3 scripts/screen-dump.py /tmp/tui-probe.log
```

Результат (см. `docs/VALIDATION.md`, §6 «Живой рендер TUI (pty)»):

```
   first-token confidence 71%
   The capital of France is Paris. It is home to about 2 million people.
   answer confidence 44% ▰▰░░░ · risky · 1 doubtful sentence
     ▌ #2 ▰░░░░ 16% · unreliable: It is home to about 2 million people.
```

## Что это НЕ проверяет

- Настоящий шлюз `opencode.ai/inference` (нужен ключ): отдаёт ли он logprobs и не вырезает ли поле.
- Поведение на длинных реальных ответах (все прогоны — на моке с двумя предложениями).
