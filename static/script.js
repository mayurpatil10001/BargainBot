/**
 * BargainBot — script.js
 * Handles search, chart rendering, and alert form.
 */

"use strict";

// ============================================================
// State
// ============================================================
let currentProduct = "";
let priceChart     = null;  // Chart.js instance (main trend)
let seasonalChart  = null;  // Chart.js instance (monthly bar)

// ============================================================
// Utility: format Indian Rupee
// ============================================================
function formatINR(value) {
  if (value == null || isNaN(value)) return "N/A";
  return "₹" + Number(value).toLocaleString("en-IN");
}

// ============================================================
// Utility: show / hide elements
// ============================================================
function show(el) {
  if (el) el.classList.add("visible");
}

function hide(el) {
  if (el) el.classList.remove("visible");
}

// ============================================================
// Fetch model stats on page load
// ============================================================
async function loadModelStats() {
  try {
    const res  = await fetch("/model-stats");
    const data = await res.json();

    const linMAE  = data.linear_mae  != null ? "₹" + Number(data.linear_mae).toLocaleString("en-IN") : "N/A";
    const propMAE = data.prophet_mae != null ? "₹" + Number(data.prophet_mae).toLocaleString("en-IN") : "N/A";
    const winner  = data.winner || "—";

    document.getElementById("val-linear").textContent  = linMAE;
    document.getElementById("val-prophet").textContent = propMAE;
    document.getElementById("val-winner").textContent  = winner;

  } catch (err) {
    console.warn("[BargainBot] Could not load model stats:", err);
  }
}

// ============================================================
// SEARCH
// ============================================================
async function searchProduct() {
  const input = document.getElementById("search-input");
  const query = (input ? input.value : "").trim();

  if (!query) {
    input && input.focus();
    return;
  }

  currentProduct = query;

  // UI: loading state
  const btn = document.getElementById("search-btn");
  if (btn) {
    btn.textContent = "Searching…";
    btn.disabled    = true;
  }

  const loadingSection    = document.getElementById("loading-section");
  const resultsSection    = document.getElementById("results-section");
  const analyticsSection  = document.getElementById("analytics-section");
  const priceAlertSection = document.getElementById("price-alert-section");
  const alertSuccess      = document.getElementById("alert-success");

  hide(resultsSection);
  hide(analyticsSection);
  hide(priceAlertSection);
  hide(alertSuccess);
  show(loadingSection);

  // ---- Groq loading status cycling text ----
  const groqMessages = [
    "Fetching live prices...",
    "Running ML price prediction...",
    "Analyzing festival calendar...",
    "Consulting AI advisor...",
    "Building your recommendation...",
  ];
  let groqMsgIndex = 0;
  // Inject status element below skeleton
  const oldStatus = document.getElementById("groq-loading-status");
  if (oldStatus) oldStatus.remove();
  const groqStatus = document.createElement("div");
  groqStatus.id = "groq-loading-status";
  groqStatus.className = "groq-loading-status";
  groqStatus.textContent = groqMessages[0];
  if (loadingSection) loadingSection.appendChild(groqStatus);

  const groqInterval = setInterval(() => {
    groqMsgIndex = (groqMsgIndex + 1) % groqMessages.length;
    groqStatus.textContent = groqMessages[groqMsgIndex];
  }, 1500);

  try {
    const response = await fetch("/search", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ product: query }),
    });

    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    // ---- Populate Card 1: Live Prices ----
    populateLivePrices(data.product, data.prices);

    // ---- Populate Card 2: Prediction ----
    populatePrediction(data.prediction);

    // ---- Groq Analysis Card (between Card 2 and events strip) ----
    renderGroqAnalysisCard(data.prediction);

    // ---- Draw Chart (Card 3) ----
    drawChart(
      data.history,
      data.prediction ? data.prediction.forecast         : [],
      data.prediction ? data.prediction.historical_prices : []
    );

    // ---- Upcoming Events Strip (between Card 2 and Card 3) ----
    renderUpcomingEvents(data.prediction ? data.prediction.upcoming_events : []);

    // ---- Populate Analytics Section ----
    if (data.prediction && data.prediction.analytics) {
      populateAnalytics(data.product, data.prediction.analytics);
      drawSeasonalChart(data.prediction.analytics.monthly_data || []);
    }

    // ---- Pre-fill alert product ----
    const alertProduct = document.getElementById("alert-product");
    if (alertProduct) alertProduct.value = data.product;

    // Reset alert form
    const alertBtn = document.getElementById("alert-btn");
    if (alertBtn) {
      alertBtn.textContent = "Notify Me";
      alertBtn.disabled    = false;
    }
    const alertEmail = document.getElementById("alert-email");
    const alertPrice2 = document.getElementById("alert-price");
    if (alertEmail) alertEmail.value = "";
    if (alertPrice2) alertPrice2.value = "";

    // Show results + analytics + alert
    hide(loadingSection);
    show(resultsSection);
    show(analyticsSection);
    show(priceAlertSection);

    // Refresh model stats
    loadModelStats();

  } catch (err) {
    console.error("[BargainBot] Search failed:", err);
    hide(loadingSection);
    alert("Search failed: " + (err.message || "Unknown error. Please try again."));
  } finally {
    clearInterval(groqInterval);
    const s = document.getElementById("groq-loading-status");
    if (s) s.remove();
    if (btn) {
      btn.textContent = "Search";
      btn.disabled    = false;
    }
  }
}

