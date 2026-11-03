const $ = (id) => document.getElementById(id);
let activeGame = null;
let busy = false;

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

$("create-form").addEventListener("submit", (event) => {
  event.preventDefault();
  perform(async () => {
    const game = await api("/games", {
      title: $("title").value,
      rules: $("rules").value,
      players: $("players").value.split("\n").map((p) => p.trim()).filter(Boolean),
    });
    renderGame(game);
    $("create-form").reset();
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
  const games = await loadGames();
  const saved = localStorage.getItem("activeGameId");
  if (games.some((game) => String(game.id) === saved)) renderGame(await api(`/games/${saved}`));
});
