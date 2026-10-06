rule CDB_SENTINEL_Network_Intel_f5ed9aad9634
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-07-31"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "f5ed9aad9634"
        ioc_count = 5

    strings:
        $ip_0 = "17.0.0.3" ascii wide nocase
        $ip_1 = "26.0.0.8" ascii wide nocase
        $ip_2 = "26.3.9.8" ascii wide nocase
        $ip_3 = "24.10.01.33" ascii wide nocase
        $dom_4 = "openshift.io" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}