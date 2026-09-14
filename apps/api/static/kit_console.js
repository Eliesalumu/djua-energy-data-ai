const form = document.querySelector("#kitForm");
const apiStatus = document.querySelector("#apiStatus");
const jsonView = document.querySelector("#jsonView");
const verdict = document.querySelector("#verdict");
const maintenanceReasons = document.querySelector("#maintenanceReasons");
const securityReasons = document.querySelector("#securityReasons");
const decisionReasons = document.querySelector("#decisionReasons");
const chatForm = document.querySelector("#chatForm");
const chatLog = document.querySelector("#chatLog");
const resultPanel = document.querySelector("#result");
const runFeedback = document.querySelector("#runFeedback");
const copyJsonButton = document.querySelector("#copyJson");

let currentJsonTab = "payload";
let lastPayload = null;
let lastResponse = null;

const presets = {
  normal: {
    battery_voltage_v: 13.28,
    battery_current_a: 3.2,
    battery_power_w: 42.5,
    battery_temperature_c: 34.5,
    state_of_charge_pct: 88,
    state_of_health_pct: 97,
    battery_error_code: "NONE",
    solar_power_w: 118,
    load_power_w: 58,
    charge_duration_seconds: 3600,
    discharge_duration_seconds: 900,
    solar_error_code: "NONE",
    abnormal_consumption_detected: "false",
    overload_detected: "false",
    geofence_status: "inside",
    enclosure_opened: "false",
    speed_mps: 0,
    device_temperature_c: 35.4,
    region: "kinshasa",
    season: "dry",
    day_period: "day",
    ambient_temperature_c: 33,
    humidity_pct: 44
  },
  critical: {
    battery_voltage_v: 11.55,
    battery_current_a: -5.6,
    battery_power_w: -64.7,
    battery_temperature_c: 55.8,
    state_of_charge_pct: 23,
    state_of_health_pct: 61,
    battery_error_code: "BATT_TEMP_HIGH",
    solar_power_w: 22,
    load_power_w: 112,
    charge_duration_seconds: 900,
    discharge_duration_seconds: 5400,
    solar_error_code: "LOW_INPUT",
    abnormal_consumption_detected: "true",
    overload_detected: "true",
    geofence_status: "inside",
    enclosure_opened: "false",
    speed_mps: 0,
    device_temperature_c: 57.3,
    region: "kinshasa",
    season: "dry",
    day_period: "day",
    ambient_temperature_c: 39,
    humidity_pct: 28
  },
  security: {
    battery_voltage_v: 12.65,
    battery_current_a: 1.4,
    battery_power_w: 17.7,
    battery_temperature_c: 38.2,
    state_of_charge_pct: 67,
    state_of_health_pct: 86,
    battery_error_code: "NONE",
    solar_power_w: 63,
    load_power_w: 44,
    charge_duration_seconds: 2800,
    discharge_duration_seconds: 2100,
    solar_error_code: "NONE",
    abnormal_consumption_detected: "false",
    overload_detected: "false",
    geofence_status: "outside",
    enclosure_opened: "true",
    speed_mps: 1.6,
    device_temperature_c: 38.2,
    region: "kinshasa",
    season: "dry",
    day_period: "night",
    ambient_temperature_c: 29,
    humidity_pct: 52
  }
};

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function setApiStatus(message, state = "idle") {
  apiStatus.classList.toggle("is-busy", state === "busy");
  apiStatus.classList.toggle("is-error", state === "error");
  apiStatus.querySelector("span").textContent = message;
}

function setRunFeedback(message, state = "idle") {
  runFeedback.classList.toggle("is-running", state === "running");
  runFeedback.classList.toggle("is-error", state === "error");
  runFeedback.querySelector("span:last-child").textContent = message;
}

function textValue(name) {
  return form.elements[name]?.value || "";
}

function numberValue(name) {
  const raw = form.elements[name]?.value;
  if (raw === "" || raw === undefined) return null;
  return Number(raw);
}

function boolValue(name) {
  return textValue(name) === "true";
}

