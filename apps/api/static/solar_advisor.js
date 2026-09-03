/**
 * ==========================================================================
 * DJUA AI SOLAR ADVISOR - APPLICATION JAVASCRIPT
 * ==========================================================================
 */

// Application State
const state = {
  catalog: [],
  components: [],
  cart: new Map(), // appliance_id -> { id, name, power_w, hours_per_day, quantity, icon, category }
  currentStep: 1,
  activeCategory: 'all',
  lastRecommendation: null,
  chatContext: {
    history: [],
    request: {}
  }
};

// Category Icon Mapping (Lucide icon names)
const CATEGORY_ICONS = {
  lighting: 'lightbulb',
  media: 'tv',
  cold_chain: 'snowflake',
  cooling: 'wind',
  computing: 'laptop',
  business: 'briefcase',
  communication: 'smartphone',
  appliance: 'plug',
  water: 'droplets',
  health: 'heart-pulse',
  office: 'printer',
  agriculture: 'wheat',
  custom: 'zap'
};

// Preset Configurations
const PRESETS = {
  household: {
    housing_type: 'household',
    city: 'Kinshasa',
    people_count: 5,
    autonomy_hours: 10,
    budget: 1200000,
    preference: 'balanced',
    items: [
      { id: 'television_led_32', qty: 1, hours: 5 },
      { id: 'led_bulb_9w', qty: 6, hours: 6 },
      { id: 'fan_table', qty: 1, hours: 8 },
      { id: 'phone_charger', qty: 2, hours: 3 }
    ]
  },
  shop: {
    housing_type: 'shop',
    city: 'Lubumbashi',
    people_count: 3,
    autonomy_hours: 12,
    budget: 2000000,
    preference: 'balanced',
    items: [
      { id: 'freezer_small', qty: 1, hours: 24 },
      { id: 'television_led_24', qty: 1, hours: 8 },
      { id: 'led_bulb_9w', qty: 4, hours: 10 },
      { id: 'fan_ceiling', qty: 1, hours: 8 },
      { id: 'pos_terminal', qty: 1, hours: 10 }
    ]
  },
  cold: {
    housing_type: 'shop',
    city: 'Goma',
    people_count: 4,
    autonomy_hours: 14,
    budget: 2800000,
    preference: 'performance',
    items: [
      { id: 'fridge_efficient', qty: 1, hours: 24 },
      { id: 'freezer_small', qty: 1, hours: 24 },
      { id: 'led_bulb_9w', qty: 4, hours: 8 }
    ]
  },
  salon: {
    housing_type: 'productive_use',
    city: 'Dakar',
    people_count: 4,
    autonomy_hours: 8,
    budget: 1600000,
    preference: 'balanced',
    items: [
      { id: 'hair_clipper', qty: 2, hours: 5 },
      { id: 'television_led_32', qty: 1, hours: 8 },
      { id: 'fan_ceiling', qty: 2, hours: 8 },
      { id: 'radio', qty: 1, hours: 8 },
      { id: 'led_bulb_9w', qty: 6, hours: 8 }
    ]
  },
  health: {
    housing_type: 'health_center',
    city: 'Abidjan',
    people_count: 15,
    autonomy_hours: 16,
    budget: 3500000,
    preference: 'autonomy',
    items: [
      { id: 'medical_nebulizer', qty: 1, hours: 2 },
      { id: 'fridge_efficient', qty: 1, hours: 24 },
      { id: 'laptop', qty: 1, hours: 6 },
      { id: 'router', qty: 1, hours: 12 },
      { id: 'led_bulb_9w', qty: 10, hours: 10 }
    ]
  }
};

// Format Helpers
function formatCurrency(amount, currency = 'XAF') {
  if (amount === undefined || amount === null) return `0 ${currency}`;
  return `${Number(amount).toLocaleString('fr-FR')} ${currency}`;
}

