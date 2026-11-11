const $ = (id) => document.getElementById(id);
let activeGame = null;
let busy = false;
let draft = null;
let savedIdeaId = null;

async function api(path, data) {
  const response = await fetch(`/api${path}`, data === undefined ? {} : {
    method: "POST",
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
    button.textContent = game.title;
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
