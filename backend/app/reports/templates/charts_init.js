/* 차트 그리기: <div class="chart" data-option-id> + <script type="application/json" id>의 option.
   echarts 가 없으면(번들 미포함) 문구만 남기고 표를 본다. 끝나면 window.__reportReady = true (PDF 인쇄 대기). */
(function () {
  function run() {
    var ok = typeof window.echarts !== "undefined";
    var divs = document.querySelectorAll("div.chart[data-option-id]");
    for (var i = 0; i < divs.length; i++) {
      var div = divs[i];
      if (!ok) {
        div.textContent = "차트 번들 없음 — 아래 표를 본다";
        div.style.height = "auto";
        continue;
      }
      try {
        var src = document.getElementById(div.getAttribute("data-option-id"));
        var option = JSON.parse(src.textContent);
        var chart = window.echarts.init(div, null, { renderer: "svg" });
        chart.setOption(option);
      } catch (e) {
        div.textContent = "차트 오류 — 아래 표를 본다";
      }
    }
    window.__reportReady = true;
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
