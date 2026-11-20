# FreeLLMAPI как источник данных для калибровки

[FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) — один OpenAI-совместимый
эндпоинт (`/v1`) поверх бесплатных тарифов десятков провайдеров. Для TruthProbe он
интересен не как «ещё один шлюз», а как **фабрика размеченных данных**: много разных
моделей через один `baseURL`, одинаковый формат `logprobs`, и есть роутер, который
сам переключается на следующую модель при 429.

## Что уже проверено (20.11.2026)

| Что | Как | Результат |
| --- | --- | --- |
| Образ поднимается | `docker run ghcr.io/tashfeenahmed/freellmapi:latest` | сервер слушает `:3001`, статус `healthy` |
| Первый запуск | `ENCRYPTION_KEY` + `FREEAPI_CONFIG_JSON` c admin-аккаунтом | БД создана, засеяно **25 моделей**, `POST /api/auth/login` → 200 |
| Каталог моделей | `GET /api/models` с токеном | отдаёт `platform`, `modelId`, `rpmLimit`, `contextWindow`, `enabled` |
| Инференс | `POST /v1/chat/completions` | **не проверен**: без ключей провайдеров все модели `enabled: false` |
| Проброс `logprobs` | — | **не проверен**, ниже объяснено, почему это главный вопрос |

Без ключей хотя бы одного провайдера (Groq, Google, Cerebras, OpenRouter…) роутер
не может обслужить ни одного запроса. Ключи кладутся на странице **Keys** локального
дашборда `http://127.0.0.1:3001`; там же в шапке лежит **unified key** вида
`freellmapi-…` — это единственный токен, который видит клиент.

## Поднять локально

```bash
KEY=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
docker run -d --name freellmapi -p 3001:3001 \
  -e ENCRYPTION_KEY="$KEY" -e NODE_ENV=production \
  -e FREEAPI_CONFIG_JSON='{"admin":{"email":"you@example.com","password":"change-me"}}' \
  -v "$HOME/freellmapi-data:/app/server/data" \
  ghcr.io/tashfeenahmed/freellmapi:latest
```

`ENCRYPTION_KEY` обязателен в `production`: без него сервер падает на старте с
`ENCRYPTION_KEY is required in production for API key encryption`.
`FREEAPI_CONFIG_JSON` создаёт первый аккаунт, чтобы не ловить setup-код из логов.

## Проверить, доходят ли logprobs

```bash
python3 scripts/probe-freellmapi.py --key freellmapi-xxxx
python3 scripts/probe-freellmapi.py --key freellmapi-xxxx --model auto:fast --jsonl labeled.jsonl
```

Скрипт делает `GET /v1/models`, затем `POST /v1/chat/completions` с
`logprobs: true, top_logprobs: 3` и печатает вердикт:

- `logprobs НЕ пришли` → для этой модели TruthProbe покажет `unavailable`, собирать
  данные бессмысленно;
- `logprobs доходят` → строка с `meanLp / minLp / phi / fracLow` дописывается в JSONL,
  остаётся проставить `label` (правда/ложь) и накопить 200–500 строк.

FreeLLMAPI заявляет, что `logprobs` пробрасывается провайдеру, но бесплатные тарифы
разных провайдеров относятся к параметру по-разному: часть просто игнорирует его,
часть отвечает 400. Поэтому проверять надо **по каждой модели отдельно**, а не «вообще».

## Подключение как провайдер в opencode

```json
{
  "provider": {
    "freellmapi": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "FreeLLMAPI",
      "options": { "baseURL": "http://127.0.0.1:3001/v1", "apiKey": "freellmapi-xxxx" },
      "models": {
        "auto": { "name": "Auto (router)" },
        "auto:fast": { "name": "Auto fast" }
      }
    }
  }
}
```

Автопроверка TruthProbe сама дёрнет эндпоинт и запишет вердикт в
`~/.local/share/opencode/truthprobe/capabilities.json`; при `status: ok` бейдж
появится без всякой настройки.

## Отдельные веса на каждую модель

Причина, по которой это нужно: форма распределения логвероятностей у моделей разная.
Один общий `sigmoid(bias + w·x)` систематически смещён для части моделей — у
детерминированных шлюзов `logprob ≈ −0.001`, у «живых» моделей хвост длиннее.

```bash
python3 scripts/calibrate.py labeled.jsonl --fit --by-model --out truthprobe-weights.json
```

JSONL должен содержать поле `model` (скрипт `probe-freellmapi.py --jsonl` пишет туда
`X-Routed-Via`, то есть `platform/model`). Выход — бандл:

```json
{
  "version": 1,
  "features": ["bias", "meanLp", "minLp", "meanPhi", "fracLow"],
  "global": { "bias": 0.0, "meanLp": 0.0, "minLp": 0.0, "meanPhi": 0.0, "fracLow": 0.0 },
  "models": {
    "groq/llama-3.3-70b": { "rows": 120, "positives": 41, "auroc": 0.78, "ece": 0.06, "weights": {} }
  }
}
```

Что это **не** делает: рантайм сейчас читает только `global` — выбор весов по модели
в скорере не реализован (`scoreAnswer` не получает id модели). Это следующий шаг:
прокинуть `providerID/modelID` в `publish-llm-event.ts` → `scoreAnswer` и выбирать
`models[<id>]` с откатом на `global`. До этого момента `--by-model` — инструмент
измерения, а не рантайм-фича, и README об этом говорит прямо.

## Чего ждать от такого источника данных

- **Плюс:** десятки моделей бесплатно, единый протокол, роутер сам обходит 429.
- **Минус:** бесплатные тарифы нестабильны по латентности и лимитам; часть моделей
  не отдаёт logprobs; «интеллект» эндпоинта падает к концу суток, когда у провайдеров
  кончаются дневные квоты.
- **Вывод:** как источник **размеченного набора** — годится; как продакшн-провайдер
  для бейджа — только с честным `unavailable` там, где logprobs не пришли.
