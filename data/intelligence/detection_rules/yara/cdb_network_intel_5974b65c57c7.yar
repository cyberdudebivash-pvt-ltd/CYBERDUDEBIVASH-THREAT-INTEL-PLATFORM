rule CDB_SENTINEL_Network_Intel_5974b65c57c7
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-18"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "5974b65c57c7"
        ioc_count = 33

    strings:
        $ip_0 = "6.50.0.0" ascii wide nocase
        $ip_1 = "5.42.0.0" ascii wide nocase
        $ip_2 = "6.49.0.0" ascii wide nocase
        $ip_3 = "0.0.0.0" ascii wide nocase
        $ip_4 = "1.6.12.17" ascii wide nocase
        $ip_5 = "2.10.2.2" ascii wide nocase
        $ip_6 = "2.9.9.6" ascii wide nocase
        $dom_7 = "http4k.org" ascii wide nocase
        $dom_8 = "openssl-library.org" ascii wide nocase
        $dom_9 = "www.ozatak.com" ascii wide nocase
        $dom_10 = "www.roblox.com" ascii wide nocase
        $dom_11 = "jpsrental.com" ascii wide nocase
        $dom_12 = "gemini-sx-login.gitbook.io" ascii wide nocase
        $dom_13 = "online-novobanco.com" ascii wide nocase
        $dom_14 = "x-novobanco.com" ascii wide nocase
        $dom_15 = "wordpress-214346-0.cloudclusters.net" ascii wide nocase
        $dom_16 = "deduction.onlinepaye.com" ascii wide nocase
        $dom_17 = "my-logacces.com" ascii wide nocase
        $dom_18 = "lubnamaryam531.github.io" ascii wide nocase
        $dom_19 = "www.roblox.com.ml" ascii wide nocase
        $dom_20 = "843824910-google.com" ascii wide nocase
        $dom_21 = "larrywiki.com" ascii wide nocase
        $dom_22 = "www.facebookpageslinkk.blogspot.com" ascii wide nocase
        $dom_23 = "lg8ems.top" ascii wide nocase
        $dom_24 = "giftcodelqne.aovlienquan-garena.com" ascii wide nocase
        $dom_25 = "demontdedsd.github.io" ascii wide nocase
        $dom_26 = "aprobacion.github.io" ascii wide nocase
        $dom_27 = "hf.com" ascii wide nocase
        $dom_28 = "90ca1592c92af967cae76eaa619ff6cc1396.com" ascii wide nocase
        $dom_29 = "abukhaledcorp.com" ascii wide nocase
        $dom_30 = "updatwhats1mns0.webcindario.com" ascii wide nocase
        $dom_31 = "www.lyx.org" ascii wide nocase
        $dom_32 = "icagenda.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}