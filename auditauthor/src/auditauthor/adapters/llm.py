import json
import os
import time

from pydantic import ValidationError

from auditauthor.config import Settings


class LiteLLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, system, content, schema, model):
        # Lazy import keeps offline parsing/tests independent of provider initialization.
        import litellm

        last_error = "Model request failed."
        for attempt in range(self.settings.model_attempts):
            try:
                response = litellm.completion(
                    model=model,
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "strict": True,
                            "schema": schema.model_json_schema(),
                        },
                    },
                    timeout=self.settings.model_timeout,
                    num_retries=0,
                )
                if response.choices[0].finish_reason != "stop":
                    raise ValueError("Incomplete model output.")
                result = schema.model_validate_json(response.choices[0].message.content or "")
                return result, response.model or model
            except (ValidationError, ValueError, json.JSONDecodeError):
                last_error = "Invalid or incomplete structured model output."
            except (
                litellm.Timeout,
                litellm.RateLimitError,
                litellm.APIConnectionError,
                litellm.InternalServerError,
            ):
                last_error = "Provider temporarily unavailable after bounded retries."
            except Exception as exc:  # noqa: BLE001 -- provider boundary must redact arbitrary SDK errors
                # Provider exceptions may contain keys or full prompts: never persist str(exc).
                raise RuntimeError(
                    f"Provider request failed ({type(exc).__name__}). Check model and credentials."
                ) from None
            if attempt + 1 < self.settings.model_attempts:
                time.sleep(min(2**attempt, 4))
        raise RuntimeError(last_error)
