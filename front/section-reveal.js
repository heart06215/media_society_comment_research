/* Local, dependency-free cursor choreography for the competition homepage. */
(() => {
  const motion = window.matchMedia("(prefers-reduced-motion: no-preference)");
  if (!motion.matches || !("IntersectionObserver" in window)) return;

  const compact = window.matchMedia("(max-width: 767px)");
  const overlay = document.createElement("div");
  overlay.className = "swarm-overlay";
  overlay.setAttribute("aria-hidden", "true");
  document.body.append(overlay);

  const cursor = document.createElement("span");
  cursor.className = "swarm-pointer";
  cursor.innerHTML = '<svg viewBox="0 0 28 32"><path d="M3 2 24 19 14 20 10 29Z"/></svg>';
  const colors = ["blue", "pink", "cyan", "yellow"];
  const tasks = new Set();
  const entering = new Map();
  let frame = 0;
  let colorIndex = 0;

  /** @param {HTMLElement} element @returns {void} */
  function finish(element) {
    element.classList.remove("swarm-build");
    element.style.removeProperty("--swarm-progress");
    element.style.removeProperty("--swarm-remainder");
    entering.delete(element);
  }

  /** @returns {void} */
  function clear() {
    cancelAnimationFrame(frame);
    frame = 0;
    tasks.clear();
    overlay.replaceChildren();
    for (const element of entering.keys()) finish(element);
  }

  /** @param {object} task @returns {void} */
  function removeTask(task) {
    task.outline.remove();
    task.pointers.forEach((pointer) => pointer.remove());
    tasks.delete(task);
  }

  /** @param {number} time @param {number} start @returns {number} */
  function progressAt(time, start) {
    const elapsed = Math.max(0, Math.min((time - start) / 620, 1));
    return 1 - Math.pow(1 - elapsed, 3);
  }

  /** @param {number} time @returns {void} */
  function draw(time) {
    for (const [element, start] of entering) {
      const progress = progressAt(time, start);
      element.style.setProperty("--swarm-progress", String(progress));
      element.style.setProperty("--swarm-remainder", ((1 - progress) * 100) + "%");
      if (progress === 1) finish(element);
    }
    for (const task of tasks) {
      const elapsed = time - task.start;
      if (elapsed < 0) continue;
      const rect = task.element.getBoundingClientRect();
      if (elapsed > 1120 || rect.bottom < 68 || rect.top > window.innerHeight) {
        removeTask(task);
        continue;
      }

      const progress = progressAt(time, task.start);
      const arrival = Math.min(elapsed / 220, 1);
      const opacity = Math.min(elapsed / 100, 1) * Math.min((1120 - elapsed) / 180, 1);
      const drift = Math.sin(elapsed / 130) * 4;
      task.outline.style.transform = `translate3d(${rect.left}px, ${rect.top}px, 0) scale(${progress})`;
      task.outline.style.opacity = String(opacity);
      task.pointers.forEach((pointer, index) => {
        const corner = task.pointers.length === 1 ? 1 : index;
        const direction = corner * 2 - 1;
        const x = rect.left + rect.width * progress * corner + direction * (32 * (1 - arrival) + drift);
        const y = rect.top + rect.height * progress * corner - 24 * (1 - arrival) + drift * direction;
        pointer.style.transform = `translate3d(${x}px, ${y}px, 0) rotate(${drift * direction}deg)`;
        pointer.style.opacity = String(opacity);
      });
    }
    frame = tasks.size || entering.size ? requestAnimationFrame(draw) : 0;
  }

  /** @param {HTMLElement} element @param {number} delay @returns {void} */
  function reveal(element, delay) {
    if (element.contains(document.activeElement)) return;
    const start = performance.now() + delay;
    element.classList.add("swarm-build");
    entering.set(element, start);
    if (!frame) frame = requestAnimationFrame(draw);
    if (tasks.size >= (compact.matches ? 2 : 3)) return;

    const rect = element.getBoundingClientRect();
    const outline = document.createElement("span");
    outline.className = "swarm-outline";
    outline.style.width = `${rect.width}px`;
    outline.style.height = `${rect.height}px`;
    const color = `var(--${colors[colorIndex % colors.length]})`;
    colorIndex += 1;
    outline.style.setProperty("--swarm-color", color);
    const pointers = Array.from({ length: compact.matches ? 1 : 2 }, () => {
      const pointer = cursor.cloneNode(true);
      pointer.style.setProperty("--swarm-color", color);
      return pointer;
    });
    overlay.append(outline, ...pointers);
    tasks.add({ element, outline, pointers, start });
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, index) => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      if (motion.matches && !document.hidden) reveal(entry.target, (index % 3) * 60);
    });
  });

  // Observe individual pieces so tall chapters reveal as the reader reaches them.
  const targets = document.querySelectorAll([
    "[data-swarm-heading] h2",
    "[data-swarm-content] > *",
    ".ambiguity-mechanisms > article",
    ".talent-levels > article",
    ".legal-grounding > div",
    ".rule-gaps > article",
    ".model-learning-path > article",
    ".impact-cost-comparison > article",
    ".innovation-points > div",
    ".assistant-panel"
  ].join(","));
  targets.forEach((target) => {
    if (target.getBoundingClientRect().top >= window.innerHeight) observer.observe(target);
  });
  // Interaction immediately restores the full content and its focus outline.
  document.addEventListener("pointerdown", clear, { passive: true });
  document.addEventListener("focusin", clear);
  window.addEventListener("resize", clear, { passive: true });
  window.addEventListener("beforeprint", clear);
  document.addEventListener("visibilitychange", () => { if (document.hidden) clear(); });
  motion.addEventListener("change", () => { if (!motion.matches) clear(); });
})();
