/* Shared progressive display for completed API answers. No secrets in the browser. */
window.DjuaTyping = {
  async write(element, text, onProgress = () => {}) {
    const characters = Array.from(String(text));
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    element.textContent = "";
    element.setAttribute("aria-busy", "true");
    try {
      if (reducedMotion) {
        element.textContent = characters.join("");
        onProgress();
        return;
      }
      const step = Math.max(1, Math.ceil(characters.length / 180));
      for (let index = 0; index < characters.length; index += step) {
        if (!element.isConnected) break;
        element.textContent += characters.slice(index, index + step).join("");
        onProgress();
        await new Promise(resolve => setTimeout(resolve, 20));
      }
    } finally {
      element.removeAttribute("aria-busy");
    }
  }
};
