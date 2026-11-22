import hashlib, json, os, pathlib
expected = json.loads(pathlib.Path('/tmp/tokenizer-cache.lock.json').read_text())
cache = pathlib.Path(os.environ['TIKTOKEN_CACHE_DIR'])
actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cache.iterdir() if p.is_file()}
assert actual == expected, 'Tokenizer assets must match the recorded original cache hashes.'
print('Verified all tokenizer assets against the original image.')
