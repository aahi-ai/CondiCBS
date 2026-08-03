import os

_PROVIDER = os.environ.get("CONDICBS_PROVIDER", "anthropic")

if _PROVIDER == "anthropic":
    from anthropic import Anthropic
    _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    _DEFAULT = "claude-sonnet-4-5"

    def _call(prompt, model, max_tokens, temperature):
        r = _client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
else:
    from openai import OpenAI
    _client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )
    _DEFAULT = "openai/gpt-4o"

    def _call(prompt, model, max_tokens, temperature):
        r = _client.chat.completions.create(
            model=model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content


DEFAULT_MODEL = os.environ.get("CONDICBS_MODEL", _DEFAULT)


def call_llm(prompt, model=None, max_tokens=300, temperature=0):
    return _call(prompt, model or DEFAULT_MODEL, max_tokens, temperature)