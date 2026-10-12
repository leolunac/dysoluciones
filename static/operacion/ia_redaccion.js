(function () {
    "use strict";

    const config = window.SIGOB_IA_REDACCION || {};
    if (!config.url) return;

    function csrfToken() {
        const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    function mostrarEstado(boton, mensaje, esError) {
        let estado = boton.parentElement.querySelector(".ia-redaccion-estado");
        if (!estado) {
            estado = document.createElement("div");
            estado.className = "ia-redaccion-estado";
            estado.setAttribute("role", "status");
            estado.style.marginTop = "8px";
            estado.style.fontSize = "12px";
            estado.style.fontWeight = "700";
            boton.parentElement.appendChild(estado);
        }
        estado.style.color = esError ? "#991b1b" : "#166534";
        estado.textContent = mensaje;
    }

    function camposDelBoton(boton) {
        const selectores = boton.dataset.iaSelectores;
        const raiz = boton.closest("form") || document;
        const elementos = selectores
            ? selectores.split(",").map(s => document.querySelector(s.trim())).filter(Boolean)
            : Array.from(raiz.querySelectorAll("textarea"));
        const campos = {};
        const referencias = {};
        elementos.forEach((elemento, indice) => {
            const valor = elemento.value.trim();
            if (!valor) return;
            const clave = (elemento.name || elemento.id || `campo_${indice}`).replace(/[^a-zA-Z0-9_-]/g, "_");
            campos[clave] = valor;
            referencias[clave] = elemento;
        });
        return {campos, referencias};
    }

    function mostrarVistaPrevia(originales, corregidos, referencias) {
        const fondo = document.createElement("div");
        fondo.style.cssText = "position:fixed;inset:0;background:#0008;z-index:9999;display:flex;align-items:center;justify-content:center;padding:18px;";
        const modal = document.createElement("div");
        modal.style.cssText = "background:white;border-radius:14px;max-width:900px;width:100%;max-height:90vh;overflow:auto;padding:22px;color:#17324d;";
        modal.innerHTML = "<h2 style='margin-top:0'>Vista previa de la corrección</h2><p>Revise la propuesta. La IA no enviará ni guardará el informe.</p>";

        Object.keys(corregidos).forEach(clave => {
            const bloque = document.createElement("div");
            bloque.style.cssText = "border:1px solid #dbe4ea;border-radius:10px;padding:12px;margin:12px 0;";
            bloque.innerHTML = `<strong>${clave.replaceAll("_", " ")}</strong>`;
            const grid = document.createElement("div");
            grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px;";
            const original = document.createElement("div");
            original.innerHTML = "<small>Original</small>";
            const originalTexto = document.createElement("div");
            originalTexto.textContent = originales[clave];
            originalTexto.style.cssText = "white-space:pre-wrap;background:#f8fafc;padding:10px;border-radius:7px;";
            original.appendChild(originalTexto);
            const propuesta = document.createElement("div");
            propuesta.innerHTML = "<small>Propuesta</small>";
            const propuestaTexto = document.createElement("div");
            propuestaTexto.textContent = corregidos[clave];
            propuestaTexto.style.cssText = "white-space:pre-wrap;background:#ecfdf5;padding:10px;border-radius:7px;";
            propuesta.appendChild(propuestaTexto);
            grid.append(original, propuesta);
            bloque.appendChild(grid);
            modal.appendChild(bloque);
        });

        const acciones = document.createElement("div");
        acciones.style.cssText = "display:flex;gap:10px;justify-content:flex-end;margin-top:18px;";
        const cancelar = document.createElement("button");
        cancelar.type = "button";
        cancelar.textContent = "Conservar texto original";
        const aplicar = document.createElement("button");
        aplicar.type = "button";
        aplicar.textContent = "Aplicar correcciones";
        [cancelar, aplicar].forEach(b => b.style.cssText = "border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer;");
        aplicar.style.background = "#08783e";
        aplicar.style.color = "white";
        cancelar.onclick = () => fondo.remove();
        aplicar.onclick = () => {
            Object.entries(corregidos).forEach(([clave, valor]) => {
                if (referencias[clave]) {
                    referencias[clave].value = valor;
                    referencias[clave].dispatchEvent(new Event("input", {bubbles: true}));
                }
            });
            fondo.remove();
        };
        acciones.append(cancelar, aplicar);
        modal.appendChild(acciones);
        fondo.appendChild(modal);
        document.body.appendChild(fondo);
    }

    document.addEventListener("click", async function (evento) {
        const boton = evento.target.closest("[data-ia-revisar]");
        if (!boton) return;
        const {campos, referencias} = camposDelBoton(boton);
        if (!Object.keys(campos).length) {
            mostrarEstado(boton, "Escriba primero el texto que desea revisar.", true);
            return;
        }

        const textoOriginal = boton.textContent;
        boton.disabled = true;
        boton.textContent = "Revisando…";
        mostrarEstado(boton, "Consultando el asistente de redacción…", false);
        try {
            const respuesta = await fetch(config.url, {
                method: "POST",
                headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
                body: JSON.stringify({campos, contexto: boton.dataset.iaContexto || "informe técnico"}),
            });
            const datos = await respuesta.json();
            if (!respuesta.ok || !datos.ok) throw new Error(datos.mensaje || "No fue posible revisar el texto.");
            mostrarVistaPrevia(campos, datos.campos, referencias);
            mostrarEstado(boton, "Propuesta lista para revisar.", false);
        } catch (error) {
            const mensaje = navigator.onLine
                ? error.message
                : "No hay conexión. Puede continuar y guardar el informe normalmente.";
            mostrarEstado(boton, mensaje, true);
        } finally {
            boton.disabled = false;
            boton.textContent = textoOriginal;
        }
    });
})();
