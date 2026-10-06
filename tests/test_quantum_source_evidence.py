import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerate_engine_data as regen

def test_sources_are_real_url_counts_without_trust_or_false_positive_inference():
    d=regen.generate_quantum([{'source_url':'https://EXAMPLE.test/a','kev':True},{'source_url':'https://example.test/b','nvd_status':'CONFIRMED'},{'source_url':'/relative'}])
    c=d['source_coverage'];assert c['total_records']==3 and c['source_link_records']==2 and c['distinct_sources']==1
    assert c['kev_marked_records']==1 and c['nvd_confirmed_records']==1
    assert 'feed_trust' not in d and 'false_positives' not in d

def test_malformed_urls_and_records_do_not_crash_regeneration():
    items=[None,{}, {'source_url':42}]+[{'source_url':url} for url in ['x','https://[bad','javascript:alert(1)','https://bad host/a','https://example.test:bad/a']]
    c=regen.generate_quantum(items)['source_coverage'];assert c['source_link_records']==0 and c['distinct_sources']==0

def test_high_risk_without_cve_is_only_a_review_candidate():
    d=regen.generate_quantum([{'id':'a','title':'Malware campaign','risk_score':9}]);r=d['review_candidates'][0]
    assert r['status']=='ANALYST_REVIEW_REQUIRED' and 'confidence' not in r
    assert d['source_coverage']['review_candidate_count']==1

def test_empty_feed_cannot_invent_eighty_percent_trust():
    d=regen.generate_quantum([]);assert d['source_coverage']['total_records']==0
    assert 'overall' not in str(d) and 'fp_rate' not in str(d)
