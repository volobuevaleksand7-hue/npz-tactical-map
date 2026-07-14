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
    var b = strip ? strip.getBoundingClientRect().bottom : 0;
    if (b > 0) { banner.style.top = Math.round(b) + 6 + "px"; return true; }
    return false; // .app ещё под бут-экраном (display:none) → rect нулевой, ретраим
  }
  function tryPlace(n) { if (place() || n <= 0) return; requestAnimationFrame(function () { tryPlace(n - 1); }); }

  banner.hidden = false;
  document.body.classList.add("has-alert");
  tryPlace(300);
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