function setPreset(name) {
  const values = presets[name];
  Object.entries(values).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input) input.value = value;
  });
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.preset === name);
  });
  lastPayload = buildPayload();
  renderJson();
  setRunFeedback("Scenario charge. Tu peux lancer l'analyse ou ajuster les valeurs.", "idle");
}

function buildRecord(offset = 0) {
  const deviceId = textValue("device_id");
  const kitId = textValue("kit_id");
  const stamp = Date.now() + offset;
  return {
    message_id: `manual-${deviceId}-${stamp}`,
    schema_version: "1.0",
    message_type: "telemetry",
    device_id: deviceId,
    kit_id: kitId,
    battery_voltage_v: numberValue("battery_voltage_v"),
    battery_current_a: numberValue("battery_current_a"),
    battery_power_w: numberValue("battery_power_w"),
    battery_temperature_c: numberValue("battery_temperature_c"),
    state_of_charge_pct: numberValue("state_of_charge_pct"),
    state_of_health_pct: numberValue("state_of_health_pct"),
    battery_error_code: textValue("battery_error_code") || "NONE",
    charge_duration_seconds: numberValue("charge_duration_seconds"),
    discharge_duration_seconds: numberValue("discharge_duration_seconds"),
    solar_power_w: numberValue("solar_power_w"),
    solar_error_code: textValue("solar_error_code") || "NONE",
    load_power_w: numberValue("load_power_w"),
    overload_detected: boolValue("overload_detected"),
    abnormal_consumption_detected: boolValue("abnormal_consumption_detected"),
    geofence_status: textValue("geofence_status"),
    enclosure_opened: boolValue("enclosure_opened"),
    speed_mps: numberValue("speed_mps"),
    device_temperature_c: numberValue("device_temperature_c"),
    region: textValue("region"),
    season: textValue("season"),
    day_period: textValue("day_period"),
    ambient_temperature_c: numberValue("ambient_temperature_c"),
    humidity_pct: numberValue("humidity_pct")
  };
}

function buildPayload() {
  const baseRecord = buildRecord(0);
  const previousRecord = {
    ...buildRecord(-300000),
    message_id: `${baseRecord.message_id}-previous`,
    battery_voltage_v: Math.max(0.1, Number(baseRecord.battery_voltage_v || 0) + 0.08),
    state_of_charge_pct: Math.min(100, Number(baseRecord.state_of_charge_pct || 0) + 2),
    state_of_health_pct: Math.min(100, Number(baseRecord.state_of_health_pct || 0) + 0.4)
  };
  return {
    schema_version: "1.0",
    request_id: `manual-console-${Date.now()}`,
    as_of: new Date().toISOString(),
    device_id: textValue("device_id"),
    kit_id: textValue("kit_id"),
    records: [previousRecord, baseRecord],
    data_quality: {
      missing_features: [],
      warnings: []
    }
  };
}

function formatJson(data) {
  return JSON.stringify(data || {}, null, 2);
}

function renderJson() {
  jsonView.textContent = formatJson(currentJsonTab === "payload" ? lastPayload : lastResponse);
}

function probabilityScore(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value) * 100);
}

function numericScore(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value));
}

function scoreLevel(score) {
  if (score === null) return "non disponible";
  if (score >= 80) return "critique";
  if (score >= 60) return "eleve";
  if (score >= 35) return "modere";
  return "faible";
}

function actionLabel(action) {
  return {
    urgent_technical_intervention: "Envoyer un technicien en urgence",
    technical_intervention: "Planifier une intervention technique",
    monitor: "Continuer la surveillance normale",
    fix_data_quality: "Verifier la qualite des donnees"
  }[action] || action || "Action non disponible";
}

function kitPredictions(response) {
  const intelligence = response?.kit_intelligence || {};
  const source = response?.kit_intelligence_source || {};
  return {
    maintenance: intelligence.maintenance?.raw_prediction
      || source.maintenance_prediction
      || response?.maintenance_prediction
      || {},
    security: intelligence.security?.raw_prediction
      || source.security_prediction
      || response?.security_prediction
      || {}
  };
}

function riskClass(priority, operationalRisk) {
  const p = String(priority || "").toLowerCase();
  if (p === "critical" || p === "high") return p;
  if (Number(operationalRisk || 0) >= 70) return "high";
  if (Number(operationalRisk || 0) >= 40) return "medium";
  return "low";
}

