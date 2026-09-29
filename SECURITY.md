# Security / Secrets

Never commit:

- Supabase service-role keys;
- PostgreSQL credentials;
- OpenAI API keys;
- paid/private-source credentials;
- bank-internal/confidential data.

Use environment variables, GitHub Actions secrets and Streamlit Secrets. The `.env` file is ignored by Git. `.streamlit/secrets.toml.example` is a template only.
