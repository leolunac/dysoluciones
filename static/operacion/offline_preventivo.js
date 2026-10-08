(function () {
    "use strict";

    const config = window.SIGOB_OFFLINE_PREVENTIVO || {};
    if (!config.usuario || !window.indexedDB) return;

    const NOMBRE_BD = "sigob-preventivos-offline";
    const VERSION_BD = 1;
    const estado = document.getElementById(
        config.estado || "estado-sincronizacion-preventivo"
    );
    const formularios = Array.from(
        document.querySelectorAll("form[data-sigob-preventivo]")
    );
    let sincronizando = false;
    let cambiosSincronizados = false;

    function uuid() {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0;
            return (c === "x" ? r : (r & 3 | 8)).toString(16);
        });
    }

    function mostrar(mensaje, tipo) {
        if (!estado) return;
        const colores = {
            local: ["#fff7ed", "#9a3412", "#fdba74"],
            pendiente: ["#fef3c7", "#92400e", "#f59e0b"],
            enviando: ["#e0f2fe", "#075985", "#38bdf8"],
            recibido: ["#dcfce7", "#166534", "#4ade80"],
            error: ["#fee2e2", "#991b1b", "#f87171"]
        };
        const color = colores[tipo] || colores.local;
        estado.textContent = mensaje;
        estado.style.display = "block";
        estado.style.background = color[0];
        estado.style.color = color[1];
        estado.style.border = `1px solid ${color[2]}`;
    }

    function abrirBase() {
        return new Promise(function (resolve, reject) {
            const solicitud = indexedDB.open(NOMBRE_BD, VERSION_BD);
            solicitud.onupgradeneeded = function () {
                const base = solicitud.result;
                if (!base.objectStoreNames.contains("cola")) {
                    const cola = base.createObjectStore("cola", {keyPath: "id"});
                    cola.createIndex("usuario", "usuario", {unique: false});
                }
                if (!base.objectStoreNames.contains("borradores")) {
                    base.createObjectStore("borradores", {keyPath: "clave"});
                }
            };
            solicitud.onsuccess = function () { resolve(solicitud.result); };
            solicitud.onerror = function () { reject(solicitud.error); };
        });
    }

    async function operar(almacen, modo, operacion) {
        const base = await abrirBase();
        return new Promise(function (resolve, reject) {
            const transaccion = base.transaction(almacen, modo);
            const solicitud = operacion(transaccion.objectStore(almacen));
            solicitud.onsuccess = function () { resolve(solicitud.result); };
            solicitud.onerror = function () { reject(solicitud.error); };
            transaccion.oncomplete = function () { base.close(); };
        });
    }

    function entradasFormulario(formulario, identificador) {
        const entradas = [];
        new FormData(formulario).forEach(function (valor, nombre) {
            if (nombre !== "csrfmiddlewaretoken") entradas.push({nombre: nombre, valor: valor});
        });
        entradas.push({nombre: "solicitud_sincronizacion", valor: identificador});
        return entradas;
    }

    function claveBorrador(formulario) {
        return [
            "preventivo",
            config.usuario,
            config.programacion,
            formulario.dataset.sigobPreventivo
        ].join(":");
    }

    async function leerBorrador(formulario) {
        return operar("borradores", "readonly", function (almacen) {
            return almacen.get(claveBorrador(formulario));
        });
    }

    async function guardarBorrador(formulario) {
        if (!config.programacion) return;
        await operar("borradores", "readwrite", function (almacen) {
            return almacen.put({
                clave: claveBorrador(formulario),
                entradas: entradasFormulario(formulario, "").filter(function (entrada) {
                    return entrada.nombre !== "solicitud_sincronizacion";
                }),
                guardado: Date.now()
            });
        });
        mostrar("Borrador preventivo guardado en este dispositivo.", "local");
    }

    function siguienteOrden() {
        const clave = `sigob:preventivo:orden:${config.usuario}`;
        const anterior = Number(localStorage.getItem(clave) || 0);
        const orden = Math.max(Date.now() * 1000, anterior + 1);
        localStorage.setItem(clave, String(orden));
        return orden;
    }

    async function encolar(formulario) {
        const id = uuid();
        const accion = formulario.dataset.sigobPreventivo;
        const entradas = entradasFormulario(formulario, id);
        const borrador = await leerBorrador(formulario);
        if (borrador && Array.isArray(borrador.entradas)) {
            borrador.entradas.forEach(function (entrada) {
                const esArchivo = entrada.valor instanceof Blob;
                const yaIncluido = entradas.some(function (actual) {
                    return actual.nombre === entrada.nombre && actual.valor instanceof Blob;
                });
                if (esArchivo && !yaIncluido) entradas.push(entrada);
            });
        }
        const item = {
            id: id,
            usuario: String(config.usuario),
            programacion: String(config.programacion),
            accion: accion,
            url: formulario.action || window.location.href,
            entradas: entradas,
            orden: siguienteOrden()
        };
        await operar("cola", "readwrite", function (almacen) {
            return almacen.add(item);
        });
        mostrar(
            "Información guardada en este dispositivo y pendiente de sincronización.",
            "pendiente"
        );
        if (accion.startsWith("agregar_")) {
            formulario.reset();
            await operar("borradores", "readwrite", function (almacen) {
                return almacen.delete(claveBorrador(formulario));
            });
        }
        return item;
    }

    async function colaUsuario() {
        const todos = await operar("cola", "readonly", function (almacen) {
            return almacen.getAll();
        });
        return todos.filter(function (item) {
            return String(item.usuario) === String(config.usuario);
        }).sort(function (a, b) { return a.orden - b.orden; });
    }

    function tokenCsrf() {
        const parte = document.cookie.split(";").map(function (valor) {
            return valor.trim();
        }).find(function (valor) { return valor.startsWith("csrftoken="); });
        return parte ? decodeURIComponent(parte.split("=")[1]) : "";
    }

    async function enviar(item) {
        const datos = new FormData();
        item.entradas.forEach(function (entrada) {
            datos.append(entrada.nombre, entrada.valor);
        });
        const csrf = tokenCsrf();
        if (csrf) datos.append("csrfmiddlewaretoken", csrf);
        const respuesta = await fetch(item.url, {
            method: "POST",
            body: datos,
            credentials: "same-origin",
            headers: {"X-SIGOB-SINCRONIZACION": "1"}
        });
        const tipo = respuesta.headers.get("content-type") || "";
        if (!tipo.includes("application/json")) {
            throw new Error("Debe iniciar sesión nuevamente para sincronizar.");
        }
        const resultado = await respuesta.json();
        if (!respuesta.ok || !resultado.ok) {
            const error = new Error(resultado.mensaje || "El servidor rechazó la información.");
            error.validacion = [400, 409, 422].includes(respuesta.status);
            throw error;
        }
        return resultado;
    }

    async function eliminarItem(id) {
        return operar("cola", "readwrite", function (almacen) {
            return almacen.delete(id);
        });
    }

    async function eliminarBorrador(accion, programacion) {
        const clave = ["preventivo", config.usuario, programacion, accion].join(":");
        return operar("borradores", "readwrite", function (almacen) {
            return almacen.delete(clave);
        });
    }

    async function recuperarItemParaCorregir(item) {
        if (String(config.programacion) !== String(item.programacion)) return false;
        const formulario = formularios.find(function (actual) {
            return actual.dataset.sigobPreventivo === item.accion;
        });
        if (!formulario) return false;
        const entradas = item.entradas.filter(function (entrada) {
            return entrada.nombre !== "solicitud_sincronizacion";
        });
        entradas.forEach(function (entrada) {
            if (entrada.valor instanceof Blob) return;
            const campo = formulario.elements.namedItem(entrada.nombre);
            if (!campo || entrada.nombre === "csrfmiddlewaretoken") return;
            if (campo.type === "checkbox") campo.checked = entrada.valor === "on";
            else campo.value = entrada.valor;
        });
        await operar("borradores", "readwrite", function (almacen) {
            return almacen.put({
                clave: claveBorrador(formulario),
                entradas: entradas,
                guardado: Date.now()
            });
        });
        await eliminarItem(item.id);
        return true;
    }

    async function sincronizar() {
        if (sincronizando || !navigator.onLine) return;
        let cola = await colaUsuario();
        if (!cola.length) return;
        sincronizando = true;
        mostrar(`Sincronizando ${cola.length} registro(s) del preventivo…`, "enviando");
        try {
            while (cola.length && navigator.onLine) {
                const item = cola[0];
                try {
                    const resultado = await enviar(item);
                    await eliminarItem(item.id);
                    await eliminarBorrador(item.accion, item.programacion);
                    cola.shift();
                    cambiosSincronizados = true;
                    mostrar(resultado.mensaje || "Información recibida por SIGOB.", "recibido");
                    if (resultado.comprobante_url) {
                        window.location.assign(resultado.comprobante_url);
                        return;
                    }
                } catch (error) {
                    const recuperado = error.validacion
                        ? await recuperarItemParaCorregir(item)
                        : false;
                    mostrar(
                        error.validacion
                            ? `${error.message} ${recuperado ? "Los datos quedaron disponibles para corregir." : "Abra este preventivo para corregirlos."}`
                            : `${error.message} La información continúa guardada en el dispositivo.`,
                        error.validacion ? "error" : "pendiente"
                    );
                    break;
                }
            }
            if (!cola.length && cambiosSincronizados && config.programacion) {
                window.location.reload();
            }
        } finally {
            sincronizando = false;
        }
    }

    function prepararFormularios() {
        formularios.forEach(function (formulario) {
            let temporizador = null;
            formulario.addEventListener("input", function () {
                clearTimeout(temporizador);
                temporizador = setTimeout(function () {
                    guardarBorrador(formulario).catch(function () {});
                }, 500);
            });
            formulario.addEventListener("change", function () {
                guardarBorrador(formulario).catch(function () {});
            });
            formulario.addEventListener("submit", async function (evento) {
                evento.preventDefault();
                if (!formulario.reportValidity()) return;
                const confirmacion = formulario.dataset.confirmar;
                if (confirmacion && !window.confirm(confirmacion)) return;
                await guardarBorrador(formulario);
                await encolar(formulario);
                await sincronizar();
            });
        });
    }

    async function restaurarBorradores(accionesPendientes) {
        for (const formulario of formularios) {
            const accion = formulario.dataset.sigobPreventivo;
            if (accionesPendientes.has(accion)) continue;
            const borrador = await leerBorrador(formulario);
            if (!borrador || !Array.isArray(borrador.entradas)) continue;
            let contieneArchivo = false;
            borrador.entradas.forEach(function (entrada) {
                if (entrada.valor instanceof Blob) {
                    contieneArchivo = true;
                    return;
                }
                const campo = formulario.elements.namedItem(entrada.nombre);
                if (!campo || entrada.nombre === "csrfmiddlewaretoken") return;
                if (campo.type === "checkbox") campo.checked = entrada.valor === "on";
                else campo.value = entrada.valor;
            });
            mostrar(
                contieneArchivo
                    ? "Se recuperó el borrador, incluida la firma guardada en este dispositivo."
                    : "Se recuperó un borrador preventivo guardado en este dispositivo.",
                "local"
            );
        }
    }

    async function iniciar() {
        prepararFormularios();
        window.addEventListener("online", sincronizar);
        const pendientes = await colaUsuario();
        await restaurarBorradores(new Set(pendientes.map(function (item) {
            return item.accion;
        })));
        if (pendientes.length) {
            mostrar(
                `${pendientes.length} registro(s) preventivo(s) pendiente(s) de sincronización.`,
                "pendiente"
            );
            await sincronizar();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            iniciar().catch(function () {
                mostrar("No fue posible abrir el almacenamiento local.", "error");
            });
        });
    } else {
        iniciar().catch(function () {
            mostrar("No fue posible abrir el almacenamiento local.", "error");
        });
    }
})();
