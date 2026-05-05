(function () {
  const payload = window.TRANSIT_JOBS_DATA || { jobs: [], generated_at: "" };
  const jobs = payload.jobs || [];

  const els = {
    generatedAt: document.getElementById("generatedAt"),
    totalJobs: document.getElementById("totalJobs"),
    searchInput: document.getElementById("searchInput"),
    agencyFilter: document.getElementById("agencyFilter"),
    categoryFilter: document.getElementById("categoryFilter"),
    seniorityFilter: document.getElementById("seniorityFilter"),
    sortSelect: document.getElementById("sortSelect"),
    salaryRange: document.getElementById("salaryRange"),
    salaryOutput: document.getElementById("salaryOutput"),
    includeUnknownSalary: document.getElementById("includeUnknownSalary"),
    agencyChips: document.getElementById("agencyChips"),
    resultCount: document.getElementById("resultCount"),
    pageSizeSelect: document.getElementById("pageSizeSelect"),
    pagination: document.getElementById("pagination"),
    jobList: document.getElementById("jobList"),
    mapView: document.getElementById("mapView"),
    listViewButton: document.getElementById("listViewButton"),
    mapViewButton: document.getElementById("mapViewButton"),
  };

  let currentView = "list";
  let currentPage = 1;

  const agencyMeta = {
    "AC Transit": { short: "AC", name: "AC Transit", color: "#0f6b50", location: "Oakland, CA", logo: "assets/agency-logos/ac-transit.png" },
    "BART": { short: "BART", name: "Bay Area Rapid Transit", color: "#0074bc", location: "Oakland, CA", logo: "assets/agency-logos/bart.png" },
    "CTA": { short: "CTA", name: "Chicago Transit Authority", color: "#c62828", location: "Chicago, IL", logo: "assets/agency-logos/cta.png" },
    "Honolulu DTS": { short: "DTS", name: "Honolulu Department of Transportation Services", color: "#007a7a", location: "Honolulu, HI", logo: "assets/agency-logos/honolulu-dts.png" },
    "King County Metro": { short: "KCM", name: "King County Metro", color: "#f0a202", location: "Seattle, WA", logo: "assets/agency-logos/king-county-metro.png" },
    "LA Metro": { short: "LA", name: "Los Angeles Metro", color: "#d11f3d", location: "Los Angeles, CA", logo: "assets/agency-logos/la-metro.png" },
    "MARTA": { short: "MARTA", name: "Metropolitan Atlanta Rapid Transit Authority", color: "#1c4f9c", location: "Atlanta, GA", logo: "assets/agency-logos/marta.png" },
    "MBTA": { short: "T", name: "Massachusetts Bay Transportation Authority", color: "#111111", location: "Boston, MA", logo: "assets/agency-logos/mbta.png" },
    "MTA": { short: "MTA", name: "Metropolitan Transportation Authority", color: "#0039a6", location: "New York, NY", logo: "assets/agency-logos/mta.svg" },
    "NJ Transit": { short: "NJT", name: "NJ Transit", color: "#f37021", location: "Newark, NJ", logo: "assets/agency-logos/nj-transit.png" },
    "RTC Transit": { short: "RTC", name: "Regional Transportation Commission of Southern Nevada", color: "#6f2c91", location: "Las Vegas, NV", logo: "assets/agency-logos/rtc-transit.png" },
    "RTD Denver": { short: "RTD", name: "Regional Transportation District Denver", color: "#005daa", location: "Denver, CO", logo: "assets/agency-logos/rtd-denver.png" },
    "SEPTA": { short: "SEPTA", name: "Southeastern Pennsylvania Transportation Authority", color: "#1f4e79", location: "Philadelphia, PA", logo: "assets/agency-logos/septa.png" },
    "SFMTA": { short: "Muni", name: "San Francisco Municipal Transportation Agency", color: "#b71c1c", location: "San Francisco, CA", logo: "assets/agency-logos/sfmta.png" },
    "Sound Transit": { short: "ST", name: "Sound Transit", color: "#00843d", location: "Seattle, WA", logo: "assets/agency-logos/sound-transit.svg" },
    "TriMet": { short: "TriMet", name: "TriMet", color: "#006b54", location: "Portland, OR", logo: "assets/agency-logos/trimet.png" },
    "WMATA": { short: "Metro", name: "Washington Metropolitan Area Transit Authority", color: "#005ea8", location: "Washington, DC", logo: "assets/agency-logos/wmata.svg" },
  };

  const agencyPoints = {
    "AC Transit": { x: 14, y: 52 },
    "BART": { x: 14, y: 52 },
    "CTA": { x: 62, y: 38 },
    "Honolulu DTS": { x: 8, y: 84 },
    "King County Metro": { x: 17, y: 21 },
    "LA Metro": { x: 18, y: 63 },
    "MARTA": { x: 69, y: 67 },
    "MBTA": { x: 88, y: 28 },
    "MTA": { x: 84, y: 35 },
    "NJ Transit": { x: 83, y: 38 },
    "RTC Transit": { x: 24, y: 58 },
    "RTD Denver": { x: 44, y: 49 },
    "SEPTA": { x: 81, y: 41 },
    "SFMTA": { x: 13, y: 53 },
    "Sound Transit": { x: 17, y: 21 },
    "TriMet": { x: 16, y: 27 },
    "WMATA": { x: 79, y: 47 },
  };

  const locationPoints = {
    "Alexandria, VA": { x: 79, y: 47 },
    "Atlanta, GA": { x: 69, y: 67 },
    "Boston, MA": { x: 88, y: 28 },
    "Brooklyn, NY": { x: 84, y: 36 },
    "Chicago, IL": { x: 62, y: 38 },
    "Denver, CO": { x: 44, y: 49 },
    "Honolulu, HI": { x: 8, y: 84 },
    "Jamaica, NY": { x: 84, y: 36 },
    "Las Vegas, NV": { x: 24, y: 58 },
    "Los Angeles, CA": { x: 18, y: 63 },
    "New York, NY": { x: 84, y: 35 },
    "Newark, NJ": { x: 83, y: 38 },
    "Oakland, CA": { x: 14, y: 52 },
    "Philadelphia, PA": { x: 81, y: 41 },
    "Portland, OR": { x: 16, y: 27 },
    "San Francisco, CA": { x: 13, y: 53 },
    "Seattle, WA": { x: 17, y: 21 },
    "Washington, DC": { x: 79, y: 47 },
  };

  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

  function truthy(value) {
    return value === true || value === "True" || value === "true" || value === 1 || value === "1";
  }

  function numeric(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function dateValue(value) {
    if (!value) return 0;
    const normalized = conciseDate(value).replace(/\b(Open Until Filled|Open until filled|Apply immediately)\b.*/i, "");
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
  }

  function uniqueSorted(field) {
    return [...new Set(jobs.map((job) => job[field]).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }

  function optionize(select, values) {
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  function formatDate(value) {
    if (!value) return "";
    const concise = conciseDate(value);
    const date = new Date(concise);
    if (Number.isNaN(date.getTime())) return concise;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function conciseDate(value) {
    const text = String(value || "").trim();
    if (!text) return "";

    const status = text.match(/\b(continuous|open until filled|apply immediately)\b/i);
    if (status && status.index < 40) return status[1].replace(/\b\w/g, (letter) => letter.toUpperCase());

    const numeric = text.match(/\b\d{1,2}\/\d{1,2}\/\d{4}/i);
    if (numeric) return numeric[0].trim();

    const month = text.match(/\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}/i);
    if (month) return month[0].trim();

    return text.length <= 48 ? text : "";
  }

  function setHeader() {
    els.totalJobs.textContent = jobs.length.toLocaleString();
    els.generatedAt.textContent = payload.generated_at ? `Updated ${formatDate(payload.generated_at)}` : "Updated locally";
  }

  function renderAgencyChips() {
    const counts = jobs.reduce((acc, job) => {
      acc[job.agency] = (acc[job.agency] || 0) + 1;
      return acc;
    }, {});

    els.agencyChips.innerHTML = Object.entries(counts)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([agency, count]) => `<button class="agency-chip" type="button" data-agency="${escapeAttribute(agency)}">${agencyBadge(agency)}<span class="agency-chip-name">${escapeHtml(agency)}</span> <span>${count}</span></button>`)
      .join("");

    els.agencyChips.querySelectorAll(".agency-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        els.agencyFilter.value = chip.dataset.agency;
        resetPage();
        renderJobs();
      });
    });
  }

  function comparableAnnual(job) {
    return numeric(job.salary_annual_min_est || job.salary_annual_max_est);
  }

  function comparableAnnualMax(job) {
    return numeric(job.salary_annual_max_est || job.salary_annual_min_est);
  }

  function passesSalary(job, minSalary, includeUnknown) {
    if (!minSalary) return true;
    if (!truthy(job.salary_is_comparable)) return includeUnknown;
    return comparableAnnual(job) >= minSalary;
  }

  const searchAliases = {
    analyst: [
      "analysis",
      "analytics",
      "analytical",
      "analyze",
      "data",
      "data science",
      "business intelligence",
      "metrics",
      "reporting",
      "dashboard",
      "visualization",
      "gis",
      "research",
      "planning",
      "planner",
      "forecast",
      "modeling",
      "performance",
      "budget",
      "finance",
      "strategy",
      "policy",
    ],
    analytics: ["analyst", "analysis", "data", "data science", "metrics", "reporting", "dashboard", "visualization"],
    data: ["analytics", "analysis", "data science", "business intelligence", "dashboard", "visualization", "gis", "reporting"],
    plan: ["planning", "planner", "plans", "strategy", "strategic", "forecast", "program", "project"],
    planner: ["planning", "strategy", "policy", "forecast", "analysis", "project", "program"],
    planning: ["planner", "strategy", "policy", "forecast", "analysis", "project", "program"],
    engineer: ["engineering", "technical", "design", "infrastructure", "systems"],
    mechanic: ["maintenance", "technician", "repair", "equipment", "vehicle"],
    driver: ["operator", "bus operator", "train operator"],
    operator: ["driver", "operations", "bus operator", "train operator"],
  };

  function searchText(job) {
    return [
      job.title,
      job.agency,
      agencyFullName(job.agency),
      agencyLocation(job.agency),
      job.city,
      job.state,
      job.category,
      job.ai_sort_category,
      job.ai_sort_seniority,
      job.department,
      job.employment_type,
      job.raw_context,
      job.description,
      job.full_job_description,
      job.all_meaningful_info,
    ]
      .join(" ")
      .toLowerCase();
  }

  function queryTokens(query) {
    return query
      .toLowerCase()
      .split(/[^a-z0-9$]+/)
      .map((token) => token.trim())
      .filter((token) => token.length > 1);
  }

  function tokenVariants(token) {
    const variants = new Set([token]);
    if (token.endsWith("s") && token.length > 3) variants.add(token.slice(0, -1));
    if (token.endsWith("er") && token.length > 5) variants.add(token.slice(0, -2));
    if (token.endsWith("or") && token.length > 5) variants.add(token.slice(0, -2));
    (searchAliases[token] || []).forEach((alias) => variants.add(alias));
    return [...variants];
  }

  function fieldText(job, fields) {
    return fields.map((field) => String(job[field] || "").toLowerCase()).join(" ");
  }

  function containsSearchTerm(text, term) {
    if (!term) return false;
    if (term.includes(" ")) return text.includes(term);
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`\\b${escaped}\\b`, "i").test(text)) return true;
    return term.length >= 4 && new RegExp(`\\b${escaped}[a-z0-9-]*\\b`, "i").test(text);
  }

  function isPlanningQuery(token) {
    return ["plan", "planner", "planning", "plans"].includes(token);
  }

  function matchesPlanningFamily(text) {
    return /\b(plan|plans|planner|planners|planning)\b/i.test(text);
  }

  function searchScore(job, query) {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return 0;

    const tokens = queryTokens(normalizedQuery);
    const planningFamilyQuery = tokens.length === 1 && isPlanningQuery(tokens[0]);
    const title = String(job.title || "").toLowerCase();
    const category = fieldText(job, ["category", "ai_sort_category", "ai_sort_seniority", "department"]);
    const body = searchText(job);
    let score = 0;

    if (planningFamilyQuery) {
      if (matchesPlanningFamily(title)) score += 120;
      if (matchesPlanningFamily(category)) score += 60;
      if (matchesPlanningFamily(body)) score += 30;
    } else {
      if (title.includes(normalizedQuery)) score += 120;
      if (category.includes(normalizedQuery)) score += 60;
      if (body.includes(normalizedQuery)) score += 30;
    }

    tokens.forEach((token) => {
      const variants = tokenVariants(token);
      let tokenScore = 0;

      if (isPlanningQuery(token)) {
        if (matchesPlanningFamily(title)) tokenScore = Math.max(tokenScore, 110);
        if (matchesPlanningFamily(category)) tokenScore = Math.max(tokenScore, 70);
      }

      variants.forEach((variant) => {
        const phraseAlias = variant.includes(" ");
        if (containsSearchTerm(title, variant)) tokenScore = Math.max(tokenScore, variant === token ? 80 : phraseAlias ? 240 : 70);
        else if (containsSearchTerm(category, variant)) tokenScore = Math.max(tokenScore, variant === token ? 44 : phraseAlias ? 62 : 44);
        else if (containsSearchTerm(body, variant)) tokenScore = Math.max(tokenScore, variant === token ? 24 : 16);
      });
      score += tokenScore;
    });

    return score;
  }

  function matchesSearch(job, query) {
    const tokens = queryTokens(query);
    if (!tokens.length) return true;
    if (tokens.length === 1 && isPlanningQuery(tokens[0])) {
      const title = String(job.title || "").toLowerCase();
      const category = fieldText(job, ["category", "ai_sort_category", "ai_sort_seniority", "department"]);
      return matchesPlanningFamily(title) || matchesPlanningFamily(category);
    }

    const body = searchText(job);
    const minimumScore = tokens.length > 1 ? tokens.length * 30 : 40;

    return (
      searchScore(job, query) >= minimumScore &&
      tokens.every((token) => tokenVariants(token).some((variant) => containsSearchTerm(body, variant)))
    );
  }

  function filterJobs() {
    const query = els.searchInput.value.trim().toLowerCase();
    const agency = els.agencyFilter.value;
    const category = els.categoryFilter.value;
    const seniority = els.seniorityFilter.value;
    const minSalary = Number(els.salaryRange.value);
    const includeUnknown = els.includeUnknownSalary.checked;

    return jobs.filter((job) => {
      return (
        (!query || matchesSearch(job, query)) &&
        (!agency || job.agency === agency) &&
        (!category || job.category === category) &&
        (!seniority || job.ai_sort_seniority === seniority) &&
        passesSalary(job, minSalary, includeUnknown)
      );
    });
  }

  function sortJobs(items) {
    const sort = els.sortSelect.value;
    const query = els.searchInput.value.trim().toLowerCase();
    const sorted = [...items];
    const textCompare = (a, b, field) => String(a[field] || "").localeCompare(String(b[field] || ""));

    sorted.sort((a, b) => {
      if (query) {
        const relevance = searchScore(b, query) - searchScore(a, query);
        if (relevance) return relevance;
      }

      if (sort === "closing_asc") {
        const aDate = dateValue(a.closing_date);
        const bDate = dateValue(b.closing_date);
        if (aDate && bDate && aDate !== bDate) return aDate - bDate;
        if (aDate !== bDate) return aDate ? -1 : 1;
      } else if (sort === "pay_desc") {
        const diff = comparableAnnualMax(b) - comparableAnnualMax(a);
        if (diff) return diff;
      } else if (sort === "pay_asc") {
        const aPay = comparableAnnual(a);
        const bPay = comparableAnnual(b);
        if (aPay && bPay && aPay !== bPay) return aPay - bPay;
        if (aPay !== bPay) return aPay ? -1 : 1;
      } else if (sort === "agency_asc") {
        const agency = textCompare(a, b, "agency");
        if (agency) return agency;
      } else if (sort === "title_asc") {
        const title = textCompare(a, b, "title");
        if (title) return title;
      } else {
        const diff = dateValue(b.posted_date) - dateValue(a.posted_date);
        if (diff) return diff;
      }

      return textCompare(a, b, "title") || textCompare(a, b, "agency");
    });

    return sorted;
  }

  function renderJobs() {
    const filtered = sortJobs(filterJobs());
    const pageSize = selectedPageSize();
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    currentPage = Math.min(Math.max(currentPage, 1), totalPages);
    const startIndex = (currentPage - 1) * pageSize;
    const pageItems = filtered.slice(startIndex, startIndex + pageSize);

    els.resultCount.textContent = resultCountText(filtered.length, startIndex, pageItems.length);
    updateAgencyChipState();
    updateViewState();

    if (!filtered.length) {
      els.jobList.innerHTML = '<div class="empty">No jobs match these filters.</div>';
      els.mapView.innerHTML = '<div class="empty">No jobs match these filters.</div>';
      els.pagination.innerHTML = "";
      return;
    }

    els.jobList.innerHTML = pageItems.map(renderJob).join("");
    renderPagination(filtered.length, pageSize, totalPages);
    renderMap(filtered);
  }

  function selectedPageSize() {
    return Number(els.pageSizeSelect.value) || 10;
  }

  function resultCountText(total, startIndex, pageCount) {
    if (!total) return "0 shown";
    const start = startIndex + 1;
    const end = startIndex + pageCount;
    return `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()}`;
  }

  function renderPagination(total, pageSize, totalPages) {
    if (total <= pageSize) {
      els.pagination.innerHTML = "";
      return;
    }

    els.pagination.innerHTML = `
      <button class="page-button" type="button" data-page-action="prev" ${currentPage === 1 ? "disabled" : ""}>Previous</button>
      <span class="page-status">Page ${currentPage.toLocaleString()} of ${totalPages.toLocaleString()}</span>
      <button class="page-button" type="button" data-page-action="next" ${currentPage === totalPages ? "disabled" : ""}>Next</button>
    `;

    els.pagination.querySelectorAll(".page-button").forEach((button) => {
      button.addEventListener("click", () => {
        currentPage += button.dataset.pageAction === "next" ? 1 : -1;
        renderJobs();
        scrollToResults();
      });
    });
  }

  function resetPage() {
    currentPage = 1;
  }

  function scrollToResults() {
    document.querySelector(".results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function updateViewState() {
    const isMap = currentView === "map";
    els.jobList.classList.toggle("hidden", isMap);
    els.mapView.classList.toggle("hidden", !isMap);
    els.pagination.classList.toggle("hidden", isMap);
    els.listViewButton.classList.toggle("active", !isMap);
    els.mapViewButton.classList.toggle("active", isMap);
    els.listViewButton.setAttribute("aria-pressed", String(!isMap));
    els.mapViewButton.setAttribute("aria-pressed", String(isMap));
  }

  function updateAgencyChipState() {
    els.agencyChips.querySelectorAll(".agency-chip").forEach((chip) => {
      chip.classList.toggle("active", chip.dataset.agency === els.agencyFilter.value);
    });
  }

  function renderJob(job) {
    const location = agencyLocation(job.agency) || [job.city, job.state].filter(Boolean).join(", ");
    const dates = [
      job.posted_date ? `Posted ${formatDate(job.posted_date)}` : "",
      job.closing_date ? `Closes ${formatDate(job.closing_date)}` : "",
    ].filter(Boolean);

    return `
      <article class="job-card">
        <div class="job-main">
          <div class="job-kicker">
            <span>${escapeHtml(agencyFullName(job.agency))}</span>
            ${location ? `<span>${escapeHtml(location)}</span>` : ""}
          </div>
          <h3 class="job-title">
            <a href="${escapeAttribute(job.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a>
          </h3>
          <div class="job-tags">
            <span class="tag">${escapeHtml(job.category || "Other")}</span>
            <span class="tag">${escapeHtml(job.ai_sort_seniority || "Professional")}</span>
            ${dates.map((date) => `<span class="tag date-tag">${escapeHtml(date)}</span>`).join("")}
          </div>
        </div>
        <div class="job-logo-slot">
          ${agencyLogo(job.agency)}
        </div>
        <div class="salary-box">
          <div class="salary-label">Pay</div>
          <div class="salary-value">${escapeHtml(job.salary_range_display || job.salary_display || job.salary_text || "Salary not listed")}</div>
          ${salaryRangeRows(job)}
        </div>
      </article>
    `;
  }

  function renderMap(filtered) {
    const groups = mapGroups(filtered);
    const markers = groups.map((group) => {
      const meta = getAgencyMeta(group.agency);
      return `
        <button class="map-marker" type="button" style="left:${group.point.x}%; top:${group.point.y}%; --agency-color:${escapeAttribute(meta.color)}" title="${escapeAttribute(group.agency)}: ${group.count} jobs" data-agency="${escapeAttribute(group.agency)}">
          <span>${escapeHtml(meta.short)}</span>
          <strong>${group.count}</strong>
        </button>
      `;
    }).join("");

    els.mapView.innerHTML = `
      <div class="map-shell">
        <div class="map-canvas">
          <div class="map-land"></div>
          <div class="map-label west">West</div>
          <div class="map-label central">Central</div>
          <div class="map-label east">East</div>
          ${markers}
        </div>
        <div class="map-results">
          ${groups.map(renderMapGroup).join("")}
        </div>
      </div>
    `;

    els.mapView.querySelectorAll(".map-marker").forEach((marker) => {
      marker.addEventListener("click", () => {
        els.agencyFilter.value = marker.dataset.agency;
        currentView = "list";
        resetPage();
        renderJobs();
      });
    });
  }

  function mapGroups(items) {
    const groups = new Map();

    items.forEach((job) => {
      const location = agencyLocation(job.agency) || [job.city, job.state].filter(Boolean).join(", ");
      const key = `${job.agency}|${location || job.agency}`;
      const point = pointForJob(job, location);

      if (!groups.has(key)) {
        groups.set(key, {
          agency: job.agency,
          location,
          point,
          count: 0,
          maxPay: 0,
          examples: [],
        });
      }

      const group = groups.get(key);
      group.count += 1;
      group.maxPay = Math.max(group.maxPay, comparableAnnualMax(job));
      if (group.examples.length < 3) group.examples.push(job);
    });

    return offsetSharedPoints([...groups.values()].sort((a, b) => b.count - a.count || a.agency.localeCompare(b.agency)));
  }

  function offsetSharedPoints(groups) {
    const seen = new Map();
    return groups.map((group) => {
      const key = `${Math.round(group.point.x)}|${Math.round(group.point.y)}`;
      const count = seen.get(key) || 0;
      seen.set(key, count + 1);
      if (!count) return group;

      const angle = count * 1.9;
      const radius = 3 + Math.min(count, 4);
      return {
        ...group,
        point: {
          x: clamp(group.point.x + Math.cos(angle) * radius, 4, 96),
          y: clamp(group.point.y + Math.sin(angle) * radius, 6, 94),
        },
      };
    });
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function pointForJob(job, location) {
    return locationPoints[location] || agencyPoints[job.agency] || { x: 50, y: 50 };
  }

  function renderMapGroup(group) {
    const pay = group.maxPay ? `Top pay ${money.format(group.maxPay)}` : "Pay varies";
    return `
      <article class="map-group">
        <div class="map-group-head">
          ${agencyBadge(group.agency)}
          <div>
            <strong>${escapeHtml(agencyFullName(group.agency))}</strong>
            <span>${escapeHtml(group.location || "Multiple locations")} &middot; ${group.count} jobs &middot; ${escapeHtml(pay)}</span>
          </div>
        </div>
        <div class="map-group-jobs">
          ${group.examples.map((job) => `<a href="${escapeAttribute(job.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(job.title)}</a>`).join("")}
        </div>
      </article>
    `;
  }

  function getAgencyMeta(agency) {
    return agencyMeta[agency] || { short: agency.slice(0, 3).toUpperCase(), name: agency, color: "#465a65" };
  }

  function agencyFullName(agency) {
    return getAgencyMeta(agency).name;
  }

  function agencyLocation(agency) {
    return getAgencyMeta(agency).location || "";
  }

  function agencyBadge(agency) {
    const meta = getAgencyMeta(agency);
    return `<span class="agency-badge" style="--agency-color:${escapeAttribute(meta.color)}" title="${escapeAttribute(meta.name)}">${escapeHtml(meta.short)}</span>`;
  }

  function agencyLogo(agency) {
    const meta = getAgencyMeta(agency);
    if (!meta.logo) return agencyBadge(agency);
    return `
      <div class="agency-logo-frame" title="${escapeAttribute(meta.name)}">
        <img class="agency-logo" src="${escapeAttribute(meta.logo)}" alt="${escapeAttribute(meta.name)} logo" loading="lazy">
      </div>
    `;
  }

  function salaryRangeRows(job) {
    if (!truthy(job.salary_is_listed) || !truthy(job.salary_is_comparable)) return "";
    const isHourly = job.salary_unit === "hourly";
    const min = numeric(isHourly ? job.salary_min : job.salary_annual_min_est);
    const max = numeric(isHourly ? job.salary_max : job.salary_annual_max_est);
    if (!min && !max) return "";

    return `
      <div class="salary-grid" aria-label="Salary range">
        <span>Min</span><strong>${formatSalaryValue(min, job.salary_unit)}</strong>
        <span>Max</span><strong>${formatSalaryValue(max || min, job.salary_unit)}</strong>
      </div>
    `;
  }

  function formatSalaryValue(value, unit) {
    if (unit === "hourly") return `$${Number(value).toFixed(2)}/hr`;
    return money.format(value);
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("`", "&#096;");
  }

  function bind() {
    const inputs = [
      els.searchInput,
      els.agencyFilter,
      els.categoryFilter,
      els.seniorityFilter,
      els.sortSelect,
      els.salaryRange,
      els.includeUnknownSalary,
      els.pageSizeSelect,
    ];

    inputs.forEach((input) => input.addEventListener("input", () => {
      els.salaryOutput.textContent = Number(els.salaryRange.value) ? money.format(Number(els.salaryRange.value)) : "Any";
      resetPage();
      renderJobs();
    }));

    els.listViewButton.addEventListener("click", () => {
      currentView = "list";
      renderJobs();
    });

    els.mapViewButton.addEventListener("click", () => {
      currentView = "map";
      renderJobs();
    });
  }

  optionize(els.agencyFilter, uniqueSorted("agency"));
  optionize(els.categoryFilter, uniqueSorted("category"));
  optionize(els.seniorityFilter, uniqueSorted("ai_sort_seniority"));
  setHeader();
  renderAgencyChips();
  renderJobs();
  bind();
})();
