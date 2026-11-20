# Prior art: уверенность модели по первым токенам

Собрано 19.11.2026. Нужно, чтобы не изобретать метрику и не повторять чужие ошибки.

## Прямо в тему

**The First Token Knows: Single-Decode Confidence for Hallucination Detection** —
Mina Gabriel, Pei Wang. arXiv **2605.05166** (v1 06.05.2026, v2 14.11.2026),
TRUST-AI 2026, CEUR Vol. 4254, pp. 55–63.

- `φ_first = 1 − нормированная энтропия top-K распределения первого содержательного токена`.
- PopQA + TriviaQA, три 7–8B instruct-модели: φ_first **догоняет или немного превосходит**
  semantic self-consistency (1 greedy декод против 1 декода + 10 сэмплов + NLI-кластеризация).
- φ_first умеренно-сильно коррелирует с semantic agreement; объединение даёт лишь небольшой
  прирост AUROC.
- Оговорка авторов: метод слаб на **high-confidence falsehoods** и **long-form generation**.

→ Берём формулу как есть (`φ_first`), но не как единственный сигнал.

## Калибровка: почему logprob ≠ правда

**Just Ask for Calibration** — Tian et al., EMNLP 2023, arXiv **2305.14975**.

- У RLHF-моделей (ChatGPT/GPT-4/Claude) **вербализованная** уверенность обычно
  лучше откалибрована, чем условные вероятности; ECE падает примерно вдвое.
- Вывод для нас: показывать «риск», а не «модель уверена на 94%».

**Beyond Logprobs: A Multi-Signal Confidence Engine for LLM-Based Document Field Extraction** —
Nitesh Kumar, arXiv **2606.24420** (IJCAI-ECAI 2026 workshop, oral).

- Token-level logprobs, verbalized confidence и multi-sample self-consistency
  «collapse toward all-positive behaviour at practical thresholds» — на рабочих порогах
  не разделяют надёжное и ненадёжное.
- Фьюжн с независимым источником (cross-call disagreement) → 0.928 ROC AUC,
  −70% selective risk против `logprob-mean`.
- Прямой вывод: **один logprob-сигнал в проде недостаточен**, нужен второй структурно иной сигнал.

**Detecting AI Hallucinations in Finance (ECLIPSE)** — arXiv **2512.03107**.

- Сравнение GPT-3.5-turbo vs Claude-3-Haiku: у Claude «lacks token-level log probabilities»,
  AUC падает с 0.89 до 0.59 — прямое подтверждение провайдерского барьера.

## Родственные методы (не в v1, но влияют на дизайн)

- **Semantic Entropy Probes** — Kossen et al., arXiv **2406.15927**: аппроксимация semantic entropy
  по hidden states одного прохода. Требует whitebox → только для локальных моделей/форка инференса.
- **lm-polygraph** (`IINemo/lm-polygraph`, ★530, MIT) — самая полная батарея UE-методов
  (logprob-based, semantic entropy, SEP) + бенчмарк. Референс реализаций.
- **SelfCheckGPT** (`potsawee/selfcheckgpt`, ★635) — sampling-based black-box.
- **llm-confidence-probe** (`prefersung`) — vLLM отдаёт token logprobs, агрегация
  в sentence-level risk, подсветка подозрительных фраз. Ближайший UX-аналог L3.
- **LLM-Hallucination-Detection-Script** (`Mattbusel`, ★19, Rust CLI) — «какие слова
  ответа перепроверить», темы `logprobs`, `token-visualization`.
- **rydz** (`mobarski`) — logprobs для классификации одним токеном (шаблон «1 запрос, 1 токен»).

## Что уже есть в экосистеме OpenCode

- Ничего с токен-логпробсами. Ближайшее — **DCGP** (`addicted2crypto/DCGP`, ★6):
  «predicts entropy, blocks hallucinations», но энтропия там по здоровью контекста
  (домены, гейты, anchors), слово `logprob` в README отсутствует.
- `@tarquinen/opencode-dcp` — управление количеством контекста, ортогонально.

## Проверенные факты про OpenCode (важно для архитектуры)

- В дереве `sst/opencode@dev` (12 659 файлов) **нет ни одного совпадения по `logprob`**.
- В `@opencode-ai/plugin` d.ts **нет** упоминаний logprobs; полный список хуков:
  `event`, `config`, `tool`, `auth`, `provider`, `chat.message`, `chat.params`, `chat.headers`,
  `permission.ask`, `command.execute.before`, `tool.execute.before`, `tool.execute.after`,
  `shell.env`, `experimental.chat.messages.transform`, `experimental.chat.system.transform`,
  `experimental.provider.small_model`, `experimental.session.compacting`,
  `experimental.compaction.autocontinue`, `experimental.text.complete`, `tool.definition`.
- `chat.params` умеет менять `options: Record<string, any>` (можно попытаться добавить
  `logprobs`), но парсер ответа их выбрасывает → фильтр на уровне ядра неизбежен.
