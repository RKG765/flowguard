// Applies the saved theme before first paint (no flash). A separate file because the page's Content-Security-Policy
// (script-src 'self') forbids inline scripts. Falls back to the OS preference, then dark.
(function () {
  try {
    var t = localStorage.getItem("fg-theme");
    if (t !== "light" && t !== "dark") t = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
  } catch (e) {
    /* storage blocked: keep the default */
  }
})();
