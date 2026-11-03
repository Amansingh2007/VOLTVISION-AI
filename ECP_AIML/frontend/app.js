/* ======================================================
   VOLTVISION AI - JAVASCRIPT APPLICATION ENGINE
   Auth, Prediction Model, Chart.js Visuals, Analytics
   python -m uvicorn main:app --reload
   cd "C:\Users\KRISHNA YADAV\OneDrive\Desktop\ECP_AIML\backend"
   ====================================================== */

// ================= BACKEND API CONFIGURATION =================
// Automatically points to origin if served from FastAPI (e.g. port 8000), or localhost:8000
const API_BASE_URL = (window.location.protocol.startsWith('http') && (window.location.port === '8000' || window.location.port === ''))
  ? window.location.origin
  : 'http://127.0.0.1:8000';

// Application State
const state = {
  user: null,
  isNewUser: false,
  currency: 'INR', // 'INR' or 'USD'
  fxRate: 0.012,   // 1 INR ~ 0.012 USD
  activeSection: 'dashboard',
  prediction: {
    bhk: 3,
    occupants: 4,
    season: 'summer',
    temp: 36,
    
    // 12 Appliances State
    acEnabled: true,
    acUnits: 2,
    acHours: 8,
    acStar: 5,

    ceilingFanEnabled: true,
    ceilingFanUnits: 3,
    ceilingFanHours: 10,
    ceilingFanType: 'standard',

    tableFanEnabled: false,
    tableFanUnits: 1,
    tableFanHours: 6,

    waterPumpEnabled: true,
    waterPumpHp: 1.0,
    waterPumpHours: 1.0,
    waterPumpTiming: 'morning',

    geyserEnabled: true,
    geyserUnits: 2,
    geyserHours: 1.5,

    fridgeEnabled: true,
    fridgeType: '3star-double',

    mixerEnabled: true,
    mixerMinutes: 20,

    ledBulbsEnabled: true,
    ledBulbsUnits: 8,
    ledBulbsHours: 6,

    tvEnabled: true,
    tvUnits: 1,
    tvHours: 4,

    wmEnabled: true,
    wmLoads: 4,

    solarEnabled: true,
    solarKw: 1.5,

    evEnabled: false,
    evKm: 20,
    
    // Calculated results
    totalKwh: 412,
    grossKwh: 592,
    solarGenKwh: 180,
    totalBill: 3296,
    tierBreakdown: {},
    breakdown: {},
    applianceItems: [],
    activeAppliancesCount: 8,
    topConsumer: null,
    pumpTimingAdvisory: null,
    efficiencyGrade: 'A',
    efficiencyScore: 82,
    carbonKg: 338,
    peakKw: 2.8,
    optimizerTip: ''
  },
  charts: {
    trend: null,
    mlForecast: null,
    backendDailyForecast: null,
    appliance: null
  }
};

// ================= INITIALIZATION =================
document.addEventListener('DOMContentLoaded', () => {
  checkStoredAuth();
  initCharts();

  if (state.isNewUser) {
    initZeroState();
  } else {
    // Check if saved prediction is stored in database/localStorage
    const saved = localStorage.getItem('voltvision_saved_prediction');
    if (saved) {
      try {
        const p = JSON.parse(saved);
        state.prediction = { ...state.prediction, ...p };
        updateUIResults();
        updateSpeedometer();
        updateCharts();
        renderApplianceBreakdownList();
      } catch (_) {
        runPrediction();
      }
    } else {
      runPrediction();
    }
  }

  runWhatIf();
  checkBackendHealth();
});

// ================= APPLIANCE SELECTION & TOGGLE ENGINE =================
const APPLIANCE_IDS = [
  'ac', 'ceiling-fan', 'table-fan', 'water-pump',
  'geyser', 'fridge', 'mixer', 'led-bulbs',
  'tv', 'wm', 'solar', 'ev'
];

function toggleAppliance(id) {
  const toggle = document.getElementById(`toggle-${id}`);
  const isChecked = toggle ? toggle.checked : false;
  const badge = document.getElementById(`badge-${id}`);
  const card = document.getElementById(`card-${id}`);

  if (badge) {
    badge.textContent = isChecked ? 'Included' : 'Not Owned';
    badge.className = `toggle-status-badge ${isChecked ? 'status-active' : 'status-off'}`;
  }
  if (card) {
    card.classList.toggle('disabled-card', !isChecked);
  }
  runPrediction();
}

function toggleAllAppliances(enable) {
  APPLIANCE_IDS.forEach(id => {
    const toggle = document.getElementById(`toggle-${id}`);
    const badge = document.getElementById(`badge-${id}`);
    const card = document.getElementById(`card-${id}`);
    if (toggle) toggle.checked = enable;
    if (badge) {
      badge.textContent = enable ? 'Included' : 'Not Owned';
      badge.className = `toggle-status-badge ${enable ? 'status-active' : 'status-off'}`;
    }
    if (card) {
      card.classList.toggle('disabled-card', !enable);
    }
  });
  runPrediction();
  showToast(`All appliances ${enable ? 'enabled' : 'disabled'}`);
}

