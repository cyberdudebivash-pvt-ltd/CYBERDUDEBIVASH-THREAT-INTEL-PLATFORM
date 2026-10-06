import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import regenerate_engine_data as regen

def test_edges_count_unique_explicit_relationships_not_node_multiples():
    item={'id':'a','title':'CVE-2026-1234 CVE-2026-1234','actor':'ExampleActor','mitre_techniques':['T1486','T1486',{'id':'T1059.001'}]}
    d=regen.generate_cortex([item,item]);kg=d['knowledge_graph']
    assert kg['total_nodes']==5 and kg['total_edges']==4
    assert kg['unique_advisories']==1 and d['actor_groups']==0
    assert kg['relationship_counts']=={'attributed_in_feed':1,'references_cve':1,'references_technique':2}
    assert 'stream' not in d

def test_actor_groups_require_two_distinct_advisories_and_order_is_stable():
    items=[{'id':'a','actor':'ExampleActor'},{'id':'b','actor':'exampleactor'}]
    a,b=regen.generate_cortex(items),regen.generate_cortex(list(reversed(items)))
    assert a['actor_groups']==1
    assert a['knowledge_graph']==b['knowledge_graph']

def test_empty_malformed_and_unknown_fields_cannot_create_fabricated_relationships():
    d=regen.generate_cortex([None,{}, {'id':'a','actor':42,'mitre_techniques':[{'id':42},None,'invalid']},{'id':'b','actor':'UNKNOWN'}])
    assert d['knowledge_graph']['total_nodes']==2
    assert d['knowledge_graph']['total_edges']==0
    assert regen.generate_cortex([])['knowledge_graph']['total_nodes']==0
