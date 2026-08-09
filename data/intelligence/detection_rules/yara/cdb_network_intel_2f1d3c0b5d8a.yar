rule CDB_SENTINEL_Network_Intel_2f1d3c0b5d8a
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-09"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "2f1d3c0b5d8a"
        ioc_count = 26

    strings:
        $ip_0 = "1.3.4.34" ascii wide nocase
        $ip_1 = "1.0.2.7" ascii wide nocase
        $dom_2 = "www.roblox.com" ascii wide nocase
        $dom_3 = "www.365bet6.com" ascii wide nocase
        $dom_4 = "www.17568.xyz" ascii wide nocase
        $dom_5 = "roblox.com.ml" ascii wide nocase
        $dom_6 = "www.17557.xyz" ascii wide nocase
        $dom_7 = "demontre.com" ascii wide nocase
        $dom_8 = "p7v3w.motnatelly.xyz" ascii wide nocase
        $dom_9 = "www.17534.xyz" ascii wide nocase
        $dom_10 = "maxcuru.com" ascii wide nocase
        $dom_11 = "www.facebookdatingonfacebook.blogspot.com" ascii wide nocase
        $dom_12 = "duajunaid53-gif.github.io" ascii wide nocase
        $dom_13 = "bhagyashridodmise75-cmd.github.io" ascii wide nocase
        $dom_14 = "xfinityaccountmanagement.weebly.com" ascii wide nocase
        $dom_15 = "performance-door.net" ascii wide nocase
        $dom_16 = "instagramlogin68.blogspot.com" ascii wide nocase
        $dom_17 = "ql5b30.info" ascii wide nocase
        $dom_18 = "bnmsc.com" ascii wide nocase
        $dom_19 = "9dra9hlj.1wpvsox.com" ascii wide nocase
        $dom_20 = "instagramlogin77.blogspot.com" ascii wide nocase
        $dom_21 = "retry-icloud.com" ascii wide nocase
        $dom_22 = "options-icloud.com" ascii wide nocase
        $dom_23 = "keep-icloud.com" ascii wide nocase
        $dom_24 = "backoffice.vns8455.com" ascii wide nocase
        $dom_25 = "call.element.io" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}