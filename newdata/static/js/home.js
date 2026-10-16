let state = {
    q: "",
    model: "All",
    category: "All",
    type: "All",
    sort: "newest"
};

let prompts = [];
let trend = [];
let trendIndex = 0;
let trendTimer = null;


/* =========================================================
   HELPERS
========================================================= */

function escapeHtml(value) {
    return String(value ?? "").replace(
        /[&<>"']/g,
        function (m) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#039;"
            }[m];
        }
    );
}


function formatNumber(value) {
    const number = Number(value || 0);

    if (number >= 1000000) {
        return (number / 1000000).toFixed(1) + "M";
    }

    if (number >= 1000) {
        return (number / 1000).toFixed(1) + "K";
    }

    return number.toString();
}


/* =========================================================
   LOAD PROMPTS FROM BACKEND
========================================================= */

async function loadPrompts() {

    const gallery = document.getElementById("gallery");

    if (!gallery) {
        return;
    }


    gallery.innerHTML = `
        <div class="empty-wide">
            Loading prompts...
        </div>
    `;


    try {

        const params = new URLSearchParams();

        params.set("q", state.q);
        params.set("model", state.model);
        params.set("category", state.category);
        params.set("type", state.type);
        params.set("sort", state.sort);


        const response = await fetch(
            "/api/prompts?" + params.toString(),
            {
                method: "GET",
                headers: {
                    "Accept": "application/json"
                }
            }
        );


        if (!response.ok) {
            throw new Error(
                "API error: " + response.status
            );
        }


        const data = await response.json();


        if (!Array.isArray(data)) {
            throw new Error(
                "Invalid API response"
            );
        }


        prompts = data;

        renderGallery();


    } catch (error) {

        console.error(
            "Failed to load prompts:",
            error
        );


        gallery.innerHTML = `
            <div class="empty-wide">
                <h3>Unable to load prompts</h3>
                <p>
                    Please check your backend or MongoDB connection.
                </p>
            </div>
        `;


        const count =
            document.getElementById("resultCount");

        if (count) {
            count.textContent = "0";
        }

    }

}


/* =========================================================
   PROMPT CARD
========================================================= */

function card(p) {

    const badges =
        (p.is_new
            ? '<span class="card-badge new">NEW</span>'
            : "") +
        (p.hot
            ? '<span class="card-badge hot">HOT</span>'
            : "");


    const promptType =
        p.prompt_type || "image";


    const image =
        p.image || "";


    const title =
        p.title || "Untitled Prompt";


    const description =
        p.description || "";


    const model =
        p.model || "";


    const category =
        p.category || "";


    return `

    <article class="prompt-card">

        <a
            href="/prompt/${encodeURIComponent(p.id)}"
            class="card-image"
        >

            <img
                src="${escapeHtml(image)}"
                alt="${escapeHtml(title)}"
                loading="lazy"
                onerror="this.style.opacity='0.2'"
            >

            ${badges}

            <span class="model-chip">
                ${escapeHtml(model)}
            </span>

        </a>


        <div class="card-body">

            <div class="card-meta">

                <span>
                    ${escapeHtml(category)}
                </span>

                <span>
                    ${escapeHtml(promptType)}
                </span>

            </div>


            <a href="/prompt/${encodeURIComponent(p.id)}">

                <h3>
                    ${escapeHtml(title)}
                </h3>

            </a>


            <p>
                ${escapeHtml(description)}
            </p>


            <div class="card-foot">

                <span>
                    ❤️ ${formatNumber(p.likes)}
                </span>

                <span>
                    🔖 ${formatNumber(p.saves)}
                </span>

                <span>
                    📋 ${formatNumber(p.copies)}
                </span>


                <button
                    type="button"
                    onclick="copyFromCard(event, '${escapeHtml(p.id)}', this)"
                    title="Copy prompt"
                >
                    <i data-lucide="copy"></i>
                </button>

            </div>

        </div>

    </article>

    `;
}


/* =========================================================
   RENDER GALLERY
========================================================= */

function renderGallery() {

    const gallery =
        document.getElementById("gallery");


    if (!gallery) {
        return;
    }


    const resultCount =
        document.getElementById("resultCount");


    if (resultCount) {
        resultCount.textContent =
            prompts.length;
    }


    if (!prompts.length) {

        gallery.innerHTML = `
            <div class="empty-wide">
                <h3>No prompts found</h3>
                <p>
                    No prompts match your current filters.
                </p>
            </div>
        `;

        return;
    }


    gallery.innerHTML =
        prompts
            .map(card)
            .join("");


    if (
        typeof lucide !== "undefined" &&
        typeof lucide.createIcons === "function"
    ) {

        lucide.createIcons();

    }

}


/* =========================================================
   COPY PROMPT
========================================================= */

