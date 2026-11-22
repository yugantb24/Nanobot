import hashlib, json, os, pathlib, subprocess

def cmd(args):
    result = subprocess.run(args, text=True, capture_output=True)
    return {'code': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}

result = {
    'os': pathlib.Path('/etc/os-release').read_text(),
    'architecture': cmd(['dpkg', '--print-architecture']),
    'packages': cmd(['dpkg-query', '-W', '-f=${Package}=${Version}\n'])['stdout'].splitlines(),
    'tools': {},
    'pythonEnvironments': {},
    'files': {},
    'browsers': {},
}
for name, args in {
    'nanobot': ['/usr/local/libexec/nanobot', '--version'],
    'mcp-cli': ['/usr/bin/mcp-cli', '--version'],
    'uv': ['/usr/local/bin/uv', '--version'],
    'node': ['node', '--version'],
    'npm': ['npm', '--version'],
    'python': ['python3', '--version'],
    'libreoffice': ['libreoffice', '--version'],
    'pdftoppm': ['pdftoppm', '-v'],
    'ghostscript': ['gs', '--version'],
}.items():
    result['tools'][name] = cmd(args)
for name in ['playwright', 'browser-use']:
    env = f'/opt/{name}-venv/bin/python'
    result['pythonEnvironments'][name] = json.loads(cmd([env, '-c',
        'import importlib.metadata,json; print(json.dumps({d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}))'])['stdout'])
for file in ['/usr/local/bin/nanobot', '/usr/local/libexec/nanobot', '/usr/bin/mcp-cli']:
    result['files'][file] = hashlib.sha256(pathlib.Path(file).read_bytes()).hexdigest()
cache = pathlib.Path('/var/cache/tiktoken')
result['tokenizerCache'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(cache.iterdir()) if p.is_file()}
browser_root = pathlib.Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/usr/local/share/ms-playwright'))
result['browsers']['directories'] = sorted(p.name for p in browser_root.iterdir())
for candidate in browser_root.glob('chromium-*/chrome-linux*/chrome'):
    result['browsers']['chromium'] = cmd([str(candidate), '--version'])
print(json.dumps(result, sort_keys=True, indent=2))
