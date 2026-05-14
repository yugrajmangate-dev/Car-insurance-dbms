(function () {
  const vehicleValueEl = document.getElementById("vehicleValue");
  const coverageTypeEl = document.getElementById("coverageType");
  const usageTypeEl = document.getElementById("usageType");
  const priorClaimsEl = document.getElementById("priorClaims");
  const accidentsEl = document.getElementById("accidents");
  const deductibleEl = document.getElementById("deductibleAmount");
  const addOnEls = Array.from(document.querySelectorAll('input[name="add_ons"]'));
  const previewEl = document.getElementById("premiumPreview");

  if (!previewEl) {
    return;
  }

  function toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function formatInr(value) {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(value);
  }

  function estimatePremium() {
    const vehicleValue = toNumber(vehicleValueEl ? vehicleValueEl.value : 0);
    const coverageType = coverageTypeEl ? coverageTypeEl.value : "";
    const usageType = usageTypeEl ? usageTypeEl.value : "";
    const priorClaims = toNumber(priorClaimsEl ? priorClaimsEl.value : 0);
    const accidents = toNumber(accidentsEl ? accidentsEl.value : 0);
    const deductible = toNumber(deductibleEl ? deductibleEl.value : 0);

    const baseRateMap = {
      "Third Party": 0.018,
      Comprehensive: 0.045,
      "Zero Depreciation": 0.06,
    };

    let premium = vehicleValue * (baseRateMap[coverageType] || 0.045);

    if (usageType === "Commercial") {
      premium *= 1.22;
    }

    premium *= 1 + Math.min(priorClaims * 0.07, 0.35);
    premium *= 1 + Math.min(accidents * 0.05, 0.25);

    addOnEls.forEach((el) => {
      if (!el.checked) {
        return;
      }
      if (el.value === "Roadside Assistance") {
        premium += 900;
      }
      if (el.value === "Engine Protect") {
        premium += 1800;
      }
      if (el.value === "Return To Invoice") {
        premium += 2500;
      }
      if (el.value === "Consumables Cover") {
        premium += 1200;
      }
    });

    const deductibleDiscount = Math.min(deductible * 0.08, premium * 0.2);
    premium = Math.max(2500, premium - deductibleDiscount);

    previewEl.textContent = formatInr(premium);
  }

  [
    vehicleValueEl,
    coverageTypeEl,
    usageTypeEl,
    priorClaimsEl,
    accidentsEl,
    deductibleEl,
    ...addOnEls,
  ]
    .filter(Boolean)
    .forEach((el) => {
      el.addEventListener("input", estimatePremium);
      el.addEventListener("change", estimatePremium);
    });

  estimatePremium();
})();