function formatWh(wh) {
  if (!wh) return '0 Wh';
  if (wh >= 1000) {
    return `${(wh / 1000).toFixed(2)} kWh`;
  }
  return `${Math.round(wh)} Wh`;
}

// Initialization on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
  initModeSwitcher();
  initStepper();
  initFormInputs();
  initCategoryFilters();
  initCustomApplianceForm();
  initQuickQuestions();
  initContactModal();
  initChatForm();

  await loadCatalogData();
  applyPreset('household');
});

// Mode Switcher (Visual vs Chat)
function initModeSwitcher() {
  const btnVisual = document.getElementById('btnModeVisual');
  const btnChat = document.getElementById('btnModeChat');
  const viewVisual = document.getElementById('viewVisualConfigurator');
  const viewChat = document.getElementById('viewChatAdvisor');

  btnVisual.addEventListener('click', () => {
    btnVisual.classList.add('active');
    btnChat.classList.remove('active');
    viewVisual.classList.add('active');
    viewChat.classList.remove('active');
    if (window.lucide) lucide.createIcons();
  });

  btnChat.addEventListener('click', () => {
    btnChat.classList.add('active');
    btnVisual.classList.remove('active');
    viewChat.classList.add('active');
    viewVisual.classList.remove('active');
    if (window.lucide) lucide.createIcons();
  });
}

// Stepper Navigation
function initStepper() {
  const stepNavItems = document.querySelectorAll('.step-nav-item');
  const wizardSteps = document.querySelectorAll('.wizard-step');
  const nextButtons = document.querySelectorAll('.btn-next');
  const prevButtons = document.querySelectorAll('.btn-prev');
  const resetBtn = document.getElementById('btnResetAll');

  function goToStep(stepNumber) {
    state.currentStep = Number(stepNumber);

    stepNavItems.forEach((item) => {
      const itemStep = Number(item.dataset.step);
      item.classList.toggle('active', itemStep === state.currentStep);
      item.classList.toggle('completed', itemStep < state.currentStep);
    });

    wizardSteps.forEach((step, idx) => {
      step.classList.toggle('active', idx + 1 === state.currentStep);
    });

    window.scrollTo({ top: 120, behavior: 'smooth' });
    if (window.lucide) lucide.createIcons();
  }

  stepNavItems.forEach((btn) => {
    btn.addEventListener('click', () => goToStep(btn.dataset.step));
  });

  nextButtons.forEach((btn) => {
    btn.addEventListener('click', () => goToStep(btn.dataset.goto));
  });

  prevButtons.forEach((btn) => {
    btn.addEventListener('click', () => goToStep(btn.dataset.goto));
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      state.cart.clear();
      renderApplianceGrid();
      renderCart();
      goToStep(1);
    });
  }

  const btnCalc = document.getElementById('btnGenerateQuote');
  if (btnCalc) {
    btnCalc.addEventListener('click', async () => {
      await generateQuote();
      goToStep(3);
    });
  }
}

// Form Inputs & Sliders
function initFormInputs() {
  const sliderAutonomy = document.getElementById('sliderAutonomy');
  const valAutonomy = document.getElementById('valAutonomy');

  if (sliderAutonomy && valAutonomy) {
    sliderAutonomy.addEventListener('input', (e) => {
      valAutonomy.textContent = `${e.target.value} h`;
    });
  }

  // Presets Buttons
  document.querySelectorAll('.preset-card').forEach((card) => {
    card.addEventListener('click', () => {
      applyPreset(card.dataset.preset);
    });
  });
}

