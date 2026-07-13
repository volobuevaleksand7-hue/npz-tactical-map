(function () {
  "use strict";

  var banner = document.getElementById("subscriptionAlert");
  var closeButton = document.getElementById("subscriptionAlertClose");
  var storageKey = "subscription_alert_hidden_until";
  var hiddenUntil = 0;

  if (!banner || !closeButton) return;

  try {
    hiddenUntil = Number(localStorage.getItem(storageKey) || 0);
  } catch (error) {}

  if (hiddenUntil > Date.now()) return;

  banner.hidden = false;
  closeButton.addEventListener("click", function () {
    try {
      localStorage.setItem(storageKey, String(Date.now() + 14 * 24 * 60 * 60 * 1000));
    } catch (error) {}
    banner.hidden = true;
  });
})();
