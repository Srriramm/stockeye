"""
llm_client.py — Model-agnostic LLM layer for StockEye.

Single seam for every AI call in the app. Supports three providers behind one
API and lets you switch the whole site between them with one env var:

    LLM_PROVIDER = gemini | anthropic | openai        (default: gemini)

Gemini is the default and is wired for a **Vertex AI Express** API key
(GEMINI_API_KEY), which the google-genai SDK consumes via
`genai.Client(vertexai=True, api_key=...)`. Set GEMINI_USE_VERTEX=false to use a
plain Gemini Developer API key instead.

Two capabilities are exposed, both provider-agnostic:

  1. generate() / generate_text() / generate_json()
       one-shot (or short multi-turn) text completion.

  2. run_agent_loop()
       a full native tool-use loop (the pattern used by agentic_trader and
       agentic_forecaster). Tools are declared once in the neutral
       Anthropic-style {name, description, input_schema} shape and translated
       to each provider's function-calling format internally.

Model tiers: every call picks a "fast" or "deep" model per provider. Override
any of them via env (e.g. GEMINI_MODEL_DEEP=gemini-2.5-pro).
"""

import json
import logging
import os
import time
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# eventlet.Timeout is the only reliable way to interrupt blocking I/O under the
# eventlet green-thread runtime the Flask app uses. Provider SDK timeouts don't
# always fire because eventlet patches the socket layer, not the SDK internals.
try:
    import eventlet
    _EVENTLET_AVAILABLE = True
except ImportError:
    _EVENTLET_AVAILABLE = False

AI_TIMEOUT = 60          # seconds — hard wall for a single provider call
_MAX_RETRIES = 3         # transient-error retries with exponential backoff

# ── Keys ──────────────────────────────────────────────────────────────────────
GEMINI_API_KEY    = os.getenv('GEMINI_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY', '')
GEMINI_USE_VERTEX = os.getenv('GEMINI_USE_VERTEX', 'true').lower() in ('1', 'true', 'yes')

# ── Model tiers per provider (env-overridable) ─────────────────────────────────
_MODELS = {
    'gemini': {
        'fast': os.getenv('GEMINI_MODEL_FAST', 'gemini-2.5-flash'),
        'deep': os.getenv('GEMINI_MODEL_DEEP', 'gemini-2.5-pro'),
    },
    'anthropic': {
        'fast': os.getenv('ANTHROPIC_MODEL_FAST', 'claude-haiku-4-5-20251001'),
        'deep': os.getenv('ANTHROPIC_MODEL_DEEP', 'claude-sonnet-5'),
    },
    'openai': {
        'fast': os.getenv('OPENAI_MODEL_FAST', 'gpt-4o-mini'),
        'deep': os.getenv('OPENAI_MODEL_DEEP', 'gpt-4o'),
    },
}


def _provider_available(name: str) -> bool:
    return {
        'gemini': bool(GEMINI_API_KEY),
        'anthropic': bool(ANTHROPIC_API_KEY),
        'openai': bool(OPENAI_API_KEY),
    }.get(name, False)


def default_provider() -> str | None:
    """Resolve the active provider: LLM_PROVIDER if set + available, else the
    first available in preference order (gemini → anthropic → openai)."""
    pref = os.getenv('LLM_PROVIDER', 'gemini').lower().strip()
    if pref and _provider_available(pref):
        return pref
    for name in ('gemini', 'anthropic', 'openai'):
        if _provider_available(name):
            return name
    return None


def is_available() -> bool:
    return default_provider() is not None


def _resolve(provider: str | None, deep: bool) -> tuple[str, str]:
    """Return (provider, model_id). Falls back to any available provider."""
    provider = (provider or default_provider())
    if not provider or not _provider_available(provider):
        provider = default_provider()
    if not provider:
        raise RuntimeError("No LLM provider configured (set GEMINI_API_KEY, "
                           "ANTHROPIC_API_KEY, or OPENAI_API_KEY).")
    tier = 'deep' if deep else 'fast'
    return provider, _MODELS[provider][tier]