function filterApplianceCategory(category, buttonEl) {
  const pills = document.querySelectorAll('.appliance-filter-pills .filter-pill-btn');
  pills.forEach(btn => btn.classList.remove('active'));
  if (buttonEl) buttonEl.classList.add('active');

  const cards = document.querySelectorAll('.appliance-input-card');
  cards.forEach(card => {
    const cat = card.getAttribute('data-category');
    if (category === 'all' || cat === category) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

// ================= ZERO STATE FOR NEW USERS =================
function setZeroFormControls() {
  APPLIANCE_IDS.forEach(id => {
    const toggle = document.getElementById(`toggle-${id}`);
    const badge = document.getElementById(`badge-${id}`);
    const card = document.getElementById(`card-${id}`);
    if (toggle) toggle.checked = false;
    if (badge) {
      badge.textContent = 'Not Owned';
      badge.className = 'toggle-status-badge status-off';
    }
    if (card) {
      card.classList.add('disabled-card');
    }
  });

  const zeroSliders = [
    { id: 'ac-units', val: '0' },
    { id: 'ac-hours', val: '0' },
    { id: 'ceiling-fan-units', val: '0' },
    { id: 'ceiling-fan-hours', val: '0' },
    { id: 'table-fan-units', val: '0' },
    { id: 'table-fan-hours', val: '0' },
    { id: 'water-pump-hours', val: '0' },
    { id: 'geyser-units', val: '0' },
    { id: 'geyser-hours', val: '0' },
    { id: 'mixer-minutes', val: '0' },
    { id: 'led-bulbs-units', val: '0' },
    { id: 'led-bulbs-hours', val: '0' },
    { id: 'tv-units', val: '0' },
    { id: 'tv-hours', val: '0' },
    { id: 'wm-loads', val: '0' },
    { id: 'solar-kw', val: '0' },
    { id: 'ev-km', val: '0' }
  ];
  zeroSliders.forEach(item => {
    const el = document.getElementById(`param-${item.id}`);
    const disp = document.getElementById(`val-${item.id}`);
    if (el) el.value = item.val;
    if (disp) disp.textContent = item.val;
  });
}

function initZeroState() {
  state.isNewUser = true;
  state.prediction = {
    bhk: 1,
    occupants: 1,
    season: 'summer',
    temp: 32,

    acEnabled: false,
    acUnits: 0,
    acHours: 0,
    acStar: 5,

    ceilingFanEnabled: false,
    ceilingFanUnits: 0,
    ceilingFanHours: 0,
    ceilingFanType: 'standard',

    tableFanEnabled: false,
    tableFanUnits: 0,
    tableFanHours: 0,

    waterPumpEnabled: false,
    waterPumpHp: 0.5,
    waterPumpHours: 0,
    waterPumpTiming: 'morning',

    geyserEnabled: false,
    geyserUnits: 0,
    geyserHours: 0,

    fridgeEnabled: false,
    fridgeType: 'single',

    mixerEnabled: false,
    mixerMinutes: 0,

    ledBulbsEnabled: false,
    ledBulbsUnits: 0,
    ledBulbsHours: 0,

    tvEnabled: false,
    tvUnits: 0,
    tvHours: 0,

    wmEnabled: false,
    wmLoads: 0,

    solarEnabled: false,
    solarKw: 0,

    evEnabled: false,
    evKm: 0,

    totalKwh: 0,
    grossKwh: 0,
    solarGenKwh: 0,
    totalBill: 0,
    solarCredit: 0,
    tierBreakdown: {
      slab1: 0,
      slab2: 0,
      slab3: 0,
      slab4: 0,
      fixed: 0
    },
    breakdown: {
      cooling: 0,
      waterHeating: 0,
      refrigeration: 0,
      baseLoad: 0,
      evAndAppliances: 0
    },
    applianceItems: [],
    activeAppliancesCount: 0,
    topConsumer: null,
    pumpTimingAdvisory: null,
    efficiencyGrade: '--',
    efficiencyScore: 0,
    carbonKg: 0,
    peakKw: 0.0,
    optimizerTip: '👋 Welcome! Connection registered with 0 kWh usage. Head to the <strong>AI Predictor</strong> tab to configure your property and appliances to generate your forecast.',
    chartData: null
  };

  setZeroFormControls();
  updateUIResults();
  updateSpeedometer();
  renderApplianceBreakdownList();
  updateCharts();
}

// ================= AUTHENTICATION LOGIC =================
function checkStoredAuth() {
  const storedUser = localStorage.getItem('voltvision_user');
  if (storedUser) {
    try {
      state.user = JSON.parse(storedUser);
      state.isNewUser = Boolean(state.user.isNewUser || !state.user.hasPrediction);
      if (state.user.bhk) state.prediction.bhk = state.user.bhk;
      if (state.user.occupants) state.prediction.occupants = state.user.occupants;
      if (state.user.solarKw !== undefined) state.prediction.solarKw = state.user.solarKw;
      showAppView();
    } catch (e) {
      showAuthView();
    }
  } else {
    showAuthView();
  }
}

function switchAuthTab(tab) {
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-register').classList.toggle('active', tab === 'register');
  document.getElementById('login-form').classList.toggle('active', tab === 'login');
  document.getElementById('register-form').classList.toggle('active', tab === 'register');
}

async function handleLogin(e) {
  e.preventDefault();
  const consumerId = document.getElementById('login-consumer-id').value.trim();
  const password = document.getElementById('login-password').value;

  if (!consumerId || !password) {
    showToast('⚠️ Please provide your Consumer ID and password');
    return;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier: consumerId, password: password })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.prediction) {
        localStorage.setItem('voltvision_saved_prediction', JSON.stringify(data.prediction));
        state.isNewUser = false;
        state.prediction = { ...state.prediction, ...data.prediction };
      } else {
        localStorage.removeItem('voltvision_saved_prediction');
        state.isNewUser = true;
      }
      const user = {
        ...data.user,
        hasPrediction: Boolean(data.prediction),
        isNewUser: !data.prediction
      };
      loginSuccess(user, '✅ Welcome back, ' + data.user.name);
      if (state.isNewUser) {
        initZeroState();
      } else {
        updateUIResults();
        updateSpeedometer();
        updateCharts();
        renderApplianceBreakdownList();
      }
      return;
    } else {
      const err = await res.json().catch(() => ({}));
      showToast('⚠️ ' + (err.detail || 'Invalid login credentials'));
      return;
    }
  } catch (_) {
    // Offline / Demo fallback
    const isDemo = consumerId.toUpperCase() === 'CA-984210';
    const user = {
      name: consumerId.includes('@') ? consumerId.split('@')[0] : (isDemo ? 'Aman Sharma' : 'Consumer ' + consumerId),
      consumerId: consumerId.toUpperCase(),
      sanctionedLoad: 5.0,
      hasPrediction: isDemo,
      isNewUser: !isDemo,
      connectionDate: '2022-04-10'
    };
    state.isNewUser = !isDemo;
    loginSuccess(user);
    if (state.isNewUser) {
      initZeroState();
    } else {
      runPrediction();
    }
  }
}

function loginAsDemo() {
  const demoUser = {
    name: 'Aman Sharma',
    consumerId: 'CA-984210',
    sanctionedLoad: 5.0,
    hasPrediction: true,
    isNewUser: false,
    connectionDate: '2023-01-15'
  };
  state.isNewUser = false;
  loginSuccess(demoUser, '⚡ Signed in with Demo Account!');
  runPrediction();
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById('reg-name').value.trim();
  const consumerId = document.getElementById('reg-consumer-id').value.trim();
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password')?.value || 'password123';

  if (!name || !consumerId || !email) {
    showToast('⚠️ Please fill in all fields');
    return;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        consumer_id: consumerId.toUpperCase(),
        email: email,
        password: password
      })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast('⚠️ ' + (data.detail || 'Registration failed'));
      return;
    }

    localStorage.removeItem('voltvision_saved_prediction');
    state.isNewUser = true;
    loginSuccess(data.user, '🎉 Registration Successful! Smart meter initialized at 0 kWh.');
    initZeroState();
  } catch (err) {
    // Offline mode
    localStorage.removeItem('voltvision_saved_prediction');
    const user = {
      name: name,
      consumerId: consumerId.toUpperCase(),
      email: email,
      sanctionedLoad: 5.0,
      hasPrediction: false,
      isNewUser: true,
      connectionDate: new Date().toISOString().split('T')[0]
    };
    state.isNewUser = true;
    loginSuccess(user, '🎉 Registration Saved (Offline Mode).');
    initZeroState();
  }
}

function loginSuccess(user, message = '✅ Welcome back, ' + user.name) {
  state.user = user;
  localStorage.setItem('voltvision_user', JSON.stringify(user));
  showAppView();
  showToast(message);
}

function handleLogout() {
  localStorage.removeItem('voltvision_user');
  state.user = null;
  showToast('👋 Logged out successfully. Redirecting to Login Portal...');
  setTimeout(() => {
    window.location.href = 'login.html';
  }, 600);
}

function showAuthView() {
  document.getElementById('auth-view').classList.remove('hidden');
  document.getElementById('app-view').classList.add('hidden');
}

