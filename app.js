const state = {
  summary: null,
  searchIndex: null,
  conceptManifest: null,
  conceptCache: new Map(),
  year: "all",
  conceptYear: "all",
  kind: "",
  department: "",
  search: "",
  conceptSearch: "",
  minAmount: "",
  maxAmount: "",
  dateFrom: "",
  dateTo: "",
  selectedProfileId: null,
  selectedProfileDetail: null,
  detailCache: new Map(),
  detailManifestCache: new Map(),
  detailShardCache: new Map(),
  conceptLoading: false,
};

const heroStats = document.querySelector("#hero-stats");
const yearFilter = document.querySelector("#year-filter");
const yearFilterSecondary = document.querySelector("#year-filter-secondary");
const kindFilter = document.querySelector("#kind-filter");
const departmentFilter = document.querySelector("#department-filter");
const searchInput = document.querySelector("#search-input");
const conceptSearchInput = document.querySelector("#concept-search-input");
const conceptYearFilter = document.querySelector("#concept-year-filter");
const minAmountFilter = document.querySelector("#min-amount-filter");
const maxAmountFilter = document.querySelector("#max-amount-filter");
const dateFromFilter = document.querySelector("#date-from-filter");
const dateToFilter = document.querySelector("#date-to-filter");
const summaryGrid = document.querySelector("#summary-grid");
const summaryTemplate = document.querySelector("#summary-card-template");
const rankTemplate = document.querySelector("#rank-item-template");
const resultTemplate = document.querySelector("#result-item-template");
const recordTemplate = document.querySelector("#record-item-template");
const searchResults = document.querySelector("#search-results");
const conceptResults = document.querySelector("#concept-results");
const conceptStatus = document.querySelector("#concept-status");
const detailTitle = document.querySelector("#detail-title");
const detailSubtitle = document.querySelector("#detail-subtitle");
const detailSummary = document.querySelector("#detail-summary");
const detailInvoiceRecords = document.querySelector("#detail-invoice-records");
const detailSupplierRecords = document.querySelector("#detail-supplier-records");
const detailContractRecords = document.querySelector("#detail-contract-records");
const detailOtherRecords = document.querySelector("#detail-other-records");

const sections = {
  invoiceSuppliers: document.querySelector("#invoice-suppliers"),
  supplierSpend: document.querySelector("#supplier-spend"),
  invoiceDepartments: document.querySelector("#invoice-departments"),
  contractSuppliers: document.querySelector("#contract-suppliers"),
  contractDepartments: document.querySelector("#contract-departments"),
  grantBeneficiaries: document.querySelector("#grant-beneficiaries"),
  budgetLines: document.querySelector("#budget-lines"),
};

console.log(
  [
    "Com Gastem a Valls",
    "Si t'han pagat per tocar aquesta web, tranquil.",
    "Tard o d'hora el teu treball tambe acabara sortint en una llista.",
    "Moltes gracies!",
  ].join("\n")
);

function money(value) {
  return new Intl.NumberFormat("ca-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(
    value || 0
  );
}

function integer(value) {
  return new Intl.NumberFormat("ca-ES").format(value || 0);
}

function formatDate(value) {
  if (!value) return "Sense data";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ca-ES", { year: "numeric", month: "short", day: "numeric" }).format(date);
}

function humanKind(kind) {
  return (
    {
      entity: "Empresa o beneficiari",
      department: "Departament",
      organization: "Organisme",
    }[kind] || kind
  );
}

function sourceLabel(source) {
  return (
    {
      invoices: "Factures",
      contracts: "Contractes",
      grants: "Ajuts",
      budget: "Pressupost",
      supplier_spend: "Despesa proveïdor",
    }[source] || source
  );
}

function setHeroStats(summary) {
  heroStats.innerHTML = "";
  const latest = summary.years[0];
  [
    {
      value: integer(summary.overview.years.length),
      label: "exercicis consolidats",
    },
    {
      value: integer(summary.overview.profile_count),
      label: "perfils cercables",
    },
    {
      value: latest ? integer(latest.invoices.count) : "0",
      label: "factures a l'últim exercici",
    },
    {
      value: latest ? integer(latest.contracts.count) : "0",
      label: "contractes menors a l'últim exercici",
    },
  ].forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "hero-stat-card";
    if (index === 0) card.classList.add("is-featured");

    const value = document.createElement("strong");
    value.className = "hero-stat-value";
    value.textContent = item.value;

    const label = document.createElement("span");
    label.className = "hero-stat-label";
    label.textContent = item.label;

    card.append(value, label);
    heroStats.append(card);
  });
}

