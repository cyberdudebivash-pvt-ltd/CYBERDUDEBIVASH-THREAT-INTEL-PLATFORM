rule CDB_SENTINEL_Network_Intel_73ebca1e9ae4
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-16"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "73ebca1e9ae4"
        ioc_count = 52

    strings:
        $ip_0 = "1.55.0.2" ascii wide nocase
        $ip_1 = "0.19.3.1" ascii wide nocase
        $ip_2 = "0.1.3.7" ascii wide nocase
        $ip_3 = "1.3.0.1" ascii wide nocase
        $ip_4 = "7.0.2.1" ascii wide nocase
        $ip_5 = "2.7.8.4" ascii wide nocase
        $ip_6 = "5.2.0.0" ascii wide nocase
        $ip_7 = "2.8.8.8" ascii wide nocase
        $ip_8 = "11.0.0.0" ascii wide nocase
        $ip_9 = "11.0.0.1" ascii wide nocase
        $ip_10 = "1.1.2.0" ascii wide nocase
        $ip_11 = "1.1.9.13" ascii wide nocase
        $dom_12 = "crates.io" ascii wide nocase
        $dom_13 = "m.lose-dafa.com" ascii wide nocase
        $dom_14 = "n3b9c37.com" ascii wide nocase
        $dom_15 = "www.netf-reintegration-definition.com" ascii wide nocase
        $dom_16 = "shayan-builds.github.io" ascii wide nocase
        $dom_17 = "pubgm.mobileaccesx-events.com" ascii wide nocase
        $dom_18 = "micr0sft.github.io" ascii wide nocase
        $dom_19 = "vh18414.vh.net" ascii wide nocase
        $dom_20 = "rbcode.net" ascii wide nocase
        $dom_21 = "subscription.companymessagecenter.com" ascii wide nocase
        $dom_22 = "css-ch.blogspot.com" ascii wide nocase
        $dom_23 = "ravichavi.github.io" ascii wide nocase
        $dom_24 = "amanvish90s.github.io" ascii wide nocase
        $dom_25 = "senapatishrestha-ctrl.github.io" ascii wide nocase
        $dom_26 = "www.securitysuite365.com" ascii wide nocase
        $dom_27 = "roblox.com.ml" ascii wide nocase
        $dom_28 = "7dhzrw85gm-cell.github.io" ascii wide nocase
        $dom_29 = "Roblox.com" ascii wide nocase
        $dom_30 = "list-serve.com" ascii wide nocase
        $dom_31 = "sbcglobal-att-signing-786084.webflow.io" ascii wide nocase
        $dom_32 = "a3b9c19.com" ascii wide nocase
        $dom_33 = "365k614.com" ascii wide nocase
        $dom_34 = "www.trezcr-live.com" ascii wide nocase
        $dom_35 = "danazxindo.stripest.biz" ascii wide nocase
        $dom_36 = "shopbalancetrial.top" ascii wide nocase
        $dom_37 = "crisp.call-whatapp.com.cn" ascii wide nocase
        $dom_38 = "www.wellsfargo.com" ascii wide nocase
        $dom_39 = "kraj9370392-alt.github.io" ascii wide nocase
        $dom_40 = "duckroblox.com" ascii wide nocase
        $dom_41 = "dyrews.github.io" ascii wide nocase
        $dom_42 = "dynnhost.com" ascii wide nocase
        $dom_43 = "www.robiox.com" ascii wide nocase
        $dom_44 = "badge-auth.com" ascii wide nocase
        $dom_45 = "mobilehsbccprivateonline.com" ascii wide nocase
        $dom_46 = "www.roblox.com" ascii wide nocase
        $dom_47 = "napervillautohaus.com" ascii wide nocase
        $dom_48 = "www.instagramloginp.blogspot.com" ascii wide nocase
        $dom_49 = "syeda-javeria-naqvi-8.github.io" ascii wide nocase
        $dom_50 = "metacpan.org" ascii wide nocase
        $dom_51 = "evil.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}