function showAppView() {
  document.getElementById('auth-view').classList.add('hidden');
  document.getElementById('app-view').classList.remove('hidden');
  
  // Populate user header
  if (state.user) {
    document.getElementById('nav-username').textContent = state.user.name;
    document.getElementById('dash-greeting-name').textContent = state.user.name.split(' ')[0];
    document.getElementById('nav-cid').textContent = state.user.consumerId;
    
    // Avatar initials
    const initials = state.user.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('nav-avatar').textContent = initials || 'AS';
  }

  if (state.isNewUser) {
    initZeroState();
  }
}

function togglePassword(inputId) {
  const input = document.getElementById(inputId);
  input.type = input.type === 'password' ? 'text' : 'password';
}

// ================= NAVIGATION =================
function switchSection(sectionId) {
  state.activeSection = sectionId;
  
  // Toggle nav buttons
  const navButtons = document.querySelectorAll('.nav-link');
  navButtons.forEach(btn => {
    const onclickAttr = btn.getAttribute('onclick') || '';
    btn.classList.toggle('active', onclickAttr.includes(sectionId));
  });

  // Toggle sections
  const sections = document.querySelectorAll('.content-section');
  sections.forEach(sec => {
    sec.classList.toggle('active', sec.id === `section-${sectionId}`);
  });

  // Re-render / resize charts once section is visible
  requestAnimationFrame(() => {
    if (sectionId === 'dashboard' && state.charts.trend) {
      state.charts.trend.resize();
      updateCharts();
    }
    if (sectionId === 'breakdown' && state.charts.appliance) {
      state.charts.appliance.resize();
      updateCharts();
    }
  });

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ================= CURRENCY TOGGLE =================
function setCurrency(curr) {
  state.currency = curr;
  document.getElementById('curr-inr').classList.toggle('active', curr === 'INR');
  document.getElementById('curr-usd').classList.toggle('active', curr === 'USD');

  // Update header tariff indicator
  const tariffText = curr === 'INR' ? '₹7.20 / kWh' : '$0.086 / kWh';
  document.getElementById('header-tariff').textContent = tariffText;

  // Re-run displays
  updateUIResults();
  runWhatIf();
  showToast(`Currency changed to ${curr}`);
}

function formatMoney(amountInInr) {
  if (state.currency === 'INR') {
    return '₹' + Math.round(amountInInr).toLocaleString('en-IN');
  } else {
    const usd = amountInInr * state.fxRate;
    return '$' + usd.toFixed(2);
  }
}

// ================= SLIDER VALUE LISTENERS =================
function updateSliderVal(id) {
  const el = document.getElementById(`param-${id}`);
  const display = document.getElementById(`val-${id}`);
  if (el && display) {
    display.textContent = el.value;
  }
}

function resetToDefaults() {
  document.getElementById('param-bhk').value = '3';
  document.getElementById('param-occupants').value = '4';
  document.getElementById('param-season').value = 'summer';
  document.getElementById('param-temp').value = '36';

  // 12 Appliances Defaults
  const defaults = [
    { id: 'ac', enabled: true, values: [{ param: 'ac-units', val: '2' }, { param: 'ac-hours', val: '8' }] },
    { id: 'ceiling-fan', enabled: true, values: [{ param: 'ceiling-fan-units', val: '3' }, { param: 'ceiling-fan-hours', val: '10' }] },
    { id: 'table-fan', enabled: false, values: [{ param: 'table-fan-units', val: '1' }, { param: 'table-fan-hours', val: '6' }] },
    { id: 'water-pump', enabled: true, values: [{ param: 'water-pump-hours', val: '1.0' }] },
    { id: 'geyser', enabled: true, values: [{ param: 'geyser-units', val: '2' }, { param: 'geyser-hours', val: '1.5' }] },
    { id: 'fridge', enabled: true, values: [] },
    { id: 'mixer', enabled: true, values: [{ param: 'mixer-minutes', val: '20' }] },
    { id: 'led-bulbs', enabled: true, values: [{ param: 'led-bulbs-units', val: '8' }, { param: 'led-bulbs-hours', val: '6' }] },
    { id: 'tv', enabled: true, values: [{ param: 'tv-units', val: '1' }, { param: 'tv-hours', val: '4' }] },
    { id: 'wm', enabled: true, values: [{ param: 'wm-loads', val: '4' }] },
    { id: 'solar', enabled: true, values: [{ param: 'solar-kw', val: '1.5' }] },
    { id: 'ev', enabled: false, values: [{ param: 'ev-km', val: '20' }] }
  ];

  defaults.forEach(app => {
    const toggle = document.getElementById(`toggle-${app.id}`);
    const badge = document.getElementById(`badge-${app.id}`);
    const card = document.getElementById(`card-${app.id}`);
    if (toggle) toggle.checked = app.enabled;
    if (badge) {
      badge.textContent = app.enabled ? 'Included' : 'Not Owned';
      badge.className = `toggle-status-badge ${app.enabled ? 'status-active' : 'status-off'}`;
    }
    if (card) {
      card.classList.toggle('disabled-card', !app.enabled);
    }
    app.values.forEach(v => {
      const el = document.getElementById(`param-${v.param}`);
      const disp = document.getElementById(`val-${v.param}`);
      if (el) el.value = v.val;
      if (disp) disp.textContent = v.val;
    });
  });

  const acStarEl = document.getElementById('param-ac-star');
  if (acStarEl) acStarEl.value = '5';
  const cfanTypeEl = document.getElementById('param-ceiling-fan-type');
  if (cfanTypeEl) cfanTypeEl.value = 'standard';
  const pumpHpEl = document.getElementById('param-water-pump-hp');
  if (pumpHpEl) pumpHpEl.value = '1.0';
  const pumpTimingEl = document.getElementById('param-water-pump-timing');
  if (pumpTimingEl) pumpTimingEl.value = 'morning';
  const fridgeEl = document.getElementById('param-fridge');
  if (fridgeEl) fridgeEl.value = '3star-double';

  ['occupants', 'temp'].forEach(updateSliderVal);

  runPrediction();
  showToast('🔄 Reset to standard 3-BHK household presets');
}

// ================= BACKEND ML PREDICTION ENGINE =================
// Formula-based local calculations have been removed. All predictions are computed by the FastAPI ML backend.
let predictionDebounceTimer = null;

function runPrediction() {
  if (predictionDebounceTimer) {
    clearTimeout(predictionDebounceTimer);
  }
  predictionDebounceTimer = setTimeout(() => {
    fetchBackendPrediction();
  }, 120);
}

async function fetchBackendPrediction() {
  // 1. Gather all input values from user controls (12 appliances)
  const payload = {
    bhk: parseInt(document.getElementById('param-bhk')?.value || 3),
    occupants: parseInt(document.getElementById('param-occupants')?.value || 4),
    season: document.getElementById('param-season')?.value || 'summer',
    temperature_c: parseFloat(document.getElementById('param-temp')?.value || 36),

    // 1. AC
    ac_enabled: document.getElementById('toggle-ac') ? document.getElementById('toggle-ac').checked : true,
    ac_units: parseInt(document.getElementById('param-ac-units')?.value || 2),
    ac_hours: parseFloat(document.getElementById('param-ac-hours')?.value || 8),
    ac_star: parseInt(document.getElementById('param-ac-star')?.value || 5),

    // 2. Ceiling Fan
    ceiling_fan_enabled: document.getElementById('toggle-ceiling-fan') ? document.getElementById('toggle-ceiling-fan').checked : true,
    ceiling_fan_units: parseInt(document.getElementById('param-ceiling-fan-units')?.value || 3),
    ceiling_fan_hours: parseFloat(document.getElementById('param-ceiling-fan-hours')?.value || 10),
    ceiling_fan_type: document.getElementById('param-ceiling-fan-type')?.value || 'standard',

    // 3. Table Fan
    table_fan_enabled: document.getElementById('toggle-table-fan') ? document.getElementById('toggle-table-fan').checked : false,
    table_fan_units: parseInt(document.getElementById('param-table-fan-units')?.value || 1),
    table_fan_hours: parseFloat(document.getElementById('param-table-fan-hours')?.value || 6),

    // 4. Water Pump
    water_pump_enabled: document.getElementById('toggle-water-pump') ? document.getElementById('toggle-water-pump').checked : true,
    water_pump_hp: parseFloat(document.getElementById('param-water-pump-hp')?.value || 1.0),
    water_pump_hours: parseFloat(document.getElementById('param-water-pump-hours')?.value || 1.0),
    water_pump_timing: document.getElementById('param-water-pump-timing')?.value || 'morning',

    // 5. Geyser
    geyser_enabled: document.getElementById('toggle-geyser') ? document.getElementById('toggle-geyser').checked : true,
    geyser_units: parseInt(document.getElementById('param-geyser-units')?.value || 2),
    geyser_hours: parseFloat(document.getElementById('param-geyser-hours')?.value || 1.5),

    // 6. Refrigerator
    fridge_enabled: document.getElementById('toggle-fridge') ? document.getElementById('toggle-fridge').checked : true,
    fridge_type: document.getElementById('param-fridge')?.value || '3star-double',

    // 7. Mixer Grinder
    mixer_enabled: document.getElementById('toggle-mixer') ? document.getElementById('toggle-mixer').checked : true,
    mixer_minutes: parseFloat(document.getElementById('param-mixer-minutes')?.value || 20),

    // 8. LED Bulbs
    led_bulbs_enabled: document.getElementById('toggle-led-bulbs') ? document.getElementById('toggle-led-bulbs').checked : true,
    led_bulbs_units: parseInt(document.getElementById('param-led-bulbs-units')?.value || 8),
    led_bulbs_hours: parseFloat(document.getElementById('param-led-bulbs-hours')?.value || 6),

    // 9. TV
    tv_enabled: document.getElementById('toggle-tv') ? document.getElementById('toggle-tv').checked : true,
    tv_units: parseInt(document.getElementById('param-tv-units')?.value || 1),
    tv_hours: parseFloat(document.getElementById('param-tv-hours')?.value || 4),

    // 10. Washing Machine
    wm_enabled: document.getElementById('toggle-wm') ? document.getElementById('toggle-wm').checked : true,
    wm_loads: parseInt(document.getElementById('param-wm-loads')?.value || 4),

    // 11. Rooftop Solar
    solar_enabled: document.getElementById('toggle-solar') ? document.getElementById('toggle-solar').checked : true,
    solar_kw: parseFloat(document.getElementById('param-solar-kw')?.value || 1.5),

    // 12. EV
    ev_enabled: document.getElementById('toggle-ev') ? document.getElementById('toggle-ev').checked : false,
    ev_km: parseFloat(document.getElementById('param-ev-km')?.value || 20)
  };

  showPredictionLoading(true);

  try {
    const res = await fetch(`${API_BASE_URL}/predict/bill`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      throw new Error(`API error HTTP ${res.status}`);
    }

    const data = await res.json();

    // Store ML results returned from backend in State
    state.prediction = {
      bhk: payload.bhk,
      occupants: payload.occupants,
      season: payload.season,
      temp: payload.temperature_c,

      acEnabled: payload.ac_enabled,
      acUnits: payload.ac_units,
      acHours: payload.ac_hours,
      acStar: payload.ac_star,

      ceilingFanEnabled: payload.ceiling_fan_enabled,
      ceilingFanUnits: payload.ceiling_fan_units,
      ceilingFanHours: payload.ceiling_fan_hours,
      ceilingFanType: payload.ceiling_fan_type,

      tableFanEnabled: payload.table_fan_enabled,
      tableFanUnits: payload.table_fan_units,
      tableFanHours: payload.table_fan_hours,

      waterPumpEnabled: payload.water_pump_enabled,
      waterPumpHp: payload.water_pump_hp,
      waterPumpHours: payload.water_pump_hours,
      waterPumpTiming: payload.water_pump_timing,

      geyserEnabled: payload.geyser_enabled,
      geyserUnits: payload.geyser_units,
      geyserHours: payload.geyser_hours,

      fridgeEnabled: payload.fridge_enabled,
      fridgeType: payload.fridge_type,

      mixerEnabled: payload.mixer_enabled,
      mixerMinutes: payload.mixer_minutes,

      ledBulbsEnabled: payload.led_bulbs_enabled,
      ledBulbsUnits: payload.led_bulbs_units,
      ledBulbsHours: payload.led_bulbs_hours,

      tvEnabled: payload.tv_enabled,
      tvUnits: payload.tv_units,
      tvHours: payload.tv_hours,

      wmEnabled: payload.wm_enabled,
      wmLoads: payload.wm_loads,

      solarEnabled: payload.solar_enabled,
      solarKw: payload.solar_kw,

      evEnabled: payload.ev_enabled,
      evKm: payload.ev_km,

      totalKwh: data.totalKwh ?? data.total_kwh,
      grossKwh: data.grossKwh ?? data.gross_kwh,
      solarGenKwh: data.solarGenKwh ?? data.solar_gen_kwh,
      totalBill: data.totalBill ?? data.total_bill,
      solarCredit: data.solarCredit ?? data.solar_credit,
      tierBreakdown: data.tierBreakdown ?? data.tier_breakdown,
      breakdown: data.breakdown,
      applianceItems: data.appliance_items || data.applianceItems || [],
      activeAppliancesCount: data.active_appliances_count ?? 0,
      topConsumer: data.top_consumer || null,
      pumpTimingAdvisory: data.pump_timing_advisory || null,
      efficiencyGrade: data.efficiencyGrade ?? data.efficiency_grade,
      efficiencyScore: data.efficiencyScore ?? data.efficiency_score,
      carbonKg: data.carbonKg ?? data.carbon_kg,
      peakKw: data.peakKw ?? data.peak_kw,
      optimizerTip: data.optimizerTip ?? data.optimizer_tip,
      source: data.source || 'backend_ml_engine',
      chartData: data.chart_data || data.chartData
    };

    // User has configured data — clear new user zero state
    state.isNewUser = false;
    if (state.user) {
      state.user.hasPrediction = true;
      state.user.isNewUser = false;
      localStorage.setItem('voltvision_user', JSON.stringify(state.user));

      // Persist prediction in SQLite Database storage
      if (state.user.consumerId) {
        fetch(`${API_BASE_URL}/api/user/${encodeURIComponent(state.user.consumerId)}/prediction`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(state.prediction)
        }).catch(e => console.warn('Database save failed:', e));
      }
    }
    localStorage.setItem('voltvision_saved_prediction', JSON.stringify(state.prediction));

    // Update UI Elements with server response
    updateUIResults();
    updateSpeedometer();
    updateCharts();
    renderApplianceBreakdownList();
    setBackendStatus(true);
  } catch (err) {
    console.warn('Backend ML prediction request failed:', err);
    setBackendStatus(false);
  } finally {
    showPredictionLoading(false);
  }
}

