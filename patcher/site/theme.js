// 밝음/어두움 고르기(마스터 10-06) — 시스템 → 밝게 → 어둡게 순으로 돈다. 고른 값은 이 브라우저에만 남는다.
// 문서 맨 앞에서 바로 돌려 html 에 data-theme 을 박는다(그려지기 전에 — 번쩍임 방지). 단추는 머리 띠에 붙인다.
(function () {
  "use strict";
  var KEY = "ed-theme", root = document.documentElement, mode = "system";
  try { mode = localStorage.getItem(KEY) || "system"; } catch (e) { /* 저장소가 막힌 창 */ }
  var apply = function () {
    if (mode === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", mode);
  };
  apply();
  var LABEL = { system: "◐ 시스템", light: "☀ 밝게", dark: "☾ 어둡게" }, NEXT = { system: "light", light: "dark", dark: "system" };
  document.addEventListener("DOMContentLoaded", function () {
    var host = document.querySelector(".band .wrap");
    if (!host) return;
    var b = document.createElement("button");
    b.type = "button"; b.className = "theme-toggle";
    var sync = function () { b.textContent = LABEL[mode]; b.setAttribute("aria-label", "화면 테마: " + LABEL[mode].slice(2) + " — 눌러서 바꾸기"); };
    sync();
    b.addEventListener("click", function () {
      mode = NEXT[mode]; apply(); sync();
      try { localStorage.setItem(KEY, mode); } catch (e) { /* 무시 */ }
    });
    host.appendChild(b);
  });
})();
