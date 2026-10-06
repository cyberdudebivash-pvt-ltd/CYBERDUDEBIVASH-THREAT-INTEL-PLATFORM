rule CDB_SENTINEL_Network_Intel_559ffaa6c1cf
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-16"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "559ffaa6c1cf"
        ioc_count = 18

    strings:
        $ip_0 = "11.0.0.0" ascii wide nocase
        $ip_1 = "11.0.0.1" ascii wide nocase
        $ip_2 = "1.1.2.0" ascii wide nocase
        $ip_3 = "1.1.9.13" ascii wide nocase
        $dom_4 = "crisp.call-whatapp.com.cn" ascii wide nocase
        $dom_5 = "www.wellsfargo.com" ascii wide nocase
        $dom_6 = "kraj9370392-alt.github.io" ascii wide nocase
        $dom_7 = "duckroblox.com" ascii wide nocase
        $dom_8 = "dyrews.github.io" ascii wide nocase
        $dom_9 = "dynnhost.com" ascii wide nocase
        $dom_10 = "www.robiox.com" ascii wide nocase
        $dom_11 = "badge-auth.com" ascii wide nocase
        $dom_12 = "mobilehsbccprivateonline.com" ascii wide nocase
        $dom_13 = "www.roblox.com" ascii wide nocase
        $dom_14 = "napervillautohaus.com" ascii wide nocase
        $dom_15 = "www.instagramloginp.blogspot.com" ascii wide nocase
        $dom_16 = "syeda-javeria-naqvi-8.github.io" ascii wide nocase
        $dom_17 = "metacpan.org" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}