function showPredictionLoading(isLoading) {
  const badgeText = document.getElementById('predictor-badge-text');
  const billEl = document.getElementById('pred-result-bill');
  const kwhEl = document.getElementById('pred-result-kwh');
  if (badgeText) {
    badgeText.textContent = isLoading ? '⚡ Calculating via ML Backend...' : 'Backend ML Prediction Forecast';
  }
  if (billEl) billEl.style.opacity = isLoading ? '0.6' : '1';
  if (kwhEl) kwhEl.style.opacity = isLoading ? '0.6' : '1';
}

async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (res.ok) {
      setBackendStatus(true);
    } else {
      setBackendStatus(false);
    }
  } catch (_) {
    setBackendStatus(false);
  }
}

function setBackendStatus(isOnline) {
  const badge = document.getElementById('backend-status-badge');
  const dot = document.getElementById('backend-status-dot');
  const text = document.getElementById('backend-status-text');
  if (!badge) return;

  if (isOnline) {
    badge.title = 'FastAPI ML Backend Connected (Live)';
    if (dot) dot.style.background = '#10b981';
    if (text) text.textContent = 'ML Backend: Online';
  } else {
    badge.title = 'FastAPI ML Backend Disconnected';
    if (dot) dot.style.background = '#ef4444';
    if (text) text.textContent = 'ML Backend: Offline';
  }
}

