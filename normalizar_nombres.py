"""Corrige el formato de los nombres YA guardados (profesores, administradores y materias).

Por qué existe: los registros anteriores pudieron guardarse en minúsculas, en MAYÚSCULAS o con espacios de más.
Solo cambia el campo `nombre`; los identificadores (id), el usuario, la contraseña y todas las relaciones
(asignaciones, evaluaciones) quedan intactos, así que no se duplica ni se pierde nada.

Uso:
    python normalizar_nombres.py              → solo MUESTRA qué cambiaría (no modifica nada)
    python normalizar_nombres.py --aplicar    → aplica los cambios en una sola transacción

Si dos profesores quedarían con el mismo nombre (duplicado real), NO se aplica nada y se indica cuáles son:
hay que decidir a mano cuál conservar (por ejemplo desactivar uno), porque fusionarlos movería evaluaciones.
"""
import sys

from app import config as cfgmod
from app import db as dbmod
from app import validar

TABLAS = (("profesores", "profesor", 5, 60), ("administradores", "administrador", 3, 60), ("materias", "materia", 3, 60))


def main():
    aplicar = "--aplicar" in sys.argv[1:]
    cfg = cfgmod.leer_config()
    try:
        cfgmod.validar_config(cfg)
    except cfgmod.ConfigIncompleta as e:
        print(f"\n✖ {e}\n")
        return 1

    conn = dbmod.conectar(cfg)
    try:
        cambios, invalidos, choques = [], [], []
        for tabla, etiqueta, minimo, maximo in TABLAS:
            with conn.cursor() as cur:
                # Los profesores capturados con nombres / apellidos por separado ya se validaron al guardarse: no se tocan,
                # para que `nombre` no deje de coincidir con sus partes. Solo se revisan los anteriores a ese cambio.
                donde = " WHERE nombres IS NULL" if tabla == "profesores" else ""
                cur.execute(f"SELECT id, nombre FROM {tabla}{donde} ORDER BY id")
                filas = cur.fetchall()
            nuevos = {}
            for f in filas:
                nuevo, err = (validar.nombre_materia(f["nombre"]) if tabla == "materias"
                              else validar.nombre_persona(f["nombre"], "El nombre", minimo, maximo))
                if err:
                    invalidos.append((tabla, f["id"], f["nombre"], err))
                    nuevo = f["nombre"]
                nuevos[f["id"]] = nuevo
                if nuevo != f["nombre"]:
                    cambios.append((tabla, f["id"], f["nombre"], nuevo))
            # La base compara sin distinguir mayúsculas/acentos (utf8mb4_unicode_ci): se simula igual
            vistos = {}
            for f in filas:
                clave = nuevos[f["id"]].casefold()
                if clave in vistos:
                    choques.append((tabla, vistos[clave], f["id"], nuevos[f["id"]]))
                vistos.setdefault(clave, f["id"])

        print("\n=== Normalización de nombres ===\n")
        if not cambios:
            print("✔ Todos los nombres ya tienen el formato correcto.")
        for tabla, i, antes, despues in cambios:
            print(f"  {tabla}#{i}: «{antes}» → «{despues}»")
        for tabla, i, nombre, err in invalidos:
            print(f"  ⚠ {tabla}#{i}: «{nombre}» no cumple las reglas ({err}) — revísalo a mano; no se modificó.")
        for tabla, a, b, nombre in choques:
            print(f"  ✖ {tabla}: los registros #{a} y #{b} quedarían como «{nombre}» (duplicado).")

        if choques:
            print("\nNo se aplicó nada: resuelve primero los duplicados indicados.\n")
            return 1
        if not cambios:
            print()
            return 0
        if not aplicar:
            print(f"\nSe cambiarían {len(cambios)} registro(s). Para aplicarlos: python normalizar_nombres.py --aplicar\n")
            return 0

        conn.begin()
        try:
            with conn.cursor() as cur:
                for tabla, i, _antes, despues in cambios:
                    cur.execute(f"UPDATE {tabla} SET nombre = %s WHERE id = %s", (despues, i))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        print(f"\n✔ Se actualizaron {len(cambios)} nombre(s).\n")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
