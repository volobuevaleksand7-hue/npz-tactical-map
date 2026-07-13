#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "$0")/.." && pwd)
index_file="$root_dir/index.html"
style_file="$root_dir/styles.css"
script_file="$root_dir/subscription-alert.js"

grep -q 'id="subscriptionAlert"' "$index_file"
grep -q 'class="subscription-alert-tag"' "$index_file"
grep -q 'class="subscription-alert-warning">Сайт подвергается атакам\.' "$index_file"
grep -q 'class="subscription-alert-sub">Сохраните резервную ссылку в Telegram\.' "$index_file"
grep -q 'href="https://t.me/bplalarm"' "$index_file"
grep -q 'Сохранить доступ' "$index_file"
grep -q 'id="subscriptionAlertClose"' "$index_file"
grep -q '/subscription-alert.js' "$index_file"
if grep -q '/sub-nudge.js' "$index_file"; then
  echo "The retired subscription popup must not load beside the alert banner" >&2
  exit 1
fi

grep -q '\.subscription-alert' "$style_file"
grep -q 'max-width:800px' "$style_file"
grep -q 'position:absolute;top:calc(84px + env(safe-area-inset-top))' "$style_file"
grep -q 'background:rgba(255,255,255,.96)' "$style_file"
grep -q '\.subscription-alert-warning' "$style_file"
grep -q '@media(max-width:700px)' "$style_file"
grep -q 'subscription-alert-cta-short' "$style_file"
grep -q 'subscriptionAlertPulse' "$style_file"
grep -q 'prefers-reduced-motion:reduce' "$style_file"

grep -q 'subscription_alert_hidden_until' "$script_file"
grep -q '14 \* 24 \* 60 \* 60 \* 1000' "$script_file"
grep -q 'banner.hidden = true' "$script_file"

node - "$script_file" <<'NODE'
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[2], "utf8");
const now = 1_000_000;

function run(hiddenUntil) {
  const banner = { hidden: true };
  let closeHandler;
  let storedValue;
  const closeButton = {
    addEventListener(eventName, handler) {
      if (eventName === "click") closeHandler = handler;
    },
  };
  vm.runInNewContext(source, {
    Date: { now: () => now },
    document: {
      getElementById(id) {
        return id === "subscriptionAlert" ? banner : closeButton;
      },
    },
    localStorage: {
      getItem: () => hiddenUntil == null ? null : String(hiddenUntil),
      setItem(key, value) { storedValue = { key, value }; },
    },
  });
  return { banner, closeHandler, storedValue: () => storedValue };
}

const visible = run(null);
if (visible.banner.hidden || typeof visible.closeHandler !== "function") throw new Error("Banner should show and wire its close action");
visible.closeHandler();
if (!visible.banner.hidden) throw new Error("Close action should hide the banner");
if (visible.storedValue().key !== "subscription_alert_hidden_until") throw new Error("Close action should persist its state");
if (Number(visible.storedValue().value) !== now + 14 * 24 * 60 * 60 * 1000) throw new Error("Dismissal should last 14 days");

const dismissed = run(now + 1);
if (!dismissed.banner.hidden || dismissed.closeHandler) throw new Error("Dismissed banner should stay hidden");
NODE

echo "subscription alert checks passed"
