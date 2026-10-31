const number = new Intl.NumberFormat("ko-KR");
const percent = new Intl.NumberFormat("ko-KR", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const decimal = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 3 });
const colors = ["#2563eb", "#e15554", "#2a9d8f", "#f4a261", "#8b5cf6", "#06b6d4", "#d946ef", "#64748b"];
function amount({ value }) { return value == null ? "-" : number.format(value); }
function fixed({ value }) { return value == null ? "-" : decimal.format(value); }
function rate({ value }) { return value == null ? "-" : percent.format(value); }
function signClass({ value }) { return value > 0 ? "up-value" : value < 0 ? "down-value" : ""; }

const identityColumns = [
  { field: "BAS_DD", headerName: "기준일", minWidth: 104, pinned: "left" },
  { field: "ISU_CD", headerName: "종목코드", minWidth: 102, pinned: "left" },
  { field: "ISU_NM", headerName: "종목명", minWidth: 140, pinned: "left" },
];
const marketColumns = [
  { field: "MKT_NM", headerName: "시장", minWidth: 86 }, { field: "TDD_CLSPRC", headerName: "종가", valueFormatter: amount },
  { field: "FLUC_RT", headerName: "등락률(%)", minWidth: 105, valueFormatter: fixed, cellClass: signClass },
  { field: "ACC_TRDVOL", headerName: "거래량", minWidth: 120, valueFormatter: amount }, { field: "ACC_TRDVAL", headerName: "거래대금", minWidth: 140, valueFormatter: amount },
  { field: "cluster", headerName: "군집", minWidth: 78 }, { field: "cluster_label", headerName: "패턴", minWidth: 130 },
];
const ohlcvColumns = [
  ["TDD_OPNPRC", "시가"], ["TDD_HGPRC", "고가"], ["TDD_LWPRC", "저가"], ["TDD_CLSPRC", "종가"],
  ["ACC_TRDVOL", "거래량"], ["ACC_TRDVAL", "거래대금"], ["MKTCAP", "시가총액"], ["LIST_SHRS", "상장주식수"],
].map(([field, headerName]) => ({ field, headerName, minWidth: field.startsWith("ACC") || field === "MKTCAP" ? 135 : 100, valueFormatter: amount }))
  .concat([{ field: "cluster", headerName: "군집", minWidth: 78 }, { field: "cluster_label", headerName: "패턴", minWidth: 130 }]);
const featureColumns = [
  ["return_rate", "일일 수익률", "rate"], ["gap_rate", "갭 수익률", "rate"], ["body_ratio", "몸통 비율", "decimal"],
  ["clv", "종가 위치 CLV", "decimal"], ["range_rate", "고저폭 비율", "rate"], ["volatility_5d", "5일 변동성", "rate"],
  ["volume_change", "거래량 변화", "rate"], ["volume_ratio_20d", "20일 거래량 배수", "decimal"],
  ["log_trading_value", "로그 거래대금", "decimal"], ["turnover_rate", "회전율", "rate"],
  ["pca_x", "PC1", "decimal"], ["pca_y", "PC2", "decimal"], ["pca_z", "PC3", "decimal"],
  ["cluster", "군집", "number"], ["cluster_label", "패턴", "text"],
].map(([field, headerName, type]) => ({ field, headerName, minWidth: 112, valueFormatter: type === "rate" ? rate : type === "decimal" ? fixed : undefined, cellClass: type === "rate" ? signClass : undefined }));

const grid = agGrid.createGrid(document.querySelector("#stock-grid"), {
  theme: agGrid.themeQuartz, columnDefs: [...identityColumns, ...marketColumns],
  defaultColDef: { sortable: true, resizable: true, filter: true, minWidth: 95 }, rowData: [], pagination: true,
  paginationPageSize: 100, paginationPageSizeSelector: [50, 100, 200, 500], animateRows: true,
  overlayNoRowsTemplate: '<span class="ag-overlay-no-rows-center">분석된 데이터가 없습니다.</span>',
});
const $ = (selector) => document.querySelector(selector);
const fromInput = $("#from-date"); const toInput = $("#to-date"); const searchButton = $("#search-button"); const csvButton = $("#csv-button"); const status = $("#status");
let payload = null; let dimension = 2;
const today = new Date(); const monthAgo = new Date(today); monthAgo.setDate(today.getDate() - 35);
fromInput.value = monthAgo.toLocaleDateString("en-CA"); toInput.value = today.toLocaleDateString("en-CA");

