import json
import re

from langfuse import propagate_attributes
from langfuse.openai import OpenAI

from prompt import SYSTEM_PROMPT, user_prompt
from schema import LearningJobRequest, LearningResult


class LearningEngine:
    def __init__(self, settings):
        self.output_callback = None
        self.settings = settings
        self.client = OpenAI(
            base_url=settings.client.url,
            api_key=settings.client.token,
            timeout=settings.client.timeout_seconds,
        )

    def run(self, job_id, request: LearningJobRequest) -> tuple[LearningResult, str]:
        with propagate_attributes(session_id=str(job_id), trace_name="learning"):
            response = self.client.chat.completions.create(
                model=self.settings.client.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(request.source)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                top_p=0.9,
                stream=False,
            )
        raw = response.choices[0].message.content or ""
        self.last_raw_output = raw
        if self.output_callback:
            self.output_callback(job_id, raw)
        return self.parse(raw), raw

    @staticmethod
    def parse(raw: str) -> LearningResult:
        value = raw.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.DOTALL)
        if fenced:
            value = fenced.group(1)
        return LearningResult.model_validate(json.loads(value))
