import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerate_engine_data as regen

def test_coverage_counts_source_evidence_not_compliance():
    data=regen.generate_sovereign([{'exec_summary':'A','nvd_status':'CONFIRMED'},{'exec_summary':' '},{'exec_summary':True},None])
    assert data['feed_coverage']=={'total_records':3,'executive_summary_records':1,'nvd_confirmed_records':1}
    assert data['evidence_type']=='feed_coverage'
    for field in ['compliance','billing','tenants','whitelabel','onboarding']:
        assert field not in data

def test_empty_feed_cannot_attest_revenue_customers_or_certification():
    data=regen.generate_sovereign([])
    assert data['feed_coverage']['total_records']==0
    assert data['assessment_status']=='FEED_COVERAGE_ONLY'
    assert 'soc2_score' not in str(data) and 'gdpr_ready' not in str(data)
