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
const clientScoreResult = document.querySelector("#clientScoreResult");
const scoringFeedback = document.querySelector("#scoringFeedback");
const scoreClientButton = document.querySelector("#scoreClientButton");
const linkedKitLabel = document.querySelector("#linkedKitLabel");
const advisorPanel = document.querySelector("#advisor");
const advisorFeedback = document.querySelector("#advisorFeedback");
const advisorResult = document.querySelector("#advisorResult");
const advisorRecommendButton = document.querySelector("#advisorRecommendButton");
const applianceGrid = document.querySelector("#applianceGrid");
const applianceSearch = document.querySelector("#applianceSearch");
const applianceCategory = document.querySelector("#applianceCategory");
const selectedAppliances = document.querySelector("#selectedAppliances");
const advisorTotals = document.querySelector("#advisorTotals");
const catalogCount = document.querySelector("#catalogCount");
const advisorChatForm = document.querySelector("#advisorChatForm");
const advisorChatLog = document.querySelector("#advisorChatLog");
const advisorLlmMode = document.querySelector("#advisorLlmMode");

let currentJsonTab = "payload";
let lastPayload = null;
let lastResponse = null;
let lastClientScoringPayload = null;
let lastClientScoringResponse = null;
let advisorCatalog = [];
let advisorContext = {};
let advisorSelection = new Map();
let lastAdvisorPayload = null;
let lastAdvisorResponse = null;

function refreshIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function verdictIconFor(level) {
  if (level === "critical" || level === "high") return "siren";
  if (level === "medium") return "triangle-alert";
  if (level === "low") return "circle-check";
  return "circle-dot";
}

function setApiStatus(message) {
  const label = apiStatus.querySelector("span");
  if (label) {
    label.textContent = message;
  } else {
    apiStatus.textContent = message;
  }
}

function setAdvisorFeedback(message, state = "idle") {
  if (!advisorFeedback) return;
  advisorFeedback.classList.toggle("is-running", state === "running");
  advisorFeedback.classList.toggle("is-error", state === "error");
  const text = advisorFeedback.querySelector("span:last-child");
  if (text) text.textContent = message;
}

function advisorNumberValue(name) {
  const raw = document.querySelector(`[name="${name}"]`)?.value;
  if (raw === "" || raw === undefined) return null;
  return Number(raw);
}

function advisorTextValue(name) {
  return document.querySelector(`[name="${name}"]`)?.value || "";
}

function formatMoney(value, currency = "XAF") {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "--";
  return `${Math.round(Number(value)).toLocaleString("fr-FR")} ${currency}`;
}

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function applianceLabel(item) {
  return item.common_name_fr || item.name || item.appliance_id;
}

function normalizeUsagePeriod(value) {
  const period = String(value || "mixed").toLowerCase();
  if (period === "evening") return "night";
  if (["day", "night", "mixed", "continuous"].includes(period)) return period;
  return "mixed";
}

function findAdvisorCatalogItem(key) {
  const normalized = normalizeText(key);
  const aliases = {
    television: ["television", "tele", "teles", "tv"],
    led_bulb: ["ampoule", "ampoules", "lampe", "lampes", "eclairage"],
    freezer: ["congelateur", "congelateurs"],
    fridge: ["refrigerateur", "frigo"],
    fan: ["ventilateur", "ventilo"],
    phone: ["telephone", "telephones", "chargeur"],
    laptop: ["ordinateur", "laptop", "pc"],
    router: ["routeur", "wifi", "internet"],
    pump: ["pompe"],
    ac: ["climatiseur", "clim"],
  };
  const target = Object.entries(aliases).find(([, values]) => values.some((alias) => normalized.includes(alias)))?.[0];
  const preferredIds = {
    television: "television_led_32",
    led_bulb: "led_bulb_9w",
    freezer: "freezer_small",
    fridge: "fridge_efficient",
    fan: "fan_table",
    phone: "phone_charger",
    laptop: "laptop",
    router: "router",
    pump: "water_pump_small",
    ac: "air_conditioner_small",
  };
  if (target && preferredIds[target]) {
    return advisorCatalog.find((item) => item.appliance_id === preferredIds[target]);
  }
  return advisorCatalog.find((item) => {
    const haystack = normalizeText(`${item.appliance_id} ${item.name} ${item.common_name_fr} ${item.category}`);
    return haystack.includes(normalized) || normalized.includes(haystack);
  });
}

function firstNumberNear(text, token) {
  const normalized = normalizeText(text);
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const before = normalized.match(new RegExp(`(\\d+)\\s+(?:\\w+\\s+){0,2}${escaped}`));
  if (before) return Number(before[1]);
  const after = normalized.match(new RegExp(`${escaped}\\s*(?:x|:|-)?\\s*(\\d+)`));
  if (after) return Number(after[1]);
  return 1;
}

function parseAdvisorMessage(message) {
  const normalized = normalizeText(message);
  const updates = {appliances: []};
  const hours = normalized.match(/(\d+(?:[.,]\d+)?)\s*(?:h|heure|heures)\b/);
  const budget = normalized.match(/budget(?:\s+de)?\s+(\d+(?:[ .]\d{3})*(?:[.,]\d+)?|\d+)/)
    || normalized.match(/(\d+(?:[ .]\d{3})*(?:[.,]\d+)?)\s*(?:xaf|fcfa|cdf|usd|dollars?)/);
  if (hours) updates.hours_per_day = Number(hours[1].replace(",", "."));
  if (budget) updates.budget = Number(budget[1].replace(/[ .]/g, "").replace(",", "."));

  [
    ["tele", "television"],
    ["teles", "television"],
    ["television", "television"],
    ["tv", "television"],
    ["ampoule", "led_bulb"],
    ["ampoules", "led_bulb"],
    ["lampe", "led_bulb"],
    ["lampes", "led_bulb"],
    ["congelateur", "freezer"],
    ["frigo", "fridge"],
    ["refrigerateur", "fridge"],
    ["ventilateur", "fan"],
    ["telephone", "phone"],
    ["ordinateur", "laptop"],
    ["routeur", "router"],
    ["pompe", "pump"],
    ["climatiseur", "ac"],
  ].forEach(([token, key]) => {
    if (!new RegExp(`\\b${token}s?\\b`).test(normalized)) return;
    const item = findAdvisorCatalogItem(key);
    if (!item) return;
    updates.appliances.push({
      item,
      quantity: firstNumberNear(message, token),
      hours_per_day: updates.hours_per_day || item.average_daily_hours || 1,
    });
  });
  return updates;
}

