rule CDB_SENTINEL_Network_Intel_5be5c80b61ca
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-20"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "5be5c80b61ca"
        ioc_count = 35

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $ip_1 = "169.254.169.254" ascii wide nocase
        $dom_2 = "book.hacktricks.xyz" ascii wide nocase
        $dom_3 = "metacpan.org" ascii wide nocase
        $dom_4 = "facebologin.blogspot.com" ascii wide nocase
        $dom_5 = "staking4portfolio.blogspot.com" ascii wide nocase
        $dom_6 = "www.staking2portfolio.blogspot.com" ascii wide nocase
        $dom_7 = "134634.xyz" ascii wide nocase
        $dom_8 = "573455.xyz" ascii wide nocase
        $dom_9 = "536346.xyz" ascii wide nocase
        $dom_10 = "xfinityaccount-upgrade.weebly.com" ascii wide nocase
        $dom_11 = "mfacebookloginn.blogspot.com" ascii wide nocase
        $dom_12 = "sabamahveen.github.io" ascii wide nocase
        $dom_13 = "seveice.h5-whatsapp-zn.hl.cn" ascii wide nocase
        $dom_14 = "anangavanged.blogspot.com" ascii wide nocase
        $dom_15 = "sso.mail.ionosdirectco.com" ascii wide nocase
        $dom_16 = "gui.ionosdirectco.com" ascii wide nocase
        $dom_17 = "post-manifacture-desanpliation.com" ascii wide nocase
        $dom_18 = "bancolombia2026.webcindario.com" ascii wide nocase
        $dom_19 = "www.whhaattss.blogspot.com" ascii wide nocase
        $dom_20 = "www.xfinity332.weebly.com" ascii wide nocase
        $dom_21 = "www.xfinity323.weebly.com" ascii wide nocase
        $dom_22 = "www.site-lg94gcvdd.godaddysites.com" ascii wide nocase
        $dom_23 = "meher-fund.org" ascii wide nocase
        $dom_24 = "hongtintuc999-vn.github.io" ascii wide nocase
        $dom_25 = "pt-shopee4477.blogspot.com" ascii wide nocase
        $dom_26 = "Hunt.io" ascii wide nocase
        $dom_27 = "automotoresrosedal.com" ascii wide nocase
        $dom_28 = "www.hsi.info" ascii wide nocase
        $dom_29 = "arm.com" ascii wide nocase
        $dom_30 = "linuxtesting.org" ascii wide nocase
        $dom_31 = "40google.com" ascii wide nocase
        $dom_32 = "lore.kernel.org" ascii wide nocase
        $dom_33 = "smtp.kernel.org" ascii wide nocase
        $dom_34 = "gmail.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}