rule CDB_SENTINEL_Network_Intel_d9a0d975a62f
{
    meta:
        author = "CyberDudeBivash SENTINEL APEX v51"
        description = "Detects network IOCs from threat intelligence feeds"
        date = "2026-08-19"
        severity = "high"
        reference = "https://intel.cyberdudebivash.com"
        batch_id = "d9a0d975a62f"
        ioc_count = 57

    strings:
        $ip_0 = "169.254.169.254" ascii wide nocase
        $ip_1 = "6.6.6.6" ascii wide nocase
        $dom_2 = "www.deskthipk.com" ascii wide nocase
        $dom_3 = "llori807.github.io" ascii wide nocase
        $dom_4 = "loginfacebook3.blogspot.com" ascii wide nocase
        $dom_5 = "www.haiws.com" ascii wide nocase
        $dom_6 = "zer2aypv.flvhzvq.com" ascii wide nocase
        $dom_7 = "www.qdsxdfrhsbc607.lhdz2016.com" ascii wide nocase
        $dom_8 = "vientianesaber.za.com" ascii wide nocase
        $dom_9 = "www.xpj66722.com" ascii wide nocase
        $dom_10 = "roblox.com" ascii wide nocase
        $dom_11 = "www.trcdesafe.com" ascii wide nocase
        $dom_12 = "hr-messages.com" ascii wide nocase
        $dom_13 = "www.24175.xyz" ascii wide nocase
        $dom_14 = "rbcode.net" ascii wide nocase
        $dom_15 = "whatsappzoeiras.blogspot.com" ascii wide nocase
        $dom_16 = "events.adobeforbusiness.com" ascii wide nocase
        $dom_17 = "ajustedevantagens.s3.us-east-005.backblazeb2.com" ascii wide nocase
        $dom_18 = "programmer804-web.github.io" ascii wide nocase
        $dom_19 = "shivamjagtap58-cloud.github.io" ascii wide nocase
        $dom_20 = "ritanshu7817.github.io" ascii wide nocase
        $dom_21 = "njj.standard.us-east-1.oortstorages.com" ascii wide nocase
        $dom_22 = "8305bcc9194402c71fb27a21b63c71483792.net" ascii wide nocase
        $dom_23 = "www.robloxc.com" ascii wide nocase
        $dom_24 = "viraj-9.github.io" ascii wide nocase
        $dom_25 = "www.aussieearners.com" ascii wide nocase
        $dom_26 = "www.rs-shop-ph.com" ascii wide nocase
        $dom_27 = "www.viniciusfrancoadvocacia.com" ascii wide nocase
        $dom_28 = "www.itsecurityservicesportal.online" ascii wide nocase
        $dom_29 = "iamnew.powerappsportals.com" ascii wide nocase
        $dom_30 = "www.diomaq.com" ascii wide nocase
        $dom_31 = "www.kohinoormotors.com" ascii wide nocase
        $dom_32 = "grabxx.eu.cc" ascii wide nocase
        $dom_33 = "www.egykey.com" ascii wide nocase
        $dom_34 = "post-manifacture-desanpliation.com" ascii wide nocase
        $dom_35 = "guz-nik.wranh.info" ascii wide nocase
        $dom_36 = "www.rbx4kb.blogspot.com" ascii wide nocase
        $dom_37 = "shopee-id2775.blogspot.com" ascii wide nocase
        $dom_38 = "www.shopee-id2775.blogspot.com" ascii wide nocase
        $dom_39 = "jeliffin.s3.eu-central-3.ionoscloud.com" ascii wide nocase
        $dom_40 = "0bf1eaed1f65f5df07365b728b3bb2a18d89.net" ascii wide nocase
        $dom_41 = "amankhan02007.github.io" ascii wide nocase
        $dom_42 = "rlaonchambry.top" ascii wide nocase
        $dom_43 = "chasejackpot.xyz" ascii wide nocase
        $dom_44 = "the-pro-1391.github.io" ascii wide nocase
        $dom_45 = "ww547.scotiabano.com" ascii wide nocase
        $dom_46 = "siddharthgaikwad-git.github.io" ascii wide nocase
        $dom_47 = "sagarsrivastava5201-code.github.io" ascii wide nocase
        $dom_48 = "varda27.github.io" ascii wide nocase
        $dom_49 = "aidenpiearce.github.io" ascii wide nocase
        $dom_50 = "f005.backblazeb2.com" ascii wide nocase
        $dom_51 = "document-share.exceptionalsonepc.com" ascii wide nocase
        $dom_52 = "socket.io" ascii wide nocase
        $dom_53 = "ssf-int.com" ascii wide nocase
        $dom_54 = "nyklawfirm.com" ascii wide nocase
        $dom_55 = "trendmicro.com" ascii wide nocase
        $dom_56 = "40bytedance.com" ascii wide nocase

    condition:
        filesize < 100MB and any of them
}