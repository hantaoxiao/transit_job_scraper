(function () {
  const payload = window.TRANSIT_JOBS_DATA || { jobs: [], generated_at: "" };
  const jobs = payload.jobs || [];

  const els = {
    generatedAt: document.getElementById("generatedAt"),
    totalJobs: document.getElementById("totalJobs"),
    searchInput: document.getElementById("searchInput"),
    agencyFilter: document.getElementById("agencyFilter"),
    stateFilter: document.getElementById("stateFilter"),
    categoryFilter: document.getElementById("categoryFilter"),
    seniorityFilter: document.getElementById("seniorityFilter"),
    employmentTypeFilter: document.getElementById("employmentTypeFilter"),
    sortSelect: document.getElementById("sortSelect"),
    salaryRange: document.getElementById("salaryRange"),
    salaryOutput: document.getElementById("salaryOutput"),
    includeUnknownSalary: document.getElementById("includeUnknownSalary"),
    clearFiltersButton: document.getElementById("clearFiltersButton"),
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
  const DEFAULT_SORT = "posted_desc";

  const agencyMeta = {
    "AC Transit": { short: "AC", name: "AC Transit", color: "#0f6b50", location: "Oakland, CA", logo: "assets/agency-logos/ac-transit.png" },
    "Access Services": { short: "AS", name: "Access Services", color: "#005eb8", location: "El Monte, CA" },
    "Antelope Valley Transit Authority": { short: "AVTA", name: "Antelope Valley Transit Authority", color: "#005eb8", location: "Lancaster, CA" },
    "BART": { short: "BART", name: "Bay Area Rapid Transit", color: "#0074bc", location: "Oakland, CA", logo: "assets/agency-logos/bart.png" },
    "Big Blue Bus": { short: "BBB", name: "Big Blue Bus", color: "#005eb8", location: "Santa Monica, CA" },
    "Broward County Transit": { short: "BCT", name: "Broward County Transit", color: "#005eb8", location: "Fort Lauderdale, FL", logo: "assets/agency-logos/broward-county-transit.png" },
    "Ben Franklin Transit": { short: "BFT", name: "Ben Franklin Transit", color: "#005eb8", location: "Richland, WA", logo: "assets/agency-logos/ben-franklin-transit.png" },
    "CDTA": { short: "CDTA", name: "Capital District Transportation Authority", color: "#005eb8", location: "Albany, NY", logo: "assets/agency-logos/cdta.png" },
    "Caltrain": { short: "Caltrain", name: "Caltrain", color: "#d52b1e", location: "San Carlos, CA", logo: "assets/agency-logos/caltrain.png" },
    "CATS": { short: "CATS", name: "Charlotte Area Transit System", color: "#1b5aa6", location: "Charlotte, NC", logo: "assets/agency-logos/cats.png" },
    "Community Transit": { short: "CT", name: "Community Transit", color: "#007f3e", location: "Everett, WA", logo: "assets/agency-logos/community-transit.png" },
    "COTA": { short: "COTA", name: "Central Ohio Transit Authority", color: "#005eb8", location: "Columbus, OH", logo: "assets/agency-logos/cota.png" },
    "CTA": { short: "CTA", name: "Chicago Transit Authority", color: "#c62828", location: "Chicago, IL", logo: "assets/agency-logos/cta.png" },
    "CapMetro": { short: "CapMetro", name: "CapMetro", color: "#d71920", location: "Austin, TX", logo: "assets/agency-logos/capmetro.png" },
    "DART": { short: "DART", name: "Dallas Area Rapid Transit", color: "#f6c600", location: "Dallas, TX", logo: "assets/agency-logos/dart.png" },
    "DDOT": { short: "DDOT", name: "Detroit Department of Transportation", color: "#005baa", location: "Detroit, MI", logo: "assets/agency-logos/ddot.png" },
    "Everett Transit": { short: "ET", name: "Everett Transit", color: "#005eb8", location: "Everett, WA", logo: "assets/agency-logos/everett-transit.png" },
    "Foothill Transit": { short: "Foothill", name: "Foothill Transit", color: "#78be20", location: "West Covina, CA", logo: "assets/agency-logos/foothill-transit.png" },
    "GCRTA": { short: "RTA", name: "Greater Cleveland Regional Transit Authority", color: "#0067b1", location: "Cleveland, OH", logo: "assets/agency-logos/gcrta.png" },
    "GRTC": { short: "GRTC", name: "Greater Richmond Transit Company", color: "#005baa", location: "Richmond, VA", logo: "assets/agency-logos/grtc.png" },
    "Gold Coast Transit District": { short: "GCTD", name: "Gold Coast Transit District", color: "#005eb8", location: "Oxnard, CA" },
    "Golden Empire Transit District": { short: "GET", name: "Golden Empire Transit District", color: "#005eb8", location: "Bakersfield, CA" },
    "Golden Gate Transit": { short: "GGT", name: "Golden Gate Bridge, Highway and Transportation District", color: "#f6c600", location: "San Francisco, CA" },
    "HART": { short: "HART", name: "Hillsborough Transit Authority", color: "#005eb8", location: "Tampa, FL", logo: "assets/agency-logos/hart.png" },
    "Hampton Roads Transit": { short: "HRT", name: "Hampton Roads Transit", color: "#004c97", location: "Norfolk, VA", logo: "assets/agency-logos/hampton-roads-transit.png" },
    "Honolulu DTS": { short: "DTS", name: "Honolulu Department of Transportation Services", color: "#007a7a", location: "Honolulu, HI", logo: "assets/agency-logos/honolulu-dts.png" },
    "Houston METRO": { short: "METRO", name: "Metropolitan Transit Authority of Harris County", color: "#d71920", location: "Houston, TX", logo: "assets/agency-logos/houston-metro.png" },
    "IndyGo": { short: "IndyGo", name: "IndyGo", color: "#6f2c91", location: "Indianapolis, IN", logo: "assets/agency-logos/indygo.png" },
    "Intercity Transit": { short: "IT", name: "Intercity Transit", color: "#005eb8", location: "Olympia, WA", logo: "assets/agency-logos/intercity-transit.png" },
    "KCATA": { short: "RideKC", name: "Kansas City Area Transportation Authority", color: "#0072ce", location: "Kansas City, MO", logo: "assets/agency-logos/kcata.png" },
    "Kern Regional Transit": { short: "KRT", name: "Kern Regional Transit", color: "#005eb8", location: "Bakersfield, CA" },
    "King County Metro": { short: "KCM", name: "King County Metro", color: "#f0a202", location: "Seattle, WA", logo: "assets/agency-logos/king-county-metro.png" },
    "Kitsap Transit": { short: "KT", name: "Kitsap Transit", color: "#005eb8", location: "Bremerton, WA", logo: "assets/agency-logos/kitsap-transit.png" },
    "LA Metro": { short: "LA", name: "Los Angeles Metro", color: "#d11f3d", location: "Los Angeles, CA", logo: "assets/agency-logos/la-metro.png" },
    "LADOT": { short: "LADOT", name: "Los Angeles Department of Transportation", color: "#005eb8", location: "Los Angeles, CA" },
    "LYNX": { short: "LYNX", name: "LYNX", color: "#6f2c91", location: "Orlando, FL", logo: "assets/agency-logos/lynx.png" },
    "Long Beach Transit": { short: "LBT", name: "Long Beach Transit", color: "#005eb8", location: "Long Beach, CA" },
    "MARTA": { short: "MARTA", name: "Metropolitan Atlanta Rapid Transit Authority", color: "#1c4f9c", location: "Atlanta, GA", logo: "assets/agency-logos/marta.png" },
    "MBTA": { short: "T", name: "Massachusetts Bay Transportation Authority", color: "#111111", location: "Boston, MA", logo: "assets/agency-logos/mbta.png" },
    "MCTS": { short: "MCTS", name: "Milwaukee County Transit System", color: "#004b8d", location: "Milwaukee, WI", logo: "assets/agency-logos/mcts.png" },
    "Miami-Dade DTPW": { short: "DTPW", name: "Miami-Dade Department of Transportation and Public Works", color: "#f58220", location: "Miami, FL", logo: "assets/agency-logos/miami-dade-dtpw.png" },
    "Metro Transit MN": { short: "Metro", name: "Metro Transit", color: "#005eb8", location: "Minneapolis, MN", logo: "assets/agency-logos/metro-transit-mn.png" },
    "Metro Transit Madison": { short: "Metro", name: "Metro Transit Madison", color: "#0072bc", location: "Madison, WI", logo: "assets/agency-logos/metro-transit-madison.png" },
    "Metra": { short: "Metra", name: "Metra", color: "#005baa", location: "Chicago, IL", logo: "assets/agency-logos/metra.png" },
    "Metrolink": { short: "Metrolink", name: "Metrolink", color: "#005daa", location: "Los Angeles, CA", logo: "assets/agency-logos/metrolink.png" },
    "Montebello Bus Lines": { short: "MBL", name: "Montebello Bus Lines", color: "#005eb8", location: "Montebello, CA" },
    "Marin Transit": { short: "Marin", name: "Marin Transit", color: "#007a53", location: "San Rafael, CA" },
    "MTC": { short: "MTC", name: "Metropolitan Transportation Commission", color: "#005eb8", location: "San Francisco, CA" },
    "MTA": { short: "MTA", name: "Metropolitan Transportation Authority", color: "#0039a6", location: "New York, NY", logo: "assets/agency-logos/mta.svg" },
    "Napa Valley Transportation Authority": { short: "NVTA", name: "Napa Valley Transportation Authority", color: "#005eb8", location: "Napa, CA" },
    "NFTA": { short: "NFTA", name: "Niagara Frontier Transportation Authority", color: "#005eb8", location: "Buffalo, NY", logo: "assets/agency-logos/nfta.png" },
    "NICE Bus": { short: "NICE", name: "NICE Bus", color: "#f37021", location: "Mineola, NY", logo: "assets/agency-logos/nice-bus.png" },
    "NJ Transit": { short: "NJT", name: "NJ Transit", color: "#f37021", location: "Newark, NJ", logo: "assets/agency-logos/nj-transit.png" },
    "North County Transit District": { short: "NCTD", name: "North County Transit District", color: "#005eb8", location: "Oceanside, CA" },
    "Norwalk Transit": { short: "NTS", name: "Norwalk Transit", color: "#005eb8", location: "Norwalk, CA" },
    "OCTA": { short: "OCTA", name: "Orange County Transportation Authority", color: "#005eb8", location: "Orange, CA", logo: "assets/agency-logos/octa.png" },
    "Omnitrans": { short: "Omni", name: "Omnitrans", color: "#005eb8", location: "San Bernardino, CA", logo: "assets/agency-logos/omnitrans.png" },
    "PATH": { short: "PATH", name: "Port Authority Trans-Hudson", color: "#003e7e", location: "Jersey City, NJ", logo: "assets/agency-logos/path.svg" },
    "Pace": { short: "Pace", name: "Pace Suburban Bus", color: "#005eb8", location: "Arlington Heights, IL", logo: "assets/agency-logos/pace.png" },
    "Palm Tran": { short: "Palm", name: "Palm Tran", color: "#007a53", location: "West Palm Beach, FL", logo: "assets/agency-logos/palm-tran.png" },
    "Pittsburgh Regional Transit": { short: "PRT", name: "Pittsburgh Regional Transit", color: "#005eb8", location: "Pittsburgh, PA", logo: "assets/agency-logos/pittsburgh-regional-transit.svg" },
    "PSTA": { short: "PSTA", name: "Pinellas Suncoast Transit Authority", color: "#005eb8", location: "St. Petersburg, FL", logo: "assets/agency-logos/psta.png" },
    "RTA New Orleans": { short: "RTA", name: "New Orleans Regional Transit Authority", color: "#003da5", location: "New Orleans, LA", logo: "assets/agency-logos/rta-new-orleans.png" },
    "Riverside Transit Agency": { short: "RTA", name: "Riverside Transit Agency", color: "#005eb8", location: "Riverside, CA", logo: "assets/agency-logos/riverside-transit-agency.png" },
    "RTC Transit": { short: "RTC", name: "Regional Transportation Commission of Southern Nevada", color: "#6f2c91", location: "Las Vegas, NV", logo: "assets/agency-logos/rtc-transit.png" },
    "RTD Denver": { short: "RTD", name: "Regional Transportation District Denver", color: "#005daa", location: "Denver, CO", logo: "assets/agency-logos/rtd-denver.png" },
    "SMART": { short: "SMART", name: "Suburban Mobility Authority for Regional Transportation", color: "#005eb8", location: "Detroit, MI", logo: "assets/agency-logos/smart.png" },
    "SORTA Metro": { short: "Metro", name: "Southwest Ohio Regional Transit Authority", color: "#005eb8", location: "Cincinnati, OH", logo: "assets/agency-logos/sorta-metro.png" },
    "SEPTA": { short: "SEPTA", name: "Southeastern Pennsylvania Transportation Authority", color: "#1f4e79", location: "Philadelphia, PA", logo: "assets/agency-logos/septa.png" },
    "SFMTA": { short: "Muni", name: "San Francisco Municipal Transportation Agency", color: "#b71c1c", location: "San Francisco, CA", logo: "assets/agency-logos/sfmta.png" },
    "SacRT": { short: "SacRT", name: "Sacramento Regional Transit", color: "#0072bc", location: "Sacramento, CA", logo: "assets/agency-logos/sacrt.svg" },
    "SamTrans": { short: "SamTrans", name: "San Mateo County Transit District", color: "#005eb8", location: "San Carlos, CA" },
    "San Joaquin RTD": { short: "RTD", name: "San Joaquin Regional Transit District", color: "#005eb8", location: "Stockton, CA" },
    "Santa Barbara MTD": { short: "SBMTD", name: "Santa Barbara Metropolitan Transit District", color: "#005eb8", location: "Santa Barbara, CA" },
    "Santa Clarita Transit": { short: "SCT", name: "Santa Clarita Transit", color: "#005eb8", location: "Santa Clarita, CA" },
    "Santa Cruz METRO": { short: "METRO", name: "Santa Cruz METRO", color: "#005eb8", location: "Santa Cruz, CA" },
    "San Diego MTS": { short: "MTS", name: "San Diego Metropolitan Transit System", color: "#005eb8", location: "San Diego, CA", logo: "assets/agency-logos/san-diego-mts.png" },
    "SANDAG": { short: "SANDAG", name: "San Diego Association of Governments", color: "#005eb8", location: "San Diego, CA" },
    "Santa Maria Regional Transit": { short: "SMRT", name: "Santa Maria Regional Transit", color: "#005eb8", location: "Santa Maria, CA" },
    "Sonoma County Transit": { short: "SCT", name: "Sonoma County Transit", color: "#005eb8", location: "Santa Rosa, CA" },
    "Sound Transit": { short: "ST", name: "Sound Transit", color: "#00843d", location: "Seattle, WA", logo: "assets/agency-logos/sound-transit.svg" },
    "Spokane Transit Authority": { short: "STA", name: "Spokane Transit Authority", color: "#005eb8", location: "Spokane, WA", logo: "assets/agency-logos/spokane-transit-authority.png" },
    "Sun Tran": { short: "Sun Tran", name: "Sun Tran", color: "#f58220", location: "Tucson, AZ", logo: "assets/agency-logos/sun-tran.png" },
    "TriMet": { short: "TriMet", name: "TriMet", color: "#006b54", location: "Portland, OR", logo: "assets/agency-logos/trimet.png" },
    "Torrance Transit": { short: "TTS", name: "Torrance Transit", color: "#005eb8", location: "Torrance, CA" },
    "Tulare County Regional Transit Agency": { short: "TCRTA", name: "Tulare County Regional Transit Agency", color: "#005eb8", location: "Visalia, CA" },
    "Utah Transit Authority": { short: "UTA", name: "Utah Transit Authority", color: "#005eb8", location: "Salt Lake City, UT", logo: "assets/agency-logos/utah-transit-authority.svg" },
    "VIA Metropolitan Transit": { short: "VIA", name: "VIA Metropolitan Transit", color: "#005eb8", location: "San Antonio, TX", logo: "assets/agency-logos/via-metropolitan-transit.png" },
    "VCTC": { short: "VCTC", name: "Ventura County Transportation Commission", color: "#005eb8", location: "Camarillo, CA" },
    "VTA": { short: "VTA", name: "Santa Clara Valley Transportation Authority", color: "#005eb8", location: "San Jose, CA", logo: "assets/agency-logos/vta.png" },
    "Valley Metro": { short: "Valley", name: "Valley Metro", color: "#7a3e98", location: "Phoenix, AZ", logo: "assets/agency-logos/valley-metro.png" },
    "WestCAT": { short: "WestCAT", name: "Western Contra Costa Transit Authority", color: "#005eb8", location: "Pinole, CA" },
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
    "Albany, NY": { x: 83, y: 31 },
    "Alexandria, VA": { x: 79, y: 47 },
    "Atlanta, GA": { x: 69, y: 67 },
    "Bakersfield, CA": { x: 18, y: 58 },
    "Boston, MA": { x: 88, y: 28 },
    "Bremerton, WA": { x: 17, y: 22 },
    "Brooklyn, NY": { x: 84, y: 36 },
    "Buffalo, NY": { x: 72, y: 35 },
    "Camarillo, CA": { x: 17, y: 60 },
    "Charlotte, NC": { x: 75, y: 61 },
    "Chicago, IL": { x: 62, y: 38 },
    "Cincinnati, OH": { x: 69, y: 48 },
    "Cleveland, OH": { x: 70, y: 39 },
    "Columbus, OH": { x: 70, y: 45 },
    "Dallas, TX": { x: 54, y: 71 },
    "Denver, CO": { x: 44, y: 49 },
    "Detroit, MI": { x: 68, y: 36 },
    "El Monte, CA": { x: 18, y: 63 },
    "Everett, WA": { x: 17, y: 21 },
    "Fort Lauderdale, FL": { x: 78, y: 84 },
    "Indianapolis, IN": { x: 65, y: 47 },
    "Honolulu, HI": { x: 8, y: 84 },
    "Houston, TX": { x: 55, y: 78 },
    "Jamaica, NY": { x: 84, y: 36 },
    "Jersey City, NJ": { x: 84, y: 37 },
    "Kansas City, MO": { x: 56, y: 51 },
    "Lancaster, CA": { x: 19, y: 61 },
    "Las Vegas, NV": { x: 24, y: 58 },
    "Long Beach, CA": { x: 18, y: 63 },
    "Los Angeles, CA": { x: 18, y: 63 },
    "Madison, WI": { x: 61, y: 36 },
    "Miami, FL": { x: 78, y: 84 },
    "Milwaukee, WI": { x: 63, y: 35 },
    "Mineola, NY": { x: 85, y: 36 },
    "Minneapolis, MN": { x: 57, y: 31 },
    "New York, NY": { x: 84, y: 35 },
    "New Orleans, LA": { x: 62, y: 79 },
    "Newark, NJ": { x: 83, y: 38 },
    "Norfolk, VA": { x: 80, y: 56 },
    "Norwalk, CA": { x: 18, y: 63 },
    "Oakland, CA": { x: 14, y: 52 },
    "Oceanside, CA": { x: 19, y: 66 },
    "Orange, CA": { x: 18, y: 62 },
    "Olympia, WA": { x: 17, y: 22 },
    "Orlando, FL": { x: 76, y: 79 },
    "Philadelphia, PA": { x: 81, y: 41 },
    "Phoenix, AZ": { x: 30, y: 65 },
    "Pittsburgh, PA": { x: 75, y: 45 },
    "Pinole, CA": { x: 14, y: 52 },
    "Portland, OR": { x: 16, y: 27 },
    "Richmond, VA": { x: 79, y: 54 },
    "Richland, WA": { x: 21, y: 26 },
    "Riverside, CA": { x: 19, y: 63 },
    "Sacramento, CA": { x: 14, y: 49 },
    "Salt Lake City, UT": { x: 35, y: 45 },
    "San Antonio, TX": { x: 52, y: 79 },
    "San Rafael, CA": { x: 13, y: 52 },
    "San Bernardino, CA": { x: 19, y: 63 },
    "San Carlos, CA": { x: 14, y: 53 },
    "San Diego, CA": { x: 19, y: 67 },
    "San Jose, CA": { x: 14, y: 54 },
    "San Francisco, CA": { x: 13, y: 53 },
    "Santa Barbara, CA": { x: 17, y: 59 },
    "Santa Clarita, CA": { x: 18, y: 62 },
    "Santa Cruz, CA": { x: 14, y: 54 },
    "Santa Maria, CA": { x: 17, y: 58 },
    "Santa Monica, CA": { x: 18, y: 63 },
    "Santa Rosa, CA": { x: 13, y: 51 },
    "Seattle, WA": { x: 17, y: 21 },
    "Spokane, WA": { x: 22, y: 23 },
    "Stockton, CA": { x: 15, y: 50 },
    "St. Petersburg, FL": { x: 75, y: 82 },
    "Tampa, FL": { x: 75, y: 81 },
    "Tucson, AZ": { x: 31, y: 70 },
    "Torrance, CA": { x: 18, y: 63 },
    "Visalia, CA": { x: 18, y: 57 },
    "Washington, DC": { x: 79, y: 47 },
    "West Covina, CA": { x: 18, y: 63 },
    "West Palm Beach, FL": { x: 79, y: 83 },
  };

  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
  const stateNameToAbbr = {
    "CONNECTICUT": "CT",
    "DISTRICT OF COLUMBIA": "DC",
    "NEW JERSEY": "NJ",
    "NEW YORK": "NY",
  };

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

  function generatedAtValue() {
    const generated = new Date(payload.generated_at || "");
    return Number.isNaN(generated.getTime()) ? Date.now() : generated.getTime();
  }

  function relativePostedDateValue(value) {
    const text = String(value || "").trim().toLowerCase();
    if (!text) return 0;

    const base = generatedAtValue();
    const dayMs = 24 * 60 * 60 * 1000;

    if (/\btoday\b/.test(text)) return base;
    if (/\byesterday\b/.test(text)) return base - dayMs;

    const relative = text.match(/(?:posted\s+)?(?:(more than|over)\s+)?(\d+|30\+)\s+(day|week|month|year)s?\s+ago/);
    if (!relative) return 0;

    const amount = relative[2] === "30+" ? 30 : Number(relative[2]);
    if (!Number.isFinite(amount)) return 0;

    const multipliers = {
      day: 1,
      week: 7,
      month: 30,
      year: 365,
    };
    const extraDay = relative[1] ? 1 : 0;
    return base - ((amount * multipliers[relative[3]]) + extraDay) * dayMs;
  }

  function postedDateValue(job) {
    return dateValue(job.posted_date_iso) || dateValue(job.posted_date) || relativePostedDateValue(job.posted_date);
  }

  function stateCode(value, job = {}) {
    if (job.agency === "MTA") return "NY";

    const text = String(value || "").trim().toUpperCase().replace(/\s+/g, " ");
    if (!text) return "";

    if (stateNameToAbbr[text]) return stateNameToAbbr[text];

    const stateNameZip = text.match(/^(NEW YORK|NEW JERSEY|CONNECTICUT|DISTRICT OF COLUMBIA)(?:\s+\d{5}(?:-\d{4})?)?$/);
    if (stateNameZip) return stateNameToAbbr[stateNameZip[1]];

    const stateZip = text.match(/^([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?$/);
    if (stateZip) return stateZip[1];

    const embeddedState = text.match(/\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b/);
    if (embeddedState) return embeddedState[1];

    const cityState = text.match(/^.+?\s+([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?$/);
    if (cityState) return cityState[1];

    return text;
  }

  function replaceOptions(select, values, allLabel, counts = new Map()) {
    const previousValue = select.value;
    select.replaceChildren();

    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = allLabel;
    select.appendChild(allOption);

    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      const count = counts.get(value);
      option.textContent = Number.isFinite(count) ? `${value} (${count.toLocaleString()})` : value;
      select.appendChild(option);
    });

    select.value = values.includes(previousValue) ? previousValue : "";
    return previousValue !== select.value;
  }

  function formatDate(value) {
    if (!value) return "";
    const concise = conciseDate(value);
    const date = new Date(concise);
    if (Number.isNaN(date.getTime())) return concise;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function formatDateTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return formatDate(value);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZoneName: "short",
    });
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
    els.generatedAt.textContent = payload.generated_at ? `Updated ${formatDateTime(payload.generated_at)}` : "Updated locally";
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

  function employmentTypeText(job) {
    return [
      job.employment_type,
      job.title,
    ]
      .join(" ")
      .toLowerCase();
  }

  function employmentTypeBucket(job) {
    const text = employmentTypeText(job);
    const type = String(job.employment_type || "").toLowerCase();

    if (/\b(part[-\s]?time|pt)\b/i.test(text)) return "part_time";
    if (/\b(full[-\s]?time|ft)\b/i.test(text)) return "full_time";
    if (/\b(regular|permanent|career service|provisional|term[-\s]?ltd|term limited|at will)\b/i.test(type)) return "full_time";
    return "";
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

  function selectedFilters() {
    const query = els.searchInput.value.trim().toLowerCase();
    return {
      query,
      agency: els.agencyFilter.value,
      state: els.stateFilter.value,
      category: els.categoryFilter.value,
      seniority: els.seniorityFilter.value,
      employmentType: els.employmentTypeFilter.value,
      minSalary: Number(els.salaryRange.value),
      includeUnknown: els.includeUnknownSalary.checked,
    };
  }

  function matchesFilters(job, filters, excluded = new Set()) {
    return (
      (excluded.has("query") || !filters.query || matchesSearch(job, filters.query)) &&
      (excluded.has("agency") || !filters.agency || job.agency === filters.agency) &&
      (excluded.has("state") || !filters.state || stateCode(job.state, job) === filters.state) &&
      (excluded.has("category") || !filters.category || job.category === filters.category) &&
      (excluded.has("seniority") || !filters.seniority || job.ai_sort_seniority === filters.seniority) &&
      (excluded.has("employmentType") || !filters.employmentType || employmentTypeBucket(job) === filters.employmentType) &&
      (excluded.has("salary") || passesSalary(job, filters.minSalary, filters.includeUnknown))
    );
  }

  function filterJobs() {
    const filters = selectedFilters();
    return jobs.filter((job) => matchesFilters(job, filters));
  }

  function optionValuesFor(key, valueForJob) {
    const filters = selectedFilters();
    const excluded = new Set([key, "query", "salary"]);
    const counts = new Map();

    jobs.forEach((job) => {
      if (!matchesFilters(job, filters, excluded)) return;
      const value = valueForJob(job);
      if (!value) return;
      counts.set(value, (counts.get(value) || 0) + 1);
    });

    const values = [...counts.keys()].sort((a, b) => a.localeCompare(b));
    return { values, counts };
  }

  function refreshFilterOptions() {
    let changed = false;

    const agencyOptions = optionValuesFor("agency", (job) => job.agency);
    changed = replaceOptions(els.agencyFilter, agencyOptions.values, "All agencies", agencyOptions.counts) || changed;

    const stateOptions = optionValuesFor("state", (job) => stateCode(job.state, job));
    changed = replaceOptions(els.stateFilter, stateOptions.values, "All states", stateOptions.counts) || changed;

    const categoryOptions = optionValuesFor("category", (job) => job.category);
    changed = replaceOptions(els.categoryFilter, categoryOptions.values, "All categories", categoryOptions.counts) || changed;

    const seniorityOptions = optionValuesFor("seniority", (job) => job.ai_sort_seniority);
    changed = replaceOptions(els.seniorityFilter, seniorityOptions.values, "All levels", seniorityOptions.counts) || changed;

    return changed;
  }

  function resetFilters() {
    els.searchInput.value = "";
    els.agencyFilter.value = "";
    els.stateFilter.value = "";
    els.categoryFilter.value = "";
    els.seniorityFilter.value = "";
    els.employmentTypeFilter.value = "";
    els.sortSelect.value = DEFAULT_SORT;
    els.salaryRange.value = "0";
    els.includeUnknownSalary.checked = true;
    updateSalaryOutput();
    refreshFilterOptions();
  }

  function sortJobs(items) {
    const sort = els.sortSelect.value || DEFAULT_SORT;
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
        const diff = postedDateValue(b) - postedDateValue(a);
        if (diff) return diff;
      }

      return textCompare(a, b, "agency") || textCompare(a, b, "title");
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

  function updateSalaryOutput() {
    els.salaryOutput.textContent = Number(els.salaryRange.value) ? money.format(Number(els.salaryRange.value)) : "Any";
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

  function renderJob(job) {
    const location = agencyLocation(job.agency) || [job.city, job.state].filter(Boolean).join(", ");
    const sourceUrl = safeExternalUrl(job.source_url);
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
            <a href="${escapeAttribute(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(job.title)}</a>
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
        els.sortSelect.value = DEFAULT_SORT;
        currentView = "list";
        resetPage();
        refreshFilterOptions();
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
          ${group.examples.map((job) => `<a href="${escapeAttribute(safeExternalUrl(job.source_url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(job.title)}</a>`).join("")}
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
    const isMonthly = job.salary_unit === "monthly";
    const min = numeric(isHourly || isMonthly ? job.salary_min : job.salary_annual_min_est);
    const max = numeric(isHourly || isMonthly ? job.salary_max : job.salary_annual_max_est);
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
    if (unit === "monthly") return `${money.format(value)}/mo`;
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

  function safeExternalUrl(value) {
    try {
      const url = new URL(String(value || ""), window.location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function bind() {
    const filterInputs = [
      els.searchInput,
      els.stateFilter,
      els.categoryFilter,
      els.seniorityFilter,
      els.employmentTypeFilter,
      els.salaryRange,
      els.includeUnknownSalary,
    ];

    filterInputs.forEach((input) => input.addEventListener("input", () => {
      els.sortSelect.value = DEFAULT_SORT;
      updateSalaryOutput();
      refreshFilterOptions();
      resetPage();
      renderJobs();
    }));

    els.agencyFilter.addEventListener("input", () => {
      els.sortSelect.value = DEFAULT_SORT;
      refreshFilterOptions();
      resetPage();
      renderJobs();
    });

    els.sortSelect.addEventListener("input", () => {
      resetPage();
      renderJobs();
    });

    els.pageSizeSelect.addEventListener("input", () => {
      resetPage();
      renderJobs();
    });

    els.clearFiltersButton.addEventListener("click", () => {
      resetFilters();
      resetPage();
      renderJobs();
    });

    els.listViewButton.addEventListener("click", () => {
      currentView = "list";
      renderJobs();
    });

    els.mapViewButton.addEventListener("click", () => {
      currentView = "map";
      renderJobs();
    });
  }

  refreshFilterOptions();
  setHeader();
  renderJobs();
  bind();
})();
