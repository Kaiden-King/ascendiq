/* AscendIQ charts: shooting % line and workouts bars, with an optional Day/Week switch.
   Used by the dashboard and the public profile. Needs Chart.js loaded first and the
   data in <script id="chart-data" type="application/json"> (Django's json_script). */
(function () {
    var source = document.getElementById("chart-data");
    if (!source) return;  // no data on this page
    var data = JSON.parse(source.textContent);

    // Words that change with the range.
    var TEXT = {
      week: { shooting: "Shooting % · 12 weeks", workouts: "Workouts per week · 12 weeks",
              note: "Gaps are weeks with no shots logged." },
      day:  { shooting: "Shooting % · 14 days", workouts: "Workouts per day · 14 days",
              note: "The line joins the days you shot. Rest days get no point, never 0%." },
    };

    // Colours come from the stylesheet's tokens, so the charts match the app.
    var css = getComputedStyle(document.documentElement);
    var orange = css.getPropertyValue("--orange").trim();
    var muted = css.getPropertyValue("--muted").trim();
    var grid = css.getPropertyValue("--hairline").trim();

    Chart.defaults.color = muted;
    Chart.defaults.font.size = 12;
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.maintainAspectRatio = false;
    function axes(yOptions) {
      return {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } },
        y: Object.assign({ grid: { color: grid }, beginAtZero: true }, yOptions),
      };
    }

    // 1. Shooting %. Days/weeks with no shots are null — never plotted as 0%.
    var shootingCanvas = document.getElementById("shooting-chart");
    var workoutsCanvas = document.getElementById("workouts-chart");
    var shootingChart = shootingCanvas && new Chart(shootingCanvas, {
      type: "line",
      data: { labels: [], datasets: [{
        data: [], borderColor: orange, backgroundColor: orange,
        borderWidth: 3, pointRadius: 4, tension: 0.3, spanGaps: false,
      }] },
      options: {
        scales: axes({ max: 100, ticks: { stepSize: 25, callback: function (v) { return v + "%"; } } }),
        plugins: { tooltip: { callbacks: { label: function (c) { return c.parsed.y + "% shooting"; } } } },
      },
    });

    // 2. Finished workouts.
    var workoutsChart = workoutsCanvas && new Chart(workoutsCanvas, {
      type: "bar",
      data: { labels: [], datasets: [{ data: [], backgroundColor: orange, borderRadius: 6, maxBarThickness: 22 }] },
      options: {
        scales: axes({ ticks: { precision: 0, stepSize: 1 } }),
        plugins: { tooltip: { callbacks: { label: function (c) {
          return c.parsed.y + (c.parsed.y === 1 ? " workout" : " workouts");
        } } } },
      },
    });

    // The big number and the up/down badge above the shooting chart.
    function showChange(view) {
      var latest = document.getElementById("trend-latest");
      var change = document.getElementById("trend-change");
      if (!latest || !change) return;
      latest.innerHTML = view.latest === null ? "—" : view.latest + "<span>%</span>";
      change.className = "trend-head__change";
      if (view.change === null) {
        change.textContent = view.latest === null ? "" : "First one to compare against";
      } else if (view.change > 0) {
        change.classList.add("trend-head__change--up");
        change.textContent = "▲ " + view.change + " pts vs " + view.compared_with;
      } else if (view.change < 0) {
        change.classList.add("trend-head__change--down");
        change.textContent = "▼ " + Math.abs(view.change) + " pts vs " + view.compared_with;
      } else {
        change.textContent = "Same as " + view.compared_with;
      }
    }

    function setText(selector, text) {
      var element = document.querySelector(selector);
      if (element) element.textContent = text;
    }

    function show(range) {
      var view = data[range];
      if (shootingChart) {
        shootingChart.data.labels = view.labels;
        shootingChart.data.datasets[0].data = view.shooting;
        // Day view joins sessions across rest days; week view keeps a missed week as a gap.
        shootingChart.data.datasets[0].spanGaps = (range === "day");
        shootingChart.update();
      }
      if (workoutsChart) {
        workoutsChart.data.labels = view.labels;
        workoutsChart.data.datasets[0].data = view.workouts;
        workoutsChart.update();
      }
      setText('[data-title="shooting"]', TEXT[range].shooting);
      setText('[data-title="workouts"]', TEXT[range].workouts);
      setText("[data-note]", TEXT[range].note);
      showChange(view);
      document.querySelectorAll(".range-switch button").forEach(function (button) {
        button.setAttribute("aria-pressed", button.dataset.range === range ? "true" : "false");
      });
    }

    document.querySelectorAll(".range-switch button").forEach(function (button) {
      button.addEventListener("click", function () { show(button.dataset.range); });
    });
    show("week");
  })();
