rule CDB_SENTINEL_Network_Intel_eb833796b8d5
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-17"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "eb833796b8d5"
        ioc_count = 54

    strings:
        $ip_0 = "15.11.0.6" ascii wide nocase
        $ip_1 = "17.0.5.34" ascii wide nocase
        $ip_2 = "17.0.5.4" ascii wide nocase
        $ip_3 = "0.0.0.0" ascii wide nocase
        $ip_4 = "5.2.3.0" ascii wide nocase
        $ip_5 = "5.2.3.8" ascii wide nocase
        $ip_6 = "6.0.0.0" ascii wide nocase
        $ip_7 = "6.0.1.0" ascii wide nocase
        $ip_8 = "1.1.2.0" ascii wide nocase
        $ip_9 = "1.1.9.13" ascii wide nocase
        $ip_10 = "17.0.0.3" ascii wide nocase
        $ip_11 = "26.0.0.8" ascii wide nocase
        $dom_12 = "xfinitywebmail26.weebly.com" ascii wide nocase
        $dom_13 = "www.roblox.com" ascii wide nocase
        $dom_14 = "bankofamericamailcompte.blogspot.com" ascii wide nocase
        $dom_15 = "rbcode.net" ascii wide nocase
        $dom_16 = "open.apknewdownload.info" ascii wide nocase
        $dom_17 = "link.curiosityproject.info" ascii wide nocase
        $dom_18 = "www.robiox.com" ascii wide nocase
        $dom_19 = "request-imap.za.com" ascii wide nocase
        $dom_20 = "a3b9c26.com" ascii wide nocase
        $dom_21 = "sasw-avhdbzawd0e4gjev.z03.azurefd.net" ascii wide nocase
        $dom_22 = "soporteishopreclamacion.com" ascii wide nocase
        $dom_23 = "misoporte-ishopmxonline.com" ascii wide nocase
        $dom_24 = "misoporteishopmx.com" ascii wide nocase
        $dom_25 = "appleishop-online.com" ascii wide nocase
        $dom_26 = "ishop-mixupmx-online.com" ascii wide nocase
        $dom_27 = "arosh2004.github.io" ascii wide nocase
        $dom_28 = "online-recuperacionishop.com" ascii wide nocase
        $dom_29 = "mireporteapplemx.com" ascii wide nocase
        $dom_30 = "online-ishopoficial.com" ascii wide nocase
        $dom_31 = "misoporte-online-mixupmx.com" ascii wide nocase
        $dom_32 = "misoporteonline-reportesmx.com" ascii wide nocase
        $dom_33 = "ishopmirecuperacion.com" ascii wide nocase
        $dom_34 = "ishopmireportemx.com" ascii wide nocase
        $dom_35 = "mireporteishop-mx.com" ascii wide nocase
        $dom_36 = "adarshkishore007.github.io" ascii wide nocase
        $dom_37 = "ishopstoreoficial.com" ascii wide nocase
        $dom_38 = "reclamacionmacstore.com" ascii wide nocase
        $dom_39 = "reclamacionapple.com" ascii wide nocase
        $dom_40 = "onlineishop-misoporte.com" ascii wide nocase
        $dom_41 = "misoporteonline-ishopmixupmx.com" ascii wide nocase
        $dom_42 = "misoporteonline-macstoremx.com" ascii wide nocase
        $dom_43 = "misoporte-mixupmx.com" ascii wide nocase
        $dom_44 = "online-macstoremexico.com" ascii wide nocase
        $dom_45 = "guptadisha1107-png.github.io" ascii wide nocase
        $dom_46 = "reclamacionesapple.com" ascii wide nocase
        $dom_47 = "ishopmixup-recuperaciomx.com" ascii wide nocase
        $dom_48 = "a3b9c2s1.com" ascii wide nocase
        $dom_49 = "vanitasikhwal-214.github.io" ascii wide nocase
        $dom_50 = "metacpan.org" ascii wide nocase
        $dom_51 = "tecosim.com" ascii wide nocase
        $dom_52 = "go.work" ascii wide nocase
        $dom_53 = "Draw.io" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}