function verdictIconFor(level) {
  if (level === "critical" || level === "high") return "siren";
  if (level === "medium") return "triangle-alert";
  if (level === "low") return "circle-check";
  return "circle-dot";
}

function verdictLabel(level) {
  return {
    critical: "Critique",
    high: "Prioritaire",
    medium: "A surveiller",
    low: "Stable"
  }[level] || "Diagnostic";
}

function setInsight(mainId, detailId, sentence, detail) {
  document.querySelector(mainId).textContent = sentence;
  document.querySelector(detailId).textContent = detail;
}

function renderReasons(list, items, emptyText) {
  list.innerHTML = "";
  const rows = items.length ? items : [emptyText];
  rows.forEach((reason) => {
    const li = document.createElement("li");
    li.textContent = reason;
    list.appendChild(li);
  });
}

function explainFromPayload(payload, response) {
  const record = payload.records[payload.records.length - 1];
  const predictions = kitPredictions(response);
  const maintenance = predictions.maintenance;
  const security = predictions.security;
  const maintenanceItems = [];
  const securityItems = [];
  const decisionItems = [];

  if (record.battery_temperature_c >= 48) maintenanceItems.push(`La batterie chauffe beaucoup: ${record.battery_temperature_c} C.`);
  if (record.battery_voltage_v <= 12.1) maintenanceItems.push(`La tension batterie est basse: ${record.battery_voltage_v} V.`);
  if (record.state_of_charge_pct <= 30) maintenanceItems.push(`La charge restante est faible: ${record.state_of_charge_pct}%.`);
  if (record.state_of_health_pct <= 75) maintenanceItems.push(`La sante batterie est degradee: ${record.state_of_health_pct}%.`);
  if (record.abnormal_consumption_detected) maintenanceItems.push("La consommation semble anormale pour ce kit.");
  if (record.overload_detected) maintenanceItems.push("Une surcharge electrique est detectee.");
  if (maintenance?.suspected_component && maintenance.suspected_component !== "none") {
    maintenanceItems.push(`Le modele soupconne le composant: ${maintenance.suspected_component}.`);
  }

  if (record.geofence_status === "outside") securityItems.push("Le kit est hors de sa zone d'installation.");
  if (record.enclosure_opened) securityItems.push("Le boitier est signale ouvert.");
  if (Number(record.speed_mps || 0) > 0.5) securityItems.push(`Un mouvement est probable: ${record.speed_mps} m/s.`);
  if (security?.suspected_event_types?.length) {
    securityItems.push(`Evenements suspects: ${security.suspected_event_types.join(", ")}.`);
  }

  const scores = response?.scores || {};
  const decision = response?.decision || response?.alert || {};
  if (scores.operational_risk !== undefined) decisionItems.push(`Risque global: ${scores.operational_risk}/100.`);
  if (scores.intervention_priority !== undefined) decisionItems.push(`Priorite terrain: ${scores.intervention_priority}/100.`);
  if (decision.recommended_action) decisionItems.push(`Action proposee: ${actionLabel(decision.recommended_action)}.`);

  return {maintenanceItems, securityItems, decisionItems};
}

function maintenanceSentence(score, record, maintenance) {
  if (score === null) return "Maintenance non calculee";
  if (record.battery_temperature_c >= 48 || record.battery_voltage_v <= 12.1 || record.state_of_health_pct <= 75) {
    return "Risque batterie important";
  }
  if (score >= 60) return "Risque technique eleve";
  if (score >= 35) return "Signaux techniques a surveiller";
  if (maintenance?.suspected_component && maintenance.suspected_component !== "none") return "Composant a verifier";
  return "Etat technique stable";
}

function securitySentence(score, record, security) {
  if (score === null) return "Securite non calculee";
  if (record.geofence_status === "outside" || record.enclosure_opened) return "Verification terrain necessaire";
  if (score >= 60) return "Activite suspecte possible";
  if (score >= 35) return "Securite a surveiller";
  if (security?.suspected_event_types?.length) return "Signal securite detecte";
  return "Aucun signal securite majeur";
}