// ============================================================
// CARD 1: Live Prices
// ============================================================
function populateLivePrices(productName, prices) {
  // Product name
  const nameEl = document.getElementById("result-product-name");
  if (nameEl) nameEl.textContent = productName;

  // Amazon
  const amazonEl = document.getElementById("price-amazon");
  if (amazonEl) {
    if (prices.amazon != null) {
      amazonEl.textContent = formatINR(prices.amazon);
      amazonEl.className   = "platform-price";
    } else {
      amazonEl.textContent = "Unavailable";
      amazonEl.className   = "platform-price unavailable";
    }
  }

  // Flipkart
  const flipEl = document.getElementById("price-flipkart");
  if (flipEl) {
    if (prices.flipkart != null) {
      flipEl.textContent = formatINR(prices.flipkart);
      flipEl.className   = "platform-price";
    } else {
      flipEl.textContent = "Unavailable";
      flipEl.className   = "platform-price unavailable";
    }
  }

  // Best deal
  const bestDealText = document.getElementById("best-deal-text");
  if (bestDealText) {
    const validPrices = Object.entries(prices).filter(([, v]) => v != null);
    if (validPrices.length > 0) {
      const best = validPrices.reduce((a, b) => (a[1] < b[1] ? a : b));
      const platformLabel = best[0] === "amazon" ? "Amazon India" : "Flipkart";
      bestDealText.textContent = `✓ Best deal on ${platformLabel} at ${formatINR(best[1])}`;
    } else {
      bestDealText.textContent = "No live prices available right now.";
    }
  }
}

