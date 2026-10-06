rule CDB_SENTINEL_Network_Intel_2f1b70fe5482
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-07-30"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "2f1b70fe5482"
        ioc_count = 15

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $ip_1 = "169.254.169.254" ascii wide nocase
        $ip_2 = "6.2.0.0" ascii wide nocase
        $ip_3 = "6.2.0.6" ascii wide nocase
        $ip_4 = "6.2.1.0" ascii wide nocase
        $ip_5 = "6.2.2.0" ascii wide nocase
        $ip_6 = "7.9.9.1" ascii wide nocase
        $dom_7 = "ci.eclipse.org" ascii wide nocase
        $dom_8 = "nodejs.org" ascii wide nocase
        $dom_9 = "lore.kernel.org" ascii wide nocase
        $dom_10 = "www.cve.org" ascii wide nocase
        $dom_11 = "harwal.net" ascii wide nocase
        $dom_12 = "socket.io" ascii wide nocase
        $dom_13 = "joomdle.com" ascii wide nocase
        $dom_14 = "balbooa.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}