function setYearOptions(summary) {
  yearFilter.innerHTML = '<option value="all">Tots</option>';
  yearFilterSecondary.innerHTML = "";

  summary.overview.years.forEach((year) => {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    yearFilter.append(option);

    const secondaryOption = document.createElement("option");
    secondaryOption.value = String(year);
    secondaryOption.textContent = String(year);
    yearFilterSecondary.append(secondaryOption);
  });

  yearFilter.value = state.year;
  yearFilterSecondary.value = state.year === "all" ? String(summary.overview.latest_year) : state.year;
}

function setConceptYearOptions(summary) {
  conceptYearFilter.innerHTML = '<option value="all">Tots</option>';
  summary.overview.years.forEach((year) => {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    conceptYearFilter.append(option);
  });
  conceptYearFilter.value = state.conceptYear;
}

function setDepartmentOptions(searchIndex) {
  const departments = searchIndex.profiles
    .filter((profile) => profile.kind === "department")
    .map((profile) => profile.name)
    .sort((left, right) => left.localeCompare(right, "ca"));

  departmentFilter.innerHTML = '<option value="">Tots els departaments</option>';
  departments.forEach((department) => {
    const option = document.createElement("option");
    option.value = department;
    option.textContent = department;
    departmentFilter.append(option);
  });
  departmentFilter.value = state.department;
}

function currentYearData() {
  if (state.year === "all") return state.summary.years[0];
  return state.summary.years.find((entry) => entry.year === Number(state.year)) || state.summary.years[0];
}

function renderSummary(yearData) {
  summaryGrid.innerHTML = "";
  [
    {
      label: "Factures",
      value: money(yearData.invoices.amount),
      note: `${integer(yearData.invoices.count)} factures vàlides`,
    },
    {
      label: "Contractes menors",
      value: money(yearData.contracts.amount),
      note: `${integer(yearData.contracts.count)} adjudicacions`,
    },
    {
      label: "Ajuts i subvencions",
      value: money(yearData.grants.amount),
      note: `${integer(yearData.grants.count)} concessions`,
    },
    {
      label: "Pressupost final",
      value: money(yearData.budget.final),
      note: `${integer(yearData.budget.count)} partides pressupostàries`,
    },
  ].forEach((card) => {
    const fragment = summaryTemplate.content.cloneNode(true);
    fragment.querySelector(".summary-label").textContent = card.label;
    fragment.querySelector(".summary-value").textContent = card.value;
    fragment.querySelector(".summary-note").textContent = card.note;
    summaryGrid.append(fragment);
  });
}

function renderRanking(target, items, amountKey = "amount", metaBuilder = null) {
  target.innerHTML = "";
  if (!items?.length) {
    target.innerHTML = '<p class="empty-state">No hi ha dades per a aquest bloc en l\'exercici seleccionat.</p>';
    return;
  }

  items.forEach((item) => {
    const fragment = rankTemplate.content.cloneNode(true);
    fragment.querySelector(".rank-name").textContent = item.name;
    fragment.querySelector(".rank-meta").textContent = metaBuilder ? metaBuilder(item) : `${integer(item.count)} registres`;
    fragment.querySelector(".rank-amount").textContent = money(item[amountKey] || item.final || 0);
    target.append(fragment);
  });
}

function sortProfiles(profiles) {
  const query = state.search.trim().toLowerCase();
  return [...profiles].sort((left, right) => {
    const leftStarts = left.name.toLowerCase().startsWith(query) ? 1 : 0;
    const rightStarts = right.name.toLowerCase().startsWith(query) ? 1 : 0;
    if (leftStarts !== rightStarts) return rightStarts - leftStarts;
    if ((left.display_amount || 0) !== (right.display_amount || 0)) {
      return (right.display_amount || 0) - (left.display_amount || 0);
    }
    return (right.display_count || 0) - (left.display_count || 0);
  });
}

function filteredProfiles() {
  const query = state.search.trim().toLowerCase();
  if (!query && !state.department) return [];

  return sortProfiles(
    state.searchIndex.profiles.filter((profile) => {
      if (state.kind && profile.kind !== state.kind) return false;
      if (state.year !== "all" && !profile.years[state.year]) return false;
      if (state.department) {
        const departmentMatch = profile.name === state.department || profile.organization === state.department;
        if (profile.kind === "department" && profile.name !== state.department) return false;
        if (profile.kind !== "department" && !departmentMatch) return false;
      }

      const haystack = [profile.name, profile.organization, profile.cif, profile.city, profile.province]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return !query || haystack.includes(query);
    })
  ).slice(0, 100);
}

