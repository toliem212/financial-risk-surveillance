# Milestone 8 — Optional OpenAI AI Enrichment Layer

Milestone 8 adds an opt-in AI layer without changing the deterministic risk engine.

## Design guardrails

- AI is disabled by default (`AI_ENABLED=0`).
- `OPENAI_API_KEY` alone does not activate paid calls.
- Deterministic Python/SQL remains authoritative for calculations, thresholds and risk signals.
- AI receives compact, pre-calculated context rather than raw market history.
- Responses use strict JSON Schema Structured Outputs.
- Responses are requested with `store=false`.
- Repeated identical requests are cached by feature + model + prompt version + content hash.
- A daily API-call cap is enforced before new requests.
- Input characters and output tokens are capped.
- Token usage is persisted in `ai_usage_log`.
- Cost estimation is optional and uses environment-supplied current prices; prices are not hard-coded.

## Features

### 1. Risk Investigation Copilot

The user explicitly clicks **Analyze selected signal with AI** from the deterministic investigation page.

The API receives only:
- the selected deterministic signal;
- rule-engine evidence;
- data-quality state;
- a maximum of 12 related observations;
- compact historical context;
- deterministic transmission/monitor-next context.

The output is concise Vietnamese and may not infer bank-specific positions, limits, P&L or exposure.

### 2. CBIS Disclosure Classifier

`python -m src.jobs.ai_classify_disclosure ...`

The classifier is intended for ambiguous disclosures or parser fallback. It produces an AI suggestion only and never overwrites HNX source records automatically.

### 3. AI Usage & Budget

Streamlit page `AI Usage & Budget` shows:
- API calls today;
- cache hits;
- monthly token usage;
- estimated cost when current model prices are configured;
- recent request audit records.

## Environment variables

```env
AI_ENABLED=0
OPENAI_API_KEY=
AI_MODEL=gpt-6-luna
AI_DAILY_CALL_LIMIT=20
AI_MAX_INPUT_CHARS=12000
AI_INVESTIGATION_MAX_OUTPUT_TOKENS=450
AI_DISCLOSURE_MAX_OUTPUT_TOKENS=220
AI_REASONING_EFFORT=none
AI_INPUT_USD_PER_MTOK=0
AI_CACHED_INPUT_USD_PER_MTOK=0
AI_OUTPUT_USD_PER_MTOK=0
```

## What AI does not do

AI does not calculate VaR, PV01, yield changes, z-scores, OMO net injection, thresholds or severity. It does not produce trading/hedging recommendations and does not infer any bank's confidential exposure.
