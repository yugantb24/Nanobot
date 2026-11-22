"""Offline checks for a disposable agent container; uses only synthetic state."""
import http.server, json, os, pathlib, signal, socket, sqlite3, subprocess, tempfile, threading, time, traceback, urllib.request, zipfile

report = {'passed': False, 'checks': [], 'customerDataUsed': False, 'liveModelUsed': False}
marker = 'FragAI offline compatibility reply'
model_requests = []
tool_calls = []
process = None
log_path = pathlib.Path('/tmp/fragai-agent.log')

def run(args, timeout=90, env=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    assert result.returncode == 0, f'{args[0]} exited {result.returncode}: {result.stderr[-1800:]} {result.stdout[-600:]}'
    return result.stdout

def checked(name):
    report['checks'].append(name)

class Fixture(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *_):
        pass
    def reply(self, status, value=None, headers=None):
        body = b'' if value is None else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        for key, val in (headers or {}).items(): self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        self.reply(405)
    def do_DELETE(self):
        self.reply(200, {})
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        if self.path == '/v1/chat/completions':
            model_requests.append(data)
            tools = [t['function'] for t in data.get('tools', []) if 'echo' in t.get('function', {}).get('name', '')]
            has_tool_result = any(m.get('role') == 'tool' for m in data.get('messages', []))
            if tools and not has_tool_result:
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'fixture-call', 'type': 'function', 'function': {'name': tools[0]['name'], 'arguments': json.dumps({'value': marker})}}]}
                finish = 'tool_calls'
            else:
                delta = {'role': 'assistant', 'content': marker}
                finish = 'stop'
            def chunk(delta, reason=None):
                return {'id': 'fixture-completion', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'mock', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
            body = ''.join('data: ' + json.dumps(item) + '\n\n' for item in [chunk(delta), chunk({}, finish)]) + 'data: [DONE]\n\n'
            encoded = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        method = data.get('method')
        if method == 'notifications/initialized': return self.reply(202)
        results = {
            'initialize': {'protocolVersion': '2025-11-25', 'capabilities': {'tools': {}, 'resources': {}, 'prompts': {}}, 'serverInfo': {'name': 'fragai-offline-fixture', 'version': '1'}},
            'tools/list': {'tools': [{'name': 'echo', 'description': 'Return the fixture value', 'inputSchema': {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']}}]},
            'resources/list': {'resources': []}, 'resources/templates/list': {'resourceTemplates': []}, 'prompts/list': {'prompts': []}, 'ping': {},
        }
        if method == 'tools/call':
            tool_calls.append(data['params'])
            results[method] = {'content': [{'type': 'text', 'text': data['params']['arguments']['value']}]}
        self.reply(200, {'jsonrpc': '2.0', 'id': data.get('id'), 'result': results.get(method, {})}, {'Mcp-Session-Id': 'fragai-fixture-session'})

def rpc(method, params, session=None, request_id=1):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-11-25'}
    if session: headers['Mcp-Session-Id'] = session
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
    if request_id is not None: payload['id'] = request_id
    req = urllib.request.Request('http://127.0.0.1:8080/mcp/chat', json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read().decode()
        sid = response.headers.get('Mcp-Session-Id', session)
        if not raw: return {}, sid
        if response.headers.get('Content-Type', '').startswith('text/event-stream'):
            values = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ') and line[6:] != '[DONE]']
            value = next(v for v in values if v.get('id') == request_id)
        else: value = json.loads(raw)
    assert 'error' not in value, value
    return value.get('result', {}), sid

def start_agent(disable_ui=False):
    global process
    env = {**os.environ, 'NANOBOT_ENV_FILE': '/home/nanobot/nanobot.env', 'NANOBOT_RUN_HEALTHZ_PATH': '/healthz', 'OTEL_SDK_DISABLED': 'true', 'ANONYMIZED_TELEMETRY': 'false'}
    args = ['/usr/local/bin/nanobot', 'run', '--state', '.nanobot/state/nanobot.db', '--config', '.nanobot/', '--config', '/home/nanobot/provider-fixture.json', '--agent', 'review']
    if disable_ui: args.append('--disable-ui')
    process = subprocess.Popen(args, stdout=log_path.open('a'), stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(150):
        assert process.poll() is None, log_path.read_text()[-2200:]
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=1) as res:
                if res.status == 200: return
        except Exception: pass
        time.sleep(0.2)
    raise AssertionError('Agent failed to become healthy: ' + log_path.read_text()[-2200:])

def stop_agent():
    global process
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    process = None

try:
    assert os.getuid() == 0, 'Run this helper in a dedicated default-user agent container.'
    home = pathlib.Path('/home/nanobot')
    (home / '.nanobot').mkdir(exist_ok=True)
    config = {'publish': {'entrypoint': ['review']}, 'agents': {'review': {'model': 'openai/mock', 'instructions': 'Use the echo tool when it is available.', 'mcpServers': ['fixture']}}, 'mcpServers': {'fixture': {'url': 'http://127.0.0.1:18992/mcp'}}}
    (home / '.nanobot/nanobot.yaml').write_text(json.dumps(config))
    provider = {'llmProviders': {'openai': {'dialect': 'OpenAIChatCompletions', 'apiKey': 'offline-fixture-only', 'baseURL': 'http://127.0.0.1:18992/v1'}}}
    (home / 'provider-fixture.json').write_text(json.dumps(provider))
    (home / 'nanobot.env').write_text('NANOBOT_DEFAULT_MODEL=openai/mock\nNANOBOT_DEFAULT_MINI_MODEL=openai/mock\nANTHROPIC_API_KEY=offline-fixture-only\nANTHROPIC_BASE_URL=http://127.0.0.1:18992/v1\n')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 18992), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.chdir(home)
    cli_config = home / 'fixture-mcp.json'
    cli_config.write_text(json.dumps({'mcpServers': {'fixture': {'url': 'http://127.0.0.1:18992/mcp'}}}))
    cli_env = {**os.environ, 'MCP_NO_DAEMON': '1'}
    assert 'echo' in run(['mcp-cli', '-c', str(cli_config), 'info', 'fixture'], env=cli_env)
    assert marker in run(['mcp-cli', '-c', str(cli_config), 'call', 'fixture', 'echo', json.dumps({'value': marker})], env=cli_env)
    checked('compiled MCP CLI: discover and execute an HTTP MCP tool offline')
    before_agent_tools = len(tool_calls)
    start_agent()
    checked('governance command, merged config, env file, port and health endpoint')
    listing, sid = rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'fragai-compatibility', 'version': '1'}})
    rpc('notifications/initialized', {}, sid, None)
    listing, _ = rpc('tools/list', {}, sid, 2)
    tool = next(t['name'] for t in listing['tools'] if t['name'] == 'chat-with-review')
    answer, _ = rpc('tools/call', {'name': tool, 'arguments': {'prompt': 'Call the echo tool and report the result.'}}, sid, 3)
    assert not answer.get('isError'), answer
    assert marker in json.dumps(answer), answer
    assert len(tool_calls) > before_agent_tools, 'The model must actually invoke the fixture MCP tool.'
    checked('agent streamed model response with an actual MCP tool call')
    report['toolName'] = tool
    report['modelRequests'] = len(model_requests)
    report['agentToolCalls'] = len(tool_calls) - before_agent_tools
    processes = run(['ps', '-eo', 'uid,args'])
    assert any(line.strip().startswith('1000 ') and '/usr/local/libexec/nanobot' in line for line in processes.splitlines())
    checked('root entrypoint drops agent execution to nanobot UID 1000')
    for port in [5900, 6080]:
        with socket.create_connection(('127.0.0.1', port), timeout=5): pass
    checked('Xvfb/VNC/websockify browser stack starts')
    browser_code = '''from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=False,args=["--no-sandbox","--disable-dev-shm-usage"])
 page=b.new_page();page.set_content("<title>FragAI fixture</title><input aria-label='Fixture value'><button>Click</button>")
 assert page.title()=="FragAI fixture";page.get_by_label("Fixture value").fill("FragAI");page.get_by_role("button").click();assert page.get_by_label("Fixture value").input_value()=="FragAI"
 b.close()
'''
    run(['runuser', '-u', 'nanobot', '--', '/opt/playwright-venv/bin/python', '-c', browser_code])
    checked('headed Chromium renders and interacts as the agent user')
    run(['browser-use', '--help'], env={**os.environ, 'ANONYMIZED_TELEMETRY': 'false'})
    checked('browser-use CLI loads its retained functionality')
    with tempfile.TemporaryDirectory(prefix='fragai-office-') as temp:
        folder = pathlib.Path(temp)
        os.chown(folder, 1000, 1000)
        (folder / 'fixture.txt').write_text(marker)
        lo = ['runuser', '-u', 'nanobot', '--', 'libreoffice', '-env:UserInstallation=file://' + temp + '/profile', '--headless', '--convert-to']
        run(lo + ['docx', '--outdir', temp, str(folder / 'fixture.txt')])
        assert zipfile.is_zipfile(folder / 'fixture.docx')
        run(lo + ['pdf', '--outdir', temp, str(folder / 'fixture.docx')])
        assert marker in run(['pdftotext', str(folder / 'fixture.pdf'), '-'])
        run(['pdftoppm', '-f', '1', '-singlefile', '-png', str(folder / 'fixture.pdf'), str(folder / 'page')])
        assert (folder / 'page.png').read_bytes().startswith(b'\x89PNG')
        (folder / 'sheet.csv').write_text('item,value\nfixture,42\n')
        run(lo + ['xlsx', '--outdir', temp, str(folder / 'sheet.csv')])
        assert zipfile.is_zipfile(folder / 'sheet.xlsx')
        run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=nullpage', str(folder / 'fixture.pdf')])
    checked('Writer DOCX/PDF, Calc XLSX, PDF text/rendering and Ghostscript')
    state = home / '.nanobot/state/nanobot.db'
    assert state.is_file()
    stop_agent()
    with sqlite3.connect(state) as db:
        db.execute('create table if not exists fragai_compatibility_marker (name text primary key)')
        present = [r[0] for r in db.execute('select name from fragai_compatibility_marker order by name')]
        expected = sorted(json.loads(os.environ.get('FRAGAI_EXPECT_MARKERS', '[]')))
        assert present == expected, {'expectedMarkers': expected, 'actualMarkers': present}
        stage = os.environ.get('FRAGAI_STAGE', 'baseline')
        db.execute('insert into fragai_compatibility_marker(name) values (?)', (stage,))
        db.commit()
        tables = db.execute("select name from sqlite_master where type='table' order by name").fetchall()
        assert tables
    start_agent(disable_ui=True)
    _, resume_sid = rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'fragai-restart', 'version': '1'}})
    tools, _ = rpc('tools/list', {}, resume_sid, 4)
    assert tool in [t['name'] for t in tools['tools']]
    with sqlite3.connect(state) as db:
        assert db.execute("select name from sqlite_master where type='table' order by name").fetchall() == tables
        report['stateMarkers'] = [r[0] for r in db.execute('select name from fragai_compatibility_marker order by name')]
        assert report['stateMarkers'] == sorted(expected + [stage])
    checked('same state database survives agent restart and --disable-ui')
    report['stateTables'] = [t[0] for t in tables]
    report['passed'] = True
except Exception as error:
    report['error'] = repr(error)
    report['modelRequestSummary'] = [{'model': r.get('model'), 'tools': [t.get('function', {}).get('name') for t in r.get('tools', [])], 'roles': [m.get('role') for m in r.get('messages', [])]} for r in model_requests]
    if log_path.exists(): report['agentLogTail'] = log_path.read_text()[-3500:]
finally:
    stop_agent()
    print(json.dumps(report, indent=2))
if not report['passed']: raise SystemExit(1)
