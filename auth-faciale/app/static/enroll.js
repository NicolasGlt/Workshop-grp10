// Enrôlement guidé, partagé par /setup et /admin. Le serveur pilote la caméra et la capture ;
// la page affiche le flux dès l'allumage, la consigne d'angle et le retour de détection, en
// interrogeant /api/enroll/state. Aperçu en miroir : « gauche » est la gauche de la personne.
(function () {
  const ARROWS = { face: "●", left: "←", right: "→", up: "↑", down: "↓" };
  const CSS = `
    .ge { margin-top: 14px; }
    .ge-cam { position: relative; width: 100%; max-width: 420px; aspect-ratio: 4 / 3; background: #000; border-radius: 8px;
              border: 3px solid var(--border, #ccc); overflow: hidden; display: flex; align-items: center; justify-content: center;
              color: #aaa; font-size: 14px; }
    .ge-cam img { width: 100%; height: 100%; object-fit: cover; transform: scaleX(-1); }
    .ge-cam.ok { border-color: var(--ok, green); } .ge-cam.ko { border-color: var(--ko, red); }
    .ge-arrow { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
                font-size: 72px; color: rgba(255,255,255,.75); text-shadow: 0 0 8px #000; pointer-events: none; }
    .ge-steps { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; font-size: 13px; }
    .ge-steps li { padding: 4px 8px; border: 1px solid var(--border, #ccc); border-radius: 999px; color: var(--muted, #777); }
    .ge-steps li.cur { border-color: var(--accent, #33f); color: var(--text, #000); font-weight: 600; }
    .ge-steps li.done { border-color: var(--ok, green); color: var(--ok, green); }
    .ge-instr { font-size: 18px; font-weight: 600; margin: 12px 0 4px; }
    .ge-hint { font-size: 15px; min-height: 20px; }
    .ge-checks { display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; margin-top: 6px; }
    .ge-checks .ok { color: var(--ok, green); } .ge-checks .ko { color: var(--ko, red); }
    .ge-meta { font-size: 12px; color: var(--muted, #777); margin-top: 4px; }
    .ge-actions { display: flex; gap: 8px; margin-top: 10px; }
    .ge-actions button { width: auto; margin: 0; }
  `;

  function addStyle() {
    if (document.getElementById("ge-style")) return;
    const s = document.createElement("style");
    s.id = "ge-style"; s.textContent = CSS;
    document.head.appendChild(s);
  }

  // start() lance l'enrôlement côté serveur et renvoie la Response de fetch.
  // onEnd(state) est appelé une fois, avec le dernier état (status done, failed ou cancelled).
  window.guidedEnroll = function (root, { start, onEnd }) {
    addStyle();
    root.innerHTML = `
      <div class="ge">
        <div class="ge-cam"><span class="ge-off">Allumage de la caméra…</span><img alt="Caméra" hidden><div class="ge-arrow"></div></div>
        <ul class="ge-steps"></ul>
        <div class="ge-instr"></div>
        <div class="ge-hint" role="status"></div>
        <div class="ge-checks"></div>
        <div class="ge-meta"></div>
        <div class="ge-actions"><button type="button" class="ge-cancel">Annuler</button><button type="button" class="ge-retry" hidden>Recommencer</button></div>
      </div>`;
    const q = (c) => root.querySelector(c);
    const img = q("img"), cam = q(".ge-cam");
    let poll = null, streaming = false;

    function stream(on) {
      if (on && !streaming) { img.src = "/camera/stream?t=" + Date.now(); img.hidden = false; q(".ge-off").hidden = true; streaming = true; }
      if (!on && streaming) { img.removeAttribute("src"); img.hidden = true; q(".ge-off").hidden = false; q(".ge-off").textContent = "Caméra éteinte"; streaming = false; }
    }

    function render(s) {
      stream(s.camera);
      const running = s.status === "running";
      q(".ge-steps").innerHTML = s.steps.map((st, i) =>
        `<li class="${st.done ? "done" : (running && i === s.step ? "cur" : "")}">${st.done ? "✓ " : ""}${st.label}</li>`).join("");
      const key = running ? s.steps[s.step].key : null;
      q(".ge-arrow").textContent = key ? ARROWS[key] : "";
      q(".ge-instr").textContent = running ? `${s.step + 1}/${s.steps.length} · ${s.instruction} (${Math.ceil(s.remaining)} s)` : "";
      const f = s.feedback;
      q(".ge-hint").textContent = running ? f.message : "";
      const check = (ok, label) => `<span class="${ok ? "ok" : "ko"}">${ok ? "✓" : "✗"} ${label}</span>`;
      q(".ge-checks").innerHTML = running ? check(f.face_ok, "visage détecté") + check(f.single, "un seul visage") + check(f.angle_ok, "angle atteint") : "";
      q(".ge-meta").textContent = running && f.yaw !== null ? `lacet ${f.yaw.toFixed(2)} · tangage ${f.pitch.toFixed(2)}` : "";
      cam.className = "ge-cam" + (running ? (f.angle_ok ? " ok" : (f.face_ok ? "" : " ko")) : "");
    }

    function finish(s) {
      clearInterval(poll); poll = null; stream(false);
      q(".ge-cancel").hidden = true;
      q(".ge-retry").hidden = s.status === "done";
      q(".ge-arrow").textContent = "";
      if (s.status === "done") { q(".ge-hint").textContent = `Visage enregistré : ${s.captured} angles.`; q(".ge-hint").className = "ge-hint ok"; }
      else { q(".ge-hint").textContent = s.status === "cancelled" ? "Enrôlement annulé." : `Échec : ${s.error}.`; q(".ge-hint").className = "ge-hint ko"; }
      onEnd(s);
    }

    async function run() {
      q(".ge-retry").hidden = true; q(".ge-cancel").hidden = false; q(".ge-hint").className = "ge-hint";
      q(".ge-hint").textContent = "Démarrage…";
      let r;
      try { r = await start(); } catch (e) { r = null; }
      if (!r || r.status !== 202) {
        let data = null; try { data = r && await r.json(); } catch (e) {}
        const why = r && r.status === 409 ? "poste occupé (connexion ou autre enrôlement en cours)" : ((data && (data.detail || data.status)) || "démarrage impossible");
        finish({ status: "failed", error: why, steps: [], captured: 0 });
        return;
      }
      poll = setInterval(async () => {
        let s;
        try { const res = await fetch("/api/enroll/state"); if (!res.ok) return; s = await res.json(); } catch (e) { return; }
        render(s);
        if (["done", "failed", "cancelled"].includes(s.status)) finish(s);
      }, 250);
    }

    q(".ge-cancel").addEventListener("click", () => fetch("/api/enroll/cancel", { method: "POST" }));
    q(".ge-retry").addEventListener("click", run);
    run();
  };
})();
