rule CDB_SENTINEL_Network_Intel_000aae8e5977
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-24"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "000aae8e5977"
        ioc_count = 57

    strings:
        $ip_0 = "1.8.5.5" ascii wide nocase
        $ip_1 = "1.0.0.1" ascii wide nocase
        $ip_2 = "2.6.0.1" ascii wide nocase
        $ip_3 = "11.2.25.0" ascii wide nocase
        $ip_4 = "21.8.1.0" ascii wide nocase
        $ip_5 = "14.1.2.0" ascii wide nocase
        $ip_6 = "12.2.1.19" ascii wide nocase
        $dom_7 = "www.gttyour-robloxrbx.blogspot.com" ascii wide nocase
        $dom_8 = "shopee0488.blogspot.com" ascii wide nocase
        $dom_9 = "waves-whatapp.hl.cn" ascii wide nocase
        $dom_10 = "dialogue-whatapp.com.cn" ascii wide nocase
        $dom_11 = "pehsad.com" ascii wide nocase
        $dom_12 = "www.roblox.com" ascii wide nocase
        $dom_13 = "www.roblox.com.ml" ascii wide nocase
        $dom_14 = "h5.ring-whatapp.com.cn" ascii wide nocase
        $dom_15 = "17534.xyz" ascii wide nocase
        $dom_16 = "www.17575.xyz" ascii wide nocase
        $dom_17 = "www.17556.xyz" ascii wide nocase
        $dom_18 = "www.17557.xyz" ascii wide nocase
        $dom_19 = "www.17552.xyz" ascii wide nocase
        $dom_20 = "www.17558.xyz" ascii wide nocase
        $dom_21 = "ronitkp06-proj.github.io" ascii wide nocase
        $dom_22 = "www.infoundianshopee40.blogspot.com" ascii wide nocase
        $dom_23 = "cipher.rosakyiv.com" ascii wide nocase
        $dom_24 = "d30sec8k5ond2x.cloudfront.net" ascii wide nocase
        $dom_25 = "lisadrosss-lang.github.io" ascii wide nocase
        $dom_26 = "maps-icloud.com" ascii wide nocase
        $dom_27 = "www.robIox.com" ascii wide nocase
        $dom_28 = "rbcode.net" ascii wide nocase
        $dom_29 = "gitweb.gentoo.org" ascii wide nocase
        $dom_30 = "acrobatreaderonline.com" ascii wide nocase
        $dom_31 = "resi.com" ascii wide nocase
        $dom_32 = "metacpan.org" ascii wide nocase
        $dom_33 = "8788.site" ascii wide nocase
        $dom_34 = "www.instagram-login-authentication.duckdns.org" ascii wide nocase
        $dom_35 = "www.shopeejkt4782.blogspot.com" ascii wide nocase
        $dom_36 = "trustwalletmycard.com" ascii wide nocase
        $dom_37 = "www.shopifyweins.com" ascii wide nocase
        $dom_38 = "www.shopifybeltd.com" ascii wide nocase
        $dom_39 = "www.policy-violation-center.com" ascii wide nocase
        $dom_40 = "infoundianshopee37.blogspot.com" ascii wide nocase
        $dom_41 = "trezorsuitev2.com" ascii wide nocase
        $dom_42 = "shopeejkt717.blogspot.com" ascii wide nocase
        $dom_43 = "site-3da5qr19c.godaddysites.com" ascii wide nocase
        $dom_44 = "infohadiahshopee2.blogspot.com" ascii wide nocase
        $dom_45 = "infoundianshopee55.blogspot.com" ascii wide nocase
        $dom_46 = "shopee-282.blogspot.com" ascii wide nocase
        $dom_47 = "pemenangshopee13.blogspot.com" ascii wide nocase
        $dom_48 = "galery-shopee77.blogspot.com" ascii wide nocase
        $dom_49 = "www.pemenang67.blogspot.com" ascii wide nocase
        $dom_50 = "www.click" ascii wide nocase
        $dom_51 = "www.pestashopee-47.blogspot.com" ascii wide nocase
        $dom_52 = "www.facebook-247-support.blogspot.com" ascii wide nocase
        $dom_53 = "wasil-se.github.io" ascii wide nocase
        $dom_54 = "compendiumusa.net" ascii wide nocase
        $dom_55 = "j2commerce.com" ascii wide nocase
        $dom_56 = "yootheme.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}