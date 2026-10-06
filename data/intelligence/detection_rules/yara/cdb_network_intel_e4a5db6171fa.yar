rule CDB_SENTINEL_Network_Intel_e4a5db6171fa
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-26"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "e4a5db6171fa"
        ioc_count = 13

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $ip_1 = "169.254.169.254" ascii wide nocase
        $ip_2 = "6.0.3.1" ascii wide nocase
        $dom_3 = "www.roblox.com" ascii wide nocase
        $dom_4 = "coinbase-lidiya.com" ascii wide nocase
        $dom_5 = "instagramfollowers7894.blogspot.com" ascii wide nocase
        $dom_6 = "facebooklogincc.blogspot.com" ascii wide nocase
        $dom_7 = "www.pastijosjis.blogspot.com" ascii wide nocase
        $dom_8 = "bah5szv.myrdbx.io" ascii wide nocase
        $dom_9 = "localhost.evil.com" ascii wide nocase
        $dom_10 = "localhost.attacker.com" ascii wide nocase
        $dom_11 = "127.0.0.1.nip.io" ascii wide nocase
        $dom_12 = "yootheme.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}