// ================= UPDATE UI ELEMENTS =================
function updateUIResults() {
  const p = state.prediction;
  const isZero = state.isNewUser || !p.totalKwh || p.totalKwh === 0;

  // Simulator Result Card
  const predKwhEl = document.getElementById('pred-result-kwh');
  if (predKwhEl) predKwhEl.textContent = p.totalKwh ?? 0;
  const predBillEl = document.getElementById('pred-result-bill');
  if (predBillEl) predBillEl.textContent = formatMoney(p.totalBill ?? 0);

  // Dynamic Tariff Slab Labels
  const s1Label = document.getElementById('slab-1-label');
  if (s1Label) s1Label.textContent = state.currency === 'INR' ? 'First 100 units @ ₹4.50' : 'First 100 units @ $0.054';
  const s2Label = document.getElementById('slab-2-label');
  if (s2Label) s2Label.textContent = state.currency === 'INR' ? '101 - 300 units @ ₹7.00' : '101 - 300 units @ $0.084';
  const s3Label = document.getElementById('slab-3-label');
  if (s3Label) s3Label.textContent = state.currency === 'INR' ? '301 - 500 units @ ₹9.50' : '301 - 500 units @ $0.114';

  // Tariff Slab Breakdown
  const tb = p.tierBreakdown || {};
  const s1 = document.getElementById('slab-1-amt');
  if (s1) s1.textContent = formatMoney(tb.slab1 || 0);
  const s2 = document.getElementById('slab-2-amt');
  if (s2) s2.textContent = formatMoney(tb.slab2 || 0);
  const s3 = document.getElementById('slab-3-amt');
  if (s3) s3.textContent = formatMoney(tb.slab3 || 0);
  const sFixed = document.getElementById('slab-fixed-amt');
  if (sFixed) sFixed.textContent = formatMoney(tb.fixed || 0);
  const sSolar = document.getElementById('slab-solar-credit');
  if (sSolar) sSolar.textContent = '-' + formatMoney(p.solarCredit || 0);
  const sNet = document.getElementById('slab-net-total');
  if (sNet) sNet.textContent = formatMoney(p.totalBill || 0);

  // Section 3 Appliance Analytics Header KPIs
  const statActive = document.getElementById('stat-active-appliances');
  const statActiveSub = document.getElementById('stat-active-appliances-sub');
  const statTop = document.getElementById('stat-top-consumer');
  const statTopShare = document.getElementById('stat-top-consumer-share');
  const statPump = document.getElementById('stat-pump-slot');
  const statPumpAdv = document.getElementById('stat-pump-advisory');

  if (isZero) {
    if (statActive) statActive.textContent = '0 Devices';
    if (statActiveSub) statActiveSub.textContent = '0 of 12 Monitored';
    if (statTop) statTop.textContent = '--';
    if (statTopShare) statTopShare.textContent = '0% of gross household load';
    if (statPump) statPump.textContent = 'Off / Disabled';
    if (statPumpAdv) statPumpAdv.textContent = 'No water pump load active';
  } else {
    const activeList = (p.applianceItems || []).filter(item => item.enabled && item.kwh > 0);
    const count = p.activeAppliancesCount || activeList.length;
    if (statActive) statActive.textContent = `${count} Devices`;
    if (statActiveSub) statActiveSub.textContent = `${count} of 12 Monitored`;

    if (p.topConsumer && p.topConsumer.name) {
      if (statTop) statTop.textContent = p.topConsumer.name;
      if (statTopShare) statTopShare.textContent = `${p.topConsumer.share_pct}% of gross demand (${p.topConsumer.kwh} kWh)`;
    } else if (activeList.length > 0) {
      const top = activeList[0];
      if (statTop) statTop.textContent = top.plainName || top.name;
      if (statTopShare) statTopShare.textContent = `${top.share_pct}% of gross demand (${top.kwh} kWh)`;
    } else {
      if (statTop) statTop.textContent = 'Balanced';
      if (statTopShare) statTopShare.textContent = 'No active heavy appliances';
    }

    if (p.waterPumpEnabled && (p.waterPumpHours > 0 || p.water_pump_hours > 0)) {
      const slot = (p.waterPumpTiming || p.water_pump_timing || 'morning').toUpperCase();
      if (statPump) statPump.textContent = `${slot} SLOT`;
      if (statPumpAdv) statPumpAdv.textContent = p.pumpTimingAdvisory || 'Running in configured slot';
    } else {
      if (statPump) statPump.textContent = 'Off / Disabled';
      if (statPumpAdv) statPumpAdv.textContent = 'Water pump is switched off';
    }
  }

  // Top Dashboard Hero
  const heroPredKwh = document.getElementById('hero-pred-kwh');
  if (heroPredKwh) heroPredKwh.textContent = `${p.totalKwh ?? 0} kWh`;

  const heroDesc = document.getElementById('dash-hero-desc') || document.querySelector('.dash-hero p');
  if (heroDesc) {
    if (isZero) {
      heroDesc.innerHTML = `Your smart meter connection is active with <span class="badge-warning font-mono" id="hero-pred-kwh">0 kWh</span> consumption recorded. Configure your appliances in the <strong class="glow-text">AI Predictor</strong> tab to generate your forecast.`;
    } else {
      heroDesc.innerHTML = `Your projected monthly consumption is <span class="badge-warning font-mono" id="hero-pred-kwh">${p.totalKwh} kWh</span>. Peak hours run between <strong class="glow-text">6:00 PM – 10:00 PM</strong>.`;
    }
  }

  // 4 KPI Cards
  const kpiKwh = document.getElementById('kpi-predicted-kwh');
  if (kpiKwh) kpiKwh.textContent = p.totalKwh ?? 0;

  const kpiBill = document.getElementById('kpi-projected-bill');
  if (kpiBill) {
    kpiBill.textContent = state.currency === 'INR'
      ? Math.round(p.totalBill || 0).toLocaleString('en-IN')
      : ((p.totalBill || 0) * state.fxRate).toFixed(2);
  }

  const kpiCurr = document.getElementById('kpi-currency-symbol');
  if (kpiCurr) kpiCurr.textContent = state.currency === 'INR' ? '₹' : '$';

  const diffBadge = document.getElementById('kpi-diff-badge');
  if (diffBadge) {
    diffBadge.textContent = isZero ? '🌱 Smart Meter Synced' : '-4.2% vs last month';
  }

  // Efficiency KPI
  const gradeEl = document.getElementById('kpi-efficiency-grade');
  if (gradeEl) gradeEl.textContent = p.efficiencyGrade || '--';

  const effProgress = document.getElementById('efficiency-progress');
  if (effProgress) effProgress.style.width = `${p.efficiencyScore || 0}%`;

  const effScoreTxt = document.getElementById('efficiency-score-txt');
  if (effScoreTxt) {
    effScoreTxt.textContent = (isZero || p.efficiencyGrade === '--' || p.efficiencyScore === 0)
      ? '0 / 100 Score (Pending Setup)'
      : `${p.efficiencyScore} / 100 Score`;
  }

  // Carbon KPI
  const carbonVal = document.getElementById('kpi-carbon-val');
  if (carbonVal) carbonVal.textContent = p.carbonKg || 0;

  const solarOffset = document.getElementById('kpi-solar-offset');
  if (solarOffset) {
    solarOffset.textContent = (p.solarGenKwh > 0)
      ? `🌿 ${Math.round(p.solarGenKwh * 0.82)} kg saved by Solar`
      : '🌿 0 kg saved by Solar';
  }

  // Savings Alert Box in Dashboard
  const alertSaveAmt = document.getElementById('alert-save-amount');
  if (alertSaveAmt) alertSaveAmt.textContent = isZero ? formatMoney(0) : formatMoney(420);

  // Dynamic AI Tip in Simulator
  const optTipEl = document.getElementById('optimizer-tip');
  if (optTipEl) {
    if (isZero) {
      optTipEl.innerHTML = 'Select your household appliances above to calculate your exact monthly prediction with machine learning.';
    } else if (p.optimizerTip) {
      optTipEl.innerHTML = p.optimizerTip;
    } else if (p.acUnits > 0 && p.acHours >= 6) {
      const acSavingUnits = Math.round((p.breakdown?.cooling || 0) * 0.18);
      optTipEl.innerHTML = `Running your AC at <strong>24°C</strong> instead of chilled 18°C will save approx <strong>${acSavingUnits} units (${formatMoney(acSavingUnits * 7.50)}/mo)</strong>.`;
    } else if (p.solarKw === 0) {
      optTipEl.innerHTML = `Installing just <strong>2 kW Rooftop Solar</strong> will save you approximately <strong>${formatMoney(1800)}/month</strong> with clean renewable energy.`;
    } else {
      optTipEl.innerHTML = `Your energy profile is currently well-balanced! Running heavy washing loads off-peak saves an extra <strong>${formatMoney(250)}/month</strong>.`;
    }
  }
}

