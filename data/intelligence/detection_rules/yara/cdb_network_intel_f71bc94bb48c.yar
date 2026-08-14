rule CDB_SENTINEL_Network_Intel_f71bc94bb48c
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-14"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "f71bc94bb48c"
        ioc_count = 23

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $dom_1 = "pay.paykmc.com" ascii wide nocase
        $dom_2 = "binancewallett.blogspot.com" ascii wide nocase
        $dom_3 = "www.comacstnew.weebly.com" ascii wide nocase
        $dom_4 = "www.comcastmailin.weebly.com" ascii wide nocase
        $dom_5 = "www.comcastwebmailinternet.weebly.com" ascii wide nocase
        $dom_6 = "www.comcastinternetserver.weebly.com" ascii wide nocase
        $dom_7 = "www.comcastlogininfo.weebly.com" ascii wide nocase
        $dom_8 = "mkamaluddin838380.github.io" ascii wide nocase
        $dom_9 = "coderkubes.com" ascii wide nocase
        $dom_10 = "www.roblox.com" ascii wide nocase
        $dom_11 = "us09webzoominterview.com" ascii wide nocase
        $dom_12 = "kundenserivecidn.jdevcloud.com" ascii wide nocase
        $dom_13 = "trueaimportant64-d7bdancyaqdxcjg6.z03.azurefd.net" ascii wide nocase
        $dom_14 = "biichoios133.on-forge.com" ascii wide nocase
        $dom_15 = "iii.tkteam.top" ascii wide nocase
        $dom_16 = "roviasdigitaisblog.com" ascii wide nocase
        $dom_17 = "portal.roviasdigitaisblog.com" ascii wide nocase
        $dom_18 = "mailbox-validatinggg-outlook-00433.weebly.com" ascii wide nocase
        $dom_19 = "encrypted-login.com" ascii wide nocase
        $dom_20 = "bhd-clientes-activar-2026.weebly.com" ascii wide nocase
        $dom_21 = "WordPress.org" ascii wide nocase
        $dom_22 = "www.portable-intelligence.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}