function applyPreset(presetKey) {
  const preset = PRESETS[presetKey];
  if (!preset) return;

  if (document.getElementById('inputHousingType')) document.getElementById('inputHousingType').value = preset.housing_type;
  if (document.getElementById('inputCity')) document.getElementById('inputCity').value = preset.city;
  if (document.getElementById('inputPeopleCount')) document.getElementById('inputPeopleCount').value = preset.people_count;
  if (document.getElementById('sliderAutonomy')) {
    document.getElementById('sliderAutonomy').value = preset.autonomy_hours;
    document.getElementById('valAutonomy').textContent = `${preset.autonomy_hours} h`;
  }
  if (document.getElementById('inputBudget')) document.getElementById('inputBudget').value = preset.budget;
  if (document.getElementById('inputPreference')) document.getElementById('inputPreference').value = preset.preference;

  // Clear & populate cart with preset items
  state.cart.clear();
  preset.items.forEach((item) => {
    const appliance = state.catalog.find((a) => a.appliance_id === item.id);
    if (appliance) {
      state.cart.set(item.id, {
        id: appliance.appliance_id,
        name: appliance.name,
        power_w: appliance.typical_power_w || appliance.rated_power_w || 50,
        hours_per_day: item.hours || appliance.average_daily_hours || 4,
        quantity: item.qty || 1,
        icon: CATEGORY_ICONS[appliance.category] || 'plug',
        category: appliance.category
      });
    }
  });

  renderApplianceGrid();
  renderCart();
}