// ================= SPEEDOMETER / LOAD GAUGE =================
function updateSpeedometer() {
  const p = state.prediction;
  const loadValEl = document.getElementById('live-kw-val');
  const safeLabelEl = document.getElementById('gauge-safe-label');
  const peakTodayEl = document.getElementById('stat-peak-today');
  const arc = document.getElementById('gauge-fill-arc');

  const peak = Number(p.peakKw || 0);
  if (loadValEl) loadValEl.textContent = peak.toFixed(1);
  if (peakTodayEl) peakTodayEl.textContent = `${(peak * 1.2).toFixed(1)} kW`;

  const sanctioned = 5.0; // kW
  const percent = peak === 0 ? 0 : Math.min(100, Math.round((peak / sanctioned) * 100));
  if (safeLabelEl) safeLabelEl.textContent = `${percent}% of 5kW Sanctioned`;

  // Total stroke arc length is 251.2
  // dashoffset from 251.2 (0%) down to 0 (100%)
  const offset = 251.2 - (251.2 * (percent / 100));
  if (arc) arc.style.strokeDashoffset = offset;
}

// ================= CHART.JS VISUALS =================
function initCharts() {
  // 1. Consumption Trend & Forecast Chart
  const trendCtx = document.getElementById('trendChart')?.getContext('2d');
  if (trendCtx && !state.charts.trend) {
    const days = Array.from({ length: 30 }, (_, i) => `Day ${i + 1}`);

    state.charts.trend = new Chart(trendCtx, {
      type: 'line',
      data: {
        labels: days,
        datasets: [
          {
            label: 'Recorded Meter Baseline (kWh)',
            data: [],
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.12)',
            fill: true,
            tension: 0.35,
            borderWidth: 3,
            pointBackgroundColor: '#3b82f6',
            pointRadius: 3,
            pointHoverRadius: 6
          },
          {
            label: 'AI Forecasted Consumption (kWh)',
            data: [],
            borderColor: '#00f2fe',
            borderDash: [5, 5],
            backgroundColor: 'rgba(0, 242, 254, 0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 3,
            pointBackgroundColor: '#00f2fe',
            pointRadius: 4,
            pointHoverRadius: 7
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            titleColor: '#00f2fe',
            bodyColor: '#fff',
            borderColor: 'rgba(0, 242, 254, 0.3)',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: function(context) {
                const val = context.parsed.y !== null ? context.parsed.y : '--';
                return `${context.dataset.label}: ${val} kWh`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8', maxTicksLimit: 10 }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8' },
            title: { display: true, text: 'Energy (kWh)', color: '#64748b' },
            beginAtZero: true
          }
        }
      }
    });
  }

  // 2. Appliance Breakdown Donut Chart
  const donutCtx = document.getElementById('applianceChart')?.getContext('2d');
  if (donutCtx && !state.charts.appliance) {
    state.charts.appliance = new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels: ['Air Conditioning', 'Water Geyser', 'Refrigerator', 'Lighting & Fans', 'EV & Laundry'],
        datasets: [{
          data: [],
          backgroundColor: ['#00f2fe', '#f59e0b', '#10b981', '#6366f1', '#ec4899'],
          borderWidth: 2,
          borderColor: '#0b1120',
          hoverOffset: 8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#cbd5e1', font: { family: "'Plus Jakarta Sans', sans-serif" }, padding: 14 }
          },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            callbacks: {
              label: function(context) {
                const val = context.parsed;
                const total = context.dataset.data.reduce((a, c) => a + c, 0);
                const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                return ` ${context.label}: ${val} kWh (${pct}%)`;
              }
            }
          }
        },
        cutout: '68%'
      }
    });
  }

  updateCharts();
}