# ── Lazy clients ────────────────────────────────────────────────────────────────
_clients: dict[str, object] = {}


def _get_client(provider: str):
    if provider in _clients:
        return _clients[provider]
    client = None
    if provider == 'gemini':
        from google import genai
        if GEMINI_USE_VERTEX:
            # Vertex AI Express mode: an express API key authenticates the
            # Vertex endpoint through the unified SDK.
            client = genai.Client(vertexai=True, api_key=GEMINI_API_KEY)
        else:
            client = genai.Client(api_key=GEMINI_API_KEY)
    elif provider == 'anthropic':
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    elif provider == 'openai':
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    _clients[provider] = client
    return client


# ── Neutral schema → provider tool formats ──────────────────────────────────────
# Neutral tool shape (Anthropic-native, reused verbatim by callers):
#   {"name": str, "description": str, "input_schema": <JSON Schema object>}

_GEMINI_TYPE = {
    'object': 'OBJECT', 'string': 'STRING', 'number': 'NUMBER',
    'integer': 'INTEGER', 'boolean': 'BOOLEAN', 'array': 'ARRAY',
}


def _to_gemini_schema(schema: dict):
    from google.genai import types
    stype = _GEMINI_TYPE.get((schema or {}).get('type', 'string'), 'STRING')
    kwargs = {'type': stype}
    if schema.get('description'):
        kwargs['description'] = schema['description']
    if schema.get('enum'):
        kwargs['enum'] = [str(e) for e in schema['enum']]
    if stype == 'OBJECT':
        props = {k: _to_gemini_schema(v) for k, v in schema.get('properties', {}).items()}
        if props:
            kwargs['properties'] = props
        if schema.get('required'):
            kwargs['required'] = schema['required']
    if stype == 'ARRAY':
        kwargs['items'] = _to_gemini_schema(schema.get('items', {'type': 'string'}))
    return types.Schema(**kwargs)


def _gemini_tools(tools: list[dict]):
    from google.genai import types
    decls = [
        types.FunctionDeclaration(
            name=t['name'],
            description=t.get('description', ''),
            parameters=_to_gemini_schema(t.get('input_schema', {'type': 'object', 'properties': {}})),
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=decls)]


def _openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            'type': 'function',
            'function': {
                'name': t['name'],
                'description': t.get('description', ''),
                'parameters': t.get('input_schema', {'type': 'object', 'properties': {}}),
            },
        }
        for t in tools
    ]


# ── Neutral conversation history ─────────────────────────────────────────────────
# A neutral message is one of:
#   {"role": "user"|"assistant", "content": str, "tool_calls": [ToolCall]?}
#   {"role": "tool_results", "results": [{"id", "name", "result": <obj>}]}
# where ToolCall = {"id": str, "name": str, "args": dict}