async function copyFromCard(event, id, button) {

    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }


    const prompt =
        prompts.find(function (item) {
            return String(item.id) === String(id);
        });


    if (!prompt) {
        return;
    }


    try {

        await navigator.clipboard.writeText(
            prompt.prompt || ""
        );


        await fetch(
            "/api/prompt/" +
            encodeURIComponent(id) +
            "/copy",
            {
                method: "POST"
            }
        );


        if (typeof toast === "function") {
            toast("Prompt copied!");
        }


        if (button) {

            button.classList.add("copied");

            setTimeout(function () {

                button.classList.remove("copied");

            }, 700);

        }


    } catch (error) {

        console.error(
            "Copy failed:",
            error
        );

    }

}


/* =========================================================
   LOAD TRENDING
========================================================= */

async function loadTrending() {

    const trendHero =
        document.getElementById("trendHero");


    /*
     * If trending section is not present,
     * this is probably prompts.html.
     */

    if (!trendHero) {
        return;
    }


    try {

        const response =
            await fetch("/api/trending");


        if (!response.ok) {
            throw new Error(
                "Trending API error"
            );
        }


        const data =
            await response.json();


        trend =
            Array.isArray(data)
                ? data
                : [];


        if (!trend.length) {
            return;
        }


        trendIndex = 0;


        const total =
            document.getElementById(
                "trendTotal"
            );


        if (total) {

            total.textContent =
                String(
                    Math.min(trend.length, 10)
                ).padStart(2, "0");

        }


        renderTrend();


        clearInterval(trendTimer);


        trendTimer = setInterval(
            function () {

                const max =
                    Math.min(
                        trend.length,
                        10
                    );


                trendIndex =
                    (trendIndex + 1) % max;


                renderTrend();

            },
            4500
        );


    } catch (error) {

        console.error(
            "Failed to load trending:",
            error
        );

    }

}


/* =========================================================
   RENDER TRENDING
========================================================= */

function renderTrend() {

    if (!trend.length) {
        return;
    }


    const max =
        Math.min(trend.length, 10);


    if (trendIndex >= max) {
        trendIndex = 0;
    }


    const p =
        trend[trendIndex];


    const trendNumber =
        document.getElementById(
            "trendNumber"
        );


    if (trendNumber) {

        trendNumber.textContent =
            String(
                trendIndex + 1
            ).padStart(2, "0");

    }


    const hero =
        document.getElementById(
            "trendHero"
        );


    if (hero) {

        hero.innerHTML = `

            <a
                href="/prompt/${encodeURIComponent(p.id)}"
                class="trend-main"
            >

                <img
                    src="${escapeHtml(p.image || "")}"
                    alt="${escapeHtml(p.title || "")}"
                >

                <div class="trend-overlay">

                    <span>
                        #${trendIndex + 1} TRENDING
                    </span>

                    <h3>
                        ${escapeHtml(p.title || "")}
                    </h3>

                    <p>
                        ${escapeHtml(
                            p.description || ""
                        )}
                    </p>

                    <div>

                        <b>
                            ❤️ ${formatNumber(p.likes)}
                        </b>

                        <b>
                            📋 ${formatNumber(p.copies)}
                        </b>

                        <b>
                            👁 ${formatNumber(p.views)}
                        </b>

                    </div>

                </div>

            </a>
        `;

    }


    const rail =
        document.getElementById(
            "trendRail"
        );


    if (rail) {

        rail.innerHTML =
            trend
                .slice(0, 10)
                .map(function (item, index) {

                    return `

                        <button
                            type="button"
                            class="${
                                index === trendIndex
                                    ? "active"
                                    : ""
                            }"
                            onclick="
                                trendIndex=${index};
                                renderTrend();
                                resetTrendTimer();
                            "
                        >

                            <img
                                src="${escapeHtml(
                                    item.image || ""
                                )}"
                                alt=""
                            >

                            <span>
                                #${index + 1}
                            </span>

                        </button>

                    `;

                })
                .join("");

    }


    if (
        typeof lucide !== "undefined" &&
        typeof lucide.createIcons === "function"
    ) {

        lucide.createIcons();

    }

}


/* =========================================================
   RESET TREND TIMER
========================================================= */

function resetTrendTimer() {

    clearInterval(trendTimer);


    if (!trend.length) {
        return;
    }


    const max =
        Math.min(trend.length, 10);


    trendTimer = setInterval(
        function () {

            trendIndex =
                (trendIndex + 1) % max;

            renderTrend();

        },
        4500
    );

}


/* =========================================================
   FILTERS
========================================================= */

function setupFilters() {

    document
        .querySelectorAll(".filter")
        .forEach(function (button) {

            button.addEventListener(
                "click",
                function () {

                    if (
                        this.dataset.model !== undefined
                    ) {

                        state.model =
                            this.dataset.model;


                        document
                            .querySelectorAll(
                                "[data-model]"
                            )
                            .forEach(function (item) {

                                item.classList.toggle(
                                    "active",
                                    item.dataset.model ===
                                    state.model
                                );

                            });

                    }


                    if (
                        this.dataset.category !== undefined
                    ) {

                        state.category =
                            this.dataset.category;


                        document
                            .querySelectorAll(
                                "[data-category]"
                            )
                            .forEach(function (item) {

                                item.classList.toggle(
                                    "active",
                                    item.dataset.category ===
                                    state.category
                                );

                            });

                    }


                    if (
                        this.dataset.type !== undefined
                    ) {

                        state.type =
                            this.dataset.type;


                        document
                            .querySelectorAll(
                                "[data-type]"
                            )
                            .forEach(function (item) {

                                item.classList.toggle(
                                    "active",
                                    item.dataset.type ===
                                    state.type
                                );

                            });

                    }


                    loadPrompts();

                }
            );

        });

}