// Category Filters & Search
function initCategoryFilters() {
  const pills = document.querySelectorAll('.cat-pill');
  const searchInput = document.getElementById('catalogSearch');

  pills.forEach((pill) => {
    pill.addEventListener('click', () => {
      pills.forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      state.activeCategory = pill.dataset.cat;
      renderApplianceGrid();
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderApplianceGrid();
    });
  }
}

// Custom Appliance Form
function initCustomApplianceForm() {
  const btnAdd = document.getElementById('btnAddCustom');
  if (!btnAdd) return;

  btnAdd.addEventListener('click', () => {
    const nameInput = document.getElementById('customName');
    const powerInput = document.getElementById('customPower');
    const hoursInput = document.getElementById('customHours');

    const name = nameInput.value.trim();
    const power = Number(powerInput.value);
    const hours = Number(hoursInput.value) || 2;

    if (!name) {
      alert('Veuillez renseigner le nom de votre appareil.');
      return;
    }
    if (!power || power <= 0) {
      alert('Veuillez renseigner une puissance en Watts valide.');
      return;
    }

    const customId = `custom_${Date.now()}`;
    state.cart.set(customId, {
      id: customId,
      name: name,
      power_w: power,
      hours_per_day: hours,
      quantity: 1,
      icon: 'zap',
      category: 'custom'
    });

    nameInput.value = '';
    powerInput.value = '';
    hoursInput.value = 2;

    renderCart();
    if (window.lucide) lucide.createIcons();
  });
}

// Load Catalog Data from Backend API
async function loadCatalogData() {
  try {
    const res = await fetch('/solar-advisor/catalogs');
    if (!res.ok) throw new Error('Erreur lors du chargement des catalogues.');
    const data = await res.json();
    state.catalog = data.appliances || [];
    state.components = data.components || [];
    renderApplianceGrid();
  } catch (err) {
    console.error('Erreur chargement catalogues:', err);
  }
}

// Render Appliance Cards Grid
function renderApplianceGrid() {
  const container = document.getElementById('catalogCardsGrid');
  if (!container) return;

  const searchQuery = (document.getElementById('catalogSearch')?.value || '').toLowerCase().trim();

  const filtered = state.catalog.filter((item) => {
    const matchesCat = state.activeCategory === 'all' || item.category === state.activeCategory;
    const matchesSearch = !searchQuery || 
      item.name.toLowerCase().includes(searchQuery) ||
      (item.common_name_fr && item.common_name_fr.toLowerCase().includes(searchQuery)) ||
      (item.notes && item.notes.toLowerCase().includes(searchQuery));
    return matchesCat && matchesSearch;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-dim);">
        <p>Aucun appareil ne correspond à votre recherche.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map((item) => {
    const cartItem = state.cart.get(item.appliance_id);
    const qty = cartItem ? cartItem.quantity : 0;
    const iconName = CATEGORY_ICONS[item.category] || 'plug';
    const power = item.typical_power_w || item.rated_power_w || 50;
    const hours = cartItem ? cartItem.hours_per_day : (item.average_daily_hours || 4);

    return `
      <div class="appliance-card ${qty > 0 ? 'is-selected' : ''}" data-id="${item.appliance_id}">
        <div class="appliance-card-top">
          <span class="appliance-icon"><i data-lucide="${iconName}"></i></span>
          <div class="appliance-meta">
            <h4>${item.common_name_fr || item.name}</h4>
            <div class="appliance-specs">
              <span class="spec-badge">${power} W</span>
              <span class="spec-badge">${hours} h/j</span>
            </div>
          </div>
        </div>

        <div class="appliance-card-controls">
          <div class="hours-slider-wrap" title="Heures d'utilisation par jour">
            <i data-lucide="clock" style="width:14px;height:14px;"></i>
            <input type="range" min="0.5" max="24" step="0.5" value="${hours}" class="appliance-hours-slider" data-id="${item.appliance_id}">
            <span>${hours}h</span>
          </div>

          <div class="qty-stepper">
            <button type="button" class="qty-btn btn-minus" data-id="${item.appliance_id}">-</button>
            <span class="qty-val">${qty}</span>
            <button type="button" class="qty-btn btn-plus" data-id="${item.appliance_id}">+</button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Attach card event listeners
  container.querySelectorAll('.btn-plus').forEach((btn) => {
    btn.addEventListener('click', () => {
      updateApplianceQty(btn.dataset.id, 1);
    });
  });

  container.querySelectorAll('.btn-minus').forEach((btn) => {
    btn.addEventListener('click', () => {
      updateApplianceQty(btn.dataset.id, -1);
    });
  });

  container.querySelectorAll('.appliance-hours-slider').forEach((slider) => {
    slider.addEventListener('input', (e) => {
      updateApplianceHours(slider.dataset.id, Number(e.target.value));
    });
  });

  if (window.lucide) lucide.createIcons();
}

function updateApplianceQty(id, delta) {
  const existing = state.cart.get(id);
  const appliance = state.catalog.find((a) => a.appliance_id === id);

  if (existing) {
    const newQty = existing.quantity + delta;
    if (newQty <= 0) {
      state.cart.delete(id);
    } else {
      existing.quantity = newQty;
      state.cart.set(id, existing);
    }
  } else if (delta > 0 && appliance) {
    state.cart.set(id, {
      id: appliance.appliance_id,
      name: appliance.common_name_fr || appliance.name,
      power_w: appliance.typical_power_w || appliance.rated_power_w || 50,
      hours_per_day: appliance.average_daily_hours || 4,
      quantity: 1,
      icon: CATEGORY_ICONS[appliance.category] || 'plug',
      category: appliance.category
    });
  }

  renderApplianceGrid();
  renderCart();
}

function updateApplianceHours(id, hours) {
  const existing = state.cart.get(id);
  if (existing) {
    existing.hours_per_day = hours;
    state.cart.set(id, existing);
    renderCart();
  }
}

// Render Energy Cart Panel
function renderCart() {
  const container = document.getElementById('selectedItemsContainer');
  const badgeCount = document.getElementById('cartCountBadge');
  const livePeakEl = document.getElementById('livePeakPower');
  const liveDailyEl = document.getElementById('liveDailyEnergy');

  if (!container) return;

  const items = Array.from(state.cart.values());

  // Metrics calculation
  let totalPeakW = 0;
  let totalDailyWh = 0;
  let totalItemsCount = 0;

  items.forEach((item) => {
    totalPeakW += item.power_w * item.quantity;
    totalDailyWh += item.power_w * item.quantity * item.hours_per_day;
    totalItemsCount += item.quantity;
  });

  if (badgeCount) badgeCount.textContent = `${totalItemsCount} appareil${totalItemsCount > 1 ? 's' : ''}`;
  if (livePeakEl) livePeakEl.textContent = `${Math.round(totalPeakW)} W`;
  if (liveDailyEl) liveDailyEl.textContent = formatWh(totalDailyWh) + ' / j';

  if (items.length === 0) {
    container.innerHTML = `
      <div class="cart-empty-state">
        <i data-lucide="info"></i>
        <p>Aucun appareil sélectionné.<br>Cliquez sur <strong>+</strong> pour ajouter vos équipements.</p>
      </div>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  container.innerHTML = items.map((item) => {
    const dailyItemWh = Math.round(item.power_w * item.quantity * item.hours_per_day);
    const iconName = item.icon || 'plug';
    return `
      <div class="cart-item-row">
        <div class="cart-item-info">
          <strong><i data-lucide="${iconName}" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></i>${item.name} (${item.quantity}x)</strong>
          <small>${item.power_w}W • ${item.hours_per_day}h/j • <em>${dailyItemWh} Wh/j</em></small>
        </div>
        <button type="button" class="cart-item-del" data-id="${item.id}" title="Retirer cet appareil">
          <i data-lucide="trash-2" style="width:16px;height:16px;"></i>
        </button>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.cart-item-del').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.cart.delete(btn.dataset.id);
      renderApplianceGrid();
      renderCart();
    });
  });

  if (window.lucide) lucide.createIcons();
}

// Generate Solar Sizing & Quote
async function generateQuote() {
  const btn = document.getElementById('btnGenerateQuote');
  if (btn) btn.classList.add('loading');

  const items = Array.from(state.cart.values());
  if (items.length === 0) {
    alert('Veuillez ajouter au moins un équipement à votre panier avant de calculer le devis.');
    if (btn) btn.classList.remove('loading');
    return;
  }

  const payload = {
    customer_id: 'prospect-' + Date.now().toString(36),
    city: document.getElementById('inputCity')?.value || 'Kinshasa',
    region: 'kinshasa',
    housing_type: document.getElementById('inputHousingType')?.value || 'household',
    people_count: Number(document.getElementById('inputPeopleCount')?.value) || 5,
    autonomy_hours: Number(document.getElementById('sliderAutonomy')?.value) || 10,
    budget: Number(document.getElementById('inputBudget')?.value) || 1500000,
    preference: document.getElementById('inputPreference')?.value || 'balanced',
    appliances: items.map((i) => ({
      name: i.name,
      appliance_id: i.id.startsWith('custom_') ? null : i.id,
      quantity: i.quantity,
      hours_per_day: i.hours_per_day,
      power_w: i.power_w,
      usage_period: 'mixed',
      essential: true
    }))
  };

  try {
    const res = await fetch('/solar-advisor/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Erreur lors du dimensionnement.');
    }

    const data = await res.json();
    state.lastRecommendation = data;
    renderQuoteResult(data);

    // Fetch AI explanation in background
    loadAIExplanation(data.recommendation_id);

  } catch (err) {
    console.error('Erreur dimensionnement:', err);
    alert('Impossible de calculer le devis : ' + err.message);
  } finally {
    if (btn) btn.classList.remove('loading');
  }
}

// Render Quote Result View
function renderQuoteResult(rec) {
  const emptyState = document.getElementById('quoteEmptyState');
  const resultContainer = document.getElementById('quoteResultContainer');

  if (emptyState) emptyState.style.display = 'none';
  if (resultContainer) resultContainer.style.display = 'block';

  // Header
  document.getElementById('quoteRef').textContent = rec.recommendation_id;
  document.getElementById('modalRecommendationId').value = rec.recommendation_id;
  document.getElementById('quoteSubtitle').textContent = `Dimensionné pour votre profil ${rec.request.housing_type} à ${rec.request.city}.`;

  // Sizing Cards
  const sizing = rec.sizing;
  const consumption = rec.consumption;
  const quote = rec.quote;

  // PV Card
  document.getElementById('cardPvCount').textContent = `${sizing.panel_count} Panneau${sizing.panel_count > 1 ? 'x' : ''}`;
  document.getElementById('cardPvPower').textContent = `de ${sizing.panel_power_w} Wc (Total ${sizing.pv_total_power_w} Wc)`;

  // Battery Card
  document.getElementById('cardBatteryCount').textContent = `${sizing.battery_count} Batterie${sizing.battery_count > 1 ? 's' : ''} ${sizing.battery_technology || 'LiFePO4'}`;
  document.getElementById('cardBatteryCap').textContent = `${formatWh(sizing.battery_capacity_wh)} utiles`;
  document.getElementById('cardAutonomyHours').textContent = `${sizing.autonomy_hours_estimated}h`;

  // Inverter Card
  document.getElementById('cardInverterPower').textContent = `Onduleur ${sizing.inverter_power_w} W`;
  document.getElementById('cardControllerInfo').textContent = `Régulateur ${sizing.controller_type || 'MPPT'} ${sizing.controller_current_a}A inclus`;
  document.getElementById('cardInverterSurge').textContent = `${sizing.inverter_surge_power_w} W`;

  // Price Card
  document.getElementById('cardTotalPrice').textContent = formatCurrency(quote.total_estimated, quote.currency);
  const paygMonthly = Math.round(quote.total_estimated / 24);
  document.getElementById('cardPaygEstimate').textContent = `Soit env. ${formatCurrency(paygMonthly, quote.currency)} / mois en PAYG`;

  // Budget Match
  const userBudget = rec.request.budget;
  const priceTag = document.getElementById('cardBudgetMatchTag');
  if (userBudget && quote.total_estimated <= userBudget) {
    priceTag.innerHTML = '<i data-lucide="check-circle" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></i> Dans votre budget';
    priceTag.style.color = 'var(--color-emerald)';
  } else if (userBudget) {
    priceTag.innerHTML = '<i data-lucide="alert-triangle" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></i> Budget indicatif dépassé';
    priceTag.style.color = 'var(--color-primary)';
  }

  // Equipment Table
  const tbody = document.getElementById('quoteTableBody');
  tbody.innerHTML = quote.items.map((item) => `
    <tr>
      <td><strong>${item.designation}</strong><br><small style="color:var(--text-dim)">${item.description || ''}</small></td>
      <td>${item.quantity}</td>
      <td>${formatCurrency(item.unit_price, quote.currency)}</td>
      <td><strong>${formatCurrency(item.total_price, quote.currency)}</strong></td>
    </tr>
  `).join('');

  document.getElementById('quoteTableTotal').innerHTML = `<strong>${formatCurrency(quote.total_estimated, quote.currency)}</strong>`;

  // Audit Metrics
  document.getElementById('auditRawEnergy').textContent = formatWh(consumption.total_daily_energy_wh) + ' / jour';
  document.getElementById('auditAdjustedEnergy').textContent = formatWh(consumption.adjusted_daily_energy_wh) + ' / jour';
  document.getElementById('auditPeakPower').textContent = `${Math.round(consumption.simultaneous_power_w)} W`;
  const annualKwh = Math.round((consumption.adjusted_daily_energy_wh * 365) / 1000);
  document.getElementById('auditAnnualEnergy').textContent = `${annualKwh} kWh / an`;
  document.getElementById('auditCo2Saved').textContent = `${Math.round(annualKwh * 0.61)} kg CO₂ / an`;

  // Print button handler
  document.getElementById('btnPrintQuote').onclick = () => window.print();

  if (window.lucide) lucide.createIcons();
}

// Load AI Explanation
async function loadAIExplanation(recommendationId) {
  const explanationEl = document.getElementById('aiExplanationBody');
  const badgeEl = document.getElementById('aiModelBadge');

  if (explanationEl) {
    explanationEl.innerHTML = '<p><em>Rédaction de l\'explication personnalisée par l\'IA DJUA...</em></p>';
  }

  try {
    const res = await fetch(`/solar-advisor/recommendations/${recommendationId}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audience: 'client' })
    });

    if (res.ok) {
      const data = await res.json();
      if (explanationEl) {
        explanationEl.innerHTML = `<p>${data.explanation.replace(/\n/g, '<br>')}</p>`;
      }
      if (badgeEl && data.used_ai) {
        badgeEl.innerHTML = `<i data-lucide="sparkles"></i> IA Active (${data.model || 'LLM'})`;
      }
    }
  } catch (err) {
    console.error('Erreur explication IA:', err);
    if (explanationEl) {
      explanationEl.innerHTML = '<p>Le devis a été dimensionné avec précision selon vos appareils déclarés.</p>';
    }
  }
  if (window.lucide) lucide.createIcons();
}

// Quick Follow-up Question Chips & Ask Advisor Form
function initQuickQuestions() {
  const chips = document.querySelectorAll('.qa-chip');
  const form = document.getElementById('formAskAdvisor');
  const input = document.getElementById('inputCustomQuestion');

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      const q = chip.dataset.q;
      if (input) input.value = q;
      askAdvisorQuestion(q);
    });
  });

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (q) askAdvisorQuestion(q);
    });
  }
}

