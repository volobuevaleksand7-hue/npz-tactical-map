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

  // баннер — fixed-оверлей (не сжимает карту). Ставим top по низу строки статуса,
  // чтобы попадал под шапку на любой ширине; body.has-alert опускает фильтр-бар карты.
  function place() {
    var strip = document.querySelector(".status-strip");
    banner.style.top = (strip ? Math.round(strip.getBoundingClientRect().bottom) + 6 : 90) + "px";
  }

  banner.hidden = false;
  document.body.classList.add("has-alert");
  place();
  window.addEventListener("resize", place);

  closeButton.addEventListener("click", function () {
    try {
      localStorage.setItem(storageKey, String(Date.now() + 14 * 24 * 60 * 60 * 1000));
    } catch (error) {}
    banner.hidden = true;
    document.body.classList.remove("has-alert");
    window.removeEventListener("resize", place);
  });
})();
