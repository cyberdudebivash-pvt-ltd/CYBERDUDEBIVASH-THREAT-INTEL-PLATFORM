rule CDB_SENTINEL_Network_Intel_abb11a262dad
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-14"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "abb11a262dad"
        ioc_count = 56

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $ip_1 = "0.1.3.6" ascii wide nocase
        $dom_2 = "ultralimiteprimedisponivel.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_3 = "gbinsta.cc" ascii wide nocase
        $dom_4 = "app.trezors-suites.com" ascii wide nocase
        $dom_5 = "tk.ercajchain.com" ascii wide nocase
        $dom_6 = "rbcode.net" ascii wide nocase
        $dom_7 = "santander.pt-atendimento.com" ascii wide nocase
        $dom_8 = "www.roblox.com" ascii wide nocase
        $dom_9 = "mapaicloud.com" ascii wide nocase
        $dom_10 = "divyasri-raju.github.io" ascii wide nocase
        $dom_11 = "soumya-shree-panda.github.io" ascii wide nocase
        $dom_12 = "aneesurrehmandm.github.io" ascii wide nocase
        $dom_13 = "facebookteamhelp.blogspot.com" ascii wide nocase
        $dom_14 = "home-exo-x-en.github.io" ascii wide nocase
        $dom_15 = "ledger-help-io.square.site" ascii wide nocase
        $dom_16 = "steamxcommunity.ru" ascii wide nocase
        $dom_17 = "www.lsoehd.com" ascii wide nocase
        $dom_18 = "www.lsioeh.com" ascii wide nocase
        $dom_19 = "www.lsoiehrf.com" ascii wide nocase
        $dom_20 = "xxfinitywebnotify.weebly.com" ascii wide nocase
        $dom_21 = "xfinitypage.weebly.com" ascii wide nocase
        $dom_22 = "newcomcastserver.weebly.com" ascii wide nocase
        $dom_23 = "promptspark.net" ascii wide nocase
        $dom_24 = "mmmyyttsswebmaiii.weebly.com" ascii wide nocase
        $dom_25 = "samratitinstitute.com" ascii wide nocase
        $dom_26 = "Chess.com" ascii wide nocase
        $dom_27 = "chess.com" ascii wide nocase
        $dom_28 = "pacific-construction.com" ascii wide nocase
        $dom_29 = "cambrialawfirm.com" ascii wide nocase
        $dom_30 = "metacpan.org" ascii wide nocase
        $dom_31 = "download.samba.org" ascii wide nocase
        $dom_32 = "rsync.samba.org" ascii wide nocase
        $dom_33 = "pay.paykmc.com" ascii wide nocase
        $dom_34 = "binancewallett.blogspot.com" ascii wide nocase
        $dom_35 = "www.comacstnew.weebly.com" ascii wide nocase
        $dom_36 = "www.comcastmailin.weebly.com" ascii wide nocase
        $dom_37 = "www.comcastwebmailinternet.weebly.com" ascii wide nocase
        $dom_38 = "www.comcastinternetserver.weebly.com" ascii wide nocase
        $dom_39 = "www.comcastlogininfo.weebly.com" ascii wide nocase
        $dom_40 = "mkamaluddin838380.github.io" ascii wide nocase
        $dom_41 = "coderkubes.com" ascii wide nocase
        $dom_42 = "us09webzoominterview.com" ascii wide nocase
        $dom_43 = "kundenserivecidn.jdevcloud.com" ascii wide nocase
        $dom_44 = "trueaimportant64-d7bdancyaqdxcjg6.z03.azurefd.net" ascii wide nocase
        $dom_45 = "biichoios133.on-forge.com" ascii wide nocase
        $dom_46 = "iii.tkteam.top" ascii wide nocase
        $dom_47 = "roviasdigitaisblog.com" ascii wide nocase
        $dom_48 = "portal.roviasdigitaisblog.com" ascii wide nocase
        $dom_49 = "mailbox-validatinggg-outlook-00433.weebly.com" ascii wide nocase
        $dom_50 = "encrypted-login.com" ascii wide nocase
        $dom_51 = "bhd-clientes-activar-2026.weebly.com" ascii wide nocase
        $dom_52 = "WordPress.org" ascii wide nocase
        $dom_53 = "www.portable-intelligence.com" ascii wide nocase
        $dom_54 = "openssh.com" ascii wide nocase
        $dom_55 = "cloud.openshift.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}