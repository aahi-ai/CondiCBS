import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

DEFAULT_MODEL = os.environ.get("CONDICBS_MODEL", "claude-sonnet-4-5")

def call_llm(prompt, model=None, max_tokens=300, temperature=0):
    resp = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text