// ============================================================
// CARD 2: Prediction
// ============================================================
function populatePrediction(pred) {
  if (!pred) return;

  const groq = pred.groq_analysis || null;

  // ---- [v7] Smart Summary Banner (very top of card, before banner/badge) ----
  const predCard = document.getElementById("card-prediction");
  const oldSummary = document.getElementById("groq-smart-summary");
  if (oldSummary) oldSummary.remove();

  if (groq && groq.smart_summary && predCard) {
    const summaryDiv = document.createElement("div");
    summaryDiv.id = "groq-smart-summary";
    summaryDiv.className = "groq-smart-summary";
    summaryDiv.innerHTML =
      `<div style="font-size:16px;color:#7C3AED;flex-shrink:0;margin-top:1px">✶</div>
       <div>
         <div style="font-size:10px;font-weight:700;color:#7C3AED;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px">AI Analysis</div>
         <div style="font-size:14px;font-weight:600;color:#0F172A;line-height:1.5">${groq.smart_summary}</div>
       </div>`;
    const cardLabel = predCard.querySelector(".card-label");
    cardLabel ? predCard.insertBefore(summaryDiv, cardLabel) : predCard.prepend(summaryDiv);
  }

  // ---- Active Event Banner (v6) ----
  const oldBanner = document.getElementById("event-live-banner");
  if (oldBanner) oldBanner.remove();

  if (pred.active_event && predCard) {
    const ae = pred.active_event;
    const banner = document.createElement("div");
    banner.id = "event-live-banner";
    banner.className = "event-banner";
    banner.innerHTML =
      `<div style="flex:1">
         <div style="font-size:14px;font-weight:700;color:#fff">🎉 ${ae.name} is LIVE!</div>
         <div style="font-size:12px;color:rgba(255,255,255,0.75);margin-top:3px">Sale ends ${ae.sale_ends}</div>
       </div>
       <div style="font-size:18px;font-weight:800;color:#fff;white-space:nowrap">${ae.discount_pct}% OFF</div>`;
    const cardLabel = predCard.querySelector(".card-label");
    cardLabel ? predCard.insertBefore(banner, cardLabel) : predCard.prepend(banner);
  }

  // Verdict badge
  const badge = document.getElementById("verdict-badge");
  if (badge) {
    const verdictMap = {
      WAIT:      { label: "⏳ Wait for a Better Deal", cls: "wait"    },
      BUY_NOW:   { label: "✅ Buy Now",                cls: "buy-now" },
      CONSIDER:  { label: "🤔 Consider Buying",       cls: "consider" },
    };
    const config = verdictMap[pred.verdict] || verdictMap["CONSIDER"];
    badge.textContent = config.label;
    badge.className   = config.cls;
  }

  // Price drop line
  const dropLine = document.getElementById("price-drop-line");
  if (dropLine) {
    if (pred.current_price && pred.predicted_price) {
      dropLine.textContent =
        `Price likely to drop from ${formatINR(pred.current_price)} → ${formatINR(pred.predicted_price)}`;
    } else {
      dropLine.textContent = "";
    }
  }

  // Savings line
  const savingsLine = document.getElementById("savings-line");
  if (savingsLine) {
    if (pred.savings > 0) {
      savingsLine.textContent = `You save ${formatINR(pred.savings)}`;
    } else {
      savingsLine.textContent = "Price is already near its predicted low.";
    }
  }

  // ---- [v7] Confidence Meter (after savings, before why row) ----
  const oldMeter = document.getElementById("groq-confidence-meter");
  if (oldMeter) oldMeter.remove();

  const savingsEl = document.getElementById("savings-line");
  if (groq && groq.confidence !== undefined && savingsEl) {
    const conf = groq.confidence;
    const confColor = conf >= 75 ? "#16A34A" : conf >= 50 ? "#2563EB" : conf >= 25 ? "#F59E0B" : "#DC2626";

    const meter = document.createElement("div");
    meter.id = "groq-confidence-meter";
    meter.className = "confidence-meter";
    meter.innerHTML =
      `<div style="display:flex;justify-content:space-between;align-items:center">
         <span style="font-size:12px;font-weight:600;color:#64748B;text-transform:uppercase;letter-spacing:0.06em">AI Confidence</span>
         <span style="font-size:14px;font-weight:700;color:${confColor}">${conf}%</span>
       </div>
       <div style="height:6px;background:#F1F5F9;border-radius:3px;margin-top:6px;overflow:hidden">
         <div id="groq-conf-bar" style="height:100%;border-radius:3px;width:0%;transition:width 0.8s ease;background:${confColor}"></div>
       </div>
       <div style="font-size:12px;color:#94A3B8;margin-top:6px">${groq.confidence_reason || ""}</div>`;

    savingsEl.insertAdjacentElement("afterend", meter);
    // Trigger CSS transition after 100ms
    setTimeout(() => {
      const bar = document.getElementById("groq-conf-bar");
      if (bar) bar.style.width = conf + "%";
    }, 100);
  }

  // Why — use Groq text when available, else ML text
  const whyEl = document.getElementById("why-text");
  if (whyEl) {
    whyEl.textContent = (groq && groq.groq_verdict_text) ? groq.groq_verdict_text : (pred.why || "—");
  }

  // Trust
  const trustEl = document.getElementById("trust-text");
  if (trustEl) {
    const trustLabels = {
      stable:     "Price has been stable — reliable prediction.",
      flash_sale: "Flash sale detected — act quickly, price may rise soon.",
      uncertain:  "Price is fluctuating — prediction is approximate.",
    };
    trustEl.textContent = trustLabels[pred.trust] || pred.trust || "—";
  }

  // Message
  const msgEl = document.getElementById("message-text");
  if (msgEl) msgEl.textContent = pred.message || "";

  // ---- Date Advice Box (v6) ----
  const oldAdvice = document.getElementById("date-advice-box");
  if (oldAdvice) oldAdvice.remove();

  const msgRow = document.getElementById("message-row");
  if (msgRow && pred.date_advice && pred.date_advice.action) {
    const da = pred.date_advice;
    const box = document.createElement("div");
    box.id = "date-advice-box";
    box.className = "date-advice-box";

    let boxHtml = "";
    if (da.action === "BUY_NOW") {
      boxHtml = `<div class="advice-inner advice-buy">
        <div class="advice-row1">✅ Buy before ${da.buy_before || "soon"}</div>
        <div class="advice-row2">${da.reason}</div>
        ${da.urgency === "HIGH" && da.days_left != null
          ? `<div class="advice-urgent"><span class="advice-pulse-dot"></span>Only ${da.days_left} day${da.days_left !== 1 ? "s" : ""} left at sale price!</div>`
          : ""}
      </div>`;
    } else if (da.action === "WAIT_FOR_EVENT") {
      boxHtml = `<div class="advice-inner advice-wait-event">
        <div class="advice-row1">⏳ Wait until ${da.buy_after}</div>
        ${da.buy_before ? `<div class="advice-row2b">Buy before ${da.buy_before}</div>` : ""}
        <div class="advice-row2">${da.reason}</div>
        ${da.projected_price != null
          ? `<div class="advice-projected">Expected sale price: ₹${Number(da.projected_price).toLocaleString("en-IN")}</div>`
          : ""}
        ${da.extra_saving != null
          ? `<div class="advice-saving">Extra saving vs now: ₹${Number(da.extra_saving).toLocaleString("en-IN")}</div>`
          : ""}
      </div>`;
    } else if (da.action === "WAIT_FOR_DIP") {
      boxHtml = `<div class="advice-inner advice-wait-dip">
        <div class="advice-row1">📉 Best time to buy: ${da.buy_after}</div>
        <div class="advice-row2">${da.reason}</div>
        ${da.predicted_low != null
          ? `<div class="advice-projected">Predicted price: ₹${Number(da.predicted_low).toLocaleString("en-IN")}</div>`
          : ""}
      </div>`;
    } else {
      boxHtml = `<div class="advice-inner advice-consider">
        <div class="advice-row1">🤔 Set an alert for your target price</div>
        <div class="advice-row2">${da.reason}</div>
      </div>`;
    }

    box.innerHTML = boxHtml;
    msgRow.insertAdjacentElement("afterend", box);
  }
}
// ============================================================
// GROQ ANALYSIS CARD (between Card 2 and Upcoming Events)
// ============================================================
function renderGroqAnalysisCard(pred) {
  // Remove any old card first (handles repeat searches)
  const old = document.querySelector(".groq-analysis-card");
  if (old) old.remove();

  const groq = (pred && pred.groq_analysis) ? pred.groq_analysis : null;
  if (!groq) return; // Graceful degradation — skip entirely if no analysis

  // Category → emoji mapping
  const catEmoji = {
    Smartphone: "📱", Laptop: "💻", Tablet: "📲", TV: "📺",
    Audio: "🎧", Appliance: "🏠", Camera: "📷", Wearable: "⌚",
    Gaming: "🎮", Fashion: "👗", Grocery: "🛒", Other: "📦",
  };
  const emoji    = catEmoji[groq.category] || "📦";
  const category = groq.category || "Other";

  // Build card HTML
  const card = document.createElement("div");
  card.className = "groq-analysis-card";
  card.innerHTML = `
    <div class="groq-card-header">
      <span class="card-label">AI PRICE ANALYSIS</span>
      <span class="groq-powered-pill">Powered by Groq + Llama 3.3</span>
    </div>

    <div class="groq-row1">
      <div class="groq-category-badge">
        <span class="groq-cat-emoji">${emoji}</span>
        <span class="groq-cat-name">${category.toUpperCase()}</span>
      </div>
      <div class="groq-category-advice">
        <div class="groq-section-label">Category Insight</div>
        <div class="groq-section-text">${groq.category_advice || ""}</div>
      </div>
    </div>

    <div class="groq-row2">
      <div class="groq-section-label">Price Analysis</div>
      <div class="groq-section-text" style="line-height:1.7">${groq.analysis_paragraph || ""}</div>
    </div>

    <div class="groq-row3">
      <div class="groq-best-time">
        <div class="groq-box-label">⏰ Best Time to Buy</div>
        <div class="groq-best-time-text">${groq.best_time_to_buy || ""}</div>
      </div>
      <div class="groq-risk-note">
        <div class="groq-box-label">⚠️ Risk to Consider</div>
        <div class="groq-risk-text">${groq.risk_note || ""}</div>
      </div>
    </div>`;

  // Insert after card-prediction and before groq-analysis-card / upcoming-events-strip
  const card2 = document.getElementById("card-prediction");
  if (card2 && card2.parentNode) {
    card2.insertAdjacentElement("afterend", card);
  }
}

