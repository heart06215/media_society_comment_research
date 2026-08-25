/* 破妄 · 主题切换(日/夜) —— 需在<head>最早引入，避免闪屏 */
(function () {
  var KEY = "powang-theme";
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  var theme = saved === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);

  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: t } }));
  }

  window.ThemeKit = {
    current: function () { return document.documentElement.getAttribute("data-theme"); },
    toggle: function () { apply(this.current() === "dark" ? "light" : "dark"); },
    chartColors: function () {
      var cs = getComputedStyle(document.documentElement);
      function v(n) { return cs.getPropertyValue(n).trim(); }
      return {
        ink: v("--ink"), paper: v("--paper"), surface: v("--surface"),
        muted: v("--muted"), grid: v("--grid"), line: v("--line"),
        blue: v("--blue"), cyan: v("--cyan"), violet: v("--violet"),
        pink: v("--pink"), yellow: v("--yellow"),
        praise: v("--cat-praise"), blame: v("--cat-blame"),
        shui: v("--cat-shui"), noise: v("--cat-noise")
      };
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () { window.ThemeKit.toggle(); });
    });
  });
})();