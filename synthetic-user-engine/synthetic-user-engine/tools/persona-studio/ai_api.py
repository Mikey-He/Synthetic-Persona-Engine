"""HTTP adapter for a Chat Completions-compatible API. No credentials in UI."""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# The engine's folder: its .env holds the keys, its config.toml the model (2026-10-19).
ROOT=Path(__file__).resolve().parents[2]/'engine'
# Gemini's Chat Completions-compatible endpoint. Only Google-approved Gemini models may be used,
# so without AI_* settings Persona Studio uses the engine's own GEMINI_API_KEY and model.
GEMINI_URL='https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'

def engine_model():
    try:
        import tomllib
        with (ROOT/'config.toml').open('rb') as f:return tomllib.load(f)['model']['id']
    except (OSError,KeyError,ValueError):return ''

def settings():
    values={}
    path=ROOT/'.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
    def get(key,default=''):return os.environ.get(key,values.get(key,default)).strip()
    result={key:get('AI_'+key.upper(),default) for key,default in {
        'api_url':'','api_key':'','model':'','json_mode':'json_object'}.items()}
    if not result['api_key'] and get('GEMINI_API_KEY'):
        result.update(api_key=get('GEMINI_API_KEY'),api_url=result['api_url'] or GEMINI_URL,
                      model=result['model'] or engine_model(),json_mode=get('AI_JSON_MODE','json_schema'))
    return result

def complete_json(prompt,schema,config):
    url,key,model=config['api_url'],config['api_key'],config['model']
    parsed=urlparse(url)
    if not key or key=='API_KEY_PLACEHOLDER':raise ValueError('Set your real AI_API_KEY in local .env; the placeholder cannot make API calls.')
    if not model or model=='YOUR_MODEL':raise ValueError('Set AI_MODEL in local .env.')
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Set AI_API_URL to a valid Chat Completions endpoint.')
    if parsed.scheme=='http' and parsed.hostname not in ('localhost','127.0.0.1','::1'):
        raise ValueError('Remote AI endpoints must use HTTPS.')
    mode=config['json_mode']
    if mode not in ('json_object','json_schema'):raise ValueError('AI_JSON_MODE must be json_object or json_schema.')
    response_format={'type':'json_object'} if mode=='json_object' else {'type':'json_schema','json_schema':{'name':'persona_output','strict':True,'schema':schema}}
    payload={'model':model,'messages':[{'role':'system','content':'Return only a JSON object matching this schema: '+json.dumps(schema)}, {'role':'user','content':prompt}],'response_format':response_format}
    request=Request(url,data=json.dumps(payload).encode('utf-8'),headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urlopen(request,timeout=180) as response:
            raw=response.read(2000001)
            if len(raw)>2000000:raise ValueError('AI response was too large. No changes applied.')
    except HTTPError as error:
        raise ValueError(f'AI API returned HTTP {error.code}. Check local endpoint, model, key and provider permissions.') from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('Could not reach the AI API. Check the endpoint and connection.') from None
    try:
        body=json.loads(raw)
        content=body['choices'][0]['message']['content']
        if not isinstance(content,str):raise ValueError()
        result=json.loads(content)
        if not isinstance(result,dict):raise ValueError()
        return result
    except (ValueError,KeyError,IndexError,TypeError):
        raise ValueError('AI API did not return a JSON object in choices[0].message.content. Check API compatibility.') from None
