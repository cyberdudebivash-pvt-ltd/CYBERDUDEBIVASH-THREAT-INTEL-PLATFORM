import ast
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def load_decoder():
    root = Path(__file__).resolve().parents[1]
    source = root / 'platform/services/api-gateway/auth.py'
    if not source.exists():
        source = Path(__file__).with_name('auth.py')
    tree = ast.parse(source.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_decode_rs256_token')
    namespace = {'jwt': jwt}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['_decode_rs256_token']


@pytest.fixture
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    key.update(kid='trusted', alg='RS256', use='sig')
    return private, key


def claims():
    return {'sub': 'customer-user', 'exp': int(time.time()) + 300, 'tenant_id': 'customer-tenant'}


def test_valid_rs256_preserves_customer_claims(keys):
    private, key = keys
    token = jwt.encode(claims(), private, algorithm='RS256', headers={'kid': 'trusted'})
    assert load_decoder()(token, {'keys': [key]})['tenant_id'] == 'customer-tenant'


@pytest.mark.parametrize('case', ['expired', 'unknown-kid', 'ambiguous', 'bad-signature', 'missing-exp', 'wrong-use'])
def test_invalid_tokens_fail_closed(keys, case):
    private, key = keys
    payload = claims()
    kid = 'trusted'
    jwks = {'keys': [key]}
    if case == 'expired': payload['exp'] = int(time.time()) - 60
    if case == 'unknown-kid': kid = 'attacker'
    if case == 'ambiguous': jwks['keys'].append(dict(key))
    if case == 'bad-signature': private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if case == 'missing-exp': payload.pop('exp')
    if case == 'wrong-use': key['use'] = 'enc'
    token = jwt.encode(payload, private, algorithm='RS256', headers={'kid': kid})
    with pytest.raises(jwt.InvalidTokenError): load_decoder()(token, jwks)


def test_der_public_key_hmac_confusion_is_rejected(keys):
    private, key = keys
    der = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    def enc(value): return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=')
    message = enc({'alg': 'HS256', 'kid': 'trusted'}) + b'.' + enc(claims())
    signature = base64.urlsafe_b64encode(hmac.new(der, message, hashlib.sha256).digest()).rstrip(b'=')
    token = (message + b'.' + signature).decode()
    with pytest.raises(jwt.InvalidTokenError, match='Only RS256'): load_decoder()(token, {'keys': [key]})


def test_single_key_without_kid_remains_supported(keys):
    private, key = keys
    token = jwt.encode(claims(), private, algorithm='RS256')
    assert load_decoder()(token, {'keys': [key]})['sub'] == 'customer-user'
