"""Invalid feed metadata cannot poison regenerated JSON or abort extraction."""
import json
import math
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerate_engine_data as regen

@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf'),'NaN','Infinity','-Infinity',True,{},[],10**400])
def test_numeric_parser_cannot_return_nonfinite_or_boolean_measurements(value):
    assert math.isfinite(regen._safe_float(value))
    assert regen._safe_float(value)==0.0

def test_numeric_parser_preserves_legitimate_zero_and_decimal():
    assert regen._safe_float(0)==0.0
    assert regen._safe_float('7.5')==7.5

def test_malformed_actor_metadata_falls_back_to_valid_fields():
    assert regen._extract_actor({'actor_tag':42,'actor':'ExampleActor','title':{},'description':[]})=='ExampleActor'
    assert regen._extract_actor({'actor_tag':42,'title':{},'description':[]})=='UNK'

def test_malformed_techniques_do_not_crash_or_accept_partial_identifiers():
    assert regen._extract_ttps({'mitre_techniques':[{'id':42,'name':{}},None,'T1486junk','T1486',{'technique_id':'T1059.001'}]})==['T1486','T1059']

def test_nonfinite_write_preserves_last_good_artifact_and_cleans_temp(tmp_path):
    p=tmp_path/'artifact.json';p.write_text('{"valid":true}')
    assert regen._safe_write(str(p),{'bad':float('nan')}) is False
    assert json.loads(p.read_text())=={'valid':True}
    assert not Path(str(p)+'.tmp').exists()
    assert regen._safe_write(str(p),{'valid':2}) is True

def test_loader_rejects_wrong_container_and_filters_nonrecords(tmp_path,monkeypatch):
    primary=tmp_path/'primary.json';fallback=tmp_path/'fallback.json'
    monkeypatch.setattr(regen,'BASELINE_PATH',str(primary));monkeypatch.setattr(regen,'FEED_PATH',str(fallback))
    primary.write_text(json.dumps({'items':{'wrong':'container'}}));fallback.write_text(json.dumps([None,42,{'id':'good'}]))
    assert regen._load_feed()==[{'id':'good'}]
