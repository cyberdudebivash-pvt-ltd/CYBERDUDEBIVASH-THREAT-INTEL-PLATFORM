rule CDB_SENTINEL_Network_Intel_4b420ec2c8a2
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-20"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "4b420ec2c8a2"
        ioc_count = 62

    strings:
        $ip_0 = "0.0.0.0" ascii wide nocase
        $ip_1 = "169.254.169.254" ascii wide nocase
        $ip_2 = "1.55.0.2" ascii wide nocase
        $ip_3 = "1.6.12.10" ascii wide nocase
        $ip_4 = "3.3.5.4" ascii wide nocase
        $dom_5 = "www.openwall.com" ascii wide nocase
        $dom_6 = "eshelyaron.com" ascii wide nocase
        $dom_7 = "lists.gnu.org" ascii wide nocase
        $dom_8 = "netcoooins-logi.webflow.io" ascii wide nocase
        $dom_9 = "2de1886ed1cab04908e53d937d7dffd68a87.net" ascii wide nocase
        $dom_10 = "flexibilidadeaseulimite.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_11 = "servicioenlineabdv.github.io" ascii wide nocase
        $dom_12 = "www.robloxc.com" ascii wide nocase
        $dom_13 = "situs-undian22.blogspot.com" ascii wide nocase
        $dom_14 = "www.situs-undian22.blogspot.com" ascii wide nocase
        $dom_15 = "www.roblox.com" ascii wide nocase
        $dom_16 = "shrimp-18.github.io" ascii wide nocase
        $dom_17 = "jerome1209op-crypto.github.io" ascii wide nocase
        $dom_18 = "jamesxxsu.github.io" ascii wide nocase
        $dom_19 = "dearestanton.github.io" ascii wide nocase
        $dom_20 = "qrcodeveloper.com" ascii wide nocase
        $dom_21 = "zsori.com" ascii wide nocase
        $dom_22 = "2daa26c334b2a314f5e25af54910d7d3b990.org" ascii wide nocase
        $dom_23 = "decameronaquarium.hoteltodoincluido.org" ascii wide nocase
        $dom_24 = "flexibilidadeadequada.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_25 = "reavaliacaodeperfil.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_26 = "metacpan.org" ascii wide nocase
        $dom_27 = "webkitgtk.org" ascii wide nocase
        $dom_28 = "book.hacktricks.xyz" ascii wide nocase
        $dom_29 = "facebologin.blogspot.com" ascii wide nocase
        $dom_30 = "staking4portfolio.blogspot.com" ascii wide nocase
        $dom_31 = "www.staking2portfolio.blogspot.com" ascii wide nocase
        $dom_32 = "134634.xyz" ascii wide nocase
        $dom_33 = "573455.xyz" ascii wide nocase
        $dom_34 = "536346.xyz" ascii wide nocase
        $dom_35 = "xfinityaccount-upgrade.weebly.com" ascii wide nocase
        $dom_36 = "mfacebookloginn.blogspot.com" ascii wide nocase
        $dom_37 = "sabamahveen.github.io" ascii wide nocase
        $dom_38 = "seveice.h5-whatsapp-zn.hl.cn" ascii wide nocase
        $dom_39 = "anangavanged.blogspot.com" ascii wide nocase
        $dom_40 = "sso.mail.ionosdirectco.com" ascii wide nocase
        $dom_41 = "gui.ionosdirectco.com" ascii wide nocase
        $dom_42 = "post-manifacture-desanpliation.com" ascii wide nocase
        $dom_43 = "bancolombia2026.webcindario.com" ascii wide nocase
        $dom_44 = "www.whhaattss.blogspot.com" ascii wide nocase
        $dom_45 = "www.xfinity332.weebly.com" ascii wide nocase
        $dom_46 = "www.xfinity323.weebly.com" ascii wide nocase
        $dom_47 = "www.site-lg94gcvdd.godaddysites.com" ascii wide nocase
        $dom_48 = "meher-fund.org" ascii wide nocase
        $dom_49 = "hongtintuc999-vn.github.io" ascii wide nocase
        $dom_50 = "pt-shopee4477.blogspot.com" ascii wide nocase
        $dom_51 = "Hunt.io" ascii wide nocase
        $dom_52 = "automotoresrosedal.com" ascii wide nocase
        $dom_53 = "www.hsi.info" ascii wide nocase
        $dom_54 = "linux.ibm.com" ascii wide nocase
        $dom_55 = "xbow.com" ascii wide nocase
        $dom_56 = "arm.com" ascii wide nocase
        $dom_57 = "linuxtesting.org" ascii wide nocase
        $dom_58 = "40google.com" ascii wide nocase
        $dom_59 = "lore.kernel.org" ascii wide nocase
        $dom_60 = "smtp.kernel.org" ascii wide nocase
        $dom_61 = "gmail.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}