def _plain_args(args) -> dict:
    """Coerce provider-specific arg containers into a plain dict."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return {k: _plain_val(v) for k, v in args.items()}
    try:
        return {k: _plain_val(v) for k, v in dict(args).items()}
    except Exception:
        return {}


def _plain_val(v):
    if isinstance(v, dict):
        return {k: _plain_val(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain_val(x) for x in v]
    try:
        from google.genai import types  # noqa
    except Exception:
        pass
    # MapComposite / RepeatedComposite from proto expose dict()/list() semantics
    if hasattr(v, 'items'):
        try:
            return {k: _plain_val(x) for k, x in v.items()}
        except Exception:
            return v
    return v


# ── Anthropic translation ─────────────────────────────────────────────────────
def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m['role']
        if role == 'user':
            out.append({'role': 'user', 'content': m['content']})
        elif role == 'assistant':
            blocks = []
            if m.get('content'):
                blocks.append({'type': 'text', 'text': m['content']})
            for tc in m.get('tool_calls', []):
                blocks.append({'type': 'tool_use', 'id': tc['id'],
                               'name': tc['name'], 'input': tc['args']})
            out.append({'role': 'assistant', 'content': blocks or ''})
        elif role == 'tool_results':
            out.append({'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': r['id'],
                 'content': json.dumps(r['result'], default=str)}
                for r in m['results']
            ]})
    return out


def _invoke_anthropic(client, model, system, messages, tools, temperature, max_tokens, deep=False):
    kwargs = dict(model=model, max_tokens=max_tokens, temperature=temperature,
                  messages=_to_anthropic_messages(messages))
    if system:
        kwargs['system'] = system
    if tools:
        kwargs['tools'] = [{'name': t['name'], 'description': t.get('description', ''),
                            'input_schema': t.get('input_schema', {'type': 'object', 'properties': {}})}
                           for t in tools]
    resp = client.messages.create(**kwargs)
    text = ''.join(b.text for b in resp.content if getattr(b, 'type', None) == 'text')
    tool_calls = [
        {'id': b.id, 'name': b.name, 'args': _plain_args(b.input)}
        for b in resp.content if getattr(b, 'type', None) == 'tool_use'
    ]
    return {'text': text, 'tool_calls': tool_calls}


# ── OpenAI translation ─────────────────────────────────────────────────────────
def _to_openai_messages(system, messages: list[dict]) -> list[dict]:
    out = []
    if system:
        out.append({'role': 'system', 'content': system})
    for m in messages:
        role = m['role']
        if role == 'user':
            out.append({'role': 'user', 'content': m['content']})
        elif role == 'assistant':
            msg = {'role': 'assistant', 'content': m.get('content') or None}
            if m.get('tool_calls'):
                msg['tool_calls'] = [
                    {'id': tc['id'], 'type': 'function',
                     'function': {'name': tc['name'], 'arguments': json.dumps(tc['args'], default=str)}}
                    for tc in m['tool_calls']
                ]
            out.append(msg)
        elif role == 'tool_results':
            for r in m['results']:
                out.append({'role': 'tool', 'tool_call_id': r['id'],
                            'content': json.dumps(r['result'], default=str)})
    return out


def _invoke_openai(client, model, system, messages, tools, temperature, max_tokens, deep=False):
    kwargs = dict(model=model, messages=_to_openai_messages(system, messages),
                  temperature=temperature, max_tokens=max_tokens, timeout=45)
    if tools:
        kwargs['tools'] = _openai_tools(tools)
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    text = msg.content or ''
    tool_calls = []
    for tc in (msg.tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or '{}')
        except Exception:
            args = {}
        tool_calls.append({'id': tc.id, 'name': tc.function.name, 'args': args})
    return {'text': text, 'tool_calls': tool_calls}


# ── Gemini translation ──────────────────────────────────────────────────────────
def _to_gemini_contents(messages: list[dict]):
    from google.genai import types
    contents = []
    for m in messages:
        role = m['role']
        if role == 'user':
            contents.append(types.Content(role='user', parts=[types.Part(text=m['content'])]))
        elif role == 'assistant':
            parts = []
            if m.get('content'):
                parts.append(types.Part(text=m['content']))
            for tc in m.get('tool_calls', []):
                parts.append(types.Part(function_call=types.FunctionCall(name=tc['name'], args=tc['args'])))
            contents.append(types.Content(role='model', parts=parts or [types.Part(text='')]))
        elif role == 'tool_results':
            parts = []
            for r in m['results']:
                result = r['result']
                if not isinstance(result, dict):
                    result = {'result': result}
                parts.append(types.Part.from_function_response(name=r['name'], response=result))
            contents.append(types.Content(role='user', parts=parts))
    return contents


def _invoke_gemini(client, model, system, messages, tools, temperature, max_tokens, deep=False):
    from google.genai import types
    cfg_kwargs = dict(temperature=temperature, max_output_tokens=max_tokens)
    if system:
        cfg_kwargs['system_instruction'] = system
    # Gemini 2.5 models "think" by default, which silently eats the output-token
    # budget and can return empty text on small budgets. Disable thinking on the
    # fast tier (cheap + deterministic); leave it on for the deep tier (and note
    # 2.5-pro does not permit disabling it anyway).
    if not deep and 'flash' in model:
        cfg_kwargs['thinking_config'] = types.ThinkingConfig(thinking_budget=0)
    if tools:
        cfg_kwargs['tools'] = _gemini_tools(tools)
        # Disable automatic function calling — we drive the loop ourselves.
        cfg_kwargs['automatic_function_calling'] = types.AutomaticFunctionCallingConfig(disable=True)
    resp = client.models.generate_content(
        model=model,
        contents=_to_gemini_contents(messages),
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    text, tool_calls = '', []
    candidates = getattr(resp, 'candidates', None) or []
    if candidates:
        parts = getattr(candidates[0].content, 'parts', None) or []
        for i, p in enumerate(parts):
            fc = getattr(p, 'function_call', None)
            if fc is not None:
                tool_calls.append({'id': f'{fc.name}-{i}', 'name': fc.name, 'args': _plain_args(fc.args)})
            elif getattr(p, 'text', None):
                text += p.text
    return {'text': text, 'tool_calls': tool_calls}


_INVOKERS = {'gemini': _invoke_gemini, 'anthropic': _invoke_anthropic, 'openai': _invoke_openai}


def _invoke(provider, model, system, messages, tools, temperature, max_tokens, deep=False):
    """Single provider call with an eventlet hard-timeout + transient retry."""
    client = _get_client(provider)
    invoker = _INVOKERS[provider]
    last_exc: Exception = RuntimeError(f"{provider} call did not run")
    for attempt in range(_MAX_RETRIES):
        try:
            def _call():
                return invoker(client, model, system, messages, tools, temperature, max_tokens, deep)
            if _EVENTLET_AVAILABLE:
                with eventlet.Timeout(AI_TIMEOUT):
                    return _call()
            return _call()
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = 2 ** attempt
                logger.warning(f"[llm:{provider}] call failed (attempt {attempt + 1}/{_MAX_RETRIES}): "
                               f"{exc} — retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"[llm:{provider}] call failed after {_MAX_RETRIES} attempts: {exc}")
    raise last_exc


# ── Public: text generation ─────────────────────────────────────────────────────
def generate(prompt: str = None, *, system: str = None, messages: list[dict] = None,
             provider: str = None, deep: bool = False, temperature: float = 0.4,
             max_tokens: int = 2000) -> dict:
    """
    Generate a text completion from any provider.

    Pass either `prompt` (single user turn) or `messages` (a list of
    {"role": "user"|"assistant", "content": str}). `system` is the system prompt.

    Returns {'text', 'provider', 'model', 'error'}. Never raises — errors are
    reported in the dict so callers keep their existing error-handling shape.
    """
    if messages is None:
        messages = [{'role': 'user', 'content': prompt or ''}]
    try:
        prov, model = _resolve(provider, deep)
    except Exception as exc:
        return {'text': '', 'provider': 'none', 'model': 'none', 'error': str(exc)}
    try:
        result = _invoke(prov, model, system, messages, None, temperature, max_tokens, deep)
        return {'text': result['text'], 'provider': prov, 'model': model, 'error': None}
    except Exception as exc:
        return {'text': '', 'provider': prov, 'model': model, 'error': str(exc)}


def generate_text(prompt: str = None, **kwargs) -> str:
    """Convenience wrapper returning just the text (empty string on error)."""
    return generate(prompt, **kwargs).get('text', '') or ''


def generate_json(prompt: str = None, **kwargs) -> dict | list | None:
    """Generate and parse a JSON object/array. Strips ```json fences. Returns
    None if nothing parseable came back."""
    text = generate_text(prompt, **kwargs)
    return _extract_json(text)


def _extract_json(text: str):
    if not text:
        return None
    t = text.strip()
    if t.startswith('```'):
        t = t.split('```', 2)[1] if t.count('```') >= 2 else t.strip('`')
        if t.startswith('json'):
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        # Fall back to the first {...} or [...] span.
        for open_c, close_c in (('{', '}'), ('[', ']')):
            start, end = t.find(open_c), t.rfind(close_c)
            if 0 <= start < end:
                try:
                    return json.loads(t[start:end + 1])
                except Exception:
                    continue
    return None