function applyAdvisorMessageParsing(message) {
  const updates = parseAdvisorMessage(message);
  if (updates.budget !== undefined) {
    const budgetInput = document.querySelector(`[name="advisor_budget"]`);
    if (budgetInput) budgetInput.value = updates.budget;
  }
  updates.appliances.forEach(({item, quantity, hours_per_day}) => {
    addAdvisorAppliance(item, {quantity, hours_per_day});
  });
  return updates;
}

function renderApplianceCategories() {
  const categories = [...new Set(advisorCatalog.map((item) => item.category).filter(Boolean))].sort();
  applianceCategory.innerHTML = `<option value="all">Toutes categories</option>`;
  categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    applianceCategory.appendChild(option);
  });
}

function renderApplianceCatalog() {
  const query = normalizeText(applianceSearch?.value);
  const category = applianceCategory?.value || "all";
  const rows = advisorCatalog.filter((item) => {
    const matchesCategory = category === "all" || item.category === category;
    const haystack = normalizeText(`${item.appliance_id} ${item.category} ${item.name} ${item.common_name_fr} ${item.notes}`);
    return matchesCategory && (!query || haystack.includes(query));
  });
  applianceGrid.innerHTML = "";
  rows.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "appliance-card";
    button.innerHTML = `
      <span>${item.category || "equipement"}</span>
      <strong>${applianceLabel(item)}</strong>
      <small>${item.typical_power_w || 0} W typique - ${item.average_daily_hours || 1} h/j - demarrage ${item.starting_power_w || item.typical_power_w || 0} W</small>
    `;
    button.addEventListener("click", () => addAdvisorAppliance(item));
    applianceGrid.appendChild(button);
  });
  catalogCount.textContent = `${rows.length}/${advisorCatalog.length} equipements`;
  refreshIcons();
}

function addAdvisorAppliance(item, overrides = {}) {
  const id = item.appliance_id;
  const existing = advisorSelection.get(id) || {};
  advisorSelection.set(id, {
    appliance_id: id,
    name: item.name,
    label: applianceLabel(item),
    category: item.category,
    quantity: Number(overrides.quantity ?? existing.quantity ?? item.quantity_default ?? 1),
    hours_per_day: Number(overrides.hours_per_day ?? existing.hours_per_day ?? item.average_daily_hours ?? 1),
    power_w: Number(overrides.power_w ?? existing.power_w ?? item.typical_power_w ?? 0),
    usage_period: normalizeUsagePeriod(overrides.usage_period ?? existing.usage_period ?? item.usage_profile),
    essential: overrides.essential ?? existing.essential ?? item.essential_or_optional !== "optional",
    simultaneous: overrides.simultaneous ?? existing.simultaneous ?? true,
  });
  renderAdvisorSelection();
}

function updateAdvisorSelection(id, field, value) {
  const item = advisorSelection.get(id);
  if (!item) return;
  if (["quantity", "hours_per_day", "power_w"].includes(field)) {
    item[field] = Number(value);
  } else {
    item[field] = value;
  }
  advisorSelection.set(id, item);
  renderAdvisorTotals();
}

function renderAdvisorTotals() {
  const rows = [...advisorSelection.values()];
  const totalWh = rows.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.hours_per_day || 0) * Number(item.power_w || 0), 0);
  const peakW = rows.reduce((sum, item) => sum + Number(item.quantity || 0) * Number(item.power_w || 0), 0);
  advisorTotals.textContent = `${rows.length} equipement(s) - ${Math.round(totalWh)} Wh/j - ${Math.round(peakW)} W`;
}

function renderAdvisorSelection() {
  const rows = [...advisorSelection.values()];
  selectedAppliances.innerHTML = "";
  if (!rows.length) {
    selectedAppliances.innerHTML = `<p class="empty-state">Selectionnez les equipements a alimenter.</p>`;
    renderAdvisorTotals();
    return;
  }
  rows.forEach((item) => {
    const row = document.createElement("div");
    row.className = "selected-row";
    row.innerHTML = `
      <div><strong>${item.label}</strong><small>${item.category} - besoin avant attribution</small></div>
      <label>Qt<input type="number" min="1" step="1" value="${item.quantity}" data-advisor-field="quantity"></label>
      <label>W<input type="number" min="1" step="1" value="${item.power_w}" data-advisor-field="power_w"></label>
      <label>h/j<input type="number" min="0.1" max="24" step="0.5" value="${item.hours_per_day}" data-advisor-field="hours_per_day"></label>
      <button type="button" class="icon-button" aria-label="Retirer ${item.label}"><i data-lucide="trash-2"></i></button>
    `;
    row.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => updateAdvisorSelection(item.appliance_id, input.dataset.advisorField, input.value));
    });
    row.querySelector("button").addEventListener("click", () => {
      advisorSelection.delete(item.appliance_id);
      renderAdvisorSelection();
    });
    selectedAppliances.appendChild(row);
  });
  renderAdvisorTotals();
  refreshIcons();
}