/* =========================================================
   CATEGORY TILES
========================================================= */

function setupCategoryTiles() {

    document
        .querySelectorAll(".category-tile")
        .forEach(function (button) {

            button.addEventListener(
                "click",
                function () {

                    state.category =
                        this.dataset.category;


                    document
                        .querySelectorAll(
                            "[data-category]"
                        )
                        .forEach(function (item) {

                            item.classList.toggle(
                                "active",
                                item.dataset.category ===
                                state.category
                            );

                        });


                    const explore =
                        document.getElementById(
                            "explore"
                        );


                    if (explore) {

                        explore.scrollIntoView({
                            behavior: "smooth"
                        });

                    }


                    loadPrompts();

                }
            );

        });

}


/* =========================================================
   POPULAR SEARCH
========================================================= */

function setupPopularSearch() {

    document
        .querySelectorAll("[data-search]")
        .forEach(function (button) {

            button.addEventListener(
                "click",
                function () {

                    const input =
                        document.getElementById(
                            "searchInput"
                        );


                    const value =
                        this.dataset.search || "";


                    if (input) {
                        input.value = value;
                    }


                    state.q = value;


                    loadPrompts();


                    const explore =
                        document.getElementById(
                            "explore"
                        );


                    if (explore) {

                        explore.scrollIntoView({
                            behavior: "smooth"
                        });

                    }

                }
            );

        });

}


/* =========================================================
   SEARCH FORM
========================================================= */

function setupSearch() {

    const form =
        document.getElementById(
            "searchForm"
        );


    if (!form) {
        return;
    }


    form.addEventListener(
        "submit",
        function (event) {

            event.preventDefault();


            const input =
                document.getElementById(
                    "searchInput"
                );


            state.q =
                input
                    ? input.value.trim()
                    : "";


            loadPrompts();

        }
    );

}


/* =========================================================
   SORT
========================================================= */

function setupSort() {

    const select =
        document.getElementById(
            "sortSelect"
        );


    if (!select) {
        return;
    }


    select.addEventListener(
        "change",
        function () {

            state.sort =
                this.value;


            loadPrompts();

        }
    );

}


/* =========================================================
   TREND BUTTONS
========================================================= */

function setupTrendButtons() {

    const previous =
        document.getElementById(
            "trendPrev"
        );


    const next =
        document.getElementById(
            "trendNext"
        );


    if (previous) {

        previous.addEventListener(
            "click",
            function () {

                if (!trend.length) {
                    return;
                }


                const max =
                    Math.min(
                        trend.length,
                        10
                    );


                trendIndex =
                    (
                        trendIndex - 1 + max
                    ) % max;


                renderTrend();

                resetTrendTimer();

            }
        );

    }


    if (next) {

        next.addEventListener(
            "click",
            function () {

                if (!trend.length) {
                    return;
                }


                const max =
                    Math.min(
                        trend.length,
                        10
                    );


                trendIndex =
                    (
                        trendIndex + 1
                    ) % max;


                renderTrend();

                resetTrendTimer();

            }
        );

    }

}


/* =========================================================
   CLEAR FILTERS
========================================================= */

function setupClearFilters() {

    const button =
        document.getElementById(
            "clearFilters"
        );


    if (!button) {
        return;
    }


    button.addEventListener(
        "click",
        function () {

            state.q = "";
            state.model = "All";
            state.category = "All";
            state.type = "All";
            state.sort = "newest";


            const input =
                document.getElementById(
                    "searchInput"
                );


            if (input) {
                input.value = "";
            }


            const sort =
                document.getElementById(
                    "sortSelect"
                );


            if (sort) {
                sort.value = "newest";
            }


            document
                .querySelectorAll(".filter")
                .forEach(function (item) {

                    item.classList.remove(
                        "active"
                    );

                });


            document
                .querySelector(
                    '[data-model="All"]'
                )
                ?.classList.add("active");


            document
                .querySelector(
                    '[data-type="All"]'
                )
                ?.classList.add("active");


            document
                .querySelector(
                    '[data-category="All"]'
                )
                ?.classList.add("active");


            loadPrompts();

        }
    );

}


/* =========================================================
   INITIALIZE
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    function () {

        setupFilters();

        setupCategoryTiles();

        setupPopularSearch();

        setupSearch();

        setupSort();

        setupTrendButtons();

        setupClearFilters();


        /*
         * Works on both:
         *
         * index.html
         * prompts.html
         *
         */

        loadPrompts();

        loadTrending();

    }
);