# ── Public: native tool-use agent loop ──────────────────────────────────────────
def run_agent_loop(*, system: str, user_prompt: str, tools: list[dict],
                   dispatch, terminal_tools: set[str],
                   provider: str = None, deep: bool = False,
                   max_iterations: int = 12, temperature: float = 0.1,
                   max_tokens: int = 4096,
                   force_terminal_at: int = None, force_terminal_message: str = None,
                   on_tool_result=None, escalate=None) -> dict:
    """
    Provider-agnostic native tool-use loop.

    Args:
        system:          system prompt.
        user_prompt:     the opening user message.
        tools:           neutral tool defs {name, description, input_schema}.
        dispatch:        fn(name, args_dict) -> JSON-serialisable result dict.
        terminal_tools:  tool names that end the loop; their args are returned.
        deep:            start on the deep model tier.
        force_terminal_at:      iteration index at which to nudge the model to
                                call a terminal tool (anti-stall).
        force_terminal_message: the nudge text.
        on_tool_result:  optional fn(name, args, result) called after each
                         non-terminal tool (e.g. to record executed trades).
        escalate:        optional fn(name, args, result, deep) -> bool; return
                         True to switch to the deep model for the rest of the loop.

    Returns:
        {'terminal_name', 'terminal_result', 'iterations', 'tools_called',
         'model', 'provider', 'error'}
    """
    try:
        prov, model = _resolve(provider, deep)
    except Exception as exc:
        return {'terminal_name': None, 'terminal_result': None, 'iterations': 0,
                'tools_called': [], 'model': 'none', 'provider': 'none', 'error': str(exc)}

    messages: list[dict] = [{'role': 'user', 'content': user_prompt}]
    terminal_name, terminal_result = None, None
    tools_called: list[str] = []
    iterations = 0
    error = None

    for iteration in range(max_iterations):
        iterations = iteration + 1
        if force_terminal_at is not None and iteration == force_terminal_at and terminal_result is None:
            messages.append({'role': 'user', 'content': force_terminal_message or
                             'You have gathered enough data. Call the final/summary tool NOW.'})

        _, model = _resolve(prov, deep)   # re-resolve in case escalate() flipped deep
        try:
            resp = _invoke(prov, model, system, messages, tools, temperature, max_tokens, deep)
        except Exception as exc:
            error = str(exc)
            logger.error(f"[llm:agent-loop] provider call failed (iter {iteration}): {exc}")
            break

        messages.append({'role': 'assistant', 'content': resp['text'],
                         'tool_calls': resp['tool_calls']})

        if not resp['tool_calls']:
            break   # model stopped without calling a tool

        results = []
        loop_done = False
        for tc in resp['tool_calls']:
            name, args = tc['name'], tc['args']
            if name in terminal_tools:
                terminal_name = name
                terminal_result = dict(args)
                results.append({'id': tc['id'], 'name': name, 'result': {'status': 'accepted'}})
                loop_done = True
                break
            result = dispatch(name, args)
            tools_called.append(name)
            if on_tool_result:
                try:
                    on_tool_result(name, args, result)
                except Exception as cb_exc:
                    logger.debug(f"on_tool_result hook error: {cb_exc}")
            if escalate and not deep:
                try:
                    if escalate(name, args, result, deep):
                        deep = True
                        logger.info(f"[llm:agent-loop] escalated to deep model tier after {name}")
                except Exception:
                    pass
            results.append({'id': tc['id'], 'name': name, 'result': result})

        messages.append({'role': 'tool_results', 'results': results})
        if loop_done:
            break

    return {'terminal_name': terminal_name, 'terminal_result': terminal_result,
            'iterations': iterations, 'tools_called': tools_called,
            'model': model, 'provider': prov, 'error': error}