function buildAdvisorPayload() {
  const appliances = [...advisorSelection.values()].map((item) => ({
    appliance_id: item.appliance_id,
    name: item.name,
    quantity: Math.max(1, Number(item.quantity || 1)),
    hours_per_day: Math.max(0.1, Number(item.hours_per_day || 1)),
    power_w: Math.max(1, Number(item.power_w || 1)),
    usage_period: normalizeUsagePeriod(item.usage_period),
    essential: Boolean(item.essential),
    simultaneous: Boolean(item.simultaneous),
  }));
  return {
    customer_id: null,
    city: advisorTextValue("advisor_city"),
    region: advisorTextValue("advisor_region"),
    housing_type: advisorTextValue("advisor_housing_type"),
    people_count: advisorNumberValue("advisor_people_count"),
    autonomy_hours: advisorNumberValue("advisor_autonomy_hours"),
    budget: advisorNumberValue("advisor_budget"),
    preference: advisorTextValue("advisor_preference") || "balanced",
    appliances,
    source: "frontend_manual_advisor",
    contact: {
      prospect_ref: advisorTextValue("advisor_prospect_ref"),
      attribution_status: "before_kit_assignment",
    },
  };
}

function renderAdvisorResult(result) {
  const sizing = result.sizing || {};
  const consumption = result.consumption || {};
  const quote = result.quote || {};
  const components = result.selected_components || {};
  const componentRows = [
    ["Panneaux", components.panel, `${sizing.panel_count || "--"} x ${sizing.panel_power_w || "--"} W`],
    ["Batteries", components.battery, `${sizing.battery_count || "--"} x ${sizing.battery_capacity_ah || "--"} Ah`],
    ["Onduleur", components.inverter, `${sizing.inverter_power_w || "--"} W continu`],
    ["Regulateur", components.controller, `${sizing.controller_current_a || "--"} A`],
  ];
  advisorResult.innerHTML = `
    <div class="advisor-summary">
      <div><span>Decision Advisor</span><strong>${result.status || "recommendation_ready"}</strong></div>
      <div><span>Energie/jour</span><strong>${consumption.total_daily_energy_kwh ?? "--"} kWh</strong></div>
      <div><span>PV installe</span><strong>${sizing.pv_total_power_w ?? "--"} W</strong></div>
      <div><span>Autonomie</span><strong>${sizing.autonomy_hours_estimated ?? "--"} h</strong></div>
      <div><span>Devis demo</span><strong>${formatMoney(quote.total_estimated, quote.currency)}</strong></div>
    </div>
    <div class="advisor-components">
      ${componentRows.map(([title, component, detail]) => `
        <div class="advisor-component">
          <span>${title}</span>
          <strong>${component ? `${component.manufacturer} ${component.model}` : "--"}</strong>
          <small>${detail}<br>${component ? formatMoney(component.unit_price, component.currency) : "--"} unite</small>
        </div>
      `).join("")}
    </div>
    <div class="advisor-assumptions">
      <strong>Explication</strong>
      <ul>${(result.explanation || result.assumptions || []).slice(0, 6).map((item) => `<li>${item}</li>`).join("")}</ul>
    </div>
  `;
  refreshIcons();
}

function addAdvisorMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  const icon = role === "user" ? "user-round" : "bot";
  div.innerHTML = `<i data-lucide="${icon}"></i><span></span>`;
  div.querySelector("span").textContent = text;
  advisorChatLog.appendChild(div);
  advisorChatLog.scrollTop = advisorChatLog.scrollHeight;
  refreshIcons();
}

function applyAdvisorPreset(kind) {
  advisorSelection.clear();
  const ids = kind === "shop"
    ? [["led_bulb_9w", 6, 8], ["freezer_small", 1, 24], ["pos_terminal", 1, 10], ["phone_charger", 3, 4], ["fan_table", 1, 8], ["radio", 1, 6]]
    : [["led_bulb_9w", 8, 6], ["television_led_32", 1, 5], ["phone_charger", 4, 3], ["fan_table", 2, 8], ["router", 1, 12], ["fridge_efficient", 1, 24]];
  ids.forEach(([id, quantity, hours]) => {
    const item = advisorCatalog.find((row) => row.appliance_id === id);
    if (item) addAdvisorAppliance(item, {quantity, hours_per_day: hours});
  });
}

function syncAdvisorSelectionFromRequest(request) {
  (request?.appliances || []).forEach((need) => {
    const item = advisorCatalog.find((row) => (
      row.appliance_id === need.appliance_id ||
      normalizeText(row.name) === normalizeText(need.name) ||
      normalizeText(row.common_name_fr) === normalizeText(need.name)
    ));
    if (item) {
      addAdvisorAppliance(item, {
        quantity: need.quantity,
        hours_per_day: need.hours_per_day,
        power_w: need.power_w,
        usage_period: need.usage_period,
        essential: need.essential,
      });
    }
  });
  ["city", "region", "housing_type", "people_count", "autonomy_hours", "budget", "preference"].forEach((field) => {
    const value = request?.[field];
    const input = document.querySelector(`[name="advisor_${field}"]`);
    if (input && value !== undefined && value !== null && value !== "") input.value = value;
  });
}

async function loadAdvisorCatalog() {
  try {
    setAdvisorFeedback("Chargement du catalogue equipements et composants...", "running");
    const response = await fetch("/solar-advisor/catalogs");
    const data = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(data));
    advisorCatalog = (data.appliances || []).sort((a, b) => applianceLabel(a).localeCompare(applianceLabel(b), "fr"));
    renderApplianceCategories();
    renderApplianceCatalog();
    applyAdvisorPreset("house");
    setAdvisorFeedback("Catalogue charge. Selectionnez ou ajustez les equipements.", "idle");
  } catch (error) {
    advisorCatalog = [];
    applianceGrid.innerHTML = `<p class="empty-state">Catalogue indisponible: ${error.message}</p>`;
    catalogCount.textContent = "0 equipement";
    setAdvisorFeedback("Impossible de charger le catalogue Advisor.", "error");
  }
}