// ============================================================
// CARD 3: Price Trend Chart
// ============================================================
function drawChart(dbHistory, forecast, historicalPrices) {
  const canvas = document.getElementById("price-chart");
  if (!canvas) return;

  // Destroy previous chart instance
  if (priceChart) {
    priceChart.destroy();
    priceChart = null;
  }

  // ---- Build the historical line ----
  // Prefer the generated 24-month history; overlay real DB records on recent dates.
  const histMap = {};

  // 1. Seed from generated monthly history (24 months back → today)
  if (historicalPrices && historicalPrices.length > 0) {
    historicalPrices.forEach((row) => {
      if (row.date && row.price != null) {
        histMap[row.date] = row.price;
      }
    });
  }

  // 2. Overwrite recent dates with actual DB records (more accurate for last N days)
  if (dbHistory && dbHistory.length > 0) {
    dbHistory.forEach((row) => {
      const dateStr = row.timestamp ? row.timestamp.split(" ")[0] : row.date;
      if (dateStr && row.price != null) {
        histMap[dateStr] = row.price;
      }
    });
  }

  const histDates  = Object.keys(histMap).sort();
  const histPrices = histDates.map((d) => histMap[d]);

  // ---- Build the forecast line ----
  const fcDates  = [];
  const fcPrices = [];
  if (forecast && forecast.length > 0) {
    forecast.forEach((f) => {
      fcDates.push(f.date);
      fcPrices.push(f.price);
    });
  }

  // ---- No data at all — show placeholder ----
  if (histDates.length === 0 && fcDates.length === 0) {
    const wrapper = document.getElementById("chart-wrapper");
    if (wrapper) {
      wrapper.innerHTML =
        '<p style="text-align:center;color:#94A3B8;padding:60px 0;font-size:14px;">' +
        "Price history will appear here after a few searches." +
        "</p>";
    }
    return;
  }

  // ---- Merge all labels for x-axis ----
  // Historical line gets null for forecast-only dates, and vice versa.
  // The two lines SHARE today's date (last hist point = first fc point) so they connect.
  const todayStr      = histDates.length > 0 ? histDates[histDates.length - 1] : (fcDates[0] || "");
  const todayPrice    = histDates.length > 0 ? histPrices[histPrices.length - 1] : null;

  const allLabelSet   = new Set([...histDates, ...fcDates]);
  const allLabels     = Array.from(allLabelSet).sort();

  // Map values; the historical dataset also gets the today price at today's index
  // so it visually meets the forecast line.
  const histDataset = allLabels.map((l) => {
    if (histDates.includes(l)) return histPrices[histDates.indexOf(l)];
    // Extend one step into forecast so lines connect
    if (l === fcDates[0] && todayPrice != null) return todayPrice;
    return null;
  });

  const fcDataset = allLabels.map((l) => {
    if (fcDates.includes(l)) return fcPrices[fcDates.indexOf(l)];
    // Start forecast one step before its first date (= today) so lines connect
    if (l === todayStr && todayPrice != null && fcDates.length > 0) return todayPrice;
    return null;
  });

  // ---- Chart.js gradient fill helper ----
  function makeGradient(ctx, chartArea) {
    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    gradient.addColorStop(0, "rgba(37, 99, 235, 0.18)");
    gradient.addColorStop(0.6, "rgba(37, 99, 235, 0.06)");
    gradient.addColorStop(1, "rgba(37, 99, 235, 0.00)");
    return gradient;
  }

  // Point radii: larger at today's junction so the join is obvious
  const histPointRadii = allLabels.map((l) => (l === todayStr ? 5 : (histDates.includes(l) ? 2 : 0)));
  const fcPointRadii   = allLabels.map((l) => (l === todayStr ? 5 : (fcDates.includes(l)   ? 3 : 0)));

  priceChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: allLabels,
      datasets: [
        {
          label:           "Price History",
          data:            histDataset,
          borderColor:     "#2563EB",
          borderWidth:     2.5,
          backgroundColor: (context) => {
            const chart = context.chart;
            const { ctx, chartArea } = chart;
            if (!chartArea) return "transparent";
            return makeGradient(ctx, chartArea);
          },
          fill:               true,
          tension:            0.35,
          pointRadius:        histPointRadii,
          pointBackgroundColor: "#2563EB",
          pointBorderColor:   "#fff",
          pointBorderWidth:   1.5,
          spanGaps:           false,
        },
        {
          label:           "AI Forecast",
          data:            fcDataset,
          borderColor:     "#F97316",
          borderWidth:     2.5,
          backgroundColor: "transparent",
          borderDash:      [7, 4],
          fill:            false,
          tension:         0.35,
          pointRadius:     fcPointRadii,
          pointBackgroundColor: allLabels.map((l) => {
            const idx = fcDates.indexOf(l);
            if (idx === -1) return "#F97316";
            return (forecast[idx] && forecast[idx].is_sale_day) ? "#7C3AED" : "#F97316";
          }),
          pointStyle: allLabels.map((l) => {
            const idx = fcDates.indexOf(l);
            if (idx === -1) return "circle";
            return (forecast[idx] && forecast[idx].is_sale_day) ? "star" : "circle";
          }),
          pointRadius: allLabels.map((l) => {
            if (l === todayStr) return 5;
            const idx = fcDates.indexOf(l);
            if (idx === -1) return 0;
            return (forecast[idx] && forecast[idx].is_sale_day) ? 7 : 3;
          }),
          pointBorderColor:  "#fff",
          pointBorderWidth:  1.5,
          spanGaps:          false,
        },
      ],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction: {
        mode:        "index",
        intersect:   false,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            font:      { family: "Inter", size: 12, weight: "500" },
            color:     "#334155",
            usePointStyle: true,
            pointStyleWidth: 10,
          },
        },
        tooltip: {
          backgroundColor: "#0F172A",
          titleColor:      "#94A3B8",
          bodyColor:       "#F8FAFC",
          borderColor:     "#1E293B",
          borderWidth:     1,
          padding:         12,
          callbacks: {
            label: (ctx) => {
              const val = ctx.parsed.y;
              if (val == null) return null;
              // Show event name on sale-day forecast points
              if (ctx.datasetIndex === 1) {
                const idx = fcDates.indexOf(ctx.label);
                if (idx !== -1 && forecast[idx] && forecast[idx].is_sale_day && forecast[idx].event_name) {
                  return [`  🎉 ${forecast[idx].event_name}`, `  ₹${Number(val).toLocaleString("en-IN")}` ];
                }
              }
              return `  ${ctx.dataset.label}: ₹${Number(val).toLocaleString("en-IN")}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid:  { display: false },
          ticks: {
            color:          "#94A3B8",
            font:           { family: "Inter", size: 11 },
            maxTicksLimit:  13,   // ~monthly ticks across 90-day forecast
            maxRotation:    0,
          },
        },
        y: {
          grid:  { color: "#F1F5F9", drawBorder: false },
          ticks: {
            color: "#94A3B8",
            font:  { family: "Inter", size: 11 },
            callback: (v) => "₹" + Number(v).toLocaleString("en-IN"),
          },
        },
      },
    },
  });
}

// ============================================================
// UPCOMING EVENTS STRIP (between Card 2 and Card 3)
// ============================================================
function renderUpcomingEvents(events) {
  // Remove old strip if it exists
  const old = document.getElementById("upcoming-events-strip");
  if (old) old.remove();

  // Hide if no events
  if (!events || events.length === 0) return;

  // Build strip HTML
  const pillsHtml = events.map((e) => {
    const isUrgent    = e.days_away <= 7;
    const isImminent  = e.days_away <= 3;
    const pillBorder  = isImminent ? "#BBF7D0" : (isUrgent ? "#FED7AA" : "#E2E8F0");
    const badgeBg     = isUrgent   ? "#FFF7ED" : "#EFF6FF";
    const badgeColor  = isUrgent   ? "#C2410C" : "#2563EB";
    const platforms   = e.platforms ? e.platforms.join(" & ") : "";
    return `<div class="event-pill" style="border-color:${pillBorder}">
      <div class="event-pill-name" title="${e.name}">${e.name}</div>
      <div class="event-pill-date">${e.date}</div>
      <div class="event-pill-days">${e.days_away} day${e.days_away !== 1 ? "s" : ""} away</div>
      <span class="event-pill-badge" style="background:${badgeBg};color:${badgeColor}">
        ${e.discount_pct}% OFF
      </span>
    </div>`;
  }).join("");

  const strip = document.createElement("div");
  strip.id        = "upcoming-events-strip";
  strip.className = "upcoming-events-strip";
  strip.innerHTML = `
    <div class="upcoming-events-header">
      <span class="upcoming-events-title">UPCOMING SALES</span>
      <span class="upcoming-events-sub">Next 90 days</span>
    </div>
    <div class="upcoming-events-pills">${pillsHtml}</div>`;

  // Insert the strip just before Card 3 (card-trend)
  const card3 = document.getElementById("card-trend");
  if (card3 && card3.parentNode) {
    card3.parentNode.insertBefore(strip, card3);
  }
}


// ============================================================
// CARD 4: Set Alert
// ============================================================
async function setAlert() {
  const email    = (document.getElementById("alert-email")?.value   || "").trim();
  const priceRaw = (document.getElementById("alert-price")?.value   || "").trim();
  const product  = (document.getElementById("alert-product")?.value || currentProduct || "").trim();

  // Validate email
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    alert("Please enter a valid email address.");
    return;
  }

  // Validate price
  const price = parseFloat(priceRaw);
  if (isNaN(price) || price <= 0) {
    alert("Please enter a valid target price greater than 0.");
    return;
  }

  if (!product) {
    alert("Please search for a product first.");
    return;
  }

  const btn = document.getElementById("alert-btn");
  if (btn) {
    btn.textContent = "Setting alert…";
    btn.disabled    = true;
  }

  try {
    const res = await fetch("/set-alert", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        product:      product,
        email:        email,
        target_price: Math.round(price),
      }),
    });

    const data = await res.json();

    if (data.error) {
      throw new Error(data.error);
    }

    // Show success message
    const successEl = document.getElementById("alert-success");
    if (successEl) {
      successEl.innerHTML =
        `✓ Alert set! We'll email <strong>${email}</strong> when ` +
        `<strong>${product}</strong> drops below <strong>${formatINR(Math.round(price))}</strong>.`;
      show(successEl);
    }

    if (btn) {
      btn.textContent = "Alert Set ✓";
      btn.disabled    = true;
    }

  } catch (err) {
    console.error("[BargainBot] Alert failed:", err);
    alert("Failed to set alert: " + (err.message || "Please try again."));
    if (btn) {
      btn.textContent = "Notify Me";
      btn.disabled    = false;
    }
  }
}

