import re
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventario.models import ProductoInventario
from inventario.servicios import fijar_saldo_inicial
from operacion.models import Accesorio


PATRON_PRODUCTO = re.compile(
    r"^INSERT INTO `productos` VALUES \("
    r"'((?:[^'\\]|\\.)*)', "
    r"'((?:[^'\\]|\\.)*)', "
    r"(?:NULL|'((?:[^'\\]|\\.)*)'), "
    r"(-?\d+(?:\.\d+)?), "
    r"(-?\d+(?:\.\d+)?), "
    r"'.*'\);$"
)


def desescapar_mysql(valor):
    return (
        valor.replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\r", "\r")
        .replace("\\n", "\n")
        .replace("\\\\", "\\")
    )


def leer_productos(ruta):
    productos = []
    with ruta.open("r", encoding="utf-8-sig") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            if not linea.startswith("INSERT INTO `productos`"):
                continue
            coincidencia = PATRON_PRODUCTO.match(linea.strip())
            if not coincidencia:
                raise CommandError(
                    f"No fue posible interpretar el producto de la línea {numero}."
                )
            codigo, descripcion, unidad, cantidad, precio = coincidencia.groups()
            productos.append(
                {
                    "codigo": desescapar_mysql(codigo).strip(),
                    "descripcion": desescapar_mysql(descripcion).strip(),
                    "unidad": desescapar_mysql(unidad or "UNID").strip() or "UNID",
                    "cantidad": Decimal(cantidad),
                    "precio": Decimal(precio),
                }
            )
    return productos


class Command(BaseCommand):
    help = "Compara e importa el saldo conciliado del aplicativo de inventario anterior."

    def add_arguments(self, parser):
        parser.add_argument("archivo_sql", type=Path)
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Aplica la importación. Sin esta opción solo realiza una simulación.",
        )
        parser.add_argument(
            "--usuario",
            help="Usuario de SIGOB que quedará como responsable de inventario.",
        )

    def handle(self, *args, **opciones):
        ruta = opciones["archivo_sql"].resolve()
        if not ruta.is_file():
            raise CommandError(f"No existe el archivo: {ruta}")

        productos = leer_productos(ruta)
        if not productos:
            raise CommandError("El archivo no contiene productos reconocibles.")
        codigos = [producto["codigo"] for producto in productos]
        if len(codigos) != len(set(codigos)):
            raise CommandError("El archivo contiene códigos de producto duplicados.")

        existentes = {
            accesorio.codigo: accesorio
            for accesorio in Accesorio.objects.filter(codigo__in=codigos)
        }
        nuevos = [p for p in productos if p["codigo"] not in existentes]
        coincidencias = len(productos) - len(nuevos)
        saldos_positivos = sum(1 for p in productos if p["cantidad"] > 0)
        unidades = sum((p["cantidad"] for p in productos), Decimal("0.00"))
        valorizado = sum(
            (p["cantidad"] * p["precio"] for p in productos),
            Decimal("0.00"),
        )

        self.stdout.write("=" * 64)
        self.stdout.write("SIMULACIÓN DE IMPORTACIÓN DE INVENTARIO")
        self.stdout.write("=" * 64)
        self.stdout.write(f"Productos en archivo: {len(productos)}")
        self.stdout.write(f"Coincidencias por código: {coincidencias}")
        self.stdout.write(f"Accesorios que se crearían: {len(nuevos)}")
        self.stdout.write(f"Productos con existencia positiva: {saldos_positivos}")
        self.stdout.write(f"Unidades físicas totales: {unidades}")
        self.stdout.write(f"Inventario valorizado: ${valorizado:,.2f}")
        if nuevos:
            self.stdout.write("\nCÓDIGOS NUEVOS (primeros 30):")
            for producto in nuevos[:30]:
                self.stdout.write(
                    f"  {producto['codigo']} | {producto['descripcion']}"
                )

        if not opciones["aplicar"]:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se modificó la base. Use --aplicar después de revisar."
                )
            )
            return

        usuario = None
        if opciones.get("usuario"):
            try:
                usuario = User.objects.get(username=opciones["usuario"])
            except User.DoesNotExist as exc:
                raise CommandError("El usuario indicado no existe.") from exc

        creados = 0
        saldos = 0
        with transaction.atomic():
            for dato in productos:
                accesorio, creado = Accesorio.objects.get_or_create(
                    codigo=dato["codigo"],
                    defaults={
                        "descripcion": dato["descripcion"],
                        "activo": True,
                    },
                )
                if creado:
                    creados += 1
                producto, _ = ProductoInventario.objects.get_or_create(
                    accesorio=accesorio,
                )
                _, registrado = fijar_saldo_inicial(
                    producto=producto,
                    cantidad=dato["cantidad"],
                    precio_referencia=dato["precio"],
                    unidad_medida=dato["unidad"],
                    usuario=usuario,
                    origen=ruta.name,
                )
                saldos += int(registrado)

            grupo, _ = Group.objects.get_or_create(name="GESTION_INVENTARIO")
            if usuario:
                usuario.groups.add(grupo)

        self.stdout.write(self.style.SUCCESS("IMPORTACIÓN COMPLETADA"))
        self.stdout.write(f"Accesorios creados: {creados}")
        self.stdout.write(f"Saldos iniciales registrados: {saldos}")
        if usuario:
            self.stdout.write(f"Responsable de inventario: {usuario.username}")
