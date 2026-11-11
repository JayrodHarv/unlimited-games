const $ = (id) => document.getElementById(id);
let activeGame = null;
let busy = false;
let draft = null;
let savedIdeaId = null;

async function api(path, data, method = "POST") {
  const response = await fetch(`/api${path}`, data === undefined && method === "POST" ? {} : {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed.");
  return result;
}

async function perform(task) {
  if (busy) return;
  busy = true;
  $("message").textContent = "";
  document.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  try { await task(); }
  catch (error) { $("message").textContent = error.message; }
  finally {
    busy = false;
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }
}

function renderGame(game) {
  activeGame = game;
  $("review").hidden = true;
  $("empty").hidden = true;
  $("active-game").hidden = false;
  $("game-title").textContent = game.title;
  $("game-controls").replaceChildren(...managementButtons("game", game));
  $("game-rules").textContent = game.rules;
  $("player").replaceChildren(...game.players.map((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    return option;
  }));
  $("moves").replaceChildren(...game.moves.map((move) => {
    const item = document.createElement("li");
    const heading = document.createElement("strong");
    heading.textContent = move.player;
    const text = document.createElement("p");
    text.className = "preserve";
    text.textContent = move.action;
    item.append(heading, text);
    return item;
  }));
  // The player remains manually selectable; this starter imposes no turn rules.
  localStorage.setItem("activeGameId", String(game.id));
}

async function loadGames() {
  const result = await api("/games");
  $("games").replaceChildren(...result.games.map((game) => {
    const button = document.createElement("button");
    button.textContent = `${game.title} · Session #${game.id}`;
    button.disabled = busy;
    button.addEventListener("click", () => perform(async () => renderGame(await api(`/games/${game.id}`))));
    return button;
  }));
  if (!result.games.length) $("games").textContent = "No saved games yet.";
  return result.games;
}

const ideaFields = {premise: "Premise", objective: "Objective", setup: "Setup", turns: "Each turn", rules: "Rules & resolution", ending: "How it ends"};

function renderIdea(idea, id = null) {
  draft = idea;
  savedIdeaId = id;
  $("empty").hidden = true;
  $("active-game").hidden = true;
  $("review").hidden = false;
  $("idea-title").textContent = idea.title;
  $("idea-controls").replaceChildren(...(id ? managementButtons("idea", {id, idea}) : []));
  $("review-status").textContent = id ? "SAVED GAME IDEA" : "2. REVIEW YOUR IDEA";
  $("idea-details").replaceChildren(...Object.entries(ideaFields).map(([key, label]) => {
    const section = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = label;
    const text = document.createElement("p");
    text.className = "preserve";
    text.textContent = idea[key];
    section.append(heading, text);
    return section;
  }));
  $("save-idea").hidden = Boolean(id);
  $("start-form").hidden = !id;
}

async function loadIdeas() {
  const result = await api("/ideas");
  $("ideas").replaceChildren(...result.ideas.map((saved) => {
    const button = document.createElement("button");
    button.textContent = saved.idea.title;
    button.disabled = busy;
    button.addEventListener("click", () => renderIdea(saved.idea, saved.id));
    return button;
  }));
  if (!result.ideas.length) $("ideas").textContent = "No saved ideas yet.";
}

let editing = null;

function managementButtons(kind, item) {
  const edit = document.createElement("button");
  edit.textContent = "Edit";
  edit.addEventListener("click", () => openEditor(kind, item));
  const remove = document.createElement("button");
  remove.textContent = "Delete";
  remove.className = "danger";
  remove.addEventListener("click", () => {
    const warning = kind === "idea"
      ? "Delete this saved game idea? Existing play sessions will be kept."
      : "Delete this play session and its entire move history? This cannot be undone.";
    if (!window.confirm(warning)) return;
    perform(async () => {
      await api(`/${kind === "idea" ? "ideas" : "games"}/${item.id}`, undefined, "DELETE");
      if (kind === "game") {
        activeGame = null;
        localStorage.removeItem("activeGameId");
      } else {
        draft = null;
        savedIdeaId = null;
      }
      $("review").hidden = true;
      $("active-game").hidden = true;
      $("empty").hidden = false;
      await loadIdeas();
      await loadGames();
      $("message").textContent = kind === "idea" ? "Game idea deleted. Existing sessions are still available." : "Play session deleted.";
    });
  });
  return [edit, remove];
}

function openEditor(kind, item) {
  editing = {kind, item};
  $("edit-error").textContent = "";
  $("edit-heading").textContent = kind === "idea" ? "Edit saved game idea" : "Edit play session";
  $("edit-note").textContent = kind === "idea"
    ? "Changes apply to future sessions. Existing sessions keep their own rules."
    : "Edit the title, rules, or players (one per line). Keep any players who have already recorded moves.";
  const values = kind === "idea" ? item.idea : {title: item.title, rules: item.rules, players: item.players.join("\n")};
  $("edit-fields").replaceChildren(...Object.entries(values).map(([key, value]) => {
    const wrapper = document.createElement("div");
    const label = document.createElement("label");
    label.htmlFor = `edit-${key}`;
    label.textContent = key === "title" ? "Title" : key === "players" ? "Players" : ideaFields[key];
    const input = document.createElement(key === "title" ? "input" : "textarea");
    input.id = `edit-${key}`;
    input.name = key;
    input.value = value;
    input.required = true;
    if (key !== "players") input.maxLength = key === "title" ? 120 : kind === "idea" ? 1200 : 10000;
    if (key !== "title") input.rows = 4;
    wrapper.append(label, input);
    return wrapper;
  }));
  $("edit-dialog").showModal();
}

$("cancel-edit").addEventListener("click", () => $("edit-dialog").close());
$("edit-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    const {kind, item} = editing;
    const values = Object.fromEntries(new FormData($("edit-form")));
    if (kind === "game") values.players = values.players.split("\n").map((name) => name.trim()).filter(Boolean);
    try {
      const result = await api(`/${kind === "idea" ? "ideas" : "games"}/${item.id}`,
        kind === "idea" ? {idea: values} : values, "PUT");
      if (kind === "idea") renderIdea(result.idea, result.id);
      else renderGame(result);
      $("edit-dialog").close();
      await loadIdeas();
      await loadGames();
      $("message").textContent = "Changes saved.";
    } catch (error) {
      $("edit-error").textContent = error.message;
    }
  });
});

