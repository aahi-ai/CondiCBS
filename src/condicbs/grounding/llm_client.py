import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

DEFAULT_MODEL = os.environ.get("CONDICBS_MODEL", "anthropic/claude-haiku-4.5")

def call_llm(prompt, model=None, max_tokens=300, temperature=0):
    response = client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content