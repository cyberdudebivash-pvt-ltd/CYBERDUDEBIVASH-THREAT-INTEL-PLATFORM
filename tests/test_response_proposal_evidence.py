"""A recommendation generator cannot attest that mitigations executed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import regenerate_engine_data as regen

def test_proposals_have_source_and_no_execution_claims():
    data=regen.generate_response_log([{'id':'a','title':'CVE vulnerability','risk_score':9,'source_url':'https://example.test/report'}])
    assert data['mode']=='recommendations_only'
    assert data['total_actions']==1
    assert 'automation_stats' not in data
    action=data['response_actions'][0]
    assert action['status']=='PROPOSED'
    assert action['requires_approval'] is True
    assert action['source_url']=='https://example.test/report'
    assert 'executed_at' not in action and 'automated' not in action
    assert action['action_type']=='patch_vulnerability'

def test_zero_and_missing_risk_do_not_become_medium_risk():
    data=regen.generate_response_log([{'title':'CVE','risk_score':0},{'title':'CVE'}])
    assert data['response_actions']==[]
    assert data['total_actions']==0

def test_action_breakdown_counts_actual_recommendations():
    data=regen.generate_response_log([{'title':'ransomware','risk_score':9},{'title':'ransomware','risk_score':8},{'title':'phishing','risk_score':7}])
    assert data['action_breakdown']=={'quarantine_host':2,'remove_phishing_email':1}
    assert sum(data['action_breakdown'].values())==data['total_actions']
