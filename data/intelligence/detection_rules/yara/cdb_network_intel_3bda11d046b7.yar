rule CDB_SENTINEL_Network_Intel_3bda11d046b7
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-15"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "3bda11d046b7"
        ioc_count = 43

    strings:
        $ip_0 = "2.10.2.2" ascii wide nocase
        $ip_1 = "169.254.169.254" ascii wide nocase
        $ip_2 = "17.0.0.3" ascii wide nocase
        $ip_3 = "26.0.0.8" ascii wide nocase
        $ip_4 = "18.0.79.6" ascii wide nocase
        $ip_5 = "18.0.80.2" ascii wide nocase
        $ip_6 = "1.2.3.44" ascii wide nocase
        $ip_7 = "9.2.09.002" ascii wide nocase
        $ip_8 = "9.2.07.002" ascii wide nocase
        $dom_9 = "layanan-pemenang33.blogspot.com" ascii wide nocase
        $dom_10 = "americasdspkits.com" ascii wide nocase
        $dom_11 = "transcript.emurgopolicyreview.com" ascii wide nocase
        $dom_12 = "www.seguridad-bancol.weebly.com" ascii wide nocase
        $dom_13 = "enelgia.club" ascii wide nocase
        $dom_14 = "emctheatre.com" ascii wide nocase
        $dom_15 = "soporteclave.com" ascii wide nocase
        $dom_16 = "rbcode.net" ascii wide nocase
        $dom_17 = "kjgmhnetuyut.blogspot.com" ascii wide nocase
        $dom_18 = "bafkreiexrtpkkflfywi6lyfj7zc5bw6zrcvv4dib4wbfjrxnkyxuiohdfm.ipfs.dweb.link" ascii wide nocase
        $dom_19 = "bafkreihql7542hbekhfae4355pumneesu37jvm2yqy22hi5wahk5pvyoci.ipfs.dweb.link" ascii wide nocase
        $dom_20 = "anshikamishra6373-blip.github.io" ascii wide nocase
        $dom_21 = "facebook-interface.blogspot.com" ascii wide nocase
        $dom_22 = "gulabahmad-code.github.io" ascii wide nocase
        $dom_23 = "login-verifydocusignauthentication.dannatel.com" ascii wide nocase
        $dom_24 = "matildasbloombox.com" ascii wide nocase
        $dom_25 = "pemenangshopee27.blogspot.com" ascii wide nocase
        $dom_26 = "www.pemenangshopee27.blogspot.com" ascii wide nocase
        $dom_27 = "program-shopee13.blogspot.com" ascii wide nocase
        $dom_28 = "www.program-shopee13.blogspot.com" ascii wide nocase
        $dom_29 = "sucursaivlrtualpersonas.com" ascii wide nocase
        $dom_30 = "docusign-server.github.io" ascii wide nocase
        $dom_31 = "www.roblox.com.ml" ascii wide nocase
        $dom_32 = "guiatotalbrasil.com" ascii wide nocase
        $dom_33 = "seguridad-bancol.weebly.com" ascii wide nocase
        $dom_34 = "site-rtvia0g17.godaddysites.com" ascii wide nocase
        $dom_35 = "variousoffers.xyz" ascii wide nocase
        $dom_36 = "ledger-security-checker.com" ascii wide nocase
        $dom_37 = "Make.com" ascii wide nocase
        $dom_38 = "granjarinya.com" ascii wide nocase
        $dom_39 = "joomshaper.com" ascii wide nocase
        $dom_40 = "Cal.com" ascii wide nocase
        $dom_41 = "tabaoca.org" ascii wide nocase
        $dom_42 = "fabrikar.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}