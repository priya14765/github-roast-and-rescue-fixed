// Front-end logic. All text is inserted with textContent, so nothing from GitHub can inject HTML.
(function () {
  "use strict";

  var USERNAME_RE = /^(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/;
  var SAMPLE_RE = /^sample_(strong|messy|empty)$/;

  var $ = function (id) { return document.getElementById(id); };
  var form = $("form"), input = $("username"), errorBox = $("username-error"), statusBox = $("status");
  var submit = $("submit"), results = $("results");
  var currentReport = null;
  var fixProgressKey = "";
  var fixProgressStorageError = false;

  // Build an element: el("a", {href: "..."}, "text")
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  // Only link to github.com, even if the data were ever tampered with.
  function safeLink(url, text) {
    if (typeof url === "string" && url.indexOf("https://github.com/") === 0) {
      return el("a", { href: url, rel: "noopener noreferrer" }, text);
    }
    return el("span", {}, text);
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function copyText(text, callback) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { callback(true); }, function () { callback(false); });
      return;
    }

    var area = el("textarea", { "aria-hidden": "true", tabindex: "-1" });
    area.value = text;
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    var copied = false;
    try { copied = document.execCommand("copy"); } catch (e) { copied = false; }
    document.body.removeChild(area);
    callback(copied);
  }

  function normaliseUsername(raw) {
    var value = raw.trim().replace(/^https?:\/\/(www\.)?github\.com\//i, "").replace(/^@/, "");
    return value.split(/[\/?#]/)[0];
  }

  function validate(raw) {
    var name = normaliseUsername(raw);
    if (!name) { return { error: "Enter a GitHub username." }; }
    if (!SAMPLE_RE.test(name) && !USERNAME_RE.test(name)) {
      return { error: "Usernames use letters, numbers and single hyphens only, up to 39 characters." };
    }
    return { name: name };
  }

  function renderScore(data) {
    var body = $("score-body");
    clear(body);
    if (data.mode === "starter") {
      body.appendChild(el("p", { "class": "score-line" }, "Not enough public work to score fairly."));
      return;
    }
    var line = el("p", { "class": "score-line" });
    line.appendChild(el("span", { "class": "score-number" }, String(data.score)));
    line.appendChild(el("span", {}, "out of 100"));
    line.appendChild(el("span", { "class": "score-grade" }, "Grade " + data.grade + ": " + data.grade_label));
    body.appendChild(line);
    var list = el("ul", { "class": "breakdown" });
    data.breakdown.forEach(function (part) {
      var item = el("li");
      var label = part.name + ": " + part.earned + " of " + part.max;
      item.appendChild(el("span", {}, label));
      var meter = el("meter", { min: "0", max: String(part.max), value: String(part.earned), "aria-label": label });
      item.appendChild(el("br"));
      item.appendChild(meter);
      list.appendChild(item);
    });
    body.appendChild(list);
    if (data.activity_months && data.activity_months.length) {
      var months = data.activity_months.map(function (m) { return m.month + " (" + m.commits + ")"; });
      body.appendChild(el("p", { "class": "help" }, "Commits seen per month in the sample: " + months.join(", ") + "."));
    }
  }

  function evidenceList(items) {
    var wrap = el("p", { "class": "evidence" });
    items.forEach(function (ev, index) {
      if (index) { wrap.appendChild(document.createTextNode(" | ")); }
      wrap.appendChild(safeLink(ev.url, ev.label));
      wrap.appendChild(document.createTextNode(": " + ev.detail));
    });
    return wrap;
  }

  function renderFixes(fixes) {
    var list = $("fixes");
    clear(list);
    var progress = $("fix-progress");
    progress.hidden = fixes.length === 0;
    fixProgressKey = currentReport
      ? "github-roast-rescue:fix-progress:" + currentReport.username.toLowerCase()
      : "";
    fixProgressStorageError = false;
    var activeFixIds = fixes.map(fixProgressId);
    var completed = loadCompletedFixes().filter(function (key) {
      return activeFixIds.indexOf(key) !== -1;
    });
    $("reset-fix-progress").disabled = completed.length === 0;
    $("score-impact-planner").hidden = currentReport.mode !== "scored" || fixes.length === 0;
    if (!fixes.length) {
      list.appendChild(el("li", {}, "No fixes needed: none of the checks found a problem in the repositories analysed."));
    }
    fixes.forEach(function (fix) {
      var item = el("li");
      var progressLabel = el("label", { "class": "fix-completion" });
      var progressCheckbox = el("input", {
        type: "checkbox",
        "class": "fix-progress-toggle",
        "aria-label": "Mark " + fix.title + " complete"
      });
      progressCheckbox.setAttribute("data-fix-key", fixProgressId(fix));
      progressCheckbox.checked = completed.indexOf(fixProgressId(fix)) !== -1;
      progressCheckbox.addEventListener("change", saveFixProgress);
      progressLabel.appendChild(progressCheckbox);
      progressLabel.appendChild(document.createTextNode(" Mark complete"));
      item.appendChild(progressLabel);

      var selectLabel = el("label", { "class": "fix-select" });
      var select = el("input", {
        type: "checkbox",
        "class": "fix-impact-toggle",
        "data-points": String(fix.points || 0),
        "aria-label": "Include " + fix.title + " in score estimate"
      });
      select.addEventListener("change", updateScoreProjection);
      selectLabel.appendChild(select);
      selectLabel.appendChild(document.createTextNode(" Plan to fix"));
      item.appendChild(selectLabel);
      item.appendChild(el("strong", {}, fix.title));
      if (fix.why) { item.appendChild(el("span", { "class": "tag" }, " (" + fix.why + ")")); }
      if (fix.how) { item.appendChild(el("p", {}, fix.how)); }
      item.appendChild(evidenceList(fix.evidence || []));
      list.appendChild(item);
    });
    updateFixProgress();
    if (currentReport.score !== null && currentReport.score !== undefined) {
      updateScoreProjection();
    }
  }

  function fixProgressId(fix) {
    var evidenceUrls = (fix.evidence || []).map(function (item) { return item.url; }).sort();
    return JSON.stringify([fix.title, evidenceUrls]);
  }

  function loadCompletedFixes() {
    if (!fixProgressKey) { return []; }
    try {
      var saved = window.localStorage.getItem(fixProgressKey);
      if (!saved) { return []; }
      var parsed = JSON.parse(saved);
      if (!Array.isArray(parsed) || !parsed.every(function (item) { return typeof item === "string"; })) {
        throw new Error("Saved fix progress has an invalid format.");
      }
      return parsed;
    } catch (error) {
      fixProgressStorageError = true;
      return [];
    }
  }

  function saveFixProgress() {
    var completed = Array.prototype.slice.call(
      document.querySelectorAll(".fix-progress-toggle:checked")
    ).map(function (checkbox) {
      return checkbox.getAttribute("data-fix-key");
    });
    try {
      window.localStorage.setItem(fixProgressKey, JSON.stringify(completed));
    } catch (error) {
      fixProgressStorageError = true;
    }
    updateFixProgress();
  }

  function updateFixProgress() {
    var toggles = Array.prototype.slice.call(document.querySelectorAll(".fix-progress-toggle"));
    var completed = toggles.filter(function (checkbox) { return checkbox.checked; }).length;
    var meter = $("fix-progress-meter");
    meter.max = String(Math.max(toggles.length, 1));
    meter.value = String(completed);
    $("fix-progress-status").textContent = fixProgressStorageError
      ? completed + " of " + toggles.length + " priority fixes complete. Progress could not be saved in this browser."
      : completed + " of " + toggles.length + " priority fixes complete.";
    $("reset-fix-progress").disabled = completed === 0;
  }

  function resetFixProgress() {
    document.querySelectorAll(".fix-progress-toggle").forEach(function (checkbox) {
      checkbox.checked = false;
    });
    fixProgressStorageError = false;
    try {
      window.localStorage.removeItem(fixProgressKey);
    } catch (error) {
      fixProgressStorageError = true;
    }
    updateFixProgress();
  }

  function selectedScoreProjection(data) {
    var selected = Array.prototype.slice.call(
      document.querySelectorAll(".fix-impact-toggle:checked")
    );
    var points = selected.reduce(function (total, checkbox) {
      return total + Number(checkbox.getAttribute("data-points"));
    }, 0);
    var gain = Math.min(Math.max(100 - data.score, 0), points);
    gain = Math.round(gain * 10) / 10;
    return {
      selected: selected,
      gain: gain,
      score: Math.min(100, Math.round(data.score + gain))
    };
  }

  function updateScoreProjection() {
    if (!currentReport || currentReport.score === null || currentReport.score === undefined) { return; }
    var projection = selectedScoreProjection(currentReport);
    $("projected-score").textContent = projection.score + " / 100";
    $("projected-gain").textContent = projection.gain > 0
      ? "(+" + projection.gain.toFixed(1) + " estimated points)"
      : "(select fixes to preview)";
    $("score-impact-meter").value = String(projection.score);
    $("impact-status").textContent = projection.selected.length
      ? projection.selected.length + " fix" + (projection.selected.length === 1 ? "" : "es") + " selected."
      : "Your current score is the baseline; nothing is selected yet.";
  }

  function renderDescriptions(items) {
    var block = $("descriptions-block"), list = $("descriptions");
    clear(list);
    block.hidden = items.length === 0;
    items.forEach(function (d) {
      var item = el("li");
      item.appendChild(safeLink(d.url, d.repo));
      item.appendChild(el("p", {}, d.suggested));
      if (!d.grounded) {
        item.appendChild(el("p", { "class": "evidence" }, "No README text to base this on, so fill in the TODO yourself."));
      }
      list.appendChild(item);
    });
  }

  function renderFinish(items) {
    var block = $("finish-block"), list = $("finish");
    clear(list);
    block.hidden = items.length === 0;
    items.forEach(function (p) {
      var item = el("li");
      item.appendChild(safeLink(p.url, p.repo));
      item.appendChild(el("p", {}, p.why));
      list.appendChild(item);
    });
  }

  function renderStrengths(items) {
    var block = $("strengths-block"), list = $("strengths");
    clear(list);
    block.hidden = items.length === 0;
    items.forEach(function (s) {
      var item = el("li");
      item.appendChild(safeLink(s.url, s.text));
      list.appendChild(item);
    });
  }

  function renderPortfolio(portfolio) {
    $("portfolio-repo-count").textContent = String(portfolio.analyzed_repos);
    $("portfolio-total-stars").textContent = String(portfolio.total_stars);

    var languages = $("portfolio-languages");
    clear(languages);
    if (portfolio.languages.length) {
      portfolio.languages.forEach(function (language) {
        var item = el("li");
        var label = language.name + ": " + language.repositories + " repositories";
        item.appendChild(el("span", {}, label));
        item.appendChild(el("meter", {
          min: "0",
          max: String(Math.max(portfolio.analyzed_repos, 1)),
          value: String(language.repositories),
          "aria-label": label
        }));
        languages.appendChild(item);
      });
    } else {
      languages.appendChild(el("li", {}, "No language data was reported for these repositories."));
    }

    var repositories = $("portfolio-top-repositories");
    clear(repositories);
    if (portfolio.top_repositories.length) {
      portfolio.top_repositories.forEach(function (repo) {
        var item = el("li");
        item.appendChild(safeLink(repo.url, repo.name));
        item.appendChild(document.createTextNode(" — " + repo.stars + (repo.stars === 1 ? " star" : " stars")));
        repositories.appendChild(item);
      });
    } else {
      repositories.appendChild(el("li", {}, "No stars on the analyzed repositories yet."));
    }
  }

  function renderRepositoryHealth(repositories) {
    var container = $("repository-health");
    clear(container);
    if (!repositories.length) {
      container.appendChild(el("p", {}, "No repositories were analyzed in depth."));
      return;
    }

    repositories.forEach(function (repo) {
      var card = el("article", { "class": "health-card" });
      var heading = el("h3");
      heading.appendChild(safeLink(repo.url, repo.name));
      card.appendChild(heading);
      card.appendChild(el("p", { "class": "health-status" }, repo.status));

      var details = [];
      if (repo.language) { details.push(repo.language); }
      details.push(repo.stars + (repo.stars === 1 ? " star" : " stars"));
      details.push(repo.last_push ? "Last push " + repo.last_push : "Last push date unavailable");
      card.appendChild(el("p", { "class": "help" }, details.join(" · ")));

      if (repo.issues.length) {
        var issueList = el("ul");
        repo.issues.forEach(function (issue) {
          var item = el("li");
          item.appendChild(el("strong", {}, issue.title));
          item.appendChild(el("p", {}, issue.detail));
          issueList.appendChild(item);
        });
        card.appendChild(issueList);
      } else if (repo.status === "Not scored") {
        card.appendChild(el("p", { "class": "help" }, "There is not enough public work to score this profile fairly."));
      } else {
        card.appendChild(el("p", { "class": "help" }, "No issues were detected by the checks run."));
      }
      container.appendChild(card);
    });
  }

  function renderActionPlan(plan) {
    $("action-plan-message").textContent = plan.message;
    var list = $("action-plan");
    clear(list);
    plan.days.forEach(function (day) {
      var item = el("li", { "class": "action-day" });
      item.appendChild(el("span", { "class": "action-day-label" }, "Day " + day.day));
      item.appendChild(el("strong", {}, day.title));
      if (day.how) { item.appendChild(el("p", {}, day.how)); }
      if (day.evidence && day.evidence.length) {
        item.appendChild(evidenceList(day.evidence));
      }
      list.appendChild(item);
    });
  }

  function reportSummary(data) {
    var lines = [
      "GitHub Roast & Rescue report for " + data.username,
      data.profile.url,
      data.mode === "starter"
        ? "Score: Not scored — not enough public work to score fairly."
        : "Score: " + data.score + "/100 (" + data.grade + ": " + data.grade_label + ")",
      "Repositories analyzed: " + data.portfolio.analyzed_repos + " of " + data.profile.public_repos + " public repositories",
      "Stars across analyzed repositories: " + data.portfolio.total_stars,
      "Languages: " + (data.portfolio.languages.map(function (item) {
        return item.name + " (" + item.repositories + ")";
      }).join(", ") || "No language data available."),
      "",
      "ROAST",
      data.roast,
      "",
      "PRIORITY FIXES"
    ];

    if (data.score !== null && data.score !== undefined) {
      var projection = selectedScoreProjection(data);
      lines.push(
        "Score impact preview: " + projection.score + "/100 (+" + projection.gain.toFixed(1)
        + " estimated points; rough estimate, not guaranteed)."
      );
      if (projection.selected.length) {
        lines.push("Selected fixes: " + projection.selected.map(function (checkbox) {
          return checkbox.getAttribute("aria-label").replace(/^Include | in score estimate$/g, "");
        }).join(", "));
      } else {
        lines.push("Selected fixes: none.");
      }
    }

    if (data.rescue.fixes.length) {
      var doneCount = document.querySelectorAll(".fix-progress-toggle:checked").length;
      lines.push(
        "Fix progress: " + doneCount + " of " + data.rescue.fixes.length + " priority fixes completed."
      );
      data.rescue.fixes.forEach(function (fix, index) {
        lines.push((index + 1) + ". " + fix.title);
        if (fix.how) { lines.push("   " + fix.how); }
        (fix.evidence || []).forEach(function (evidence) {
          lines.push("   " + evidence.label + ": " + evidence.detail + " (" + evidence.url + ")");
        });
      });
    } else {
      lines.push("No priority fixes found by the checks run.");
    }

    lines.push("", "REPOSITORY HEALTH");
    if (data.repository_health.length) {
      data.repository_health.forEach(function (repo) {
        lines.push("- " + repo.name + " — " + repo.status + " (" + repo.url + ")");
        repo.issues.forEach(function (issue) { lines.push("  - " + issue.title + ": " + issue.detail); });
      });
    } else {
      lines.push("No repositories analyzed in depth.");
    }

    lines.push("", "7-DAY ACTION PLAN");
    if (data.action_plan.days.length) {
      data.action_plan.days.forEach(function (day) {
        lines.push("Day " + day.day + ": " + day.title);
      });
    } else {
      lines.push(data.action_plan.message);
    }
    lines.push("", "Generated from public GitHub data. Findings are limited to the repositories and checks shown.");
    return lines.join("\n");
  }

  function render(data) {
    currentReport = data;
    var meta = data.meta || {};
    var banner = $("sample-banner");
    banner.hidden = !meta.sample;
    banner.textContent = meta.sample ? "Sample data: this is a made-up profile for demo purposes, not a real GitHub account." : "";
    $("notes").textContent = (meta.notes || []).filter(function (n) { return n.indexOf("SAMPLE") === -1; }).join(" ");

    var avatar = $("avatar");
    if (data.profile.avatar_url && data.profile.avatar_url.indexOf("https://avatars.githubusercontent.com/") === 0) {
      avatar.src = data.profile.avatar_url;
      avatar.alt = "GitHub avatar of " + data.username;
      avatar.hidden = false;
    } else {
      avatar.hidden = true;
    }
    $("profile-line").textContent = data.username + (data.profile.name ? " (" + data.profile.name + ")" : "") +
      ": " + data.profile.public_repos + " public repositories, " + data.profile.followers + " followers";

    renderScore(data);
    renderPortfolio(data.portfolio);
    renderRepositoryHealth(data.repository_health);
    renderActionPlan(data.action_plan);
    $("roast-text").textContent = data.roast;
    renderFixes(data.rescue.fixes);
    $("readme-out").value = data.rescue.readme;
    renderDescriptions(data.rescue.repo_descriptions);
    renderFinish(data.rescue.finish_first);
    renderStrengths(data.strengths || []);
    results.hidden = false;
    $("score-heading").focus();           // move keyboard and screen-reader focus to the results
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-sample]"), function (button) {
    button.addEventListener("click", function () {
      input.value = button.getAttribute("data-sample");
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        submit.click();
      }
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    errorBox.textContent = "";
    var checked = validate(input.value);
    if (checked.error) {
      errorBox.textContent = checked.error;
      input.setAttribute("aria-invalid", "true");
      input.focus();
      return;
    }
    input.removeAttribute("aria-invalid");
    submit.disabled = true;
    results.hidden = true;
    statusBox.textContent = "Reading the profile. This can take up to 20 seconds.";
    fetch("/api/analyze?username=" + encodeURIComponent(checked.name))
      .then(function (response) {
        return response.json().then(function (body) { return { ok: response.ok, body: body }; });
      })
      .then(function (outcome) {
        if (!outcome.ok) { throw new Error(outcome.body.error || "Something went wrong."); }
        statusBox.textContent = "Done. Results are below.";
        render(outcome.body);
      })
      .catch(function (err) {
        statusBox.textContent = "";
        errorBox.textContent = err.message || "Could not reach the server. Please try again.";
        input.focus();
      })
      .then(function () { submit.disabled = false; });
  });

  $("copy").addEventListener("click", function () {
    var area = $("readme-out"), message = $("copy-status");
    function done(ok) { message.textContent = ok ? "Copied to clipboard." : "Copy failed. Select the text and copy it manually."; }
    copyText(area.value, done);
  });

  $("print-report").addEventListener("click", function () { window.print(); });
  $("copy-summary").addEventListener("click", function () {
    if (!currentReport) { return; }
    copyText(reportSummary(currentReport), function (ok) {
      $("summary-status").textContent = ok
        ? "Report summary copied."
        : "Copy failed. Try your browser's print or copy controls.";
    });
  });
  $("reset-fix-progress").addEventListener("click", resetFixProgress);
})();