$("create-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    $("message").textContent = "Developing your game idea…";
    const result = await api("/ideas/draft", {
      prompt: $("prompt").value, genre: $("genre").value, complexity: $("complexity").value,
    });
    renderIdea(result.idea);
    $("revision").value = "";
    $("message").textContent = "Review your idea below. Request changes or approve it when ready.";
  });
});

$("revision-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    $("message").textContent = "Revising your game idea…";
    const result = await api("/ideas/draft", {prompt: $("revision").value, idea: draft});
    renderIdea(result.idea);
    $("revision").value = "";
    $("message").textContent = "Updated idea ready for review.";
  });
});

$("save-idea").addEventListener("click", () => perform(async () => {
  const result = await api("/ideas", {idea: draft});
  renderIdea(result.idea, result.id);
  await loadIdeas();
  $("message").textContent = "Idea saved. Add players to start a new session.";
}));

$("start-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    const game = await api(`/ideas/${savedIdeaId}/instances`, {
      players: $("players").value.split("\n").map((name) => name.trim()).filter(Boolean),
    });
    renderGame(game);
    await loadGames();
  });
});

$("move-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    const player = $("player").value;
    renderGame(await api(`/games/${activeGame.id}/moves`, {
      player, action: $("action").value,
    }));
    $("player").value = player;
    $("action").value = "";
  });
});

perform(async () => {
  await loadIdeas();
  const games = await loadGames();
  const saved = localStorage.getItem("activeGameId");
  if (games.some((game) => String(game.id) === saved)) renderGame(await api(`/games/${saved}`));
});
