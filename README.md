# Support Chat Translator

A courier or customer message goes in. The service detects the language, translates the message, and returns it. Every call records how long it took, how many tokens it used, and what it cost. A second script scores those translations against messages labeled by hand.

The scorecard is three numbers: whether the meaning survived, the latency, and the cost.

## Status

This repository holds the plan. Code follows the roadmap below, in that order.

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

`source_language` is `auto` when the service should detect the language, or a language code (`fi`, `en`) when the caller already knows it.

The response includes the detected source language, the translation, the model name, latency in milliseconds, input and output token counts, estimated cost in USD, and whether the reply came from the cache.

## Cost

Each model has a configured price per million input tokens and per million output tokens, taken from that provider's published rates. The estimate stored on the call is:

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

Commands land here with the first runnable slice. The intended start is:

```bash
cp .env.example .env   # API key stays local
docker compose up --build
```

Secrets stay in `.env`. That file is gitignored.

## Roadmap

1. **Skeleton.** FastAPI app, settings, Dockerfile, and Compose for the API, Postgres, and Redis. Health check, plus a test that the app boots.
2. **Model interface.** One interface for the completion call, a fake implementation for tests, and one real client that can target two configured models. `POST /translate` uses the interface. Detection sits in front of the call.
3. **Postgres.** Persist original text, translation, model name, latency, token count, and estimated cost.
4. **Redis.** Cache key is model, source language, target language, and text. Short TTL. A hit returns the stored translation and skips the model.
5. **Metrics.** Prometheus request count, latency histogram, and cost counter, labeled by model. Scrape config in Compose.
6. **Labeled messages.** About 30 hand-written messages with reference translations and the strings that must not change.
7. **Evaluation.** Run both models on those messages. Score meaning, latency, and cost. Write the comparison table into this README.
8. **CI.** GitHub Actions runs the tests on every push.
