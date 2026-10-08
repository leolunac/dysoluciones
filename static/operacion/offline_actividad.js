(function () {
    "use strict";

    const config = window.SIGOB_OFFLINE_ACTIVIDAD || {};
    if (!config.usuario) return;

    const CLAVE_COLA = `sigob:actividad:cola:${config.usuario}`;
    const CLAVE_BORRADOR = config.servicio
        ? `sigob:actividad:borrador:${config.usuario}:${config.servicio}`
        : "";
    const formulario = config.formulario
        ? document.getElementById(config.formulario)
        : null;
    const estado = document.getElementById(config.estado || "estado-sincronizacion");
    let guardando = null;
    let sincronizando = false;

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

    function leerCola() {
        try {
            const datos = JSON.parse(localStorage.getItem(CLAVE_COLA) || "[]");
            return Array.isArray(datos) ? datos : [];
        } catch (error) {
            return [];
        }
    }

    function guardarCola(cola) {
        localStorage.setItem(CLAVE_COLA, JSON.stringify(cola));
    }

    function serializar(form) {
        return Array.from(new FormData(form).entries()).map(function (entrada) {
            return [entrada[0], String(entrada[1])];
        });
    }

    function crearFormData(datos) {
        const formData = new FormData();
        datos.forEach(function (entrada) {
            if (entrada[0] !== "csrfmiddlewaretoken") {
                formData.append(entrada[0], entrada[1]);
            }
        });
        const token = document.cookie
            .split(";")
            .map(function (parte) { return parte.trim(); })
            .find(function (parte) { return parte.startsWith("csrftoken="); });
        if (token) formData.append("csrfmiddlewaretoken", decodeURIComponent(token.split("=")[1]));
        return formData;
    }

    function accesoriosDelBorrador(datos) {
        const grupos = {};
        const nombres = [
            "accesorio_id[]", "cantidad[]", "detalle_remision_id[]",
            "es_otro[]", "descripcion_otro[]", "observacion[]",
            "descripcion_mostrada[]"
        ];
        nombres.forEach(function (nombre) {
            grupos[nombre] = datos.filter(function (item) {
                return item[0] === nombre;
            }).map(function (item) { return item[1]; });
        });
        return grupos["cantidad[]"].map(function (_, indice) {
            const otro = grupos["es_otro[]"][indice] === "1";
            const accesorioId = grupos["accesorio_id[]"][indice] || "";
            const descripcionOtro = grupos["descripcion_otro[]"][indice] || "";
            return {
                accesorioId: accesorioId,
                detalleRemisionId: grupos["detalle_remision_id[]"][indice] || "",
                descripcion: grupos["descripcion_mostrada[]"][indice]
                    || (otro ? descripcionOtro : `Accesorio #${accesorioId}`),
                cantidad: grupos["cantidad[]"][indice] || "1",
                esOtro: otro,
                descripcionOtro: descripcionOtro,
                observacion: grupos["observacion[]"][indice] || ""
            };
        });
    }

    function guardarBorrador() {
        if (!formulario || !CLAVE_BORRADOR) return;
        const datos = serializar(formulario);
        localStorage.setItem(CLAVE_BORRADOR, JSON.stringify({datos: datos, guardado: Date.now()}));
        mostrar("Borrador guardado en este dispositivo.", "local");
    }

    function restaurarBorrador() {
        if (!formulario || !CLAVE_BORRADOR) return;
        let borrador;
        try {
            borrador = JSON.parse(localStorage.getItem(CLAVE_BORRADOR) || "null");
        } catch (error) {
            borrador = null;
        }
        if (!borrador || !Array.isArray(borrador.datos)) return;

        const simples = {};
        borrador.datos.forEach(function (entrada) {
            if (!entrada[0].endsWith("[]")) simples[entrada[0]] = entrada[1];
        });
        Object.keys(simples).forEach(function (nombre) {
            const campo = formulario.elements.namedItem(nombre);
            if (!campo || nombre === "csrfmiddlewaretoken") return;
            if (campo.type === "checkbox") campo.checked = simples[nombre] === "on";
            else campo.value = simples[nombre];
        });

        const crearFila = window.sigobCrearFilaAccesorio;
        if (typeof crearFila === "function") {
            accesoriosDelBorrador(borrador.datos).forEach(crearFila);
        }
        mostrar("Se recuperó el borrador guardado en este dispositivo.", "local");
    }

    async function enviar(item) {
        const respuesta = await fetch(item.url, {
            method: "POST",
            body: crearFormData(item.datos),
            credentials: "same-origin",
            headers: {"X-SIGOB-SINCRONIZACION": "1"}
        });
        const tipo = respuesta.headers.get("content-type") || "";
        if (!tipo.includes("application/json")) {
            throw new Error("La sesión debe iniciarse nuevamente para sincronizar.");
        }
        const resultado = await respuesta.json();
        if (!respuesta.ok || !resultado.ok) {
            const error = new Error(resultado.mensaje || "El servidor rechazó el informe.");
            error.validacion = respuesta.status === 422 || respuesta.status === 400;
            throw error;
        }
        return resultado;
    }

    async function sincronizarCola() {
        if (sincronizando || !navigator.onLine) return;
        let cola = leerCola();
        if (!cola.length) return;
        sincronizando = true;
        mostrar(`Sincronizando ${cola.length} informe(s) pendiente(s)…`, "enviando");
        try {
            while (cola.length && navigator.onLine) {
                const item = cola[0];
                try {
                    const resultado = await enviar(item);
                    cola.shift();
                    guardarCola(cola);
                    if (item.claveBorrador) localStorage.removeItem(item.claveBorrador);
                    mostrar(
                        `Informe ${resultado.numero_informe || ""} recibido correctamente por SIGOB.`,
                        "recibido"
                    );
                    if (formulario && resultado.comprobante_url) {
                        window.location.assign(resultado.comprobante_url);
                        return;
                    }
                } catch (error) {
                    if (error.validacion) {
                        mostrar(`${error.message} Abra el servicio y revise los datos.`, "error");
                    } else {
                        mostrar(`${error.message} El informe continúa guardado en este dispositivo.`, "pendiente");
                    }
                    break;
                }
            }
        } finally {
            sincronizando = false;
        }
    }

    function encolar() {
        const datos = serializar(formulario);
        const solicitud = datos.find(function (item) {
            return item[0] === "solicitud_sincronizacion";
        });
        const cola = leerCola();
        const indiceExistente = cola.findIndex(function (item) {
            return item.id === solicitud[1];
        });
        const item = {
            id: solicitud[1],
            url: formulario.action || window.location.href,
            datos: datos,
            claveBorrador: CLAVE_BORRADOR,
            creado: Date.now()
        };
        if (indiceExistente === -1) {
            cola.push(item);
        } else {
            cola[indiceExistente] = item;
        }
        guardarCola(cola);
        mostrar("Informe guardado en este dispositivo y pendiente de sincronización.", "pendiente");
    }

    function iniciar() {
        if (formulario) {
            const identificador = formulario.elements.namedItem("solicitud_sincronizacion");
            if (identificador && !identificador.value) identificador.value = uuid();
            restaurarBorrador();

            formulario.addEventListener("input", function () {
                clearTimeout(guardando);
                guardando = setTimeout(guardarBorrador, 500);
            });
            formulario.addEventListener("change", guardarBorrador);
            formulario.addEventListener("submit", async function (evento) {
                evento.preventDefault();
                if (!formulario.reportValidity()) return;
                guardarBorrador();
                encolar();
                await sincronizarCola();
            });
        }

        window.addEventListener("online", sincronizarCola);
        const pendientes = leerCola().length;
        if (pendientes) {
            mostrar(`${pendientes} informe(s) pendiente(s) de sincronización.`, "pendiente");
            sincronizarCola();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", iniciar);
    } else {
        iniciar();
    }
})();
