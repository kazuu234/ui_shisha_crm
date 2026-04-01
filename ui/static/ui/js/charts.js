let dailyChart = null;
let segmentChart = null;
let staffChart = null;

const COLORS = {
  accent: "#2D7D7B",
  accentLight: "rgba(45, 125, 123, 0.1)",
  new: "#2D7D7B",
  repeat: "#B8860B",
  regular: "#4A7C59",
  textPrimary: "#1C1917",
  textSecondary: "#57534E",
  borderDefault: "#E0DCD4",
};

function initCharts() {
  if (dailyChart) {
    dailyChart.destroy();
    dailyChart = null;
  }
  if (segmentChart) {
    segmentChart.destroy();
    segmentChart = null;
  }
  if (staffChart) {
    staffChart.destroy();
    staffChart = null;
  }

  const dailyEl = document.getElementById("daily-data");
  const segmentEl = document.getElementById("segment-data");
  const staffEl = document.getElementById("staff-data");

  if (!dailyEl || !segmentEl || !staffEl) return;

  const dailyData = JSON.parse(dailyEl.textContent);
  const segmentData = JSON.parse(segmentEl.textContent);
  const staffData = JSON.parse(staffEl.textContent);

  const dailyCanvas = document.getElementById("chart-daily");
  if (dailyCanvas) {
    dailyChart = new Chart(dailyCanvas, {
      type: "line",
      data: {
        labels: dailyData.labels,
        datasets: [
          {
            label: dailyData.datasets[0].label,
            data: dailyData.datasets[0].data,
            borderColor: COLORS.accent,
            backgroundColor: COLORS.accentLight,
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { color: COLORS.borderDefault },
            ticks: { color: COLORS.textSecondary, maxTicksLimit: 10 },
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.borderDefault },
            ticks: { color: COLORS.textSecondary, precision: 0 },
          },
        },
      },
    });
  }

  const segmentCanvas = document.getElementById("chart-segment");
  if (segmentCanvas) {
    segmentChart = new Chart(segmentCanvas, {
      type: "doughnut",
      data: {
        labels: segmentData.labels,
        datasets: [
          {
            data: segmentData.datasets[0].data,
            backgroundColor: [COLORS.new, COLORS.repeat, COLORS.regular],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: COLORS.textPrimary },
          },
        },
      },
    });
  }

  const staffCanvas = document.getElementById("chart-staff");
  if (staffCanvas) {
    staffChart = new Chart(staffCanvas, {
      type: "bar",
      data: {
        labels: staffData.labels,
        datasets: [
          {
            label: staffData.datasets[0].label,
            data: staffData.datasets[0].data,
            backgroundColor: COLORS.accent,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: COLORS.textPrimary },
          },
          y: {
            beginAtZero: true,
            grid: { color: COLORS.borderDefault },
            ticks: { color: COLORS.textSecondary, precision: 0 },
          },
        },
      },
    });
  }
}

document.addEventListener("DOMContentLoaded", initCharts);