// ============================================================
// Enter key in search input
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("search-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        searchProduct();
      }
    });
  }

  // Load model stats immediately
  loadModelStats();
});

// ============================================================
// ANALYTICS: populate all analytics cards
// ============================================================
function populateAnalytics(productName, a) {
  if (!a) return;

  // Product tag
  const tag = document.getElementById("analytics-product-tag");
  if (tag) tag.textContent = productName;

  // ---- Real data provenance badge ----
  const oldBadge = document.getElementById("analytics-data-badge");
  if (oldBadge) oldBadge.remove();
  const analyticsHeader = document.getElementById("analytics-header");
  if (analyticsHeader) {
    const badge = document.createElement("span");
    badge.id = "analytics-data-badge";
    badge.className = "analytics-data-badge";
    if (a.data_source === "real") {
      badge.textContent = `✓ Based on ${a.data_points} real price records`;
      badge.style.cssText = "background:#F0FDF4;border:1px solid #BBF7D0;color:#15803D";
    } else if (a.data_source === "limited") {
      badge.textContent = `⚠ Limited data — ${a.data_points} records (search again to build history)`;
      badge.style.cssText = "background:#FFFBEB;border:1px solid #FDE68A;color:#92400E";
    } else {
      badge.textContent = "📊 No price history yet — analytics will improve with each search";
      badge.style.cssText = "background:#F8FAFC;border:1px solid #E2E8F0;color:#64748B";
    }
    analyticsHeader.appendChild(badge);
  }

  // Price Statistics
  const fmt = (v) => v != null ? "₹" + Number(v).toLocaleString("en-IN") : "—";

  const athEl    = document.getElementById("stat-ath");
  const atlEl    = document.getElementById("stat-atl");
  const avgEl    = document.getElementById("stat-avg");
  const vsAvgEl  = document.getElementById("stat-vs-avg");

  if (athEl)   athEl.textContent   = fmt(a.all_time_high);
  if (atlEl)   atlEl.textContent   = fmt(a.all_time_low);
  if (avgEl)   avgEl.textContent   = fmt(a.avg_price);

  if (vsAvgEl) {
    const pct = a.vs_avg_pct;
    if (pct == null) {
      vsAvgEl.textContent = "—";
    } else {
      vsAvgEl.textContent  = (pct > 0 ? "+" : "") + pct + "%";
      vsAvgEl.className    = "stat-item-value " + (pct <= 0 ? "text-green" : "text-red");
    }
  }

  // Deal Score ring gauge
  const scoreEl   = document.getElementById("deal-score-number");
  const ringEl    = document.getElementById("ring-fill-circle");
  const verdictEl = document.getElementById("deal-score-verdict");

  const score = a.deal_score != null ? a.deal_score : 0;
  const circumference = 314;  // 2π × r=50
  const offset        = circumference * (1 - score / 100);

  if (scoreEl)   scoreEl.textContent = score;
  if (ringEl) {
    ringEl.style.strokeDashoffset = offset;
    const scoreClass = (
      score >= 75 ? "score-great" :
      score >= 50 ? "score-good"  :
      score >= 25 ? "score-ok"    : "score-poor"
    );
    ringEl.setAttribute("class", "ring-fill " + scoreClass);
  }
  if (verdictEl) {
    verdictEl.textContent = (
      score >= 75 ? "🔥 Excellent deal right now" :
      score >= 50 ? "👍 Good deal" :
      score >= 25 ? "⚠️ Fair deal — wait for a drop" :
                    "❌ Near all-time high — wait"
    );
  }

  // Trend indicator
  const trendIconEl = document.getElementById("trend-icon");
  const trendTextEl = document.getElementById("trend-text");
  const trend = a.trend || "stable";
  if (trendIconEl) {
    trendIconEl.textContent = trend === "down" ? "↓" : trend === "up" ? "↑" : "→";
    trendIconEl.style.color = trend === "down" ? "#16A34A" : trend === "up" ? "#DC2626" : "#64748B";
  }
  if (trendTextEl) {
    trendTextEl.textContent = trend === "down" ? "Price trending down"
                            : trend === "up"   ? "Price trending up"
                            :                   "Price stable";
  }

  // Buy Intelligence
  const bestMonthEl  = document.getElementById("intel-best-month");
  const dropsEl      = document.getElementById("intel-drops");
  const maxSavingsEl = document.getElementById("intel-max-savings");

  if (bestMonthEl) bestMonthEl.textContent = a.best_month || "—";

  if (dropsEl) {
    const total = a.price_drops || 0;
    const fcDips = a.fc_dips || 0;
    const realDrops = total - fcDips;
    if (total === 0) {
      dropsEl.textContent = "No significant drops in forecast";
    } else {
      let parts = [];
      if (realDrops > 0) parts.push(realDrops + " recorded");
      if (fcDips > 0)    parts.push(fcDips + " predicted by ML");
      dropsEl.textContent = parts.join(" · ") + (a.avg_drop_pct > 0 ? " (avg −" + a.avg_drop_pct + "% each)" : "");
    }
  }

  if (maxSavingsEl) {
    if (a.max_savings != null && a.max_savings > 0) {
      const note = a.savings_note ? ` (${a.savings_note})` : "";
      maxSavingsEl.textContent = fmt(a.max_savings) + " (" + a.max_savings_pct + "% off)" + note;
    } else {
      maxSavingsEl.textContent = "Price at forecast minimum — no cheaper time predicted";
    }
  }

  // Seasonal badge
  const dropBadge = document.getElementById("seasonal-drop-badge");
  if (dropBadge) {
    const fc = a.fc_dips || 0;
    const rd = (a.price_drops || 0) - fc;
    if (fc > 0 || rd > 0) {
      dropBadge.textContent = (rd > 0 ? rd + " actual + " : "") + (fc > 0 ? fc + " predicted" : "") + " price dips";
    } else {
      dropBadge.textContent = "Showing real scraped + ML forecast data";
    }
  }
}