async function askAdvisorQuestion(question) {
  if (!state.lastRecommendation) {
    alert('Veuillez d\'abord calculer votre devis.');
    return;
  }

  const answerCard = document.getElementById('aiAnswerCard');
  const answerText = document.getElementById('aiAnswerText');
  const btnSubmit = document.getElementById('btnSubmitQuestion');

  if (answerCard) answerCard.style.display = 'block';
  if (answerText) answerText.innerHTML = '<em>L\'Advisor formule votre réponse basée sur votre devis...</em>';
  if (btnSubmit) btnSubmit.disabled = true;

  try {
    const res = await fetch(`/solar-advisor/recommendations/${state.lastRecommendation.recommendation_id}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question })
    });

    if (!res.ok) throw new Error('Erreur lors de la réponse.');
    const data = await res.json();
    if (answerText) {
      answerText.innerHTML = data.answer.replace(/\n/g, '<br>');
    }
  } catch (err) {
    if (answerText) {
      answerText.textContent = 'Désolé, impossible de répondre pour le moment. Veuillez réessayer.';
    }
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
    if (window.lucide) lucide.createIcons();
  }
}

// Contact Callback Modal
function initContactModal() {
  const modal = document.getElementById('contactModal');
  const btnOpen = document.getElementById('btnOpenContactModal');
  const btnOpen2 = document.getElementById('btnRequestCallback');
  const btnClose = document.getElementById('btnCloseModal');
  const btnCancel = document.getElementById('btnCancelModal');
  const btnFinish = document.getElementById('btnFinishModal');
  const form = document.getElementById('formContactRequest');
  const formSection = document.getElementById('formContactRequest');
  const successState = document.getElementById('modalSuccessState');

  function openModal() {
    if (modal) {
      modal.style.display = 'grid';
      formSection.style.display = 'block';
      successState.style.display = 'none';
    }
  }

  function closeModal() {
    if (modal) modal.style.display = 'none';
  }

  if (btnOpen) btnOpen.addEventListener('click', openModal);
  if (btnOpen2) btnOpen2.addEventListener('click', openModal);
  if (btnClose) btnClose.addEventListener('click', closeModal);
  if (btnCancel) btnCancel.addEventListener('click', closeModal);
  if (btnFinish) btnFinish.addEventListener('click', closeModal);

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const recId = document.getElementById('modalRecommendationId').value;
      if (!recId) {
        alert('Erreur: aucun devis associé.');
        return;
      }

      const payload = {
        name: document.getElementById('contactName').value,
        phone: document.getElementById('contactPhone').value,
        email: document.getElementById('contactEmail').value,
        message: document.getElementById('contactMessage').value
      };

      try {
        const res = await fetch(`/solar-advisor/recommendations/${recId}/contact`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Erreur lors de la réservation.');
        formSection.style.display = 'none';
        successState.style.display = 'block';
      } catch (err) {
        alert('Impossible d\'enregistrer la demande: ' + err.message);
      }
    });
  }
}

// Conversational Assistant Mode
function initChatForm() {
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInputText');
  const messagesArea = document.getElementById('chatMessagesArea');
  const clearBtn = document.getElementById('btnClearChat');

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      state.chatContext = { history: [], request: {} };
      if (messagesArea) {
        messagesArea.innerHTML = `
          <div class="chat-bubble assistant">
            <div class="bubble-avatar"><i data-lucide="bot"></i></div>
            <div class="bubble-text">
              <p>Bonjour ! Je suis <strong>DJUA AI Solar Advisor</strong>.</p>
              <p>Décrivez-moi simplement vos appareils et votre ville pour préparer votre kit solaire.</p>
            </div>
          </div>
        `;
      }
      if (window.lucide) lucide.createIcons();
    });
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = input.value.trim();
      if (!msg) return;

      appendChatMessage('user', msg);
      input.value = '';

      try {
        const res = await fetch('/solar-advisor/conversation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: msg,
            context: state.chatContext.request
          })
        });

        if (!res.ok) throw new Error('Erreur de communication.');
        const data = await res.json();
        state.chatContext.request = data.request;

        appendChatMessage('assistant', data.assistant_message);

        // If the AI updated appliances, sync to cart and state!
        if (data.request && data.request.appliances && data.request.appliances.length > 0) {
          syncChatToCart(data.request);
        }

        // If a recommendation is ready, display it!
        if (data.can_recommend && data.recommendation) {
          state.lastRecommendation = data.recommendation;
          renderQuoteResult(data.recommendation);
          appendChatMessage('assistant', `<strong>Votre devis complet a été calculé avec succès !</strong> Rendez-vous sur l'onglet <em>Configurateur Visuel (Étape 3)</em> pour voir tous les détails.`);
        }

      } catch (err) {
        appendChatMessage('assistant', 'Désolé, une erreur est survenue lors de l\'échange. Veuillez réessayer.');
      }
    });
  }
}

