rule CDB_SENTINEL_Network_Intel_e96fde488269
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-13"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "e96fde488269"
        ioc_count = 20

    strings:
        $dom_0 = "www.comacstnew.weebly.com" ascii wide nocase
        $dom_1 = "www.comcastmailin.weebly.com" ascii wide nocase
        $dom_2 = "www.comcastwebmailinternet.weebly.com" ascii wide nocase
        $dom_3 = "www.comcastinternetserver.weebly.com" ascii wide nocase
        $dom_4 = "www.comcastlogininfo.weebly.com" ascii wide nocase
        $dom_5 = "mkamaluddin838380.github.io" ascii wide nocase
        $dom_6 = "coderkubes.com" ascii wide nocase
        $dom_7 = "www.roblox.com" ascii wide nocase
        $dom_8 = "us09webzoominterview.com" ascii wide nocase
        $dom_9 = "kundenserivecidn.jdevcloud.com" ascii wide nocase
        $dom_10 = "trueaimportant64-d7bdancyaqdxcjg6.z03.azurefd.net" ascii wide nocase
        $dom_11 = "biichoios133.on-forge.com" ascii wide nocase
        $dom_12 = "iii.tkteam.top" ascii wide nocase
        $dom_13 = "roviasdigitaisblog.com" ascii wide nocase
        $dom_14 = "portal.roviasdigitaisblog.com" ascii wide nocase
        $dom_15 = "mailbox-validatinggg-outlook-00433.weebly.com" ascii wide nocase
        $dom_16 = "encrypted-login.com" ascii wide nocase
        $dom_17 = "bhd-clientes-activar-2026.weebly.com" ascii wide nocase
        $dom_18 = "WordPress.org" ascii wide nocase
        $dom_19 = "www.portable-intelligence.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}