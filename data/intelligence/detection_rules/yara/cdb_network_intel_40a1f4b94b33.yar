rule CDB_SENTINEL_Network_Intel_40a1f4b94b33
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-02"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "40a1f4b94b33"
        ioc_count = 6

    strings:
        $ip_0 = "2.7.9.8" ascii wide nocase
        $ip_1 = "1.6.12.6" ascii wide nocase
        $ip_2 = "5.9.9.8" ascii wide nocase
        $ip_3 = "1.0.0.4" ascii wide nocase
        $ip_4 = "0.0.0.0" ascii wide nocase
        $dom_5 = "VPS.org" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}