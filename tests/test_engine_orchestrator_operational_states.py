import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerate_engine_data as regen

def test_empty_feed_fails_without_touching_last_valid_artifact(tmp_path,monkeypatch):
    saved=tmp_path/'saved.json';saved.write_text('saved')
    monkeypatch.setattr(regen,'ROOT',str(tmp_path));monkeypatch.setattr(regen,'_load_feed',lambda:[])
    with pytest.raises(SystemExit) as result:regen.main()
    assert result.value.code==1 and saved.read_text()=='saved'

@pytest.mark.parametrize('scan',[{'status':'AWAITING_SCAN','metrics':{},'findings_summary':[]},{'status':'COMPLETED','metrics':{'total_findings':0,'critical_findings':0},'findings_summary':[]}])
def test_scan_state_does_not_abort_remaining_output_publication(tmp_path,monkeypatch,scan):
    monkeypatch.setattr(regen,'ROOT',str(tmp_path))
    monkeypatch.setattr(regen,'_load_feed',lambda:[{'id':'test','title':'CVE-2026-1234 vulnerability','risk_score':9,'source_url':'https://example.test/report'}])
    monkeypatch.setattr(regen,'generate_bughunter',lambda *args:scan)
    regen.main()
    for name in ['api/engines.json','data/incidents/incidents.json','data/responses/response_log.json','data/threathunts/hunts.json','api/ai/tracker.json']:
        assert isinstance(json.loads((tmp_path/name).read_text()),dict)
    assert json.loads((tmp_path/'data/bughunter/bughunter_output.json').read_text())==scan