const presets = {
  normal: {
    tenure_months: 18,
    active_contracts: 1,
    battery_voltage_v: 13.28,
    battery_current_a: 3.2,
    battery_power_w: 42.5,
    state_of_charge_pct: 88,
    state_of_health_pct: 97,
    battery_error_code: "NONE",
    solar_power_w: 118,
    load_power_w: 58,
    abnormal_consumption_detected: "false",
    overload_detected: "false",
    geofence_status: "inside",
    enclosure_opened: "false",
    region: "kinshasa",
    season: "dry",
    day_period: "day",
    ambient_temperature_c: 33,
    humidity_pct: 44,
    charge_duration_seconds: 3600,
    discharge_duration_seconds: 900,
    solar_error_code: "NONE",
    speed_mps: 0,
    device_temperature_c: 35.4
  },
  critical: {
    tenure_months: 7,
    active_contracts: 1,
    battery_voltage_v: 11.55,
    battery_current_a: -5.6,
    battery_power_w: -64.7,
    state_of_charge_pct: 23,
    state_of_health_pct: 61,
    battery_error_code: "BATT_TEMP_HIGH",
    solar_power_w: 22,
    load_power_w: 112,
    abnormal_consumption_detected: "true",
    overload_detected: "true",
    geofence_status: "inside",
    enclosure_opened: "false",
    region: "kinshasa",
    season: "dry",
    day_period: "day",
    ambient_temperature_c: 39,
    humidity_pct: 28,
    charge_duration_seconds: 900,
    discharge_duration_seconds: 5400,
    solar_error_code: "LOW_INPUT",
    speed_mps: 0,
    device_temperature_c: 57.3
  },
  security: {
    tenure_months: 10,
    active_contracts: 1,
    battery_voltage_v: 12.65,
    battery_current_a: 1.4,
    battery_power_w: 17.7,
    state_of_charge_pct: 67,
    state_of_health_pct: 86,
    battery_error_code: "NONE",
    solar_power_w: 63,
    load_power_w: 44,
    abnormal_consumption_detected: "false",
    overload_detected: "false",
    geofence_status: "outside",
    enclosure_opened: "true",
    region: "kinshasa",
    season: "dry",
    day_period: "night",
    ambient_temperature_c: 29,
    humidity_pct: 52,
    charge_duration_seconds: 2800,
    discharge_duration_seconds: 2100,
    solar_error_code: "NONE",
    speed_mps: 1.6,
    device_temperature_c: 38.2
  }
};

function setPreset(name) {
  const values = presets[name];
  Object.entries(values).forEach(([key, value]) => {
    const input = form.elements[key];
    if (input) input.value = value;
  });
  syncClientKitLink();
}

function syncClientKitLink() {
  const clientId = textValue("client_id");
  const kitId = textValue("kit_id");
  linkedKitLabel.textContent = `${clientId} · ${kitId}`;
}

function numberValue(name) {
  const raw = form.elements[name]?.value;
  if (raw === "" || raw === undefined) return null;
  return Number(raw);
}

function textValue(name) {
  return form.elements[name]?.value || "";
}

function boolValue(name) {
  return textValue(name) === "true";
}

function buildPayments(clientId, contractId) {
  const profile = form.elements.scoring_payment_profile?.value || "good";
  const amount = numberValue("scoring_periodic_amount_usd") || 20;
  const profiles = {
    good: [
      ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0]
    ],
    late: [
      ["paid", 0], ["late", 7], ["paid", 0], ["late", 14], ["paid", 0], ["paid", 0]
    ],
    missed: [
      ["paid", 0], ["missed", null], ["late", 12], ["failed", null], ["paid", 0], ["missed", null]
    ]
  }[profile] || [
    ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0], ["paid", 0]
  ];

  return profiles.map(([status, daysLate], index) => {
    const month = String(index + 3).padStart(2, "0");
    const paidDay = daysLate === null ? null : String(1 + daysLate).padStart(2, "0");
    return {
      payment_id: `pay-${clientId}-${index + 1}`,
      client_id: clientId,
      contract_id: contractId,
      due_date: `2026-${month}-01T00:00:00+02:00`,
      paid_at: paidDay ? `2026-${month}-${paidDay}T12:00:00+02:00` : null,
      amount_due: amount,
      amount_paid: status === "missed" || status === "failed" ? 0 : amount,
      days_late: daysLate,
      status,
      method: "orange_money"
    };
  });
}

function buildRecord(offset = 0) {
  const nowSeconds = Math.floor(Date.now() / 1000) + offset;
  const deviceId = textValue("device_id");
  const kitId = textValue("kit_id");
  return {
    message_id: `manual-${deviceId}-${nowSeconds}-${offset}`,
    schema_version: "1.0",
    message_type: "telemetry",
    device_id: deviceId,
    kit_id: kitId,
    serial_number: `SN-${kitId}`,
    event_time: String(nowSeconds),
    sequence_number: Math.max(1, Math.floor(nowSeconds % 100000) + offset + 1),
    battery_voltage_v: numberValue("battery_voltage_v"),
    battery_current_a: numberValue("battery_current_a"),
    battery_power_w: numberValue("battery_power_w"),
    state_of_charge_pct: numberValue("state_of_charge_pct"),
    state_of_health_pct: numberValue("state_of_health_pct"),
    battery_error_code: textValue("battery_error_code"),
    charge_duration_seconds: numberValue("charge_duration_seconds"),
    discharge_duration_seconds: numberValue("discharge_duration_seconds"),
    solar_power_w: numberValue("solar_power_w"),
    solar_error_code: textValue("solar_error_code"),
    load_power_w: numberValue("load_power_w"),
    overload_detected: boolValue("overload_detected"),
    abnormal_consumption_detected: boolValue("abnormal_consumption_detected"),
    geofence_status: textValue("geofence_status"),
    enclosure_opened: boolValue("enclosure_opened"),
    device_temperature_c: numberValue("device_temperature_c"),
    region: textValue("region"),
    season: textValue("season"),
    day_period: textValue("day_period"),
    ambient_temperature_c: numberValue("ambient_temperature_c"),
    humidity_pct: numberValue("humidity_pct")
  };
}