function selectedProfileMeta() {
  const profiles = filteredProfiles();
  if (!state.selectedProfileId) return null;
  return profiles.find((profile) => profile.id === state.selectedProfileId) || null;
}

function renderResults() {
  const profiles = filteredProfiles();
  searchResults.innerHTML = "";

  if (!state.search.trim() && !state.department) {
    searchResults.innerHTML = '<p class="empty-state">Escriu una cerca o selecciona un departament per carregar resultats.</p>';
    return;
  }

  if (!profiles.length) {
    searchResults.innerHTML = '<p class="empty-state">No hi ha resultats amb aquest filtre.</p>';
    state.selectedProfileId = null;
    state.selectedProfileDetail = null;
    return;
  }

  if (!selectedProfileMeta()) {
    state.selectedProfileId = profiles[0].id;
  }

  profiles.forEach((profile) => {
    const fragment = resultTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".result-item");
    button.dataset.id = profile.id;

    if (profile.id === state.selectedProfileId) {
      button.classList.add("is-active");
    }

    fragment.querySelector(".result-kind").textContent = humanKind(profile.kind);
    fragment.querySelector(".result-name").textContent = profile.name;

    const yearBucket = state.year !== "all" ? profile.years[state.year] : null;
    const visibleAmount = yearBucket ? yearBucket.amount : profile.display_amount;
    const visibleCount = yearBucket ? yearBucket.count : profile.display_count;

    fragment.querySelector(".result-meta").textContent =
      `${sourceLabel(profile.display_source)} ${money(visibleAmount)} · ${integer(visibleCount)} registres principals`;

    button.addEventListener("click", async () => {
      state.selectedProfileId = profile.id;
      renderResults();
      await loadSelectedProfileDetail();
      renderDetail();
    });

    searchResults.append(fragment);
  });
}

async function loadSelectedProfileDetail() {
  const meta = selectedProfileMeta();
  if (!meta) {
    state.selectedProfileDetail = null;
    return;
  }

  detailTitle.textContent = meta.name;
  detailSubtitle.textContent = "Carregant detall...";
  const cacheKey = `${meta.id}:${state.year}`;

  if (state.detailCache.has(cacheKey)) {
    state.selectedProfileDetail = state.detailCache.get(cacheKey);
    return;
  }

  let manifest = state.detailManifestCache.get(meta.id);
  if (!manifest) {
    const response = await fetch(`data/profiles/${meta.file}`);
    if (!response.ok) throw new Error("No s'ha pogut carregar el detall del perfil.");
    manifest = await response.json();
    state.detailManifestCache.set(meta.id, manifest);
  }

  if (!manifest.sharded) {
    state.detailCache.set(cacheKey, manifest);
    state.selectedProfileDetail = manifest;
    return;
  }

  const yearsToLoad =
    state.year === "all"
      ? Object.keys(manifest.year_files || {}).sort((left, right) => Number(right) - Number(left))
      : [state.year];

  const records = [];
  for (const year of yearsToLoad) {
    const files = manifest.year_files?.[year];
    const shardFiles = Array.isArray(files) ? files : files ? [files] : [];
    for (const file of shardFiles) {
      const shardCacheKey = `${meta.id}:${file}`;
      let shard = state.detailShardCache.get(shardCacheKey);
      if (!shard) {
        const shardResponse = await fetch(`data/profiles/${file}`);
        if (!shardResponse.ok) throw new Error("No s'ha pogut carregar una part del detall del perfil.");
        shard = await shardResponse.json();
        state.detailShardCache.set(shardCacheKey, shard);
      }
      records.push(...(shard.records || []));
    }
  }

  const detail = { ...manifest, records };
  state.detailCache.set(cacheKey, detail);
  state.selectedProfileDetail = detail;
}

function filteredDetailRecords(profile) {
  if (!profile) return [];
  return profile.records.filter((record) => {
    if (state.year !== "all" && String(record.year) !== state.year) return false;
    if (state.minAmount && (record.amount || 0) < Number(state.minAmount)) return false;
    if (state.maxAmount && (record.amount || 0) > Number(state.maxAmount)) return false;
    if (state.dateFrom && record.date && record.date.slice(0, 10) < state.dateFrom) return false;
    if (state.dateTo && record.date && record.date.slice(0, 10) > state.dateTo) return false;
    return true;
  });
}

