rule CDB_SENTINEL_Network_Intel_1d37008eedde
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-21"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "1d37008eedde"
        ioc_count = 27

    strings:
        $ip_0 = "2.6.0.1" ascii wide nocase
        $ip_1 = "0.0.0.0" ascii wide nocase
        $ip_2 = "0.9.1.3" ascii wide nocase
        $ip_3 = "11.5.7.0" ascii wide nocase
        $ip_4 = "4.3.0.1" ascii wide nocase
        $ip_5 = "6.7.4.8" ascii wide nocase
        $ip_6 = "7.20.30.50" ascii wide nocase
        $ip_7 = "1.20.60.50" ascii wide nocase
        $ip_8 = "6.1.5.9" ascii wide nocase
        $dom_9 = "crates.io" ascii wide nocase
        $dom_10 = "metacpan.org" ascii wide nocase
        $dom_11 = "docs.wagtail.org" ascii wide nocase
        $dom_12 = "wagtail.org" ascii wide nocase
        $dom_13 = "wintercms.com" ascii wide nocase
        $dom_14 = "www.cve.org" ascii wide nocase
        $dom_15 = "www.agingenieria.com" ascii wide nocase
        $dom_16 = "www.made-in-china.com" ascii wide nocase
        $dom_17 = "dccrsorgia.github.io" ascii wide nocase
        $dom_18 = "aidenpiearce.github.io" ascii wide nocase
        $dom_19 = "valli-18.github.io" ascii wide nocase
        $dom_20 = "www.14025.xyz" ascii wide nocase
        $dom_21 = "fairtrade.com" ascii wide nocase
        $dom_22 = "www.14088.xyz" ascii wide nocase
        $dom_23 = "m4nfdw.top" ascii wide nocase
        $dom_24 = "em6gto.top" ascii wide nocase
        $dom_25 = "go.opentelemetry.io" ascii wide nocase
        $dom_26 = "usbank.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}