function updateCharts() {
  if (!state.charts.trend || !state.charts.appliance) return;

  const p = state.prediction;
  const isZero = state.isNewUser || !p.totalKwh || p.totalKwh === 0;

  // 1. Update Donut Chart
  const activeDonutItems = (p.applianceItems || []).filter(item => item.enabled && item.kwh > 0);

  if (isZero || activeDonutItems.length === 0) {
    state.charts.appliance.data.labels = ['No usage recorded yet'];
    state.charts.appliance.data.datasets[0].data = [1];
    state.charts.appliance.data.datasets[0].backgroundColor = ['rgba(255, 255, 255, 0.08)'];
    state.charts.appliance.update();
  } else {
    state.charts.appliance.data.labels = activeDonutItems.map(item => item.plainName || item.name);
    state.charts.appliance.data.datasets[0].data = activeDonutItems.map(item => item.kwh);
    state.charts.appliance.data.datasets[0].backgroundColor = activeDonutItems.map(item => item.color);
    state.charts.appliance.update();
  }

  // 2. Update Trend Chart
  const chart = state.charts.trend;
  const subtitle = document.querySelector('#trendChart')?.closest('.chart-card')?.querySelector('.card-subtitle');
  const legend = document.querySelector('#trendChart')?.closest('.chart-card')?.querySelector('.chart-legend-custom');

  if (isZero) {
    const days = Array.from({ length: 30 }, (_, i) => `Day ${i + 1}`);
    chart.data.labels = days;
    chart.data.datasets[0].label = 'Recorded Meter Baseline (0.0 kWh)';
    chart.data.datasets[0].data = Array(30).fill(0);
    chart.data.datasets[1].label = 'AI ML Forecast (0.0 kWh)';
    chart.data.datasets[1].data = Array(30).fill(0);
    chart.update();

    if (subtitle) {
      subtitle.innerHTML = '⚡ <strong>Smart meter connection initialized at 0 kWh</strong>. Configure appliances in the AI Predictor tab to generate your AI forecast.';
    }
    if (legend) {
      legend.innerHTML = `
        <span class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> Recorded Baseline (0 kWh)</span>
        <span class="legend-item"><span class="legend-dot forecast"></span> AI ML Forecast (0 kWh)</span>
      `;
    }
  } else if (p.chartData && p.chartData.labels && p.chartData.forecast_kwh) {
    chart.data.labels = p.chartData.labels;
    chart.data.datasets[0].label = 'Recorded Meter Baseline (kWh)';
    chart.data.datasets[0].data = p.chartData.recorded_kwh;
    chart.data.datasets[1].label = `AI ML Forecast (~${p.chartData.avg_daily_kwh} kWh/day)`;
    chart.data.datasets[1].data = p.chartData.forecast_kwh;
    chart.update();

    if (subtitle) {
      subtitle.innerHTML = `AI Daily Forecast: ~<strong>${p.chartData.avg_daily_kwh} kWh/day</strong> (${p.totalKwh} kWh/mo) &bull; Calibrated by ML Backend`;
    }
    if (legend) {
      legend.innerHTML = `
        <span class="legend-item"><span class="legend-dot" style="background:#3b82f6;"></span> Recorded Baseline</span>
        <span class="legend-item"><span class="legend-dot forecast"></span> AI ML Forecast (~${p.chartData.avg_daily_kwh} kWh/d)</span>
      `;
    }
  } else {
    // Dynamic fallback matching user's predicted total kWh
    const avgForecastDaily = (p.totalKwh || 412) / 30;
    const days = Array.from({ length: 30 }, (_, i) => `Day ${i + 1}`);
    const actualData = [13.2, 14.1, 12.8, 15.0, 16.2, 14.5, 13.9, 14.8, 15.2, 16.5, 17.1, 14.0, 13.5, 14.2, 15.8, 16.2, 15.0, 14.7];
    const actualSeries = [...actualData, ...Array(12).fill(null)];
    const forecastSeries = Array(17).fill(null);
    forecastSeries.push(actualData[17]); // Day 18 anchor

    for (let d = 19; d <= 30; d++) {
      const variation = Math.sin(d) * (avgForecastDaily * 0.12);
      forecastSeries.push(Number((avgForecastDaily + variation).toFixed(1)));
    }

    chart.data.labels = days;
    chart.data.datasets[0].label = 'Recorded Meter Baseline (kWh)';
    chart.data.datasets[0].data = actualSeries;
    chart.data.datasets[1].label = `AI ML Forecast (~${avgForecastDaily.toFixed(1)} kWh/day)`;
    chart.data.datasets[1].data = forecastSeries;
    chart.update();
  }
}