function operationalSentence(score) {
  if (score === null) return "Risque global non calcule";
  if (score >= 80) return "Intervention prioritaire";
  if (score >= 60) return "Action a planifier vite";
  if (score >= 35) return "Surveillance renforcee";
  return "Exploitation normale";
}

function renderResult(response) {
  const intelligence = response.kit_intelligence || {};
  const scores = response.scores || {
    operational_risk: intelligence.operational_risk?.score,
    intervention_priority: intelligence.operational_risk?.score
  };
  const decision = response.decision || {
    priority: response.alert?.priority || intelligence.operational_risk?.level,
    recommended_action: response.alert?.recommended_action
      || intelligence.maintenance?.recommended_action
      || intelligence.security?.recommended_action
  };
  const predictions = kitPredictions(response);
  const maintenance = predictions.maintenance;
  const security = predictions.security;
  const record = lastPayload?.records?.[lastPayload.records.length - 1] || {};
  const maintenanceScore = probabilityScore(maintenance.technical_risk_probability ?? intelligence.maintenance?.risk_probability);
  const securityScore = probabilityScore(security.suspicious_activity_score ?? intelligence.security?.risk_probability);
  const operationalScore = numericScore(scores.operational_risk);
  const priorityScore = numericScore(scores.intervention_priority);
  const level = riskClass(decision.priority, operationalScore);

  verdict.className = `verdict ${level}`;
  verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="${verdictIconFor(level)}"></i><span>${verdictLabel(level)}</span>`;
  verdict.querySelector("strong").textContent = level === "critical" || level === "high"
    ? "Ce kit doit etre traite en priorite."
    : level === "medium"
      ? "Ce kit merite une surveillance rapprochee."
      : "Ce kit est dans un etat acceptable.";
  verdict.querySelector("p").textContent = actionLabel(decision.recommended_action);

  setInsight("#maintenanceInsight", "#maintenanceScore", maintenanceSentence(maintenanceScore, record, maintenance), `Score maintenance: ${maintenanceScore ?? "--"}% (${scoreLevel(maintenanceScore)})`);
  setInsight("#securityInsight", "#securityScore", securitySentence(securityScore, record, security), `Score securite: ${securityScore ?? "--"}% (${scoreLevel(securityScore)})`);
  setInsight("#operationalInsight", "#operationalScore", operationalSentence(operationalScore), `Score global: ${operationalScore ?? "--"}/100 (${scoreLevel(operationalScore)})`);
  setInsight("#priorityInsight", "#priorityScore", actionLabel(decision.recommended_action), `Priorite: ${priorityScore ?? "--"}/100 (${scoreLevel(priorityScore)})`);

  const explanations = explainFromPayload(lastPayload, response);
  renderReasons(maintenanceReasons, explanations.maintenanceItems, "Aucun signal maintenance important detecte.");
  renderReasons(securityReasons, explanations.securityItems, "Aucun signal securite important detecte.");
  renderReasons(decisionReasons, explanations.decisionItems, "Aucune decision globale disponible.");
  refreshIcons();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = data.detail || data.error || data;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2));
  }
  return data;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  const icon = role === "user" ? "user-round" : "bot";
  div.innerHTML = `<i data-lucide="${icon}"></i><span></span>`;
  div.querySelector("span").textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  refreshIcons();
}

function detectChatDomain(message) {
  const text = message.toLowerCase();
  if (/(maintenance|panne|batterie|temperature|tension|sante|charge|solaire)/.test(text)) return "maintenance";
  if (/(securite|security|boitier|geofence|sabotage|fraude|mouvement|vol)/.test(text)) return "security";
  return "kit_diagnostic";
}

function buildChatContext(message) {
  return {
    requested_domain: detectChatDomain(message),
    kit_payload: lastPayload,
    kit_prediction: lastResponse
  };
}

function focusResultPanel() {
  resultPanel.scrollIntoView({behavior: "smooth", block: "start"});
  window.setTimeout(() => resultPanel.focus({preventScroll: true}), 250);
}

function showPredictionLoading() {
  resultPanel.classList.add("is-loading");
  resultPanel.classList.remove("is-fresh");
  verdict.className = "verdict medium";
  verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="loader-circle"></i><span>Analyse</span>`;
  verdict.querySelector("strong").textContent = "Analyse du device en cours...";
  verdict.querySelector("p").textContent = "Le backend calcule les risques maintenance et securite a partir des mesures.";
  renderReasons(maintenanceReasons, ["Lecture des signaux batterie et consommation."], "");
  renderReasons(securityReasons, ["Lecture des signaux zone, mouvement et boitier."], "");
  renderReasons(decisionReasons, ["Calcul de la priorite terrain."], "");
  refreshIcons();
}