function buildPayload() {
  const clientId = textValue("client_id");
  const contractId = textValue("contract_id");
  const asOf = new Date().toISOString();
  const baseRecord = buildRecord(0);
  const previousRecord = {
    ...buildRecord(-300),
    message_id: `${baseRecord.message_id}-previous`,
    sequence_number: Math.max(1, baseRecord.sequence_number - 1),
    state_of_health_pct: Math.min(100, baseRecord.state_of_health_pct + 0.4)
  };
  return {
    schema_version: "1.0",
    request_id: `manual-console-${Date.now()}`,
    as_of: asOf,
    identity: {
      client_id: clientId,
      kit_id: textValue("kit_id"),
      device_id: textValue("device_id"),
      installation_id: `installation-${textValue("kit_id")}`,
      contract_id: contractId,
      assignment_id: textValue("assignment_id"),
      resolution_status: "resolved"
    },
    customer: {
      customer_segment: textValue("customer_segment"),
      tenure_months: numberValue("tenure_months"),
      active_contracts: numberValue("active_contracts")
    },
    contract: {
      contract_id: contractId,
      status: "active",
      periodic_amount_usd: numberValue("scoring_periodic_amount_usd")
    },
    payments: buildPayments(clientId, contractId),
    records: [previousRecord, baseRecord],
    data_quality: {
      identity_resolved: true,
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

function scorePercent(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "--";
  return `${Math.round(Number(value) * 100)}%`;
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
  if (score >= 60) return "a surveiller";
  if (score >= 35) return "modere";
  return "faible";
}

function hasSecurityFieldAlert(record) {
  return Boolean(record.enclosure_opened || record.geofence_status === "outside");
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

function maintenanceSentence(score, record, maintenance) {
  if (score === null) return "Maintenance non calculee";
  if (record.battery_voltage_v <= 12.1 || record.state_of_health_pct <= 75) {
    return "Batterie degradee: intervention technique a prevoir";
  }
  if (score >= 60) return "Risque de panne visible: surveiller la batterie";
  if (score >= 35) return "Quelques signaux faibles: controle recommande";
  if (maintenance?.suspected_component && maintenance.suspected_component !== "none") return "Composant a surveiller";
  return "Kit techniquement stable";
}

function securitySentence(score, record, security) {
  if (score === null) return "Securite non calculee";
  if (hasSecurityFieldAlert(record)) {
    return "Alerte securite: verification terrain necessaire";
  }
  if (score >= 60) return "Activite suspecte possible";
  if (score >= 35) return "Securite a surveiller";
  if (security?.suspected_event_types?.length) return "Signal securite detecte";
  return "Aucun signal de fraude majeur";
}

function operationalSentence(score) {
  if (score === null) return "Risque operationnel non calcule";
  if (score >= 80) return "Etat critique: intervention prioritaire";
  if (score >= 60) return "Risque eleve: planifier une action";
  if (score >= 35) return "Surveillance renforcee recommandee";
  return "Exploitation normale";
}

function prioritySentence(score) {
  if (score === null) return "Priorite non calculee";
  if (score >= 80) return "A traiter en urgence";
  if (score >= 60) return "A planifier rapidement";
  if (score >= 35) return "A suivre dans le monitoring";
  return "Pas d'action urgente";
}

function clientValueSentence(score) {
  if (score === null) return "Valeur client non calculee";
  if (score >= 75) return "Client a forte valeur";
  if (score >= 50) return "Client de valeur moyenne";
  return "Client a potentiel limite";
}

function paymentRiskSentence(score) {
  if (score === null) return "Risque paiement non calcule";
  if (score >= 75) return "Risque paiement eleve";
  if (score >= 50) return "Risque paiement a surveiller";
  if (score >= 30) return "Quelques retards acceptables";
  return "Paiements globalement fiables";
}

function actionLabel(action) {
  return {
    urgent_technical_intervention: "Intervention technique urgente",
    technical_intervention: "Intervention technique a planifier",
    commercial_follow_up: "Suivi commercial paiement",
    payment_monitoring: "Surveillance paiement",
    monitor: "Surveillance standard",
    resolve_identity: "Resoudre l'identite client-kit",
    fix_data_quality: "Corriger la qualite des donnees"
  }[action] || action || "Decision non disponible";
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
      || {},
  };
}

function summarizePayments(payments) {
  const rows = payments || [];
  const late = rows.filter((payment) => payment.status === "late" || Number(payment.days_late || 0) > 0);
  const missed = rows.filter((payment) => ["missed", "failed"].includes(payment.status));
  const paid = rows.filter((payment) => payment.status === "paid");
  const outstanding = rows.reduce((total, payment) => (
    total + Math.max(Number(payment.amount_due || 0) - Number(payment.amount_paid || 0), 0)
  ), 0);
  const averageDaysLate = late.length
    ? Math.round(late.reduce((total, payment) => total + Number(payment.days_late || 0), 0) / late.length)
    : 0;
  return {total: rows.length, paid: paid.length, late: late.length, missed: missed.length, outstanding, averageDaysLate};
}

function renderClientScoring(result, payload) {
  const scores = result.scores || {};
  const identity = result.identity || payload.identity || {};
  const paymentSummary = summarizePayments(payload.payments || []);
  const customer = payload.customer || {};
  const contract = payload.contract || {};
  const quality = result.data_quality || {};
  const source = result.kit_intelligence_source || {};
  const predictions = kitPredictions(result);
  const maintenance = predictions.maintenance;
  const security = predictions.security;
  const clientValue = numericScore(scores.client_value);
  const paymentRisk = numericScore(scores.payment_risk);
  const operationalRisk = numericScore(scores.operational_risk);
  const priority = numericScore(scores.intervention_priority);
  const kitFactors = [];
  if (maintenance.technical_risk_probability !== undefined) kitFactors.push(`maintenance ${scorePercent(maintenance.technical_risk_probability)}`);
  if (security.suspicious_activity_score !== undefined) kitFactors.push(`securite ${scorePercent(security.suspicious_activity_score)}`);
  if (source.feature_snapshot?.maintenance?.solar_load_ratio !== undefined) kitFactors.push(`ratio solaire/charge ${source.feature_snapshot.maintenance.solar_load_ratio}`);

  clientScoreResult.innerHTML = `
    <div class="client-score-header">
      <span>Decision client</span>
      <strong>${actionLabel(result.decision?.recommended_action)}</strong>
      <small>${identity.client_id || "--"} - ${identity.kit_id || "--"} - confiance ${Math.round(Number(result.confidence || 0) * 100)}%</small>
    </div>
    <div class="client-score-grid">
      <div><span><i data-lucide="badge-dollar-sign"></i>Valeur client</span><strong>${clientValue ?? "--"}/100</strong><small>${clientValueSentence(clientValue)}: segment ${customer.customer_segment || "--"}, anciennete ${customer.tenure_months ?? "--"} mois, ${customer.active_contracts ?? "--"} contrat(s), ${contract.periodic_amount_usd ?? "--"} USD/mois.</small></div>
      <div><span><i data-lucide="receipt"></i>Risque paiement</span><strong>${paymentRisk ?? "--"}/100</strong><small>${paymentRiskSentence(paymentRisk)}: ${paymentSummary.total} paiement(s), ${paymentSummary.late} retard(s), ${paymentSummary.missed} impaye/echec, retard moyen ${paymentSummary.averageDaysLate} j, solde ${paymentSummary.outstanding} USD.</small></div>
      <div><span><i data-lucide="activity"></i>Risque operationnel</span><strong>${operationalRisk ?? "--"}/100</strong><small>${operationalSentence(operationalRisk)}. ${kitFactors.join(" | ") || "Aucune prediction kit rattachee."}</small></div>
      <div><span><i data-lucide="flag"></i>Priorite intervention</span><strong>${priority ?? "--"}/100</strong><small>${prioritySentence(priority)}. Combine valeur client, paiement, risque kit et qualite des donnees.</small></div>
    </div>
    <div class="client-score-evidence">
      <section><h4>Entrees paiement</h4><p>Profil: ${form.elements.scoring_payment_profile?.selectedOptions?.[0]?.textContent || "--"}; montant: ${contract.periodic_amount_usd ?? "--"} USD.</p></section>
      <section><h4>Entrees client</h4><p>Segment ${customer.customer_segment || "--"}, anciennete ${customer.tenure_months ?? "--"} mois, contrats actifs ${customer.active_contracts ?? "--"}.</p></section>
      <section><h4>Entrees kit</h4><p>${kitFactors.join("; ") || "Le scoring n'a pas recu de signaux kit calcules."}</p></section>
      <section><h4>Qualite data</h4><p>Statut ${quality.status || "--"}; warnings: ${(quality.warnings || []).join("; ") || "aucun"}.</p></section>
    </div>
  `;
}

function detectChatDomain(message) {
  const text = message.toLowerCase();
  if (/(scoring|score client|client|paiement|payment|impaye|impay|retard|echeance)/.test(text)) return "client_scoring";
  if (/(maintenance|panne|batterie|temperature|tension|sante|charge|solaire)/.test(text)) return "maintenance";
  if (/(securite|security|boitier|geofence|sabotage|fraude|mouvement)/.test(text)) return "security";
  return "kit_diagnostic";
}

function buildChatContext(message) {
  return {
    requested_domain: detectChatDomain(message),
    kit_payload: lastPayload,
    kit_prediction: lastResponse,
    client_scoring_payload: lastClientScoringPayload,
    client_scoring: lastClientScoringResponse
  };
}

function riskClass(priority, operationalRisk) {
  const p = String(priority || "").toLowerCase();
  if (p === "critical" || p === "high") return p;
  if (Number(operationalRisk || 0) >= 70) return "high";
  if (Number(operationalRisk || 0) >= 40) return "medium";
  return "low";
}

function explainFromPayload(payload, response) {
  const record = payload.records[payload.records.length - 1];
  const maintenanceItems = [];
  const securityItems = [];
  const decisionItems = [];
  if (record.battery_voltage_v <= 12.1) maintenanceItems.push(`Tension batterie faible (${record.battery_voltage_v} V).`);
  if (record.state_of_health_pct <= 75) maintenanceItems.push(`Sante batterie degradee (${record.state_of_health_pct}%).`);
  if (record.abnormal_consumption_detected) maintenanceItems.push("Consommation anormale detectee cote charge.");
  if (record.geofence_status === "outside") securityItems.push("Le kit est sorti de sa zone d'installation.");
  if (record.enclosure_opened) securityItems.push("Boitier ouvert detecte.");

  const predictions = kitPredictions(response);
  const maintenance = predictions.maintenance;
  const security = predictions.security;
  if (maintenance?.suspected_component) maintenanceItems.push(`Composant suspecte par le modele (${maintenance.suspected_component}).`);
  if (security?.suspected_event_types?.length) securityItems.push(`Evenements suspectes (${security.suspected_event_types.join(", ")}).`);
  if (response?.scores?.operational_risk !== undefined) {
    decisionItems.push(
      `Risque operationnel=${response.scores.operational_risk}/100, priorite=${response.scores.intervention_priority ?? response.scores.operational_risk}/100.`
    );
  }
  return {maintenanceItems, securityItems, decisionItems};
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
  const level = riskClass(decision.priority, scores.operational_risk);
  const displayedPriority = ["critical", "high", "medium"].includes(String(decision.priority).toLowerCase())
    ? decision.priority
    : level;
  verdict.className = `verdict ${level}`;
  verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="${verdictIconFor(level)}"></i><span>${displayedPriority}</span>`;
  verdict.querySelector("strong").textContent = level === "critical" || level === "high"
    ? "Ce kit necessite une intervention prioritaire."
    : level === "medium"
      ? "Ce kit doit rester sous surveillance rapprochee."
      : "Ce kit est dans un etat acceptable.";
  verdict.querySelector("p").textContent = decision.recommended_action
    ? `Action recommandee: ${decision.recommended_action}.`
    : "Decision non disponible.";

  const record = lastPayload?.records?.[lastPayload.records.length - 1] || {};
  const maintenanceScore = probabilityScore(maintenance.technical_risk_probability ?? intelligence.maintenance?.risk_probability);
  const securityScore = probabilityScore(security.suspicious_activity_score ?? intelligence.security?.risk_probability);
  const operationalScore = numericScore(scores.operational_risk);
  const priorityScore = numericScore(scores.intervention_priority);

  setInsight(
    "#maintenanceInsight",
    "#maintenanceScore",
    maintenanceSentence(maintenanceScore, record, maintenance),
    `Score maintenance: ${maintenanceScore ?? "--"}% (${scoreLevel(maintenanceScore)})`
  );
  setInsight(
    "#securityInsight",
    "#securityScore",
    securitySentence(securityScore, record, security),
    hasSecurityFieldAlert(record)
      ? `Alerte terrain active. Score modele securite: ${securityScore ?? "--"}% (${scoreLevel(securityScore)})`
      : `Score modele securite: ${securityScore ?? "--"}% (${scoreLevel(securityScore)})`
  );
  setInsight(
    "#operationalInsight",
    "#operationalScore",
    operationalSentence(operationalScore),
    `Score operationnel: ${operationalScore ?? "--"}/100 (${scoreLevel(operationalScore)})`
  );
  setInsight(
    "#priorityInsight",
    "#priorityScore",
    prioritySentence(priorityScore),
    `Score priorite: ${priorityScore ?? "--"}/100 (${scoreLevel(priorityScore)})`
  );
  const explanations = explainFromPayload(lastPayload, response);
  renderReasons(maintenanceReasons, explanations.maintenanceItems, "Aucun signal maintenance critique detecte.");
  renderReasons(securityReasons, explanations.securityItems, "Aucun signal terrain securite detecte.");
  renderReasons(decisionReasons, explanations.decisionItems, "Aucune decision globale disponible.");
  refreshIcons();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2));
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

function setRunFeedback(message, state = "idle") {
  if (!runFeedback) return;
  runFeedback.classList.toggle("is-running", state === "running");
  runFeedback.classList.toggle("is-error", state === "error");
  const text = runFeedback.querySelector("span:last-child");
  if (text) text.textContent = message;
}

function focusResultPanel() {
  if (!resultPanel) return;
  resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => resultPanel.focus({ preventScroll: true }), 250);
}

function showPredictionLoading() {
  resultPanel?.classList.add("is-loading");
  resultPanel?.classList.remove("is-fresh");
  verdict.className = "verdict medium";
  verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="loader-circle"></i><span>Calcul</span>`;
  verdict.querySelector("strong").textContent = "Analyse du kit en cours...";
  verdict.querySelector("p").textContent = "L'API recoit le snapshot backend complet, calcule les risques kit puis prepare la decision client.";
  renderReasons(maintenanceReasons, ["Analyse des mesures batterie, charge et stabilite electrique."], "");
  renderReasons(securityReasons, ["Controle des signaux terrain: geofence, mouvement, boitier et sabotage."], "");
  renderReasons(decisionReasons, ["La priorite combine identite resolue, paiements, telemetrie et risques kit."], "");
  refreshIcons();
}

function showPredictionComplete(response) {
  const intelligence = response?.kit_intelligence || {};
  const scores = response?.scores || {operational_risk: intelligence.operational_risk?.score};
  const priority = response?.decision?.priority || response?.alert?.priority || intelligence.operational_risk?.level || "decision";
  setRunFeedback(
    `Prediction terminee: priorite ${priority}, risque operationnel ${scores.operational_risk ?? "--"}/100.`,
    "idle"
  );
  resultPanel?.classList.remove("is-loading");
  resultPanel?.classList.add("is-fresh");
  window.setTimeout(() => resultPanel?.classList.remove("is-fresh"), 1800);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector(".primary-action");
  const buttonLabel = button.querySelector(".button-label");
  const originalLabel = buttonLabel?.textContent || button.textContent;
  button.disabled = true;
  button.classList.add("is-loading");
  if (buttonLabel) buttonLabel.textContent = "Prediction en cours...";
  setApiStatus("Calcul...");
  setRunFeedback("Prediction en cours: le JSON est envoye a l'API IA/Data.", "running");
  showPredictionLoading();
  focusResultPanel();
  try {
    lastPayload = buildPayload();
    currentJsonTab = "payload";
    renderJson();
    lastResponse = await postJson("/v1/customer/evaluate-from-telemetry", lastPayload);
    currentJsonTab = "response";
    renderJson();
    renderResult(lastResponse);
    setApiStatus("Prediction OK");
    showPredictionComplete(lastResponse);
    focusResultPanel();
    addMessage("assistant", "Prediction terminee. Je peux maintenant expliquer le diagnostic de ce kit.");
  } catch (error) {
    setApiStatus("Erreur");
    setRunFeedback(`Erreur API: ${error.message}`, "error");
    resultPanel?.classList.remove("is-loading");
    resultPanel?.classList.add("is-fresh");
    verdict.className = "verdict critical";
    verdict.querySelector(".verdict-label").innerHTML = `<i data-lucide="octagon-alert"></i><span>Erreur</span>`;
    verdict.querySelector("strong").textContent = "La prediction a echoue.";
    verdict.querySelector("p").textContent = error.message;
    refreshIcons();
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    if (buttonLabel) buttonLabel.textContent = originalLabel;
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

document.querySelector("#copyJson").addEventListener("click", async () => {
  await navigator.clipboard.writeText(jsonView.textContent);
  setApiStatus("JSON copie");
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = chatForm.elements.message;
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  try {
    const answer = await postJson("/demo/kit-console/chat", {
      message,
      context: buildChatContext(message)
    });
    addMessage("assistant", answer.answer);
  } catch (error) {
    addMessage("assistant", `Je n'arrive pas a repondre: ${error.message}`);
  }
});

scoreClientButton.addEventListener("click", async () => {
  const button = scoreClientButton;
  button.disabled = true;
  scoringFeedback.querySelector("span:last-child").textContent = "Scoring client en cours...";
  scoringFeedback.classList.add("is-running");
  const payload = buildPayload();
  lastClientScoringPayload = payload;
  try {
    const result = await postJson("/v1/customer/evaluate-from-telemetry", payload);
    lastClientScoringResponse = result;
    const scores = result.scores || {};
    const identity = result.identity || {};
    clientScoreResult.innerHTML = `<strong>${scores.client_value ?? "--"}/100</strong><span>Risque paiement: ${scores.payment_risk ?? "--"}/100</span><p>${identity.client_id} · ${identity.kit_id}<br>${result.decision?.recommended_action || "Decision non disponible."}</p>`;
    renderClientScoring(result, payload);
    scoringFeedback.querySelector("span:last-child").textContent = "Scoring client calcule avec paiements + prediction maintenance/securite du kit.";
  } catch (error) {
    clientScoreResult.textContent = `Erreur scoring: ${error.message}`;
    scoringFeedback.querySelector("span:last-child").textContent = "Le scoring client a echoue.";
    scoringFeedback.classList.add("is-error");
  } finally {
    button.disabled = false;
    scoringFeedback.classList.remove("is-running");
    refreshIcons();
  }
});

advisorRecommendButton.addEventListener("click", async () => {
  const button = advisorRecommendButton;
  const buttonLabel = button.querySelector(".button-label");
  const originalLabel = buttonLabel?.textContent || "Recommander le kit solaire";
  const payload = buildAdvisorPayload();
  if (!payload.appliances.length) {
    setAdvisorFeedback("Selectionnez au moins un equipement avant de recommander.", "error");
    return;
  }
  button.disabled = true;
  button.classList.add("is-loading");
  if (buttonLabel) buttonLabel.textContent = "Dimensionnement...";
  setAdvisorFeedback("Calcul Advisor: consommation, panneaux, batterie, onduleur et devis.", "running");
  try {
    lastAdvisorPayload = payload;
    lastAdvisorResponse = await postJson("/solar-advisor/recommend", payload);
    renderAdvisorResult(lastAdvisorResponse);
    setAdvisorFeedback(`Recommandation prete: ${formatMoney(lastAdvisorResponse.quote?.total_estimated, lastAdvisorResponse.quote?.currency)}.`, "idle");
    addAdvisorMessage("assistant", `Kit recommande: ${lastAdvisorResponse.sizing?.pv_total_power_w} W PV, ${lastAdvisorResponse.sizing?.battery_total_capacity_wh} Wh batterie, devis demo ${formatMoney(lastAdvisorResponse.quote?.total_estimated, lastAdvisorResponse.quote?.currency)}.`);
  } catch (error) {
    setAdvisorFeedback(`Erreur Advisor: ${error.message}`, "error");
    advisorResult.innerHTML = `<div class="advisor-empty"><i data-lucide="octagon-alert"></i><span>${error.message}</span></div>`;
    refreshIcons();
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    if (buttonLabel) buttonLabel.textContent = originalLabel;
  }
});

advisorChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = advisorChatForm.elements.message;
  const message = input.value.trim();
  if (!message) return;
  addAdvisorMessage("user", message);
  input.value = "";
  try {
    const result = await postJson("/solar-advisor/conversation", {
      message,
      context: {
        ...advisorContext,
        ...buildAdvisorPayload(),
        llm_requested: advisorLlmMode.checked,
        source: advisorLlmMode.checked ? "frontend_llm_advisor" : "frontend_manual_advisor"
      }
    });
    advisorContext = result.request || advisorContext;
    syncAdvisorSelectionFromRequest(result.request);
    addAdvisorMessage("assistant", result.assistant_message || "J'ai mis a jour la selection Advisor.");
    if (result.recommendation) {
      lastAdvisorResponse = result.recommendation;
      renderAdvisorResult(result.recommendation);
    }
    setAdvisorFeedback(result.used_ai ? `Conversation LLM active (${result.model || "modele disponible"}).` : "Conversation locale active; LLM non disponible ou desactive.", "idle");
  } catch (error) {
    addAdvisorMessage("assistant", `Je n'arrive pas a traiter ce message Advisor: ${error.message}`);
    setAdvisorFeedback("La conversation Advisor a echoue.", "error");
  }
});

applianceSearch.addEventListener("input", renderApplianceCatalog);
applianceCategory.addEventListener("change", renderApplianceCatalog);
document.querySelector("#advisorPresetHouse").addEventListener("click", () => applyAdvisorPreset("house"));
document.querySelector("#advisorPresetShop").addEventListener("click", () => applyAdvisorPreset("shop"));
document.querySelector("#advisorReset").addEventListener("click", () => {
  advisorSelection.clear();
  advisorContext = {};
  renderAdvisorSelection();
  advisorResult.innerHTML = `<div class="advisor-empty"><i data-lucide="panel-top"></i><span>La recommandation Advisor apparaitra ici avec panneaux, batterie, onduleur, regulateur et devis.</span></div>`;
  setAdvisorFeedback("Selection Advisor remise a zero.", "idle");
  refreshIcons();
});

["client_id", "kit_id"].forEach((name) => {
  form.elements[name].addEventListener("input", syncClientKitLink);
});

setPreset("critical");
lastPayload = buildPayload();
renderJson();
loadAdvisorCatalog();
refreshIcons();
