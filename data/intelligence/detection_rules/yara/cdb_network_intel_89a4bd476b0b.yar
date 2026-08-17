rule CDB_SENTINEL_Network_Intel_89a4bd476b0b
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-17"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "89a4bd476b0b"
        ioc_count = 46

    strings:
        $ip_0 = "1.1.2.0" ascii wide nocase
        $ip_1 = "1.1.9.13" ascii wide nocase
        $ip_2 = "17.0.0.3" ascii wide nocase
        $ip_3 = "26.0.0.8" ascii wide nocase
        $ip_4 = "5.2.3.0" ascii wide nocase
        $ip_5 = "5.2.3.8" ascii wide nocase
        $ip_6 = "6.0.0.0" ascii wide nocase
        $ip_7 = "6.0.1.0" ascii wide nocase
        $dom_8 = "www.roblox.com" ascii wide nocase
        $dom_9 = "rbcode.net" ascii wide nocase
        $dom_10 = "open.apknewdownload.info" ascii wide nocase
        $dom_11 = "link.curiosityproject.info" ascii wide nocase
        $dom_12 = "www.robiox.com" ascii wide nocase
        $dom_13 = "request-imap.za.com" ascii wide nocase
        $dom_14 = "a3b9c26.com" ascii wide nocase
        $dom_15 = "sasw-avhdbzawd0e4gjev.z03.azurefd.net" ascii wide nocase
        $dom_16 = "soporteishopreclamacion.com" ascii wide nocase
        $dom_17 = "misoporte-ishopmxonline.com" ascii wide nocase
        $dom_18 = "misoporteishopmx.com" ascii wide nocase
        $dom_19 = "appleishop-online.com" ascii wide nocase
        $dom_20 = "ishop-mixupmx-online.com" ascii wide nocase
        $dom_21 = "arosh2004.github.io" ascii wide nocase
        $dom_22 = "online-recuperacionishop.com" ascii wide nocase
        $dom_23 = "mireporteapplemx.com" ascii wide nocase
        $dom_24 = "online-ishopoficial.com" ascii wide nocase
        $dom_25 = "misoporte-online-mixupmx.com" ascii wide nocase
        $dom_26 = "misoporteonline-reportesmx.com" ascii wide nocase
        $dom_27 = "ishopmirecuperacion.com" ascii wide nocase
        $dom_28 = "ishopmireportemx.com" ascii wide nocase
        $dom_29 = "mireporteishop-mx.com" ascii wide nocase
        $dom_30 = "adarshkishore007.github.io" ascii wide nocase
        $dom_31 = "ishopstoreoficial.com" ascii wide nocase
        $dom_32 = "reclamacionmacstore.com" ascii wide nocase
        $dom_33 = "reclamacionapple.com" ascii wide nocase
        $dom_34 = "onlineishop-misoporte.com" ascii wide nocase
        $dom_35 = "misoporteonline-ishopmixupmx.com" ascii wide nocase
        $dom_36 = "misoporteonline-macstoremx.com" ascii wide nocase
        $dom_37 = "misoporte-mixupmx.com" ascii wide nocase
        $dom_38 = "online-macstoremexico.com" ascii wide nocase
        $dom_39 = "guptadisha1107-png.github.io" ascii wide nocase
        $dom_40 = "reclamacionesapple.com" ascii wide nocase
        $dom_41 = "ishopmixup-recuperaciomx.com" ascii wide nocase
        $dom_42 = "a3b9c2s1.com" ascii wide nocase
        $dom_43 = "vanitasikhwal-214.github.io" ascii wide nocase
        $dom_44 = "metacpan.org" ascii wide nocase
        $dom_45 = "Draw.io" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}