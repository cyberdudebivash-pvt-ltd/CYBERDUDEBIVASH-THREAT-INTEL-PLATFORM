rule CDB_SENTINEL_Network_Intel_a929aaa60fed
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-08"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "a929aaa60fed"
        ioc_count = 4

    strings:
        $ip_0 = "3.1.3.1" ascii wide nocase
        $ip_1 = "1.6.12.10" ascii wide nocase
        $ip_2 = "3.6.4.1" ascii wide nocase
        $ip_3 = "3.8.13.1" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}