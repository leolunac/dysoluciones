(function () {
  "use strict";
  const root = document.getElementById("lector-qr");
  if (!root) return;
  const video = document.getElementById("video-qr");
  const canvas = document.getElementById("lienzo-qr");
  const context = canvas.getContext("2d", { willReadFrequently: true });
  const estado = document.getElementById("estado-lector");
  const iniciar = document.getElementById("activar-camara");
  const detener = document.getElementById("detener-camara");
  const foto = document.getElementById("foto-qr");
  let stream = null;
  let sesion = 0;
  let timer = null;

  function parar() {
    sesion += 1;
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
    stream = null;
    video.srcObject = null;
    video.hidden = true;
    detener.hidden = true;
    iniciar.disabled = false;
  }

  function leer(imagen, ancho, alto) {
    const escala = Math.min(1, 1200 / Math.max(ancho, alto));
    canvas.width = Math.max(1, Math.round(ancho * escala));
    canvas.height = Math.max(1, Math.round(alto * escala));
    context.drawImage(imagen, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    return window.jsQR(pixels.data, pixels.width, pixels.height, { inversionAttempts: "dontInvert" });
  }

  function consultar(resultado) {
    const codigo = String(resultado.data || "").trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9._-]{0,39}$/.test(codigo)) {
      estado.textContent = "Ese QR no contiene un código interno de accesorio. Use la etiqueta de SIGOB o escriba el código.";
      return false;
    }
    parar();
    estado.textContent = "Código " + codigo + " leído. Consultando existencia...";
    const url = new URL(root.dataset.consulta, window.location.origin);
    url.searchParams.set("codigo", codigo);
    window.location.assign(url.href);
    return true;
  }

  function cuadro(ticket) {
    if (ticket !== sesion || !stream) return;
    if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
      try {
        const resultado = leer(video, video.videoWidth, video.videoHeight);
        if (resultado && consultar(resultado)) return;
      } catch (_) {
        parar();
        estado.textContent = "No se pudo procesar la cámara. Pruebe con una foto del QR o escriba el código.";
        return;
      }
    }
    timer = window.setTimeout(function () { cuadro(ticket); }, 200);
  }

  iniciar.addEventListener("click", async function () {
    parar();
    if (typeof window.jsQR !== "function" || !context) {
      estado.textContent = "No se cargó el lector. Recargue la página o escriba el código del accesorio.";
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      estado.textContent = "La cámara en vivo requiere conexión HTTPS y un navegador compatible. Puede leer una foto o escribir el código.";
      return;
    }
    const ticket = ++sesion;
    iniciar.disabled = true;
    detener.hidden = false;
    estado.textContent = "Solicitando permiso para la cámara...";
    try {
      const nueva = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (ticket !== sesion) {
        nueva.getTracks().forEach(function (track) { track.stop(); });
        return;
      }
      stream = nueva;
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
      if (ticket !== sesion) return;
      estado.textContent = "Apunte al QR completo, con buena luz y sin reflejos.";
      cuadro(ticket);
    } catch (_) {
      if (ticket !== sesion) return;
      parar();
      estado.textContent = "No se pudo abrir la cámara. Revise el permiso o elija una foto del QR. También puede escribir el código.";
    }
  });

  detener.addEventListener("click", function () {
    parar();
    estado.textContent = "Cámara detenida. Puede volver a abrirla o escribir el código.";
  });

  foto.addEventListener("change", async function () {
    parar();
    const archivo = foto.files && foto.files[0];
    if (!archivo) return;
    if (!/^(image\/jpeg|image\/png|image\/webp)$/.test(archivo.type) || archivo.size > 15 * 1024 * 1024) {
      estado.textContent = "Elija una foto JPG, PNG o WebP de hasta 15 MB.";
      foto.value = "";
      return;
    }
    if (typeof window.jsQR !== "function" || !context) {
      estado.textContent = "No se cargó el lector. Recargue o escriba el código del accesorio.";
      return;
    }
    const ticket = ++sesion;
    const direccion = URL.createObjectURL(archivo);
    estado.textContent = "Leyendo la foto en su dispositivo...";
    try {
      const imagen = new Image();
      await new Promise(function (resolve, reject) { imagen.onload = resolve; imagen.onerror = reject; imagen.src = direccion; });
      if (ticket !== sesion) return;
      const resultado = leer(imagen, imagen.naturalWidth, imagen.naturalHeight);
      if (resultado) consultar(resultado);
      else estado.textContent = "No se encontró un QR legible. Tome una foto más cercana o escriba el código.";
    } catch (_) {
      if (ticket === sesion) estado.textContent = "No se pudo leer esta foto. Pruebe otra o escriba el código.";
    } finally {
      URL.revokeObjectURL(direccion);
      foto.value = "";
    }
  });

  window.addEventListener("pagehide", parar);
  document.addEventListener("visibilitychange", function () { if (document.hidden) parar(); });
}());
