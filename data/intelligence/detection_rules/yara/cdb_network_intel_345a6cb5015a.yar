rule CDB_SENTINEL_Network_Intel_345a6cb5015a
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-01"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "345a6cb5015a"
        ioc_count = 39

    strings:
        $ip_0 = "3.7.8.1" ascii wide nocase
        $ip_1 = "2.9.9.6" ascii wide nocase
        $ip_2 = "9.7.2.1" ascii wide nocase
        $ip_3 = "9.7.2.11" ascii wide nocase
        $ip_4 = "9.6.1.1" ascii wide nocase
        $ip_5 = "9.6.1.13" ascii wide nocase
        $ip_6 = "1.3.5.0" ascii wide nocase
        $ip_7 = "1.3.5.1" ascii wide nocase
        $ip_8 = "1.3.5.2" ascii wide nocase
        $ip_9 = "1.3.5.3" ascii wide nocase
        $ip_10 = "1.3.6.0" ascii wide nocase
        $ip_11 = "1.3.6.1" ascii wide nocase
        $ip_12 = "1.3.7.0" ascii wide nocase
        $ip_13 = "1.3.7.1" ascii wide nocase
        $ip_14 = "1.3.7.2" ascii wide nocase
        $ip_15 = "1.3.8.0" ascii wide nocase
        $ip_16 = "1.3.8.1" ascii wide nocase
        $ip_17 = "1.3.8.2" ascii wide nocase
        $ip_18 = "1.3.8.3" ascii wide nocase
        $ip_19 = "1.3.8.4" ascii wide nocase
        $ip_20 = "17.0.0.3" ascii wide nocase
        $ip_21 = "26.0.0.7" ascii wide nocase
        $ip_22 = "2.2.1.4" ascii wide nocase
        $ip_23 = "0.0.0.0" ascii wide nocase
        $ip_24 = "13.0.1.0" ascii wide nocase
        $ip_25 = "13.0.7.2" ascii wide nocase
        $ip_26 = "12.0.1.0" ascii wide nocase
        $ip_27 = "12.0.12.27" ascii wide nocase
        $ip_28 = "26.0.0.8" ascii wide nocase
        $ip_29 = "6.2.2.0" ascii wide nocase
        $ip_30 = "6.1.2.0" ascii wide nocase
        $ip_31 = "6.2.0.0" ascii wide nocase
        $ip_32 = "6.2.1.0" ascii wide nocase
        $ip_33 = "5.03.01.49" ascii wide nocase
        $ip_34 = "1.1.24.2" ascii wide nocase
        $dom_35 = "discuss.rubyonrails.org" ascii wide nocase
        $dom_36 = "cve.org" ascii wide nocase
        $dom_37 = "WordPress.org" ascii wide nocase
        $dom_38 = "ci.eclipse.org" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}