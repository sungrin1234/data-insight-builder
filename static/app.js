/**
 * AI Data Insight Builder - Frontend Logic (Vanilla JS + Chart.js)
 * 
 * Console Log 규칙 준수:
 * [PAGE], [UPLOAD], [INSPECT], [SUGGEST], [RUN], [CHART], [EXPLAIN], [ERROR]
 */

document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] 페이지 로드 완료");

    // 전역 상태 변수
    let currentChartInstance = null;
    let currentInspection = null;

    // DOM 요소 캐싱
    const healthBadge = document.getElementById("healthBadge");
    const csvFileInput = document.getElementById("csvFileInput");
    const selectedFileName = document.getElementById("selectedFileName");
    const inspectLoading = document.getElementById("inspectLoading");

    // 진단 섹션 요소
    const diagnoseSection = document.getElementById("diagnoseSection");
    const warningsBox = document.getElementById("warningsBox");
    const metricEncoding = document.getElementById("metricEncoding");
    const metricSkiprows = document.getElementById("metricSkiprows");
    const metricShape = document.getElementById("metricShape");
    const metricRecYear = document.getElementById("metricRecYear");
    const metricAggregates = document.getElementById("metricAggregates");
    const previewHead = document.getElementById("previewHead");
    const previewBody = document.getElementById("previewBody");

    // 제안 섹션 요소
    const suggestSection = document.getElementById("suggestSection");
    const suggestLoading = document.getElementById("suggestLoading");
    const suggestionCards = document.getElementById("suggestionCards");
    const btnRequestSuggest = document.getElementById("btnRequestSuggest");

    // 실행 섹션 요소
    const runSection = document.getElementById("runSection");
    const toolSelect = document.getElementById("toolSelect");
    const paramRefPeriod = document.getElementById("paramRefPeriod");
    const paramTargetItem = document.getElementById("paramTargetItem");
    const paramExcludeAgg = document.getElementById("paramExcludeAgg");
    const btnRunTool = document.getElementById("btnRunTool");
    const runLoading = document.getElementById("runLoading");

    // 결과 섹션 요소
    const resultSection = document.getElementById("resultSection");
    const resultMetaBox = document.getElementById("resultMetaBox");
    const resultChartCanvas = document.getElementById("resultChart");
    const resultTable = document.getElementById("resultTable");

    // 해석 섹션 요소
    const explainSection = document.getElementById("explainSection");
    const btnRequestExplain = document.getElementById("btnRequestExplain");
    const explainLoading = document.getElementById("explainLoading");
    const reportBox = document.getElementById("reportBox");

    // ==========================================
    // 0. 서버 상태 확인 (GET /health)
    // ==========================================
    async function checkHealth() {
        try {
            const res = await fetch("/health");
            if (!res.ok) throw new Error("서버 응답 오류");
            const data = await res.json();
            
            if (data.status === "ok") {
                if (data.gemini_api_key_configured) {
                    healthBadge.textContent = `🟢 연결됨 (모델: ${data.model})`;
                    healthBadge.className = "health-badge ok";
                } else {
                    healthBadge.textContent = "🟡 연결됨 (API 키 미설정)";
                    healthBadge.className = "health-badge warn";
                }
            }
        } catch (err) {
            console.error("[ERROR] Health check 실패:", err.message);
            healthBadge.textContent = "🔴 서버 오프라인";
            healthBadge.className = "health-badge warn";
        }
    }
    checkHealth();

    // ==========================================
    // 1. 파일 선택 및 드래그앤드롭 진단 요청 (POST /inspect)
    // ==========================================
    const dropZone = document.getElementById("dropZone");

    async function handleFile(file) {
        if (!file) return;

        console.log(`[UPLOAD] 파일 선택: name=${file.name}, size=${file.size} bytes`);
        selectedFileName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

        const formData = new FormData();
        formData.append("file", file);

        inspectLoading.classList.remove("hidden");
        console.log("[INSPECT] 진단 요청 시작");

        try {
            const res = await fetch("/inspect", {
                method: "POST",
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "진단 처리 중 오류가 발생했습니다.");
            }

            currentInspection = data;
            console.log(`[INSPECT] 응답 수신: rows=${data.rows}, cols=${data.columns_count}, warnings=${data.warnings.length}`);

            // 진단 결과 UI 반영
            renderInspection(data);

            // 후속 섹션 표시 및 자동 제안 요청
            diagnoseSection.classList.remove("hidden");
            suggestSection.classList.remove("hidden");
            runSection.classList.remove("hidden");
            if (chatSection) chatSection.classList.remove("hidden");

            // 권장 기준 연도 입력창에 자동 채우기
            if (data.recommended_year) {
                paramRefPeriod.value = data.recommended_year;
            }

            // 자동 분석 제안 요청
            requestSuggestions();

        } catch (err) {
            console.error("[ERROR] /inspect 요청 실패:", err.message);
            alert(`[오류] ${err.message}`);
        } finally {
            inspectLoading.classList.add("hidden");
        }
    }

    const btnStartInspect = document.getElementById("btnStartInspect");

    if (csvFileInput) {
        csvFileInput.addEventListener("change", (e) => {
            const files = e.target.files;
            if (files && files.length > 0) {
                const f = files[0];
                selectedFileName.textContent = `✅ 선택됨: ${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
                selectedFileName.style.color = "#059669";
            }
        });
    }

    if (btnStartInspect) {
        btnStartInspect.addEventListener("click", () => {
            const files = csvFileInput ? csvFileInput.files : null;
            if (!files || files.length === 0) {
                alert("먼저 [파일 선택] 버튼을 눌러 CSV 파일을 골라주세요!");
                return;
            }
            handleFile(files[0]);
        });
    }

    // 진단 리포트 화면 렌더링
    function renderInspection(data) {
        metricEncoding.textContent = data.encoding;
        metricSkiprows.textContent = `${data.skiprows} 줄`;
        metricShape.textContent = `${data.rows.toLocaleString()}행 × ${data.columns_count}열`;
        metricRecYear.textContent = data.recommended_year ? `${data.recommended_year}년` : "감지 안 됨";
        metricAggregates.textContent = `${data.aggregate_candidates_count}개 후보 감지`;

        // 경고 메시지 렌더링
        if (data.warnings && data.warnings.length > 0) {
            warningsBox.innerHTML = data.warnings.map(w => `<div class="warning-item">⚠️ ${w}</div>`).join("");
            warningsBox.classList.remove("hidden");
        } else {
            warningsBox.classList.add("hidden");
        }

        // 데이터 미리보기 렌더링
        if (data.preview_rows && data.preview_rows.length > 0) {
            const cols = Object.keys(data.preview_rows[0]);
            previewHead.innerHTML = `<tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
            previewBody.innerHTML = data.preview_rows.map(row => {
                return `<tr>${cols.map(c => `<td>${escapeHtml(row[c] !== null ? String(row[c]) : "")}</td>`).join("")}</tr>`;
            }).join("");
        }
    }

    // ==========================================
    // 2. Gemini 분석 제안 요청 (POST /suggest)
    // ==========================================
    async function requestSuggestions() {
        console.log("[SUGGEST] 제안 요청 시작");
        suggestLoading.classList.remove("hidden");
        suggestionCards.innerHTML = "";

        try {
            const res = await fetch("/suggest", {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "분석 제안 생성 중 오류가 발생했습니다.");
            }

            const suggestions = data.suggestions || [];
            console.log(`[SUGGEST] 응답 수신: 제안 개수=${suggestions.length}`);
            renderSuggestions(suggestions);

        } catch (err) {
            console.error("[ERROR] /suggest 요청 실패:", err.message);
            suggestionCards.innerHTML = `<div class="warning-item">⚠️ AI 제안을 불러오지 못했습니다: ${escapeHtml(err.message)}</div>`;
        } finally {
            suggestLoading.classList.add("hidden");
        }
    }

    btnRequestSuggest.addEventListener("click", requestSuggestions);

    // AI 제안 카드 렌더링
    function renderSuggestions(suggestions) {
        if (!suggestions || suggestions.length === 0) {
            suggestionCards.innerHTML = `<p class="desc">제안된 분석 항목이 없습니다.</p>`;
            return;
        }

        suggestionCards.innerHTML = suggestions.map((s, idx) => {
            return `
                <div class="suggestion-card" data-idx="${idx}">
                    <div class="suggestion-header">
                        <span class="suggestion-badge">추천 분석 #${idx + 1}</span>
                        <span class="suggestion-period">기준: ${escapeHtml(s.reference_period || "")}</span>
                    </div>
                    <div class="suggestion-why"><strong>도구:</strong> ${escapeHtml(s.tool)}<br>${escapeHtml(s.why || "")}</div>
                    ${s.caution ? `<div class="suggestion-caution">⚠️ ${escapeHtml(s.caution)}</div>` : ""}
                    <button class="btn btn-secondary btn-sm" style="margin-top:auto;">이 분석 선택 &rarr;</button>
                </div>
            `;
        }).join("");

        // 카드 클릭 시 폼에 파라미터 자동 채우기 및 스크롤
        document.querySelectorAll(".suggestion-card").forEach(card => {
            card.addEventListener("click", () => {
                const idx = parseInt(card.dataset.idx, 10);
                const s = suggestions[idx];
                applySuggestionToForm(s);
            });
        });
    }

    function applySuggestionToForm(suggestion) {
        if (!suggestion) return;

        toolSelect.value = suggestion.tool;
        if (suggestion.reference_period) {
            paramRefPeriod.value = suggestion.reference_period;
        }
        if (suggestion.params) {
            if (suggestion.params.target_item) {
                paramTargetItem.value = suggestion.params.target_item;
            }
            if (suggestion.params.exclude_aggregates !== undefined) {
                paramExcludeAgg.checked = Boolean(suggestion.params.exclude_aggregates);
            }
        }

        // 4단계 폼으로 부드럽게 스크롤
        runSection.scrollIntoView({ behavior: "smooth" });
    }

    // ==========================================
    // 3. Pandas 계산 실행 (POST /run)
    // ==========================================
    btnRunTool.addEventListener("click", async () => {
        const toolName = toolSelect.value;
        const refPeriod = paramRefPeriod.value.trim();
        const targetItem = paramTargetItem.value.trim();
        const excludeAgg = paramExcludeAgg.checked;

        // 파라미터 구성
        const params = {
            exclude_aggregates: excludeAgg
        };

        if (refPeriod) {
            params.reference_period = refPeriod;
            params.value_column = refPeriod;
        }

        if (toolName === "compare_one_vs_all" && targetItem) {
            params.target_item = targetItem;
        }

        if (toolName === "trend_line") {
            params.target_labels = targetItem ? targetItem.split(",").map(t => t.trim()) : ["Korea, Rep.", "Japan", "United States"];
        }

        if (toolName === "change_rate") {
            params.start_period = "2014";
            params.end_period = refPeriod || "2024";
        }

        console.log(`[RUN] 도구 실행 시작: tool=${toolName}, period=${refPeriod}`);
        runLoading.classList.remove("hidden");

        try {
            const res = await fetch("/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tool: toolName,
                    params: params
                })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "도구 실행 중 오류가 발생했습니다.");
            }

            console.log(`[RUN] 결과 수신: rows_used=${data.rows_used}, rows_excluded=${data.rows_excluded}`);

            // 계산 결과 표시
            renderRunResult(data);

            resultSection.classList.remove("hidden");
            explainSection.classList.remove("hidden");
            resultSection.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] /run 실행 실패:", err.message);
            alert(`[오류] ${err.message}`);
        } finally {
            runLoading.classList.add("hidden");
        }
    });

    // 계산 결과 화면 및 Chart.js 렌더링
    function renderRunResult(data) {
        // 메타데이터 배너 렌더링
        resultMetaBox.innerHTML = `
            <div><strong>분석 도구:</strong> ${escapeHtml(data.tool)} &bull; <strong>기준 시점:</strong> ${escapeHtml(data.reference_period || "전체")}</div>
            <div><strong>사용한 표본:</strong> ${data.rows_used}개 행 &bull; <strong>제외된 표본:</strong> ${data.rows_excluded}개 행 (${escapeHtml(data.exclusion_reason || "")})</div>
            <div><strong>단위:</strong> ${escapeHtml(data.unit || "")}</div>
            ${data.caution ? `<div><strong>⚠️ 주의사항:</strong> ${escapeHtml(data.caution)}</div>` : ""}
        `;

        // 차트 렌더링 (차트 데이터가 존재하는 경우)
        if (data.chart_data && data.chart_type) {
            resultChartCanvas.style.display = "block";
            renderChart(data.chart_type, data.chart_data, data.chart_options);
        } else {
            resultChartCanvas.style.display = "none";
            if (currentChartInstance) {
                currentChartInstance.destroy();
                currentChartInstance = null;
            }
        }

        // 결과 테이블 렌더링
        renderResultTable(data);
    }

    function renderChart(type, chartData, options = {}) {
        if (currentChartInstance) {
            currentChartInstance.destroy();
        }

        const ctx = resultChartCanvas.getContext("2d");
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "top" }
            }
        };

        currentChartInstance = new Chart(ctx, {
            type: type,
            data: chartData,
            options: Object.assign({}, defaultOptions, options)
        });

        console.log(`[CHART] 차트 렌더 완료 (타입: ${type})`);
    }

    function renderResultTable(data) {
        if (data.table && data.table.length > 0) {
            const cols = Object.keys(data.table[0]);
            resultTable.innerHTML = `
                <thead>
                    <tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>
                </thead>
                <tbody>
                    ${data.table.map(row => `
                        <tr>${cols.map(c => `<td>${escapeHtml(row[c] !== null ? String(row[c]) : "")}</td>`).join("")}</tr>
                    `).join("")}
                </tbody>
            `;
            resultTable.parentElement.style.display = "block";
        } else if (data.stats) {
            // describe_numeric 통계표
            const stats = data.stats;
            resultTable.innerHTML = `
                <thead><tr><th>통계 지표</th><th>값</th></tr></thead>
                <tbody>
                    <tr><td>표본 수 (Count)</td><td>${stats.count}</td></tr>
                    <tr><td>산술 평균 (Mean)</td><td>${stats.mean}</td></tr>
                    <tr><td>중앙값 (Median)</td><td>${stats.median}</td></tr>
                    <tr><td>표준편차 (Std)</td><td>${stats.std}</td></tr>
                    <tr><td>최솟값 (Min)</td><td>${stats.min}</td></tr>
                    <tr><td>25% 분위수 (Q25)</td><td>${stats.q25}</td></tr>
                    <tr><td>75% 분위수 (Q75)</td><td>${stats.q75}</td></tr>
                    <tr><td>최댓값 (Max)</td><td>${stats.max}</td></tr>
                </tbody>
            `;
            resultTable.parentElement.style.display = "block";
        } else {
            resultTable.parentElement.style.display = "none";
        }
    }

    // ==========================================
    // 4. Gemini 해석 보고서 요청 (POST /explain)
    // ==========================================
    btnRequestExplain.addEventListener("click", async () => {
        const mode = document.querySelector('input[name="explainMode"]:checked').value;
        console.log(`[EXPLAIN] 해석 요청 시작: 모드=${mode}`);

        explainLoading.classList.remove("hidden");
        reportBox.classList.add("hidden");

        try {
            const res = await fetch("/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode: mode })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "해석 보고서 생성 중 오류가 발생했습니다.");
            }

            console.log(`[EXPLAIN] 응답 수신: 모드=${data.mode}`);
            renderReport(data.report);

            reportBox.classList.remove("hidden");
            reportBox.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] /explain 요청 실패:", err.message);
            alert(`[오류] ${err.message}`);
        } finally {
            explainLoading.classList.add("hidden");
        }
    });

    // 간단한 마크다운 렌더러 (## 제목, 글머리기호, 굵은글씨 등 파싱)
    function renderReport(mdText) {
        if (!mdText) {
            reportBox.innerHTML = "<p>생성된 보고서가 없습니다.</p>";
            return;
        }

        let html = mdText
            // 헤더 변환
            .replace(/^### (.*$)/gim, "<h3>$1</h3>")
            .replace(/^## (.*$)/gim, "<h2>$1</h2>")
            .replace(/^# (.*$)/gim, "<h1>$1</h1>")
            // 굵은 글씨
            .replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>")
            // 글머리 기호
            .replace(/^\s*\*\s(.*$)/gim, "<li>$1</li>")
            .replace(/^\s*-\s(.*$)/gim, "<li>$1</li>")
            // 줄바꿈
            .replace(/\n\n/gim, "<p></p>")
            .replace(/\n/gim, "<br>");

        reportBox.innerHTML = html;
    }

    // ==========================================
    // 4.5. 💬 데이터 궁금증 Q&A 대화창 로직
    // ==========================================
    const chatSection = document.getElementById("chatSection");
    const chatMessages = document.getElementById("chatMessages");
    const chatInput = document.getElementById("chatInput");
    const btnSendQuestion = document.getElementById("btnSendQuestion");
    const chatLoading = document.getElementById("chatLoading");

    async function sendQuestion(text) {
        const question = text || chatInput.value.trim();
        if (!question) return;

        // 사용자 메시지 버블 추가
        appendChatMessage("user", question);
        chatInput.value = "";
        chatLoading.classList.remove("hidden");

        try {
            const res = await fetch("/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: question })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "답변을 불러오지 못했습니다.");
            }

            appendChatMessage("ai", data.answer);
        } catch (err) {
            console.error("[ERROR] /ask 호출 실패:", err.message);
            appendChatMessage("ai", `⚠️ 답변 생성 실패: ${err.message}`);
        } finally {
            chatLoading.classList.add("hidden");
        }
    }

    function appendChatMessage(sender, text) {
        const bubble = document.createElement("div");
        bubble.className = `chat-bubble ${sender}`;

        // 줄바꿈 보존 및 간단 변환
        bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    if (btnSendQuestion) {
        btnSendQuestion.addEventListener("click", () => sendQuestion());
    }

    if (chatInput) {
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                sendQuestion();
            }
        });
    }

    // 추천 질문 버튼 클릭 시 자동 질문
    document.querySelectorAll(".quick-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const q = btn.dataset.q;
            sendQuestion(q);
        });
    });


    // ==========================================
    // 5. 🍁 가을 단풍잎 모드 및 파티클 애니메이션
    // ==========================================
    const autumnToggle = document.getElementById("autumnToggle");
    const autumnCanvas = document.getElementById("autumnCanvas");
    let autumnAnimationId = null;
    let leaves = [];

    // 단풍잎 이모지 및 색상 종류
    const leafIcons = ["🍁", "🍂", "🍁", "🍂", "🍃"];

    function initLeaves() {
        leaves = [];
        const count = 40;
        const w = window.innerWidth;
        const h = window.innerHeight;

        for (let i = 0; i < count; i++) {
            leaves.push({
                x: Math.random() * w,
                y: Math.random() * h, // 처음 켤 때 화면 전체에 골고루 분산
                size: 18 + Math.random() * 18,
                speedY: 1.2 + Math.random() * 1.8,
                speedX: (Math.random() - 0.5) * 1.2,
                angle: Math.random() * 360,
                spinSpeed: (Math.random() - 0.5) * 2.5,
                swayAmplitude: 20 + Math.random() * 30,
                swaySpeed: 0.015 + Math.random() * 0.02,
                swayOffset: Math.random() * Math.PI * 2,
                icon: leafIcons[Math.floor(Math.random() * leafIcons.length)]
            });
        }
    }

    function renderLeaves() {
        if (!autumnCanvas || autumnCanvas.classList.contains("hidden")) {
            return;
        }

        const ctx = autumnCanvas.getContext("2d");
        const w = (autumnCanvas.width = window.innerWidth);
        const h = (autumnCanvas.height = window.innerHeight);

        ctx.clearRect(0, 0, w, h);

        leaves.forEach(leaf => {
            leaf.y += leaf.speedY;
            leaf.swayOffset += leaf.swaySpeed;
            leaf.x += leaf.speedX + Math.sin(leaf.swayOffset) * 0.9;
            leaf.angle += leaf.spinSpeed;

            // 바닥에 닿으면 다시 화면 위로 재배치
            if (leaf.y > h + 30) {
                leaf.y = -30;
                leaf.x = Math.random() * w;
            }
            if (leaf.x > w + 40) leaf.x = -30;
            if (leaf.x < -40) leaf.x = w + 30;

            ctx.save();
            ctx.translate(leaf.x, leaf.y);
            ctx.rotate((leaf.angle * Math.PI) / 180);
            ctx.font = `${leaf.size}px "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(leaf.icon, 0, 0);
            ctx.restore();
        });

        autumnAnimationId = requestAnimationFrame(renderLeaves);
    }

    if (autumnToggle && autumnCanvas) {
        autumnToggle.addEventListener("change", (e) => {
            const isAutumn = e.target.checked;
            document.body.classList.toggle("autumn-mode", isAutumn);

            if (isAutumn) {
                autumnCanvas.classList.remove("hidden");
                autumnCanvas.width = window.innerWidth;
                autumnCanvas.height = window.innerHeight;
                initLeaves();
                if (autumnAnimationId) cancelAnimationFrame(autumnAnimationId);
                autumnAnimationId = requestAnimationFrame(renderLeaves);
                console.log("[THEME] 🍁 가을 단풍잎 모드 활성화");
            } else {
                autumnCanvas.classList.add("hidden");
                if (autumnAnimationId) {
                    cancelAnimationFrame(autumnAnimationId);
                    autumnAnimationId = null;
                }
                const ctx = autumnCanvas.getContext("2d");
                ctx.clearRect(0, 0, autumnCanvas.width, autumnCanvas.height);
                console.log("[THEME] 🍂 가을 단풍잎 모드 비활성화");
            }
        });

        window.addEventListener("resize", () => {
            if (autumnCanvas && !autumnCanvas.classList.contains("hidden")) {
                autumnCanvas.width = window.innerWidth;
                autumnCanvas.height = window.innerHeight;
            }
        });
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});