const pageMeta = {
  dashboard: ["SETUP", "분석 설정"],
  visual: ["PATTERN MAP", "군집 지도"],
  grid: ["DATA EXPLORER", "데이터 탐색"],
};
function closeMenu() { document.body.classList.remove("menu-open"); }
function activatePage(page) {
  document.querySelectorAll("[data-page-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.pagePanel === page));
  document.querySelectorAll("[data-page]").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
  $("#page-kicker").textContent = pageMeta[page][0]; $("#page-title").textContent = pageMeta[page][1];
  closeMenu();
  requestAnimationFrame(() => {
    if (page === "visual" && payload) Plotly.Plots.resize($("#cluster-plot"));
    if (page === "grid") { grid.refreshCells(); grid.redrawRows(); }
  });
}

function setStatus(message, error = false) { status.textContent = message; status.classList.toggle("error", error); }
function setView(next) {
  const columns = next === "ohlcv" ? [...identityColumns, ...ohlcvColumns] : next === "features" ? [...identityColumns, ...featureColumns] : [...identityColumns, ...marketColumns];
  grid.setGridOption("columnDefs", columns);
  document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === next));
}
function updateSummary(data) {
  $("#period-value").textContent = `${data.from_date} ~ ${data.to_date}`; $("#records-value").textContent = `${number.format(data.record_count)}건`;
  $("#rejected-value").textContent = `유효성 검사 제외 ${number.format(data.rejected_count)}건`; $("#clusters-value").textContent = `${data.analysis.cluster_count}개`;
  $("#variance-value").textContent = percent.format(data.analysis.explained_variance_ratio.reduce((sum, value) => sum + value, 0));
}
function renderProfiles(data) {
  $("#cluster-profiles").innerHTML = data.analysis.profiles.map((profile) => `<button class="profile-card" data-cluster="${profile.cluster}" style="--cluster:${colors[profile.cluster % colors.length]}"><span>C${profile.cluster} · ${profile.label}</span><strong>${number.format(profile.count)}건</strong><small>평균 수익 ${percent.format(profile.mean_return)} · 거래량 ${decimal.format(profile.mean_volume_ratio)}×</small></button>`).join("");
  document.querySelectorAll(".profile-card").forEach((card) => card.addEventListener("click", () => filterCluster(Number(card.dataset.cluster))));
}
function renderPlot() {
  if (!payload) return;
  const traces = payload.analysis.profiles.map((profile) => {
    const rows = payload.data.filter((row) => row.cluster === profile.cluster);
    const common = {
      x: rows.map((row) => row.pca_x), y: rows.map((row) => row.pca_y), mode: "markers", name: `C${profile.cluster} ${profile.label}`,
      customdata: rows.map((row) => [row.BAS_DD, row.ISU_CD, row.ISU_NM, row.return_rate, row.volume_ratio_20d]),
      marker: { color: colors[profile.cluster % colors.length], size: dimension === 3 ? 4 : 7, opacity: .72, line: { width: .4, color: "#fff" } },
      hovertemplate: "%{customdata[0]} · %{customdata[2]}<br>수익률 %{customdata[3]:.2%}<br>거래량 배수 %{customdata[4]:.2f}×<extra></extra>",
    };
    return dimension === 3 ? { ...common, type: "scatter3d", z: rows.map((row) => row.pca_z) } : { ...common, type: "scattergl" };
  });
  const axis = { gridcolor: "#e9edf4", zerolinecolor: "#cbd5e1", title: "PC1" };
  const layout = { margin: { l: 48, r: 20, t: 18, b: 44 }, paper_bgcolor: "transparent", plot_bgcolor: "#fbfcfe", font: { family: "Inter, sans-serif", color: "#334155" }, legend: { orientation: "h", y: 1.08 }, xaxis: axis, yaxis: { ...axis, title: "PC2" }, scene: { xaxis: axis, yaxis: { ...axis, title: "PC2" }, zaxis: { ...axis, title: "PC3" }, bgcolor: "#fbfcfe" }, hovermode: "closest", dragmode: dimension === 3 ? "orbit" : "lasso" };
  Plotly.react("cluster-plot", traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["toImage"] });
  const plot = $("#cluster-plot"); plot.removeAllListeners?.("plotly_click");
  plot.on("plotly_click", ({ points }) => { const selected = points[0]?.customdata; if (!selected) return; grid.setGridOption("quickFilterText", `${selected[0]} ${selected[1]}`); setStatus(`${selected[0]} ${selected[2]} 레코드를 표에서 선택했습니다.`); activatePage("grid"); });
}
function filterCluster(cluster) { grid.setFilterModel({ cluster: { filterType: "number", type: "equals", filter: cluster } }); setStatus(`군집 C${cluster}만 표에 표시합니다. 필터 해제로 전체를 볼 수 있습니다.`); activatePage("grid"); }
async function loadData() {
  if (!fromInput.value || !toInput.value) return setStatus("시작일과 종료일을 입력하세요.", true);
  if (fromInput.value > toInput.value) return setStatus("시작일은 종료일보다 늦을 수 없습니다.", true);
  searchButton.disabled = true; csvButton.disabled = true; grid.setGridOption("rowData", []); setStatus("KRX 수집 → OHLCV 정제 → 10차원 군집 분석을 실행하고 있습니다…");
  try {
    const params = new URLSearchParams({ from: fromInput.value, to: toInput.value, clusters: $("#cluster-count").value });
    if ($("#symbols").value.trim()) params.set("symbols", $("#symbols").value.trim());
    const response = await fetch(`/api/v1/stocks/analysis?${params}`); const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "분석 데이터를 불러오지 못했습니다.");
    payload = result; grid.setGridOption("rowData", result.data); updateSummary(result); renderProfiles(result); csvButton.disabled = false;
    $("#visual-badge").textContent = result.analysis.cluster_count; $("#grid-badge").textContent = number.format(result.record_count);
    document.querySelectorAll(".sidebar-flow li").forEach((item) => item.classList.add("done"));
    setStatus(`${number.format(result.record_count)}건을 ${result.analysis.cluster_count}개 패턴으로 분석했습니다. 점과 군집 카드를 선택해 탐색하세요.`);
    activatePage("visual"); requestAnimationFrame(renderPlot);
  } catch (error) { setStatus(error.message, true); } finally { searchButton.disabled = false; }
}
searchButton.addEventListener("click", loadData);
csvButton.addEventListener("click", () => grid.exportDataAsCsv({ fileName: `krx_ohlcv_analysis_${fromInput.value}_${toInput.value}.csv` }));
$("#clear-filter").addEventListener("click", () => { grid.setFilterModel(null); grid.setGridOption("quickFilterText", ""); setStatus("표 필터를 해제했습니다."); });
document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
document.querySelectorAll("[data-dimension]").forEach((button) => button.addEventListener("click", () => { dimension = Number(button.dataset.dimension); document.querySelectorAll("[data-dimension]").forEach((item) => item.classList.toggle("active", item === button)); renderPlot(); }));
document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => activatePage(button.dataset.page)));
document.querySelectorAll("[data-go-page]").forEach((button) => button.addEventListener("click", () => activatePage(button.dataset.goPage)));
$("#open-menu").addEventListener("click", () => document.body.classList.add("menu-open"));
$("#close-menu").addEventListener("click", closeMenu); $("#sidebar-backdrop").addEventListener("click", closeMenu);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenu(); });
window.addEventListener("resize", () => { if (payload && $("[data-page-panel='visual']").classList.contains("active")) Plotly.Plots.resize($("#cluster-plot")); });
