rule CDB_SENTINEL_Network_Intel_1806eb9112d8
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-21"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "1806eb9112d8"
        ioc_count = 61

    strings:
        $ip_0 = "2.6.0.1" ascii wide nocase
        $ip_1 = "0.0.0.0" ascii wide nocase
        $ip_2 = "16.01.0.6" ascii wide nocase
        $ip_3 = "1.5.0.1" ascii wide nocase
        $ip_4 = "2.2.4.2" ascii wide nocase
        $ip_5 = "9.14.2.8" ascii wide nocase
        $ip_6 = "0.9.1.3" ascii wide nocase
        $ip_7 = "11.5.7.0" ascii wide nocase
        $ip_8 = "4.3.0.1" ascii wide nocase
        $ip_9 = "6.7.4.8" ascii wide nocase
        $ip_10 = "7.20.30.50" ascii wide nocase
        $ip_11 = "1.20.60.50" ascii wide nocase
        $ip_12 = "6.1.5.9" ascii wide nocase
        $dom_13 = "swisborrgloginmain.webflow.io" ascii wide nocase
        $dom_14 = "verifysecurenow.weebly.com" ascii wide nocase
        $dom_15 = "www.roblox.com.ml" ascii wide nocase
        $dom_16 = "steamncomnnunity.ru" ascii wide nocase
        $dom_17 = "telcgram.us.cc" ascii wide nocase
        $dom_18 = "www.0365nn.com" ascii wide nocase
        $dom_19 = "usc1.contabostorage.com" ascii wide nocase
        $dom_20 = "admin.tiktokshopvip.com" ascii wide nocase
        $dom_21 = "picker770.github.io" ascii wide nocase
        $dom_22 = "vinis0usa.github.io" ascii wide nocase
        $dom_23 = "phantomwalletsupport.github.io" ascii wide nocase
        $dom_24 = "adhieswari13-cmyk.github.io" ascii wide nocase
        $dom_25 = "polimova.com" ascii wide nocase
        $dom_26 = "vmi3503792.contaboserver.net" ascii wide nocase
        $dom_27 = "financialcompany-controls.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_28 = "netflx-update.com" ascii wide nocase
        $dom_29 = "www.roblox.com" ascii wide nocase
        $dom_30 = "seuplanosilimitado.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_31 = "br.portalrenovacao.com" ascii wide nocase
        $dom_32 = "ammmaka.top" ascii wide nocase
        $dom_33 = "smraflow.top" ascii wide nocase
        $dom_34 = "tuamigo.tubanruralportaleswebsgt.click" ascii wide nocase
        $dom_35 = "www.bybiksn.com" ascii wide nocase
        $dom_36 = "cembra.ch-0826.com" ascii wide nocase
        $dom_37 = "office365-reactivation-email0.iceiy.com" ascii wide nocase
        $dom_38 = "videoserviceprime.com" ascii wide nocase
        $dom_39 = "lppm-kim.com" ascii wide nocase
        $dom_40 = "at.iasaoj.com" ascii wide nocase
        $dom_41 = "24155.xyz" ascii wide nocase
        $dom_42 = "crates.io" ascii wide nocase
        $dom_43 = "metacpan.org" ascii wide nocase
        $dom_44 = "docs.wagtail.org" ascii wide nocase
        $dom_45 = "wagtail.org" ascii wide nocase
        $dom_46 = "wintercms.com" ascii wide nocase
        $dom_47 = "www.cve.org" ascii wide nocase
        $dom_48 = "www.agingenieria.com" ascii wide nocase
        $dom_49 = "www.made-in-china.com" ascii wide nocase
        $dom_50 = "dccrsorgia.github.io" ascii wide nocase
        $dom_51 = "aidenpiearce.github.io" ascii wide nocase
        $dom_52 = "valli-18.github.io" ascii wide nocase
        $dom_53 = "www.14025.xyz" ascii wide nocase
        $dom_54 = "fairtrade.com" ascii wide nocase
        $dom_55 = "www.14088.xyz" ascii wide nocase
        $dom_56 = "m4nfdw.top" ascii wide nocase
        $dom_57 = "em6gto.top" ascii wide nocase
        $dom_58 = "go.opentelemetry.io" ascii wide nocase
        $dom_59 = "usbank.com" ascii wide nocase
        $dom_60 = "regularlabs.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}