function renderRecordGroup(target, records, emptyText) {
  target.innerHTML = "";

  if (!records.length) {
    target.innerHTML = `<p class="empty-state">${emptyText}</p>`;
    return;
  }

  records.forEach((record) => {
    const fragment = recordTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".record-item");
    const toggle = fragment.querySelector(".record-toggle");
    const details = fragment.querySelector(".record-details");

    if (record.is_cancelled) {
      article.classList.add("is-cancelled");
    }

    fragment.querySelector(".record-source").textContent = record.source_label;
    fragment.querySelector(".record-amount").textContent = money(record.amount);
    fragment.querySelector(".record-title").textContent = record.title || record.counterparty || "Registre sense títol";
    fragment.querySelector(".record-meta").textContent = [
      formatDate(record.date),
      record.organization,
      record.department,
      record.counterparty,
      record.reference ? `Ref. ${record.reference}` : "",
      record.status,
      record.source_file,
    ]
      .filter(Boolean)
      .join(" · ");

    const entries = Object.entries(record.raw_fields || {});
    if (!entries.length) {
      details.hidden = true;
      toggle.disabled = true;
    } else {
      const detailList = document.createElement("dl");
      detailList.className = "record-field-list";
      entries.forEach(([key, value]) => {
        const wrap = document.createElement("div");
        const dt = document.createElement("dt");
        const dd = document.createElement("dd");
        dt.textContent = key;
        dd.textContent = String(value);
        wrap.append(dt, dd);
        detailList.append(wrap);
      });
      details.append(detailList);
      toggle.addEventListener("click", () => {
        const isOpen = article.classList.toggle("is-open");
        details.hidden = !isOpen;
      });
    }

    target.append(fragment);
  });
}

function summarizeFilteredRecords(records) {
  const summary = {
    invoices: { amount: 0, count: 0 },
    supplier_spend: { amount: 0, count: 0 },
    contracts: { amount: 0, count: 0 },
    grants: { amount: 0, count: 0 },
    budget: { amount: 0, count: 0 },
  };

  records.forEach((record) => {
    if (!summary[record.source] || record.is_cancelled) return;
    summary[record.source].amount += record.amount || 0;
    summary[record.source].count += 1;
  });

  return summary;
}

function renderDetail() {
  const profile = state.selectedProfileDetail;
  const meta = selectedProfileMeta();

  if (!meta) {
    detailTitle.textContent = "Escriu una cerca i selecciona un resultat";
    detailSubtitle.textContent = "Només es carregarà el detall complet del perfil que obris.";
    detailSummary.innerHTML = "";
    detailInvoiceRecords.innerHTML = '<p class="empty-state">Sense detall carregat.</p>';
    detailSupplierRecords.innerHTML = '<p class="empty-state">Sense detall carregat.</p>';
    detailContractRecords.innerHTML = '<p class="empty-state">Sense detall carregat.</p>';
    detailOtherRecords.innerHTML = '<p class="empty-state">Sense detall carregat.</p>';
    return;
  }

  if (!profile) {
    detailTitle.textContent = meta.name;
    detailSubtitle.textContent = "Selecciona el resultat per carregar-ne el detall.";
    detailSummary.innerHTML = "";
    detailInvoiceRecords.innerHTML = '<p class="empty-state">Encara no s\'ha carregat el detall d\'aquest perfil.</p>';
    detailSupplierRecords.innerHTML = '<p class="empty-state">Encara no s\'ha carregat el detall d\'aquest perfil.</p>';
    detailContractRecords.innerHTML = '<p class="empty-state">Encara no s\'ha carregat el detall d\'aquest perfil.</p>';
    detailOtherRecords.innerHTML = '<p class="empty-state">Encara no s\'ha carregat el detall d\'aquest perfil.</p>';
    return;
  }

  const records = filteredDetailRecords(profile);
  const invoiceRecords = records.filter((record) => record.source === "invoices");
  const supplierRecords = records.filter((record) => record.source === "supplier_spend");
  const contractRecords = records.filter((record) => record.source === "contracts");
  const otherRecords = records.filter((record) => !["invoices", "supplier_spend", "contracts"].includes(record.source));
  const filteredSummary = summarizeFilteredRecords(records);

  detailTitle.textContent = profile.name;
  detailSubtitle.textContent =
    `${humanKind(profile.kind)} · ${integer(records.length)} registres visibles` +
    ` · Factures ${money(filteredSummary.invoices.amount)}`;
  detailSummary.innerHTML = [
    profile.organization || "Organisme no especificat",
    profile.cif || "Sense CIF visible",
    [profile.city, profile.province].filter(Boolean).join(", ") || "Sense ubicació",
    [
      filteredSummary.invoices.count ? `Factures ${money(filteredSummary.invoices.amount)}` : "",
      filteredSummary.supplier_spend.count ? `Despesa proveïdor ${money(filteredSummary.supplier_spend.amount)}` : "",
      filteredSummary.contracts.count ? `Contractes ${money(filteredSummary.contracts.amount)}` : "",
      filteredSummary.grants.count ? `Ajuts ${money(filteredSummary.grants.amount)}` : "",
      filteredSummary.budget.count ? `Pressupost ${money(filteredSummary.budget.amount)}` : "",
    ]
      .filter(Boolean)
      .join(" · ") || "Sense desglossament",
  ]
    .map((text) => `<div class="detail-pill">${text}</div>`)
    .join("");

  renderRecordGroup(detailInvoiceRecords, invoiceRecords, "No hi ha factures amb aquest filtre.");
  renderRecordGroup(detailSupplierRecords, supplierRecords, "No hi ha despesa de proveïdor amb aquest filtre.");
  renderRecordGroup(detailContractRecords, contractRecords, "No hi ha contractes menors amb aquest filtre.");
  renderRecordGroup(detailOtherRecords, otherRecords, "No hi ha altres registres amb aquest filtre.");
}

