// ==UserScript==
// @name         Pulse Revive Request
// @namespace    http://tampermonkey.net/
// @version      0.8.9
// @description  Send revive requests to Pulse Discord using verified sessionStorage path
// @authors       Gaskarth, Zible
// @license      MIT
// @match        https://www.torn.com/hospitalview.php*
// @connect      torn-request-receiver-service.onrender.com
// @grant        GM_xmlhttpRequest
// @downloadURL https://update.greasyfork.org/scripts/567628/Pulse%20Revive%20Request.user.js
// @updateURL https://update.greasyfork.org/scripts/567628/Pulse%20Revive%20Request.meta.js
// ==/UserScript==

(function() {
    'use strict';

    const SCRIPT_VERSION = '0.8.9';
    const RELAY_URL = 'RELAY_URL';
    const formatSeconds = (t) =>{
       if (t >= 86400) return `${(t / 86400).toFixed(1)} days`;
        if (t >= 3600) return `${(t / 3600).toFixed(1)} hours`;
        if (t >= 60) return `${(t / 60).toFixed(1)} minutes`;
        return `${Math.round(t)} seconds`;
    };
    const getTornData = () => {
        try {
            const header = JSON.parse(sessionStorage.getItem(`headerData`));
             if (!header) throw new Error("sessionStorage header data not found");
           const userID = header.user?.data?.userID || '';
            const isHospitalized = (header?.user?.state?.status==="hospital")??false;
            const isLoggedIn = (header?.user?.isLoggedIn)??false;
            const isAbroad = (header?.user?.isAbroad || header?.user?.isTravelling)??false;
            //
            const session = JSON.parse(sessionStorage.getItem(`sidebarData${userID}`));
            if (!session) throw new Error("sessionStorage sidebarData$ session data not found");
            //
            const userName = session?.user?.name || 'Unknown';
            //
            const hospitalIcon = session?.statusIcons?.icons?.hospital;
            const hospitalTime = (hospitalIcon?.timerExpiresAt - hospitalIcon?.serverTimestamp) ?? 0;
            const hospitalReason = hospitalIcon?.subtitle ?? 'Unknown';
            //
            const factionIcon = session.statusIcons?.icons?.faction;
            let factionName = factionIcon?.subtitle?.split(' of ').pop() ?? 'Unknown';

            return { userName, userID, factionName , isAbroad, isHospitalized, hospitalTime:hospitalTime? formatSeconds(hospitalTime):'' ,hospitalReason};
        } catch (e) {
            console.error("Pulse Script Error:", e);
            return { userName: 'User', userID: 'Unknown', factionName: 'Unknown',isAbroad:false, isHospitalized:false, hospitalTime: 'Unknown' };
        }
    };

    const info = getTornData();
    console.log(info)
    //
    const btn = document.createElement('button');
    btn.style = `margin: 6px; padding: 4px 8px; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; background: ${info.isHospitalized ? '#b22222' : '#555'}; color: white; transition: 0.3s;`;
    const originalLabel = info.isHospitalized ? `Request a revive from Pulse V${SCRIPT_VERSION}` : `Test request from Pulse: ${SCRIPT_VERSION}`;
    btn.innerText = originalLabel;

    btn.onclick = function() {
        const debug = false;
        const info = getTornData();
        btn.disabled = true;
        btn.innerText = "Request sent...";
        btn.style.background = "#333";

        const payload = {
            script_version: SCRIPT_VERSION,
            title: "🚑 Pulse Revive Request",
            user_name: info.userName || "Unknown",
            user_id: String(info.userID || "Unknown"),
            faction_name: info.factionName || "Unknown",
            is_hospitalized: Boolean(info.isHospitalized),
            hospital_time: info.isHospitalized ? (info.hospitalTime || "Unknown") : null,
            hospital_reason: info.isHospitalized ? (info.hospitalReason || "Unknown") : null,
            location: info.isAbroad ? "Abroad" : "Torn City",
            profile_url: `https://www.torn.com/profiles.php?XID=${info.userID || ""}`,
            timestamp: new Date().toISOString()
        };

        if(!debug) GM_xmlhttpRequest({
            method: "POST",
            url: RELAY_URL,
            data: JSON.stringify(payload),
            headers: { "Content-Type": "application/json" },
            onload: () => console.log(`Pulse: Notification sent (v${SCRIPT_VERSION})`)
        });
        else alert(JSON.stringify( payload));

        setTimeout(() => {
            btn.disabled = false;
            btn.innerText = originalLabel;
            btn.style.background = info.isHospitalized ? (info.isAbroad ?'22b222':'#b22222') : '#555';
        }, 15000);
    };

    setTimeout(() => {
        const header = document.querySelector('.content-title');
        if (header) header.appendChild(btn);
    }, 500);
})();