rule CDB_SENTINEL_Network_Intel_96edb092a8de
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-24"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "96edb092a8de"
        ioc_count = 32

    strings:
        $ip_0 = "11.2.25.0" ascii wide nocase
        $ip_1 = "21.8.1.0" ascii wide nocase
        $ip_2 = "14.1.2.0" ascii wide nocase
        $ip_3 = "12.2.1.19" ascii wide nocase
        $ip_4 = "1.8.5.5" ascii wide nocase
        $ip_5 = "1.0.0.1" ascii wide nocase
        $ip_6 = "2.6.0.1" ascii wide nocase
        $dom_7 = "metacpan.org" ascii wide nocase
        $dom_8 = "8788.site" ascii wide nocase
        $dom_9 = "www.instagram-login-authentication.duckdns.org" ascii wide nocase
        $dom_10 = "www.shopeejkt4782.blogspot.com" ascii wide nocase
        $dom_11 = "trustwalletmycard.com" ascii wide nocase
        $dom_12 = "www.shopifyweins.com" ascii wide nocase
        $dom_13 = "www.shopifybeltd.com" ascii wide nocase
        $dom_14 = "www.policy-violation-center.com" ascii wide nocase
        $dom_15 = "infoundianshopee37.blogspot.com" ascii wide nocase
        $dom_16 = "trezorsuitev2.com" ascii wide nocase
        $dom_17 = "shopeejkt717.blogspot.com" ascii wide nocase
        $dom_18 = "site-3da5qr19c.godaddysites.com" ascii wide nocase
        $dom_19 = "infohadiahshopee2.blogspot.com" ascii wide nocase
        $dom_20 = "infoundianshopee55.blogspot.com" ascii wide nocase
        $dom_21 = "shopee-282.blogspot.com" ascii wide nocase
        $dom_22 = "pemenangshopee13.blogspot.com" ascii wide nocase
        $dom_23 = "galery-shopee77.blogspot.com" ascii wide nocase
        $dom_24 = "www.pemenang67.blogspot.com" ascii wide nocase
        $dom_25 = "www.click" ascii wide nocase
        $dom_26 = "www.pestashopee-47.blogspot.com" ascii wide nocase
        $dom_27 = "www.facebook-247-support.blogspot.com" ascii wide nocase
        $dom_28 = "wasil-se.github.io" ascii wide nocase
        $dom_29 = "compendiumusa.net" ascii wide nocase
        $dom_30 = "j2commerce.com" ascii wide nocase
        $dom_31 = "yootheme.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}