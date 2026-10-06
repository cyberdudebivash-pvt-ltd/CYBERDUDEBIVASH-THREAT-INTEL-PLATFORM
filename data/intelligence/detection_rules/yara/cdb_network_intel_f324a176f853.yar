rule CDB_SENTINEL_Network_Intel_f324a176f853
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-03"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "f324a176f853"
        ioc_count = 2

    strings:
        $ip_0 = "1.8.5.3" ascii wide nocase
        $ip_1 = "0.0.0.0" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}