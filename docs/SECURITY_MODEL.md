# Security Model

## Secret separation

### Local development `.env`
May contain:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- optional `OPENAI_API_KEY`

`.env` is gitignored.

### GitHub Actions secrets
Ingestion requires:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The service-role key is required because scheduled workers archive raw source material into the private Storage bucket.

### Streamlit Community Cloud secrets
The public dashboard should receive only:

- `DATABASE_URL`
- optional AI settings / `OPENAI_API_KEY` if the Copilot is intentionally exposed

**Do not put `SUPABASE_SERVICE_ROLE_KEY` into Streamlit.** The dashboard does not need to write raw source objects.

## AI boundary

- AI is disabled by default.
- Deterministic data, calculations and alerts remain core truth.
- API inputs are compact deterministic context or ambiguous disclosure excerpts, not arbitrary database dumps.
- `store=False` is used in Responses API requests.
- paid calls have call/input/output caps and content-hash caching.

## Public-source credentials

The project does not bypass authentication or scrape paid/protected feeds. Sources that require an account should only be integrated with legitimate user credentials and terms-compatible access.

## Repository hygiene

Never commit:

- `.env`;
- `.streamlit/secrets.toml`;
- database passwords;
- Supabase service-role keys;
- OpenAI API keys;
- confidential bank data.
