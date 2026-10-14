# Support Chat Translator

A courier or customer message goes in. The service detects the language, translates the message, and returns it. Every call records how long it took, how many tokens it used, and what it cost. A second script scores those translations against messages labeled by hand.

The scorecard is three numbers: whether the meaning survived, the latency, and the cost.

## Status

`POST /translate` detects the language, calls the model through one interface, stores the call in Postgres, and caches the translation in Redis. Prometheus counts requests, latency, and estimated cost for each model. A repeated sentence within the cache window skips the model. Tests use a fake model, so CI does not call a provider. The database test runs against Postgres and the cache test runs against Redis, including in GitHub Actions. Docker Compose starts the API, Postgres, Redis, and Prometheus.

Next: about 30 labeled support messages.

## What this project includes

- **Python service.** FastAPI with `POST /translate`. The body is the text, the source language, and the target language.
- **One model interface.** The route calls that interface. Swapping models means a new implementation, not a new route.
- **Real support text.** About 30 messages written for this repo: Finnish, English, and a mix of both. The set includes an order number, a street address, an emoji, a very short message, and a rude one. The order number and the address must come back unchanged.
- **PostgreSQL.** Each call stores the original text, the translation, the model name, latency, token count, and estimated cost.
- **Redis.** A short-lived cache so the same sentence is not translated twice.
- **Evaluation script.** Scores the 30 messages on meaning, latency, and cost, then runs two models. The comparison table in this README is that script's output.
- **Docker Compose.** The API, Postgres, and Redis start with one command.
- **GitHub Actions.** Tests run on every push.
- **Prometheus.** Request count, latency, and cost per model. These are the same signals DataDog would show in production.

Docker Compose is the deployment shown here. Kubernetes stays out of this repo: a toy cluster would not look like production experience. Docker, a real database, and measured cost are the parts that can be shown honestly.

## API

`POST /translate`

```json
{
  "text": "Tilaus #48291 on myöhässä, osoite Mannerheimintie 12",
  "source_language": "auto",
  "target_language": "en"
}
```

`source_language` is `auto` when the service should detect the language, or a language code (`fi`, `en`) when the caller already knows it. Optional `model` selects one of the two configured models. When it is omitted, the service uses `MODEL_A_NAME`.

```json
{
  "source_language": "fi",
  "target_language": "en",
  "translation": "Order #48291 is late, address Mannerheimintie 12",
  "model": "gpt-4.1-mini",
  "latency_ms": 840,
  "input_tokens": 42,
  "output_tokens": 18,
  "estimated_cost_usd": 0.0000456,
  "cached": false
}
```

The sample translation above shows the response shape. A live call fills those fields from the model.

If the detected language and the target language are the same, the original text is returned, the model is not called, and the token counts and cost are zero.

A second request with the same model, source language, target language, and text, inside `CACHE_TTL_SECONDS` (one hour by default), returns the stored translation with `"cached": true` and zero tokens and cost. The model is not called again. The cache key is a hash of those four values. A different model is a separate entry.

## Cost

Each model has a configured price per million input tokens and per million output tokens. The defaults are OpenAI's standard rates for `gpt-4.1-mini` and `gpt-4.1` as published in October 2026: $0.40 / $1.60 and $2.00 / $8.00 per million tokens. Cached-input and batch rates are separate and are not used. Change the values in `.env` if the price page changes, or if you point the client at another provider. The estimate for a call is:

```text
(input_tokens * input_price + output_tokens * output_price) / 1_000_000
```

That figure is an estimate from token counts and the price table. It is the number the scorecard and the metrics use.

## Quality

Each labeled message has three fields written by hand:

- the original text
- a reference translation
- the facts that must survive (the customer's request, and any order number or street address character for character)

Meaning is a pass or fail per message. A translation passes when every required fact is present and every protected string is unchanged. The quality number in the comparison table is the share of the 30 messages that pass.

Latency is the median and the 95th percentile of the recorded call times. Cost is the mean and the total estimated cost across the same run. Both come from the rows the API writes, so the table matches what Postgres stored.

| Model | Meaning | Median latency | p95 latency | Mean cost | Total cost |
| --- | --- | --- | --- | --- | --- |
| _filled by the evaluation script_ | | | | | |

## Stack

- Python, FastAPI
- PostgreSQL
- Redis
- Prometheus
- Docker Compose
- GitHub Actions

The model client speaks an OpenAI-compatible chat API. Model name, base URL, and prices live in configuration, which is how the route stays fixed while two models are compared.

Language detection runs before the model call when `source_language` is `auto`. A provided language code skips detection.

## Layout

```text
app/                 API, model interface, database, cache, metrics
eval/                labeled messages and the scoring script
tests/
docker-compose.yml
.github/workflows/   test workflow
```

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

cp .env.example .env   # API key stays local; the skeleton boots without one
docker compose up --build
```

`GET http://localhost:8000/health` returns `{"status": "ok"}`.

`POST /translate` needs `LLM_API_KEY` in `.env` when the real client is used. Rebuild the API container after changing `.env`.

```bash
curl -s http://localhost:8000/translate \
  -H 'content-type: application/json' \
  -d '{"text":"Tilaus on myöhässä","source_language":"auto","target_language":"en"}'
```

Secrets stay in `.env`. That file is gitignored. The database password in Compose is for this local stack only.

A successful `POST /translate` inserts one row. Read the latest rows with:

```bash
docker compose exec postgres psql -U translator -d translator \
  -c "select original_text, translation, model, latency_ms, input_tokens, output_tokens, estimated_cost_usd, cached from translations order by id desc limit 5;"
```

Cached translations live in Redis under keys that start with `translate:`. List them with:

```bash
docker compose exec redis redis-cli --scan --pattern 'translate:*'
```

## Metrics

`GET /metrics` exposes three series, labeled by model:

- `translation_requests_total`
- `translation_latency_seconds`
- `translation_cost_usd_total`

These are the same signals DataDog would show in production. Prometheus scrapes them in this project. A cache hit still counts as a request, with zero added cost.

With the stack running, open [http://localhost:9090](http://localhost:9090) and query `translation_requests_total`. The raw series are also at [http://localhost:8000/metrics](http://localhost:8000/metrics).

## Roadmap

1. **Skeleton.** Done. FastAPI app, settings, Dockerfile, and Compose for the API, Postgres, and Redis. Health check, plus a test that the app boots.
2. **Model interface.** Done. One interface for the completion call, a fake implementation for tests, and one real client that can target two configured models. `POST /translate` uses the interface. Detection sits in front of the call.
3. **Postgres.** Done. Each successful call stores the original text, the translation, the source and target languages, the model name, latency, input and output token counts, and estimated cost.
4. **Redis.** Done. The cache key is a hash of the model, source language, target language, and text. The TTL is one hour by default. A hit returns the stored translation and skips the model.
5. **Metrics.** Done. Prometheus request count, latency histogram, and cost counter, labeled by model. Scrape config in Compose.
6. **Labeled messages.** About 30 hand-written messages with reference translations and the strings that must not change.
7. **Evaluation.** Run both models on those messages. Score meaning, latency, and cost. Write the comparison table into this README.
8. **CI.** Done. GitHub Actions runs the tests on every push.