async function ensureConceptIndexLoaded() {
  if (state.conceptManifest) return;
  const response = await fetch("data/concepts/manifest.json");
  if (!response.ok) throw new Error("No s'ha pogut carregar l'índex de conceptes.");
  state.conceptManifest = await response.json();
}

async function ensureConceptYearLoaded(year) {
  await ensureConceptIndexLoaded();
  if (state.conceptCache.has(year)) return;
  const files = state.conceptManifest?.years?.[year]?.files || [];
  if (!files.length) {
    state.conceptCache.set(year, []);
    return;
  }
  const chunks = await Promise.all(
    files.map(async (file) => {
      const response = await fetch(`data/concepts/${file}`);
      if (!response.ok) throw new Error("No s'ha pogut carregar l'any de conceptes seleccionat.");
      const payload = await response.json();
      return payload.records || [];
    })
  );
  state.conceptCache.set(year, chunks.flat());
}

function filteredConceptRecords() {
  const query = state.conceptSearch.trim().toLowerCase();
  if (!query || !state.conceptManifest) return [];

  const records =
    state.conceptYear === "all"
      ? Object.keys(state.conceptManifest.years || {})
          .flatMap((year) => state.conceptCache.get(year) || [])
      : state.conceptCache.get(state.conceptYear) || [];

  return records
    .filter((record) => {
      const haystack = [record.title, record.counterparty, record.department, record.organization, record.reference]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    })
    .sort((left, right) => {
      if ((right.year || 0) !== (left.year || 0)) return (right.year || 0) - (left.year || 0);
      return (right.amount || 0) - (left.amount || 0);
    })
    .slice(0, 50);
}

function renderConceptResults() {
  conceptResults.innerHTML = "";
  conceptStatus.textContent = "";

  if (!state.conceptSearch.trim()) {
    conceptResults.innerHTML = '<p class="empty-state">Escriu un concepte per buscar actes, campanyes o accions.</p>';
    return;
  }

  if (state.conceptLoading) {
    conceptStatus.textContent = `Any: ${state.conceptYear === "all" ? "Tots" : state.conceptYear} · calculant despesa...`;
    conceptResults.innerHTML = '<p class="empty-state">Calculant euros gastats i carregant coincidències...</p>';
    return;
  }

  if (!state.conceptManifest) {
    conceptResults.innerHTML = '<p class="empty-state">Carregant índex de conceptes...</p>';
    return;
  }

  const records = filteredConceptRecords();
  conceptStatus.textContent = `Any: ${state.conceptYear === "all" ? "Tots" : state.conceptYear} · ${integer(records.length)} coincidències`;
  renderRecordGroup(conceptResults, records, "No hi ha coincidències per aquest concepte.");
}

