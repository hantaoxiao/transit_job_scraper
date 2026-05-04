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
    jobList: document.getElementById("jobList"),
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
    const normalized = String(value).replace(/\b(Open Until Filled|Open until filled|Apply immediately)\b.*/i, "");
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
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
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
      .map(([agency, count]) => `<button class="agency-chip" type="button" data-agency="${escapeAttribute(agency)}">${escapeHtml(agency)} <span>${count}</span></button>`)
      .join("");

    els.agencyChips.querySelectorAll(".agency-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        els.agencyFilter.value = chip.dataset.agency;
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

  function filterJobs() {
    const query = els.searchInput.value.trim().toLowerCase();
    const agency = els.agencyFilter.value;
    const category = els.categoryFilter.value;
    const seniority = els.seniorityFilter.value;
    const minSalary = Number(els.salaryRange.value);
    const includeUnknown = els.includeUnknownSalary.checked;

    return jobs.filter((job) => {
      const haystack = [
        job.title,
        job.agency,
        job.city,
        job.state,
        job.category,
        job.ai_sort_seniority,
        job.raw_context,
      ]
        .join(" ")
        .toLowerCase();

      return (
        (!query || haystack.includes(query)) &&
        (!agency || job.agency === agency) &&
        (!category || job.category === category) &&
        (!seniority || job.ai_sort_seniority === seniority) &&
        passesSalary(job, minSalary, includeUnknown)
      );
    });
  }

  function sortJobs(items) {
    const sort = els.sortSelect.value;
    const sorted = [...items];
    const textCompare = (a, b, field) => String(a[field] || "").localeCompare(String(b[field] || ""));

    sorted.sort((a, b) => {
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
    els.resultCount.textContent = `${filtered.length.toLocaleString()} shown`;
    updateAgencyChipState();

    if (!filtered.length) {
      els.jobList.innerHTML = '<div class="empty">No jobs match these filters.</div>';
      return;
    }

    els.jobList.innerHTML = filtered.slice(0, 300).map(renderJob).join("");
  }

  function updateAgencyChipState() {
    els.agencyChips.querySelectorAll(".agency-chip").forEach((chip) => {
      chip.classList.toggle("active", chip.dataset.agency === els.agencyFilter.value);
    });
  }

  function renderJob(job) {
    const location = [job.city, job.state].filter(Boolean).join(", ");
    const dates = [
      job.posted_date ? `Posted ${formatDate(job.posted_date)}` : "",
      job.closing_date ? `Closes ${formatDate(job.closing_date)}` : "",
    ].filter(Boolean);

    return `
      <article class="job-card">
        <div class="job-main">
          <div class="job-kicker">
            <span>${escapeHtml(job.agency)}</span>
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
        <div class="salary-box">
          <div class="salary-label">Pay</div>
          <div class="salary-value">${escapeHtml(job.salary_range_display || job.salary_display || job.salary_text || "Salary not listed")}</div>
          ${salaryRangeRows(job)}
        </div>
      </article>
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
    ];

    inputs.forEach((input) => input.addEventListener("input", () => {
      els.salaryOutput.textContent = Number(els.salaryRange.value) ? money.format(Number(els.salaryRange.value)) : "Any";
      renderJobs();
    }));
  }

  optionize(els.agencyFilter, uniqueSorted("agency"));
  optionize(els.categoryFilter, uniqueSorted("category"));
  optionize(els.seniorityFilter, uniqueSorted("ai_sort_seniority"));
  setHeader();
  renderAgencyChips();
  renderJobs();
  bind();
})();
