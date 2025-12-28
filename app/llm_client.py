from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings


class LLMClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing (set env var).")
        self.client = OpenAI()
        if not hasattr(self.client, "responses") or not hasattr(
            getattr(self.client, "responses"), "parse"
        ):
            raise RuntimeError(
                "Installed openai package does not support responses.parse. "
                "Install openai>=1.55.0 to use structured parsing."
            )

    def parse_structured(
        self,
        *,
        model: str,
        instructions: str,
        user_input: str,
        text_format: type[BaseModel],
        max_output_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> BaseModel:
        resp = self.client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            text_format=text_format,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        return resp.output_parsed
