(function () {
    function getCookie(name) {
        return document.cookie
            .split(";")
            .map(function (part) { return part.trim(); })
            .filter(function (part) { return part.indexOf(name + "=") === 0; })
            .map(function (part) { return decodeURIComponent(part.slice(name.length + 1)); })[0];
    }

    function setCookie(name, value) {
        document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=31536000; samesite=lax";
    }

    function uuid() {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (char) {
            var random = Math.random() * 16 | 0;
            var value = char === "x" ? random : (random & 0x3 | 0x8);
            return value.toString(16);
        });
    }

    function timezoneOffset() {
        var offsetMinutes = -new Date().getTimezoneOffset();
        var sign = offsetMinutes >= 0 ? "+" : "-";
        var absolute = Math.abs(offsetMinutes);
        var hours = String(Math.floor(absolute / 60)).padStart(2, "0");
        var minutes = String(absolute % 60).padStart(2, "0");
        return "UTC" + sign + hours + ":" + minutes;
    }

    function populateFraudContext() {
        var deviceId = getCookie("ledgerhouse_device_id");
        if (!deviceId) {
            deviceId = uuid();
            setCookie("ledgerhouse_device_id", deviceId);
        }
        var screenValue = "width=" + screen.width +
            "&height=" + screen.height +
            "&scaling-factor=" + (window.devicePixelRatio || 1) +
            "&colour-depth=" + screen.colorDepth;
        var windowValue = "width=" + window.innerWidth + "&height=" + window.innerHeight;
        document.querySelectorAll("[data-fraud-context]").forEach(function (form) {
            form.querySelectorAll("[data-fraud-field]").forEach(function (field) {
                if (field.name === "fraud_device_id") field.value = deviceId;
                if (field.name === "fraud_browser_js_user_agent") field.value = navigator.userAgent;
                if (field.name === "fraud_screens") field.value = screenValue;
                if (field.name === "fraud_timezone") field.value = timezoneOffset();
                if (field.name === "fraud_window_size") field.value = windowValue;
            });
        });
    }

    document.addEventListener("DOMContentLoaded", populateFraudContext);
}());