function showPredictionComplete(response) {
  const intelligence = response?.kit_intelligence || {};
  const scores = response?.scores || {operational_risk: intelligence.operational_risk?.score};
  const priority = response?.decision?.priority || response?.alert?.priority || intelligence.operational_risk?.level || "ok";
  setRunFeedback(`Analyse terminee: priorite ${verdictLabel(riskClass(priority, scores.operational_risk))}, risque global ${scores.operational_risk ?? "--"}/100.`, "idle");
  resultPanel.classList.remove("is-loading");
  resultPanel.classList.add("is-fresh");
  window.setTimeout(() => resultPanel.classList.remove("is-fresh"), 1800);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector(".primary-action");
  const buttonLabel = button.querySelector(".button-label");
  button.disabled = true;
  button.classList.add("is-loading");
  buttonLabel.textContent = "Analyse en cours...";
  setApiStatus("Analyse...", "busy");
  setRunFeedback("Le JSON device est envoye au backend.", "running");
  showPredictionLoading();
  focusResultPanel();

  try {
    lastPayload = buildPayload();
    currentJsonTab = "payload";
    renderJson();
    lastResponse = await postJson("/v1/devices/evaluate-from-telemetry", lastPayload);
    currentJsonTab = "response";
    document.querySelectorAll("[data-json-tab]").forEach((item) => item.classList.toggle("active", item.dataset.jsonTab === "response"));
    renderJson();
    renderResult(lastResponse);
    setApiStatus("Analyse OK");
    showPredictionComplete(lastResponse);
    addMessage("assistant", "Analyse terminee. Je peux expliquer le resultat ou proposer la prochaine action.");
  } catch (error) {
    setApiStatus("Erreur", "error");
    setRunFeedback(`Analyse impossible: ${error.message}`, "error");
    resultPanel.classList.remove("is-loading");
    verdict.className = "verdict critical";
    verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="octagon-alert"></i><span>Erreur</span>`;
    verdict.querySelector("strong").textContent = "Le backend n'a pas pu analyser ce device.";
    verdict.querySelector("p").textContent = error.message;
    refreshIcons();
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    buttonLabel.textContent = "Analyser le device";
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = chatForm.elements.message;
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  if (!lastPayload || !lastResponse) {
    addMessage("assistant", "Lance d'abord une analyse. Ensuite je pourrai expliquer ce kit avec ses mesures et sa prediction.");
    return;
  }
  try {
    const answer = await postJson("/demo/kit-console/chat", {
      message,
      context: buildChatContext(message)
    });
    addMessage("assistant", answer.answer || "Je n'ai pas trouve d'explication exploitable.");
  } catch (error) {
    addMessage("assistant", `Je n'arrive pas a repondre pour le moment. Detail: ${error.message}`);
  }
});

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => setPreset(button.dataset.preset));
});

document.querySelectorAll("[data-json-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    currentJsonTab = button.dataset.jsonTab;
    document.querySelectorAll("[data-json-tab]").forEach((item) => item.classList.toggle("active", item === button));
    renderJson();
  });
});

document.querySelectorAll("[data-chat-question]").forEach((button) => {
  button.addEventListener("click", () => {
    chatForm.elements.message.value = button.dataset.chatQuestion;
    chatForm.elements.message.focus();
  });
});

copyJsonButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(jsonView.textContent);
  setApiStatus("JSON copie");
});

form.addEventListener("input", () => {
  lastPayload = buildPayload();
  if (currentJsonTab === "payload") renderJson();
});

setPreset("critical");
lastPayload = buildPayload();
renderJson();
refreshIcons();