// ============================================================
// ANALYTICS: Monthly price trend bar chart (actual + forecast)
// ============================================================
function drawSeasonalChart(monthlyData) {
  const canvas  = document.getElementById("seasonal-chart");
  const wrapper = document.getElementById("seasonal-chart-wrapper");
  const label   = document.getElementById("seasonal-label");
  if (!canvas || !wrapper) return;

  // Clean up old chart and overlay
  if (seasonalChart) {
    seasonalChart.destroy();
    seasonalChart = null;
  }
  const oldMsg = wrapper.querySelector(".seasonal-no-data");
  if (oldMsg) oldMsg.remove();
  canvas.style.display = "";

  if (!monthlyData || monthlyData.length === 0) {
    canvas.style.display = "none";
    const msg = document.createElement("div");
    msg.className = "seasonal-no-data";
    msg.innerHTML = `
      <div style="font-size:2rem;margin-bottom:10px">📊</div>
      <div style="font-weight:600;color:#334155;margin-bottom:6px">No Data Yet</div>
      <div style="font-size:13px;color:#64748B">Try searching a product to see the price trend.</div>`;
    wrapper.appendChild(msg);
    return;
  }

  // Separate actual vs forecast months
  const actualData   = monthlyData.filter(d => d.type === "actual"   || !d.type);
  const forecastData = monthlyData.filter(d => d.type === "forecast");
  const allMonths    = monthlyData.map(d => d.month);

  // Update card label
  if (label) {
    const a = actualData.length, f = forecastData.length;
    const parts = [];
    if (a > 0) parts.push(`${a} actual month${a > 1 ? "s" : ""}`);
    if (f > 0) parts.push(`${f} ML forecast month${f > 1 ? "s" : ""}`);
    label.textContent = "Monthly Price Trend" + (parts.length ? " (" + parts.join(" + ") + ")" : "");
  }

  const labels = allMonths.map(m => {
    const [yr, mo] = m.split("-");
    const d = new Date(Number(yr), Number(mo) - 1, 1);
    return d.toLocaleString("en-IN", { month: "short" }) + " '" + yr.slice(2);
  });
  const prices = monthlyData.map(d => d.price);

  // Color: purple for actual, light blue for forecast; festival months in amber
  const FEST = ["Oct", "Nov"];
  const bgColors = monthlyData.map(d => {
    const [yr, mo] = d.month.split("-");
    const shortMon = new Date(Number(yr), Number(mo) - 1, 1).toLocaleString("en-IN", { month: "short" });
    if (FEST.includes(shortMon)) return d.type === "forecast" ? "rgba(245,158,11,0.45)" : "#F59E0B";
    return d.type === "forecast" ? "rgba(59,130,246,0.50)" : "rgba(124,58,237,0.80)";
  });
  const borderColors = monthlyData.map(d => {
    const [yr, mo] = d.month.split("-");
    const shortMon = new Date(Number(yr), Number(mo) - 1, 1).toLocaleString("en-IN", { month: "short" });
    if (FEST.includes(shortMon)) return "#D97706";
    return d.type === "forecast" ? "#3B82F6" : "#7C3AED";
  });

  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pad  = Math.max((maxP - minP) * 0.15, minP * 0.02);

  seasonalChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label:            "Price",
        data:             prices,
        backgroundColor:  bgColors,
        borderColor:      borderColors,
        borderWidth:      1.5,
        borderRadius:     5,
        borderSkipped:    false,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F172A",
          titleColor:      "#94A3B8",
          bodyColor:       "#F8FAFC",
          borderColor:     "#1E293B",
          borderWidth:     1,
          padding:         10,
          callbacks: {
            label: (ctx) => {
              const d = monthlyData[ctx.dataIndex];
              const tag = d.type === "forecast" ? " (ML forecast)" : " (actual)";
              return "  ₹" + Number(ctx.parsed.y).toLocaleString("en-IN") + tag;
            },
            afterLabel: (ctx) => {
              const lbl = ctx.label || "";
              return FEST.some(m => lbl.startsWith(m)) ? "  🎉 Festival season" : "";
            },
          },
        },
      },
      scales: {
        x: {
          grid:  { display: false },
          ticks: {
            color:         "#94A3B8",
            font:          { family: "Inter", size: 10 },
            maxRotation:   45,
            maxTicksLimit: 18,
          },
        },
        y: {
          min:   Math.max(0, Math.floor(minP - pad)),
          max:   Math.ceil(maxP + pad),
          grid:  { color: "#F1F5F9", drawBorder: false },
          ticks: {
            color: "#94A3B8",
            font:  { family: "Inter", size: 10 },
            callback: (v) => "₹" + Number(v).toLocaleString("en-IN"),
          },
        },
      },
    },
  });
}