// ================= APPLIANCE BREAKDOWN LIST =================
function renderApplianceBreakdownList() {
  const container = document.getElementById('appliance-bars-container');
  if (!container) return;

  const p = state.prediction;
  const isZero = state.isNewUser || !p.grossKwh || p.grossKwh === 0;

  if (isZero) {
    container.innerHTML = `
      <div style="padding: 28px 20px; text-align: center; color: var(--text-muted); background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1);">
        <div style="font-size: 2rem; margin-bottom: 8px;">🔌</div>
        <strong style="color: #cbd5e1; font-size: 1rem;">No Appliances Modeled Yet</strong>
        <p style="margin-top: 6px; font-size: 0.88rem; color: #64748b; max-width: 420px; margin-left: auto; margin-right: auto;">
          Smart meter initialized at 0 kWh. Head over to the <a href="javascript:void(0)" onclick="switchSection('predictor')" style="color: var(--brand-cyan); text-decoration: underline;">AI Predictor</a> tab to add your home equipment and calculate usage.
        </p>
      </div>
    `;
    return;
  }

  const activeItems = (p.applianceItems || [])
    .filter(item => item.enabled && item.kwh > 0)
    .sort((a, b) => b.kwh - a.kwh);

  if (activeItems.length === 0) {
    container.innerHTML = `
      <div style="padding: 28px 20px; text-align: center; color: var(--text-muted); background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1);">
        <div style="font-size: 2rem; margin-bottom: 8px;">⚠️</div>
        <strong style="color: #cbd5e1; font-size: 1rem;">All Appliances are Toggled Off</strong>
        <p style="margin-top: 6px; font-size: 0.88rem; color: #64748b; max-width: 420px; margin-left: auto; margin-right: auto;">
          Enable one or more appliances in the AI Predictor tab to see real-time consumption and cost analytics.
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = activeItems.map(item => {
    const costFormatted = formatMoney(item.cost_inr || (item.kwh * 7.50));
    return `
      <div class="bar-item">
        <div class="bar-header">
          <strong>${item.emoji} ${item.name}</strong>
          <span><strong>${item.kwh} kWh</strong> (${item.share_pct}% of gross)</span>
        </div>
        <div class="bar-track">
          <div class="bar-progress" style="width: ${item.share_pct}%; background: ${item.color};"></div>
        </div>
        <div class="bar-timing-sub">
          <span>⏱️ ${item.timing}</span>
          <span class="cost-tag">Est. ${costFormatted}/mo</span>
        </div>
      </div>
    `;
  }).join('');
}

// ================= "WHAT-IF" SCENARIO SIMULATOR =================
async function runWhatIf() {
  const acCheck = document.getElementById('whatif-ac-temp')?.checked || false;
  const geyserCheck = document.getElementById('whatif-geyser-timer')?.checked || false;
  const ledCheck = document.getElementById('whatif-led')?.checked || false;
  const solarCheck = document.getElementById('whatif-solar-add')?.checked || false;

  try {
    const res = await fetch(`${API_BASE_URL}/calculate/whatif`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ac_temp_optimized: acCheck,
        geyser_timer_used: geyserCheck,
        led_bldc_installed: ledCheck,
        solar_add_1kw: solarCheck
      })
    });
    if (res.ok) {
      const data = await res.json();
      const totalDisplay = document.getElementById('whatif-total-savings');
      if (totalDisplay) {
        totalDisplay.textContent = formatMoney(data.total_savings_inr) + ' / month';
      }
      document.getElementById('save-ac-temp').textContent = `Save ${formatMoney(data.ac_saving_inr)}/mo`;
      document.getElementById('save-geyser').textContent = `Save ${formatMoney(data.geyser_saving_inr)}/mo`;
      document.getElementById('save-led').textContent = `Save ${formatMoney(data.led_saving_inr)}/mo`;
      document.getElementById('save-solar').textContent = `Save ${formatMoney(data.solar_saving_inr)}/mo`;
      return;
    }
  } catch (_) {}

  // Fallback if backend temporarily disconnected
  let totalSavedInr = 0;
  if (acCheck) totalSavedInr += 580;
  if (geyserCheck) totalSavedInr += 315;
  if (ledCheck) totalSavedInr += 240;
  if (solarCheck) totalSavedInr += 840;

  const totalDisplay = document.getElementById('whatif-total-savings');
  if (totalDisplay) {
    totalDisplay.textContent = formatMoney(totalSavedInr) + ' / month';
  }

  document.getElementById('save-ac-temp').textContent = `Save ${formatMoney(580)}/mo`;
  document.getElementById('save-geyser').textContent = `Save ${formatMoney(315)}/mo`;
  document.getElementById('save-led').textContent = `Save ${formatMoney(240)}/mo`;
  document.getElementById('save-solar').textContent = `Save ${formatMoney(840)}/mo`;
}

// ================= APPLY PREDICTION TO DASHBOARD =================
async function applyPredictionToDashboard() {
  if (predictionDebounceTimer) {
    clearTimeout(predictionDebounceTimer);
    predictionDebounceTimer = null;
  }
  showPredictionLoading(true);
  await fetchBackendPrediction();
  switchSection('dashboard');
  requestAnimationFrame(() => {
    if (state.charts.trend) {
      state.charts.trend.resize();
    }
    updateCharts();
    updateUIResults();
    updateSpeedometer();
    renderApplianceBreakdownList();
  });
  showToast('✅ Prediction applied! Dashboard graphs & KPIs updated.');
}

// ================= EXPORT REPORT =================
function exportReport() {
  const p = state.prediction;
  const activeAppList = (p.applianceItems && p.applianceItems.length > 0)
    ? p.applianceItems.filter(i => i.enabled && i.kwh > 0).map(i => `- ${i.plainName || i.name}: ${i.kwh} kWh (${i.share_pct}%) [${i.timing}]`).join('\n')
    : `- No appliances enabled`;

  const reportText = `
======================================================
VOLTVISION AI - ELECTRICITY CONSUMPTION PREDICTION REPORT
======================================================
Consumer Name:    ${state.user?.name || 'Aman Sharma'}
Consumer ID:      ${state.user?.consumerId || 'CA-984210'}
Date of Report:   ${new Date().toLocaleDateString('en-IN', { dateStyle: 'full' })}
Currency:         ${state.currency}

PREDICTION SUMMARY:
------------------------------------------------------
Estimated Monthly Usage:  ${p.totalKwh} kWh
Gross Household Demand:   ${p.grossKwh} kWh
Solar Generation Credit:  ${p.solarGenKwh} kWh
Projected Electricity Bill: ${formatMoney(p.totalBill)}
Active Appliances:        ${p.activeAppliancesCount || 0} monitored devices
Energy Efficiency Grade:  ${p.efficiencyGrade} (${p.efficiencyScore}/100)
Est. Carbon Footprint:    ${p.carbonKg} kg CO2e
Peak Demand Load:         ${p.peakKw} kW

APPLIANCE-LEVEL BREAKDOWN:
------------------------------------------------------
${activeAppList}

TARIFF SLAB DETAILS:
------------------------------------------------------
- Slab 1 (0-100 units):     ${formatMoney(p.tierBreakdown.slab1)}
- Slab 2 (101-300 units):   ${formatMoney(p.tierBreakdown.slab2)}
- Slab 3 (301-500 units):   ${formatMoney(p.tierBreakdown.slab3)}
- Fixed Meter Charges:     ${formatMoney(p.tierBreakdown.fixed)}
- Solar Credit Deducted:   -${formatMoney(p.solarCredit)}
- TOTAL PAYABLE:           ${formatMoney(p.totalBill)}

Generated by VoltVision AI Forecasting Engine.
======================================================
  `.trim();

  // Create downloadable text file
  const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `VoltVision_Prediction_${state.user?.consumerId || 'Report'}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast('📄 Prediction Report downloaded successfully!');
}

// ================= TOAST SYSTEM =================
function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>⚡</span> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function demoAlert(msg) {
  showToast(msg);
}

// ================= BACKEND ML FORECAST CONNECTION =================
// Requests a forecast from the FastAPI machine-learning backend.
// Example from the browser console: getBackendForecast(7)
async function getBackendForecast(days = 7) {
  try {
    const response = await fetch(`${API_BASE_URL}/forecast`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ days: days })
    });

    if (!response.ok) {
      let detail = `API error: ${response.status}`;
      try {
        const errorBody = await response.json();
        if (errorBody.detail) detail += ` - ${errorBody.detail}`;
      } catch (_) {
        // Keep the HTTP status message if the response is not JSON.
      }
      throw new Error(detail);
    }

    const result = await response.json();
    console.log('ML Forecast Result:', result);
    showToast('✅ ML forecast received from backend!');
    return result;
  } catch (error) {
    console.error('Backend connection failed:', error);
    showToast('⚠️ Could not connect to the backend. Check that FastAPI is running.');
    return null;
  }
}

// Expose the backend forecast helper for browser-console testing.
// This does not change the dashboard UI or the existing prediction flow.
window.getBackendForecast = getBackendForecast;
