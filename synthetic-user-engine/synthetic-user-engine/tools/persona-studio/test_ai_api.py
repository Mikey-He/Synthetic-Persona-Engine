import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ai_api
import survey_text


def test_placeholder_and_remote_http_are_rejected():
    config={'api_url':'https://example.invalid/v1/chat/completions','api_key':'API_KEY_PLACEHOLDER','model':'test-model','json_mode':'json_object'}
    with pytest.raises(ValueError,match='placeholder'):
        ai_api.complete_json('prompt',{},config)
    config.update(api_key='fixture-only',api_url='http://example.invalid/v1/chat/completions')
    with pytest.raises(ValueError,match='HTTPS'):
        ai_api.complete_json('prompt',{},config)


def test_api_route_keeps_quote_validation(tmp_path):
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            captured.append((self.headers.get('Authorization'),json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            result={'summary':'Synthetic fixture','unknowns':[],'updates':[{'path':'detailCheck','value_json':'2','quote':'I check every field.','confidence':'explicit','reason':'Explicit report'}]}
            raw=json.dumps({'choices':[{'message':{'content':json.dumps(result)}}]}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config={'api_url':f'http://127.0.0.1:{server.server_port}/v1/chat/completions','api_key':'fixture-only','model':'fixture-model','json_mode':'json_object'}
    try:
        with patch('survey_text.api_settings',return_value=config):
            result=survey_text.extract_text('I check every field.',tmp_path)
        assert result['updates'][0]['value']==2
        assert captured[0][0]=='Bearer fixture-only'
        assert captured[0][1]['model']=='fixture-model'
        assert captured[0][1]['response_format']=={'type':'json_object'}
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_env_file_and_environment_precedence(tmp_path):
    (tmp_path/'.env').write_text('AI_API_KEY=API_KEY_PLACEHOLDER\nAI_MODEL=fixture\n')
    with patch.object(ai_api,'ROOT',tmp_path),patch.dict(ai_api.os.environ,{'AI_MODEL':'override'},clear=True):
        config=ai_api.settings()
    assert config['model']=='override' and config['api_key']=='API_KEY_PLACEHOLDER'