function render() {
  const yearData = currentYearData();
  renderSummary(yearData);
  renderRanking(
    sections.invoiceSuppliers,
    yearData.invoices.top_suppliers,
    "amount",
    (item) => [item.cif, item.city, item.province].filter(Boolean).join(" · ") || `${integer(item.count)} registres`
  );
  renderRanking(
    sections.supplierSpend,
    yearData.invoices.top_supplier_spend || [],
    "amount",
    (item) => [item.cif, item.city, item.province].filter(Boolean).join(" · ") || `${integer(item.count)} registres`
  );
  renderRanking(sections.invoiceDepartments, yearData.invoices.top_departments);
  renderRanking(
    sections.contractSuppliers,
    yearData.contracts.top_suppliers,
    "amount",
    (item) => [item.department, item.type, item.cif].filter(Boolean).join(" · ") || `${integer(item.count)} adjudicacions`
  );
  renderRanking(sections.contractDepartments, yearData.contracts.top_departments);
  renderRanking(sections.grantBeneficiaries, yearData.grants.top_beneficiaries);
  renderRanking(
    sections.budgetLines,
    yearData.budget.top_lines,
    "final",
    (item) => `Inicial ${money(item.initial)} · Disponible ${money(item.available)}`
  );
  renderResults();
  renderDetail();
  renderConceptResults();
}

function bindEvents() {
  searchInput.addEventListener("input", (event) => {
    state.search = event.target.value;
    state.selectedProfileId = null;
    state.selectedProfileDetail = null;
    render();
  });

  yearFilter.addEventListener("change", (event) => {
    state.year = event.target.value;
    yearFilterSecondary.value = state.year === "all" ? String(state.summary.overview.latest_year) : state.year;
    state.selectedProfileDetail = null;
    render();
  });

  yearFilterSecondary.addEventListener("change", (event) => {
    state.year = event.target.value;
    yearFilter.value = state.year;
    state.selectedProfileDetail = null;
    render();
  });

  kindFilter.addEventListener("change", (event) => {
    state.kind = event.target.value;
    state.selectedProfileId = null;
    state.selectedProfileDetail = null;
    render();
  });

  departmentFilter.addEventListener("change", (event) => {
    state.department = event.target.value;
    state.selectedProfileId = null;
    state.selectedProfileDetail = null;
    render();
  });

  minAmountFilter?.addEventListener("input", (event) => {
    state.minAmount = event.target.value;
    renderDetail();
  });

  maxAmountFilter?.addEventListener("input", (event) => {
    state.maxAmount = event.target.value;
    renderDetail();
  });

  dateFromFilter?.addEventListener("input", (event) => {
    state.dateFrom = event.target.value;
    renderDetail();
  });

  dateToFilter?.addEventListener("input", (event) => {
    state.dateTo = event.target.value;
    renderDetail();
  });

  conceptSearchInput.addEventListener("input", async (event) => {
    state.conceptSearch = event.target.value;
    if (state.conceptSearch.trim()) {
      state.conceptLoading = true;
      renderConceptResults();
      if (state.conceptYear === "all") {
        await ensureConceptIndexLoaded();
        for (const year of Object.keys(state.conceptManifest.years || {})) {
          await ensureConceptYearLoaded(year);
        }
      } else {
        await ensureConceptYearLoaded(state.conceptYear);
      }
      state.conceptLoading = false;
    } else {
      state.conceptLoading = false;
    }
    renderConceptResults();
  });

  conceptYearFilter.addEventListener("change", async (event) => {
    state.conceptYear = event.target.value;
    if (state.conceptSearch.trim()) {
      state.conceptLoading = true;
      renderConceptResults();
      if (state.conceptYear === "all") {
        await ensureConceptIndexLoaded();
        for (const year of Object.keys(state.conceptManifest.years || {})) {
          await ensureConceptYearLoaded(year);
        }
      } else {
        await ensureConceptYearLoaded(state.conceptYear);
      }
      state.conceptLoading = false;
    } else {
      state.conceptLoading = false;
    }
    renderConceptResults();
  });
}

async function init() {
  const [summaryResponse, searchResponse] = await Promise.all([
    fetch("data/transparency_summary.json"),
    fetch("data/search_index.json"),
  ]);

  if (!summaryResponse.ok || !searchResponse.ok) {
    throw new Error("No s'han pogut carregar els fitxers principals de dades.");
  }

  state.summary = await summaryResponse.json();
  state.searchIndex = await searchResponse.json();

  setHeroStats(state.summary);
  setYearOptions(state.summary);
  setConceptYearOptions(state.summary);
  setDepartmentOptions(state.searchIndex);
  bindEvents();
  render();
}

init().catch((error) => {
  console.error(error);
  searchResults.innerHTML = '<p class="empty-state">Error carregant la web de dades.</p>';
});
