(function () {
  "use strict";
  var root = document.getElementById("scan-app");
  if (!root) return;
  var pid = root.getAttribute("data-pid");
  var csrf = root.getAttribute("data-csrf") || "";
  var video = document.getElementById("scan-video");
  var startBtn = document.getElementById("scan-start");
  var stopBtn = document.getElementById("scan-stop");
  var hint = document.getElementById("scan-hint");
  var form = document.getElementById("scan-manual");
  var input = document.getElementById("scan-input");
  var queueList = document.getElementById("scan-queue");
  var queueCount = document.getElementById("scan-queue-count");
  var logBox = document.getElementById("scan-log");
  var countBox = document.getElementById("scan-count");
  var storeKey = "sd-scan-queue-" + pid;
  var stream = null;
  var detector = null;
  var ticking = false;

  function loadQueue() {
    try {
      var raw = window.localStorage.getItem(storeKey);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function saveQueue(items) {
    try {
      window.localStorage.setItem(storeKey, JSON.stringify(items));
    } catch (e) {}
    renderQueue(items);
  }

  function renderQueue(items) {
    queueList.innerHTML = "";
    items.forEach(function (code) {
      var li = document.createElement("li");
      li.className = "list-group-item";
      li.textContent = code;
      queueList.appendChild(li);
    });
    queueCount.textContent = String(items.length);
  }

  function note(text, ok) {
    var div = document.createElement("div");
    div.className = ok ? "alert alert-success" : "alert alert-danger";
    div.textContent = text;
    logBox.prepend(div);
    while (logBox.children.length > 5) logBox.lastChild.remove();
  }

  function send(code) {
    return window
      .fetch("/popis/" + encodeURIComponent(pid) + "/found", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ asset_id: code }),
      })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { status: resp.status, data: data };
        });
      });
  }

  function submit(code) {
    code = (code || "").trim();
    if (!code) return;
    send(code).then(function (res) {
      if (res.status === 200 && res.data.ok) {
        countBox.textContent = res.data.found + "/" + res.data.total;
        note(code + " евидентиран.", true);
      } else {
        var items = loadQueue();
        if (items.indexOf(code) < 0) items.push(code);
        saveQueue(items);
        note(code + ": " + (res.data.error || "неуспешно, зачувано во ред."), false);
      }
    }).catch(function () {
      var items = loadQueue();
      if (items.indexOf(code) < 0) items.push(code);
      saveQueue(items);
      note(code + ": нема врска, зачувано во ред.", false);
    });
  }

  function flush() {
    var items = loadQueue();
    if (!items.length) return;
    var code = items[0];
    send(code).then(function (res) {
      if (res.status === 200 && res.data.ok) {
        countBox.textContent = res.data.found + "/" + res.data.total;
        saveQueue(loadQueue().filter(function (c) { return c !== code; }));
        flush();
      }
    }).catch(function () {});
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submit(input.value);
    input.value = "";
    input.focus();
  });

  function loop() {
    if (!ticking) return;
    if (detector && video.readyState === video.HAVE_ENOUGH_DATA) {
      detector.detect(video).then(function (codes) {
        if (codes && codes.length && codes[0].rawValue) submit(codes[0].rawValue);
        setTimeout(loop, 600);
      }).catch(function () {
        setTimeout(loop, 900);
      });
    } else {
      setTimeout(loop, 900);
    }
  }

  startBtn.addEventListener("click", function () {
    if (!window.navigator.mediaDevices || !window.navigator.mediaDevices.getUserMedia) {
      hint.textContent = "Камерата не е поддржана — користете рачен внес.";
      return;
    }
    window.navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
      .then(function (s) {
        stream = s;
        video.srcObject = s;
        video.play();
        startBtn.hidden = true;
        stopBtn.hidden = false;
        if ("BarcodeDetector" in window) {
          try {
            detector = new window.BarcodeDetector({ formats: ["qr_code", "code_128", "code_39", "ean_13"] });
          } catch (e) {
            detector = null;
          }
        }
        if (!detector) hint.textContent = "Скенирањето со камера не е поддржано — користете рачен внес.";
        ticking = true;
        loop();
      })
      .catch(function () {
        hint.textContent = "Камерата е недостапна — користете рачен внес.";
      });
  });

  function stop() {
    ticking = false;
    if (stream) {
      stream.getTracks().forEach(function (t) { t.stop(); });
      stream = null;
    }
    startBtn.hidden = false;
    stopBtn.hidden = true;
  }
  stopBtn.addEventListener("click", stop);
  window.addEventListener("online", flush);
  renderQueue(loadQueue());
  flush();
})();
