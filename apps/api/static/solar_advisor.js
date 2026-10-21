const form = document.querySelector("#solarChat");
const messages = document.querySelector("#messages");
const quote = document.querySelector("#quote");
let context = {};
let recommendationId = null;
let busy = false;

function messageBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  const content = document.createElement("span");
  content.textContent = text;
  bubble.append(content);
  messages.append(bubble);
  messages.scrollTop = messages.scrollHeight;
  return content;
}

messageBubble("assistant", "Bonjour ! Quels appareils souhaitez-vous alimenter, et pendant combien d’heures par jour ?");

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  const input = form.elements.message;
  const text = input.value.trim();
  if (!text) return;
  busy = true;
  form.querySelector("button").disabled = true;
  messageBubble("user", text);
  input.value = "";
  const pending = messageBubble("assistant", "Je prépare votre réponse…");
  try {
    const quoteQuestion = recommendationId && document.querySelector("#chatMode").value === "quote";
    const url = quoteQuestion
      ? `/solar-advisor/recommendations/${encodeURIComponent(recommendationId)}/ask`
      : "/solar-advisor/conversation";
    const result = await window.DjuaApi.request(url, {
      method: "POST", body: quoteQuestion ? { question: text } : { message: text, context }
    });
    window.DjuaApi.requireAnswer(result, ["assistant_message", "answer", "explanation"]);
    if (result.recommendation && (!result.recommendation.quote || !result.recommendation.sizing || typeof result.recommendation.recommendation_id !== "string")) {
      throw new window.DjuaApi.ApiError("Le devis renvoye par le serveur est incomplet.", 200, "INVALID_QUOTE_RESPONSE");
    }
    if (result.request) context = result.request;
    if (result.recommendation) {
      const rec = result.recommendation;
      recommendationId = rec.recommendation_id;
      document.querySelector('#chatMode option[value="quote"]').disabled = false;
      quote.hidden = false;
      quote.textContent = `Estimation : ${rec.quote.total_estimated} ${rec.quote.currency} · ${rec.sizing.panel_count} panneau(x) · autonomie estimée : ${rec.sizing.autonomy_hours_estimated} h. Prix de démonstration, à confirmer avec un technicien.`;
    }
    await window.DjuaTyping.write(pending, result.assistant_message || result.answer || result.explanation || "Aucune réponse disponible.", () => {
      messages.scrollTop = messages.scrollHeight;
    });
    const source = document.createElement("small");
    source.textContent = result.used_ai ? "Réponse OpenAI" : `Mode local : ${result.warning || "OpenAI indisponible"}`;
    pending.parentElement.append(source);
  } catch (error) {
    pending.textContent = `La réponse n’a pas pu être obtenue : ${error.message}`;
    input.value = text;
  } finally {
    busy = false;
    form.querySelector("button").disabled = false;
    input.focus();
  }
});
