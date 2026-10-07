# AI Coach provider configuration (7 October 2026)

The old code defaulted ordinary requests to `glm-4.7-flash` and strategic requests to `glm-5.2`, using GLM credentials and endpoints. Merely adding `DEEPSEEK_API_KEY` did not select DeepSeek. The UI displayed the internal budget tier `cheap`, which did not identify the actual model. The home server's private environment was not accessible during this investigation, so its live model and successful provider delivery have not been verified.

The updated resolver uses DeepSeek for ordinary tiers when its key is present and per-tier model/endpoint overrides are empty. It calls `https://api.deepseek.com/chat/completions` and defaults to `deepseek-flash`. This is the model named in the official DeepSeek documentation retrieved on 7 October 2026. Older examples naming `deepseek-chat` or `deepseek-coder` must not be assumed to describe current model availability. Model names remain configurable. Explicit tier overrides win: an existing `.env` containing `LLM_PROVIDER_CHEAP=glm-4.7-flash` still intentionally selects GLM.

For an instance using only DeepSeek, set the following in the server's private `.env`; replace the placeholder securely and never commit the file:

```dotenv
DEEPSEEK_API_KEY=<your-secret-key>
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_THINKING=false
LLM_PROVIDER_CHEAP=
LLM_PROVIDER_POWERFUL=
LLM_API_BASE_CHEAP=
LLM_API_BASE_POWERFUL=
LLM_API_KEY_CHEAP=
LLM_API_KEY_POWERFUL=
```

Strategic requests use the same model by default. Set `DEEPSEEK_MODEL_POWERFUL=deepseek-v4-pro` only if that available model and its increased cost are desired. A custom OpenAI-compatible per-tier endpoint requires its own model and key; unrelated vendor credentials are not silently reused. Other configured services, including embeddings/transcription and optional medical routing, have separate settings.

From the repository root, after the updated image is available and installed, recreate the API and worker to load environment changes:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --no-build --force-recreate api worker
```

Use the same deployment overrides/image variables as your normal installation. For an updater-managed installation, add `-f .apex-updater/active.compose.yml` after your usual Compose files and use `--pull never --no-deps` to retain the pinned image when recreating `api worker`; do not run the plain command above against an older host checkout. In the supplied Compose configuration, the worker also hosts Celery Beat. Recreating containers does not update an old image by itself; see [AUTO_UPDATES.md](AUTO_UPDATES.md) for installing the tested main image. Verify a real Coach request afterward: its response now reports the actual model, rather than the internal tier.

The agent now obtains an owned, AI-eligible multi-day recovery summary in one tool call, reuses identical successful reads (including concurrent duplicates), invalidates cached reads after writes, and reserves time for a final answer. Maximums remain bounded: eight iterations, 24 tool calls, 32,000 tokens and 180 seconds total, with per-call limits. Repeated or blocked tool requests end with a localized explanation. These limits prevent runaway work; they cannot guarantee a remote provider will finish during an outage. Thinking is explicitly disabled by default for ordinary lookup latency; when enabled, returned reasoning content is preserved for compatible tool continuations.

Routing requests that use a paid DeepSeek model are accounted as paid even when the internal routing tier is named `free`. Tests use an HTTP transport fixture and fake credentials, and exercise actual request endpoint/model selection, tool reuse, ownership and budget behavior. No live DeepSeek key was available in the cloud environment.

Sources: [DeepSeek API documentation](https://api-docs.deepseek.com/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode), [tool calls](https://api-docs.deepseek.com/guides/tool_calls). Availability and pricing can change after the retrieval date.
