/* Shared API boundary. One attempt per user action; errors never become data. */
(function (root) {
  class ApiError extends Error {
    constructor(message, status = 0, code = "API_ERROR") {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
    }
  }

  function baseUrl() {
    const configured = root.DJUA_API_BASE_URL || root.document?.querySelector('meta[name="djua-api-base-url"]')?.content || root.location.origin;
    let url;
    try { url = new URL(configured); } catch { throw new ApiError("Configuration de l'URL API invalide.", 0, "API_CONFIGURATION_ERROR"); }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new ApiError("Configuration de l'URL API invalide.", 0, "API_CONFIGURATION_ERROR");
    }
    return url.href.replace(/\/$/, "");
  }

  async function request(path, { method = "GET", body, timeoutMs = 60000 } = {}) {
    if (!path.startsWith("/") || path.startsWith("//")) throw new ApiError("Chemin API invalide.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await root.fetch(baseUrl() + path, {
        method, headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal
      });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { /* Render can return HTML errors. */ }
      if (!response.ok) {
        const message = typeof data?.error?.message === "string" ? data.error.message
          : typeof data?.detail === "string" ? data.detail
          : response.status === 401 ? "Authentification refusee par le backend."
          : response.status === 503 ? "Backend temporairement indisponible. Reessayez manuellement."
          : `Erreur API HTTP ${response.status}.`;
        throw new ApiError(message, response.status, data?.error?.code || "HTTP_ERROR");
      }
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        throw new ApiError("Reponse JSON du serveur absente ou invalide.", response.status, "INVALID_RESPONSE");
      }
      if (data.ok === false) throw new ApiError(data.error?.message || "La requete a echoue.", response.status, data.error?.code);
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error?.name === "AbortError") throw new ApiError("Le serveur met trop de temps a repondre.", 0, "API_TIMEOUT");
      throw new ApiError("Connexion au backend impossible. Verifiez son URL et la configuration CORS.", 0, "API_NETWORK_ERROR");
    } finally {
      clearTimeout(timer);
    }
  }

  function requireAnswer(data, fields = ["answer"]) {
    if (!data || typeof data !== "object" || !fields.some(key => typeof data[key] === "string" && data[key].trim())) {
      throw new ApiError("Le serveur n'a pas renvoye de reponse de chat valide.", 200, "INVALID_CHAT_RESPONSE");
    }
    return data;
  }

  root.DjuaApi = { request, requireAnswer, ApiError,
    async chat(message) { return requireAnswer(await request("/ai/chat", { method: "POST", body: { message } })); }
  };
})(typeof window === "undefined" ? globalThis : window);