function appendChatMessage(sender, text) {
  const area = document.getElementById('chatMessagesArea');
  if (!area) return;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${sender}`;
  bubble.innerHTML = `
    <div class="bubble-avatar"><i data-lucide="${sender === 'assistant' ? 'bot' : 'user'}"></i></div>
    <div class="bubble-text"><p>${text.replace(/\n/g, '<br>')}</p></div>
  `;
  area.appendChild(bubble);
  area.scrollTop = area.scrollHeight;
  if (window.lucide) lucide.createIcons();
}

function syncChatToCart(extractedRequest) {
  if (!extractedRequest.appliances) return;

  extractedRequest.appliances.forEach((app) => {
    const id = app.appliance_id || `chat_${app.name}`;
    const catalogItem = state.catalog.find((c) => c.appliance_id === app.appliance_id);

    state.cart.set(id, {
      id: id,
      name: app.name,
      power_w: app.power_w || (catalogItem ? (catalogItem.typical_power_w || catalogItem.rated_power_w) : 50),
      hours_per_day: app.hours_per_day || (catalogItem ? catalogItem.average_daily_hours : 4),
      quantity: app.quantity || 1,
      icon: catalogItem ? (CATEGORY_ICONS[catalogItem.category] || 'plug') : 'zap',
      category: catalogItem ? catalogItem.category : 'custom'
    });
  });

  if (extractedRequest.city && document.getElementById('inputCity')) {
    document.getElementById('inputCity').value = extractedRequest.city;
  }
  if (extractedRequest.autonomy_hours && document.getElementById('sliderAutonomy')) {
    document.getElementById('sliderAutonomy').value = extractedRequest.autonomy_hours;
    document.getElementById('valAutonomy').textContent = `${extractedRequest.autonomy_hours} h`;
  }

  renderApplianceGrid();
  renderCart();
}
