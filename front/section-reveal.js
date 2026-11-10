/* First-visit chapter reveals. Base content stays visible before any enhancement. */
(() => {
  const motion = window.matchMedia("(prefers-reduced-motion: no-preference)");
  if (!motion.matches || !("IntersectionObserver" in window)) return;

  const trace = document.createElement("span");
  trace.className = "swarm-trace";
  trace.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    trace.append(document.createElement("span"));
  }

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const target = entry.target;
      observer.unobserve(target);
      if (!motion.matches) continue;

      if (target.hasAttribute("data-swarm-heading")) {
        target.append(trace.cloneNode(true));
        target.classList.add("swarm-heading-enter");
      } else {
        target.classList.add("swarm-content-enter");
      }
    }
  });

  // Leave the initial viewport and any content above a restored scroll position alone.
  document.querySelectorAll("[data-swarm-heading], [data-swarm-content]").forEach((target) => {
    if (target.getBoundingClientRect().top >= window.innerHeight) observer.observe(target);
  });
})();
